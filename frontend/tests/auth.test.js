import { test } from 'node:test'
import assert from 'node:assert/strict'
import { mockSession, mockFetch, user } from './fixtures/social.js'
import * as session from '../src/platform/secureSession.js'
import { login, register, changePassword, updateProfile } from '../src/services/authApi.js'
import { auth, clearAuth, restoreAuth, saveAuth } from '../src/stores/auth.js'
import { authenticatedFetch, setUnauthorizedHandler } from '../src/services/authenticatedFetch.js'
import { registrationErrors, accountError, passwordError } from '../src/utils/authValidation.js'
test('registration validates every field, reserved names and confirmation', () => {
 const form = { account:'player_1', display_name:'Dong', password:'12345678', confirm:'12345678', registration_code:'ABCD-EFGH-JKLM-NPQR' }
 assert.ok(Object.values(registrationErrors(form)).every(value => !value))
 for (const [key,value] of [['account','abc'],['display_name','AI 1?'],['password','123'],['confirm','wrong'],['registration_code','bad']]) assert.ok(registrationErrors({...form,[key]:value})[key])
 assert.ok(accountError('中文账号')); assert.ok(passwordError('x'.repeat(65)))
})
test('login and registration use public contract; session stores only the token', async () => {
 const storage=mockSession(), payload={ user,token:'opaque-token',expires_at:'2099-01-01T00:00:00Z' }
 const calls=mockFetch([{status:200,data:payload},{status:201,data:payload},{status:200,data:user}])
 saveAuth(await login({account:user.account,password:'password'}))
 assert.equal(storage.get('dl.auth.token'),'opaque-token'); assert.equal(calls[0].headers.Authorization,undefined)
 assert.deepEqual(calls[0].body,{account:user.account,password:'password',client_type:'web'})
 const body={account:user.account,password:'password',display_name:user.display_name,registration_code:'ABCD-EFGH-JKLM-NPQR'}
 await register(body); assert.deepEqual(calls[1].body,body)
 auth.restored=false; await restoreAuth(); assert.equal(calls[2].headers.Authorization,'Bearer opaque-token'); clearAuth(); assert.equal(storage.size,0)
})
test('401 clears session once per request; public invalid credentials never redirects', async () => {
 mockSession(); session.set('token'); let redirects=0; setUnauthorizedHandler(() => { redirects++ })
 mockFetch([{status:401,data:{detail:'登录已失效',code:'unauthorized'}},{status:401,data:{detail:'账号或密码错误',code:'invalid_credentials'}}])
 await assert.rejects(authenticatedFetch('/me'),e => e.status === 401); assert.equal(session.get(),''); assert.equal(redirects,1)
 await assert.rejects(login({account:'user',password:'bad'})); assert.equal(redirects,1)
})
test('profile PATCH and password change handle 204 without parsing JSON', async () => {
 mockSession(); const calls=mockFetch([{status:200,data:user},{status:204}]); await updateProfile('小东'); await changePassword('old-password','new-password'); assert.equal(calls[0].method,'PATCH'); assert.deepEqual(calls[1].body,{current_password:'old-password',new_password:'new-password'})
})
