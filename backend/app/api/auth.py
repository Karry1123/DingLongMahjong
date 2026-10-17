"""Account HTTP API."""
import threading
import time
from collections import defaultdict, deque
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel
from app.auth import (digest_code, fail, hash_password, issue_token, public_user, require_user,
                      validate_account, validate_display_name, validate_password, verify_password)
from app.storage.db import connect, utcnow

router = APIRouter(prefix='/api', tags=['auth'])
_attempts = defaultdict(deque)
_rate_lock = threading.Lock()


def rate_limit(request: Request):
    ip = request.client.host if request.client else 'unknown'
    now = time.monotonic()
    with _rate_lock:
        attempts = _attempts[ip]
        while attempts and attempts[0] <= now - 60:
            attempts.popleft()
        if len(attempts) >= 10:
            fail(429, 'rate_limited', '操作过于频繁，请稍后再试')
        attempts.append(now)


class Register(BaseModel):
    account: str
    password: str
    display_name: str
    registration_code: str


class Login(BaseModel):
    account: str
    password: str
    client_type: Literal['web', 'native'] = 'web'


class Rename(BaseModel):
    display_name: str


class ChangePassword(BaseModel):
    current_password: str
    new_password: str


@router.post('/auth/register', status_code=201, dependencies=[Depends(rate_limit)])
def register(payload: Register):
    normalized = validate_account(payload.account)
    validate_password(payload.password)
    name = validate_display_name(payload.display_name)
    password_hash = hash_password(payload.password)
    now = utcnow()
    with connect() as db:
        code = db.execute('SELECT * FROM registration_codes WHERE code_digest=?', (digest_code(payload.registration_code),)).fetchone()
        if not code or code['used_by'] or code['revoked_at'] or (code['expires_at'] and code['expires_at'] <= now):
            fail(422, 'invalid_registration_code', '注册码无效、已使用或已过期')
        if db.execute('SELECT id FROM users WHERE account_normalized=?', (normalized,)).fetchone():
            fail(409, 'account_exists', '该账号已注册')
        user = {'id': str(uuid4()), 'account': payload.account, 'display_name': name}
        db.execute('INSERT INTO users(id,account,account_normalized,display_name,password_hash,created_at) VALUES(?,?,?,?,?,?)', (user['id'], payload.account, normalized, name, password_hash, now))
        changed = db.execute('UPDATE registration_codes SET used_by=?,used_at=? WHERE code_digest=? AND used_by IS NULL AND revoked_at IS NULL', (user['id'], now, code['code_digest']))
        if changed.rowcount != 1:
            fail(422, 'invalid_registration_code', '注册码已使用')
        return issue_token(db, user)


@router.post('/auth/login', dependencies=[Depends(rate_limit)])
def login(payload: Login):
    with connect() as db:
        user = db.execute('SELECT * FROM users WHERE account_normalized=?', (payload.account.lower(),)).fetchone()
        # Always compute scrypt, including unknown accounts.
        encoded = user['password_hash'] if user else hash_password('invalid-account')
        valid = verify_password(payload.password, encoded)
        if not user or not valid:
            fail(401, 'invalid_credentials', '账号或密码错误')
        return issue_token(db, user, payload.client_type)


@router.post('/auth/logout', status_code=204)
def logout(user=Depends(require_user)):
    with connect() as db:
        db.execute('UPDATE auth_tokens SET revoked_at=? WHERE token_digest=?', (utcnow(), user['token_digest']))
    return Response(status_code=204)


@router.get('/me')
def me(user=Depends(require_user)):
    with connect() as db:
        row = db.execute("SELECT m.id FROM matches m JOIN match_members mm ON mm.match_id=m.id WHERE mm.user_id=? AND m.status IN ('inviting','waiting','countdown','playing')", (user['id'],)).fetchone()
    return {**public_user(user), 'active_match_id': row['id'] if row else None}


@router.patch('/me')
def rename(payload: Rename, user=Depends(require_user)):
    name = validate_display_name(payload.display_name)
    with connect() as db:
        db.execute('UPDATE users SET display_name=? WHERE id=?', (name, user['id']))
    return {**public_user(user), 'display_name': name}


@router.post('/auth/change-password', status_code=204)
def change_password(payload: ChangePassword, user=Depends(require_user)):
    validate_password(payload.new_password)
    with connect() as db:
        current = db.execute('SELECT password_hash FROM users WHERE id=?', (user['id'],)).fetchone()
        if not verify_password(payload.current_password, current['password_hash']):
            fail(401, 'invalid_credentials', '账号或密码错误')
        db.execute('UPDATE users SET password_hash=? WHERE id=?', (hash_password(payload.new_password), user['id']))
        db.execute('UPDATE auth_tokens SET revoked_at=? WHERE user_id=? AND token_digest<>? AND revoked_at IS NULL', (utcnow(), user['id'], user['token_digest']))
    return Response(status_code=204)
