import { authenticatedFetch as request, post } from './authenticatedFetch.js'
export const searchUsers = account => request(`/users/search?account=${encodeURIComponent(account.trim())}`)
export const getFriends = () => request('/friends')
export const getRequests = () => request('/friend-requests')
export const requestFriend = target_user_id => post('/friend-requests', { target_user_id })
export const acceptRequest = id => post(`/friend-requests/${encodeURIComponent(id)}/accept`)
export const rejectRequest = id => post(`/friend-requests/${encodeURIComponent(id)}/reject`)
export const removeFriend = id => request(`/friends/${encodeURIComponent(id)}`, { method: 'DELETE' })
