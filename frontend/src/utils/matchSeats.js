export function waitingSeats(match) {
 const members = match?.members || []
 const invitations = (match?.invitations || []).filter(i => !members.some(m => m.user_id === i.invitee.id) && i.status !== 'accepted')
 const empty = [1,2,3,4].filter(seat => !members.some(m => m.seat === seat))
 return [1,2,3,4].map(seat => {
  const member = members.find(m => m.seat === seat)
  if (member) return { seat, name:member.display_name, label: member.online === false ? '离线 · 等待重连' : member.ready ? '已准备' : '未准备' }
  if (match?.ai_seats?.includes(seat)) return { seat, name:`AI ${seat}号`, label:'AI 补位' }
  const invitation = invitations[empty.indexOf(seat)]
  return { seat, name:invitation?.invitee.display_name || '虚位以待', label: invitation ? ({ pending:'待接受', declined:'拒绝', expired:'邀请已过期', cancelled:'邀请已取消' }[invitation.status] || invitation.status) : '可补邀好友' }
 })
}
