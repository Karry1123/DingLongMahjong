import { authenticatedFetch as request, post } from './authenticatedFetch.js'
const matchPath = id => `/matches/${encodeURIComponent(id)}`
export const createMatch = invitee_ids => post('/matches', { invitee_ids })
export const inviteFriends = (id, invitee_ids) => post(`${matchPath(id)}/invitations`, { invitee_ids })
export const getInvitations = () => request('/invitations')
export const acceptInvitation = id => post(`/invitations/${encodeURIComponent(id)}/accept`)
export const declineInvitation = id => post(`/invitations/${encodeURIComponent(id)}/decline`)
export const getMatch = id => request(matchPath(id))
export const startMatch = id => post(`${matchPath(id)}/start`)
export const leaveMatch = id => post(`${matchPath(id)}/leave`)
export const getMatchHistory = (cursor = '') => request(`/me/match-history?limit=20&cursor=${encodeURIComponent(cursor)}`)
