import { test } from 'node:test'
import assert from 'node:assert/strict'
import { friend, mockSession, mockFetch } from './fixtures/social.js'
import { searchUsers, requestFriend, removeFriend } from '../src/services/socialApi.js'
import { friends, refreshFriends, respondRequest, clearFriends } from '../src/stores/friends.js'
test('complete account search is encoded and crossed requests refresh into accepted friends', async () => {
 mockSession(); const calls=mockFetch([{status:200,data:{items:[{...friend,relationship:'incoming'}]}},{status:201,data:{id:'r1',status:'accepted'}},{status:200,data:{items:[friend]}},{status:200,data:{incoming:[],outgoing:[]}}])
 assert.equal((await searchUsers(' Player_2 ')).items[0].relationship,'incoming'); assert.ok(calls[0].url.endsWith('account=Player_2'))
 assert.equal((await requestFriend(friend.id)).status,'accepted'); assert.deepEqual(calls[1].body,{target_user_id:friend.id}); await refreshFriends(); assert.deepEqual(friends.items,[friend]); clearFriends()
})
test('accept, reject or withdraw and delete use the contract paths', async () => {
 mockSession(); const calls=mockFetch([{status:200,data:{id:'r1',status:'accepted'}},{status:200,data:{items:[friend]}},{status:200,data:{incoming:[],outgoing:[]}},{status:204},{status:200,data:{items:[friend]}},{status:200,data:{incoming:[],outgoing:[]}},{status:204}])
 await respondRequest('r1',true); await respondRequest('r2',false); await removeFriend(friend.id)
 assert.ok(calls[0].url.endsWith('/friend-requests/r1/accept')); assert.ok(calls[3].url.endsWith('/friend-requests/r2/reject')); assert.equal(calls[6].method,'DELETE')
})
