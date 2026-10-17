"""Password, registration code and revocable opaque-token authentication."""
import base64
import hashlib
import hmac
import re
import secrets
import unicodedata
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import Header, HTTPException
from app.storage.db import connect, utcnow


def fail(status, code, detail):
    raise HTTPException(status, detail={'detail': detail, 'code': code})


def public_user(user):
    return {key: user[key] for key in ('id', 'account', 'display_name')}


def validate_account(account):
    if not isinstance(account, str) or not re.fullmatch(r'[A-Za-z0-9_]{4,24}', account):
        fail(422, 'invalid_account', '账号须为 4~24 位英文字母、数字或下划线')
    return account.lower()


def validate_password(password):
    if not isinstance(password, str) or not 8 <= len(password) <= 64:
        fail(422, 'invalid_password', '密码须为 8~64 个字符')


def validate_display_name(value):
    name = value.strip()
    compact = re.sub(r'[\s\W_]', '', unicodedata.normalize('NFKC', name))
    if not compact or any(unicodedata.category(c).startswith('C') for c in name) or len(name) > 6:
        fail(422, 'invalid_display_name', '昵称须为 1~6 个有效字符')
    if re.search(r'ai[1-4一二三四](?![0-9])', compact, re.IGNORECASE):
        fail(422, 'invalid_display_name', 'AI 1号至 AI 4号为系统保留昵称')
    return name


def hash_password(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return '$'.join(['scrypt', '16384', '8', '1', base64.b64encode(salt).decode(), base64.b64encode(digest).decode()])


def verify_password(password, encoded):
    try:
        scheme, n, r, p, salt, expected = encoded.split('$')
        if scheme != 'scrypt':
            return False
        digest = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p))
        return hmac.compare_digest(digest, base64.b64decode(expected))
    except (ValueError, TypeError):
        return False


def normalize_code(code):
    return code.replace('-', '').upper()


def digest_code(code):
    return hashlib.sha256(normalize_code(code).encode()).hexdigest()


def token_digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def issue_token(db, user, client_type='web'):
    token = secrets.token_urlsafe(32)
    now = utcnow()
    expiry = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    db.execute('INSERT INTO auth_tokens(token_digest,user_id,client_type,expires_at,created_at) VALUES(?,?,?,?,?)', (token_digest(token), user['id'], client_type, expiry, now))
    return {'user': public_user(user), 'token': token, 'expires_at': expiry}


def authenticate_token(token):
    if not token or not isinstance(token, str):
        return None
    with connect() as db:
        row = db.execute('SELECT u.*,t.token_digest FROM auth_tokens t JOIN users u ON u.id=t.user_id WHERE t.token_digest=? AND t.revoked_at IS NULL AND t.expires_at>?', (token_digest(token), utcnow())).fetchone()
        return dict(row) if row else None


def require_user(authorization: str | None = Header(default=None)):
    parts = authorization.split() if authorization else []
    user = authenticate_token(parts[1]) if len(parts) == 2 and parts[0].lower() == 'bearer' else None
    if user is None:
        fail(401, 'unauthorized', '请先登录或重新登录')
    return user
