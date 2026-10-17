import { test } from 'node:test'
import assert from 'node:assert/strict'
import { mockSession, match } from './fixtures/social.js'
import { set } from '../src/platform/secureSession.js'
import { createRealtimeConnection } from '../src/utils/realtimeConnection.js'
import { applySnapshot, activeMatch, clearActiveMatch } from '../src/stores/activeMatch.js'
function harness() {
 const sockets=[], tasks=new Map(), delays=[], statuses=[], terminals=[]; let sequence=0
 class Socket { constructor(url) { this.url=url; this.readyState=0; this.sent=[]; sockets.push(this) } open() { this.readyState=1; this.onopen() } send(data) { this.sent.push(JSON.parse(data)) } close(code=1006) { this.readyState=3; this.onclose({code}) } message(data) { this.onmessage({data:JSON.stringify(data)}) } }
 const connection=createRealtimeConnection({url:'ws://localhost/api/matches/match-1/ws',Socket,schedule:(fn,delay) => { const id=++sequence; tasks.set(id,fn); delays.push(delay); return id },cancel:id=>tasks.delete(id),onMessage:message=>{ if(message.type==='state') applySnapshot(message) },onStatus:value=>statuses.push(value),onTerminal:code=>terminals.push(code)})
 return {connection,sockets,tasks,delays,statuses,terminals}
}
test('first message authenticates; disconnected actions are not queued; snapshot replaces stale game after retry', () => {
 mockSession(); set('bearer'); clearActiveMatch(); const h=harness(); h.connection.start(); const first=h.sockets[0]; first.open(); assert.deepEqual(first.sent,[{type:'authenticate',token:'bearer'}])
 first.message({type:'state',match,game:{game_id:'g1',revision:8,actions:['old']}}); first.close(); assert.equal(h.connection.send({type:'game_action'}),false); assert.equal(h.delays.at(-1),1000)
 const retry=[...h.tasks.values()][0]; h.tasks.clear(); retry(); const second=h.sockets[1]; second.open(); second.message({type:'state',match,game:{game_id:'g1',revision:12,actions:[]}})
 first.message({type:'state',match,game:{revision:9}}); assert.equal(activeMatch.game.revision,12); assert.deepEqual(activeMatch.game.actions,[]); assert.equal(h.statuses.at(-1),'connected'); h.connection.stop(); assert.equal(h.tasks.size,0)
})
test('reconnect uses bounded exponential backoff; authorization and duplicate connections stop retries', () => {
 mockSession(); const h=harness(); h.connection.start(); for (let i=0;i<6;i++) { h.sockets.at(-1).close(); assert.equal(h.delays.at(-1),Math.min(1000*2**i,15000)); const fn=[...h.tasks.values()][0]; h.tasks.clear(); fn() }
 h.sockets.at(-1).close(4409); assert.deepEqual(h.terminals,[4409]); assert.equal(h.tasks.size,0); h.connection.stop()
 for (const code of [4401,4403]) { const h=harness(); h.connection.start(); h.sockets[0].close(code); assert.deepEqual(h.terminals,[code]); assert.equal(h.tasks.size,0); h.connection.stop() }
})
