export function formatDate(d) {
  if (!d) return ''
  return d.replace('T', ' ').slice(0, 19)
}

export function shortenSender(s) {
  if (!s) return ''
  const match = s.match(/^([^<]+)/)
  return match ? match[1].trim() : s
}

const escapeMap = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }

function escapeHtml(s) {
  return s.replace(/[&<>"]/g, c => escapeMap[c])
}

const urlRe = /https?:\/\/[^\s<>")\]},;]+/g

export function linkifyLine(line) {
  const escaped = escapeHtml(line)
  return escaped.replace(urlRe, url => {
    // Trim trailing punctuation that's likely not part of the URL
    let href = url
    while (/[.),:;!?]$/.test(href) && !href.includes('(')) href = href.slice(0, -1)
    const tail = url.slice(href.length)
    return `<a href="${href}" target="_blank" rel="noopener">${href}</a>${tail}`
  })
}
