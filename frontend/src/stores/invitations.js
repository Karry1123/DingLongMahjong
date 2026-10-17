import { reactive } from 'vue'
import * as api from '../services/matchApi.js'
export const invitations = reactive({ items: [] })
let generation = 0
export function clearInvitations() { generation++; invitations.items = [] }
export async function refreshInvitations() { const version = generation; const data = await api.getInvitations(); if (version === generation) invitations.items = data.items }
export async function respondInvitation(id, accept) { const data = await (accept ? api.acceptInvitation(id) : api.declineInvitation(id)); await refreshInvitations(); return data?.match }
