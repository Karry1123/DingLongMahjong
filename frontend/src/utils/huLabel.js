/** Only the final score belongs on a win action. */
export function huResultLabel(info) {
  const points = info?.final_hu ?? info?.final_points
  if (points == null || !Number.isFinite(Number(points))) return ''
  return info?.is_lazi || info?.payments?.is_lazi || Number(points) >= 100
    ? '辣子' : `${Number(points)}胡`
}
