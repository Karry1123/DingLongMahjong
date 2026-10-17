import { test } from 'node:test'
import assert from 'node:assert/strict'
import { match, friend, mockSession, mockFetch } from './fixtures/social.js'
import { createMatch, inviteFriends, startMatch, leaveMatch, getMatchHistory } from '../src/services/matchApi.js'
import { respondInvitation, invitations } from '../src/stores/invitations.js'
import { waitingSeats } from '../src/utils/matchSeats.js'
test('create, supplement, accept, decline, start, leave and history conform to fixtures', async () => {
 mockSession(); const calls=mockFetch([{status:201,data:{match}},{status:200,data:{match}},{status:200,data:{match}},{status:200,data:{items:[]}},{status:204},{status:200,data:{items:[]}},{status:200,data:{match:{...match,status:'countdown',start_at:4000,ai_seats:[3,4]}}},{status:204},{status:200,data:{items:[],next_cursor:null}}])
 await createMatch([friend.id]); await inviteFriends(match.id,[friend.id]); assert.deepEqual(await respondInvitation('i1',true),match); await respondInvitation('i2',false); const started=await startMatch(match.id); assert.equal(started.match.status,'countdown'); await leaveMatch(match.id); await getMatchHistory('next cursor')
 assert.deepEqual(calls[0].body,{invitee_ids:[friend.id]}); assert.ok(calls[1].url.endsWith('/matches/match-1/invitations')); assert.ok(calls[2].url.endsWith('/invitations/i1/accept')); assert.ok(calls[4].url.endsWith('/invitations/i2/decline')); assert.equal(invitations.items.length,0); assert.ok(calls[8].url.endsWith('cursor=next%20cursor'))
})
test('four seats show prepared, pending, declined and AI states using one-based match seats', () => {
 const fixture={...match,invitations:[match.invitations[0],{...match.invitations[0],invitee:{...friend,id:'user-3'},status:'declined'}],ai_seats:[4]}
 const seats=waitingSeats(fixture); assert.deepEqual(seats.map(s=>s.seat),[1,2,3,4]); assert.deepEqual(seats.map(s=>s.label),['已准备','待接受','拒绝','AI 补位'])
})
