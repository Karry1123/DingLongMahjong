import { reactive } from 'vue'
import * as api from '../services/socialApi.js'
export const friends = reactive({ items: [], incoming: [], outgoing: [] })
let generation = 0
export function clearFriends() { generation++; friends.items = []; friends.incoming = []; friends.outgoing = [] }
export async function refreshFriends() {
  const version = generation
  const [list, requests] = await Promise.all([api.getFriends(), api.getRequests()])
  if (version === generation) Object.assign(friends, { items: list.items, ...requests })
}
export async function respondRequest(id, accept) { await (accept ? api.acceptRequest(id) : api.rejectRequest(id)); await refreshFriends() }
