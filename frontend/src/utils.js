export function formatDate(d) {
  if (!d) return ''
  return d.replace('T', ' ').slice(0, 19)
}

export function shortenSender(s) {
  if (!s) return ''
  const match = s.match(/^([^<]+)/)
  return match ? match[1].trim() : s
}
