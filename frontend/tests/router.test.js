import { test } from 'node:test'
import assert from 'node:assert/strict'
import { isLegacyPath, legacyNotice, loginRedirect, safeRedirect } from '../src/router/guards.js'
test('legacy room links show the migration message; all private routes preserve intended destination', () => {
 assert.ok(isLegacyPath('/pvp')); assert.ok(isLegacyPath('/pvp/room/123456')); assert.equal(legacyNotice,'房间号对战已升级为好友邀请')
 for (const path of ['/home','/friends','/friends/requests','/invite','/matches/m1/waiting','/matches/m1/play','/records','/settings','/pve','/sandbox']) assert.deepEqual(loginRedirect({fullPath:path,meta:{}},false),{path:'/login',query:{redirect:path}})
 assert.equal(loginRedirect({meta:{public:true}},false),true); assert.equal(loginRedirect({meta:{}},true),true)
})
test('post-login redirects reject external and recursive login targets', () => {
 for (const path of ['//evil.example','https://evil.example','/login','/register?redirect=/login',null]) assert.equal(safeRedirect(path),'/home')
 assert.equal(safeRedirect('/matches/m1/waiting'),'/matches/m1/waiting')
})
