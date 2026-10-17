from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from app.api import auth
from app.auth import digest_code, hash_password, verify_password
from app.storage.db import connect, ensure_schema, utcnow

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.delenv('DATABASE_URL', raising=False)
    monkeypatch.setenv('AUTH_DB_PATH', str(tmp_path / 'auth.db'))
    ensure_schema()
    auth._attempts.clear()
    application = FastAPI()
    application.include_router(auth.router)
    @application.exception_handler(HTTPException)
    async def error(request, exception):
        return JSONResponse(status_code=exception.status_code, content=exception.detail)
    with TestClient(application) as result:
        yield result

def code(value='ABCD-EFGH-JKLM-NPQR', expires_at='2099-01-01T00:00:00+00:00', revoked_at=None):
    with connect() as db:
        db.execute('INSERT INTO registration_codes(code_digest,batch,expires_at,revoked_at,created_at) VALUES(?,?,?,?,?)', (digest_code(value),'test',expires_at,revoked_at,utcnow()))
    return value

def register(client, account='Alice_1', registration_code=None):
    return client.post('/api/auth/register', json=dict(account=account,password='password123',display_name='小明',registration_code=registration_code or code()))

def test_password_hash():
    value = hash_password('password123')
    assert value.startswith('scrypt$16384$8$1$')
    assert value != hash_password('password123')
    assert verify_password('password123', value)
    assert not verify_password('wrong', value)

def test_account_login_logout_change_password(client):
    response = register(client)
    assert response.status_code == 201
    original = response.json()
    headers = {'Authorization':'Bearer '+original['token']}
    assert client.get('/api/me', headers=headers).json()['active_match_id'] is None
    second = client.post('/api/auth/login', json={'account':'aLICE_1','password':'password123','client_type':'native'})
    assert second.status_code == 200
    assert client.patch('/api/me',headers=headers,json={'display_name':'小红'}).json()['display_name'] == '小红'
    assert client.post('/api/auth/change-password',headers=headers,json={'current_password':'password123','new_password':'newpassword123'}).status_code == 204
    assert client.get('/api/me',headers={'Authorization':'Bearer '+second.json()['token']}).status_code == 401
    assert client.get('/api/me',headers=headers).status_code == 200
    assert client.post('/api/auth/login',json={'account':'alice_1','password':'password123'}).json() == {'detail':'账号或密码错误','code':'invalid_credentials'}
    assert client.post('/api/auth/login',json={'account':'alice_1','password':'newpassword123'}).status_code == 200
    assert client.post('/api/auth/logout',headers=headers).status_code == 204
    assert client.get('/api/me',headers=headers).status_code == 401
    with connect() as db:
        assert all(row['token_digest'] != original['token'] for row in db.execute('SELECT token_digest FROM auth_tokens').fetchall())

def test_validation_and_code_consumption(client):
    value = code()
    assert register(client,account='bad',registration_code=value).status_code == 422
    assert register(client,registration_code=value.lower().replace('-','')).status_code == 201
    assert register(client,account='other_user',registration_code=value).status_code == 422
    value2 = code('QRST-UVWX-YZAB-CDEF')
    assert register(client,account='alice_1',registration_code=value2).status_code == 409
    assert register(client,account='other_user',registration_code=value2).status_code == 201

def test_expired_revoked_and_token_expiry(client):
    assert register(client,registration_code=code(expires_at='2000-01-01T00:00:00+00:00')).status_code == 422
    assert register(client,registration_code=code('QRST-UVWX-YZAB-CDEF',revoked_at=utcnow())).status_code == 422
    result = register(client,registration_code=code('BCDE-FGHJ-KLMN-PQRS')).json()
    with connect() as db:
        db.execute("UPDATE auth_tokens SET expires_at='2000-01-01T00:00:00+00:00'")
    assert client.get('/api/me',headers={'Authorization':'Bearer '+result['token']}).status_code == 401

def test_rate_limit(client):
    for _ in range(10):
        assert client.post('/api/auth/login',json={'account':'missing','password':'wrong'}).status_code == 401
    assert client.post('/api/auth/register',json={'account':'testuser','password':'password123','display_name':'小明','registration_code':'x'}).status_code == 429

def test_same_code_concurrent_registration(client):
    value = code()
    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(lambda account: register(client,account,value), ['first_user','second_user']))
    assert sorted(response.status_code for response in responses) == [201,422]
    with connect() as db:
        assert len(db.execute('SELECT id FROM users').fetchall()) == 1
