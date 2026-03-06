const BASE = '/api'

async function fetchJSON(url) {
  const res = await fetch(url)
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json()
}

export function getStats() {
  return fetchJSON(`${BASE}/stats`)
}

export function getInboxes() {
  return fetchJSON(`${BASE}/inboxes`)
}

export function getInbox(name, { page = 1, perPage = 50, after = null } = {}) {
  const params = new URLSearchParams({ page, per_page: perPage })
  if (after) params.set('after', after)
  return fetchJSON(`${BASE}/inboxes/${name}?${params}`)
}

export function getMessage(messageId) {
  return fetchJSON(`${BASE}/messages/${encodeURIComponent(messageId)}`)
}

export function getThread(messageId) {
  return fetchJSON(`${BASE}/threads/${encodeURIComponent(messageId)}`)
}

export function locateInbox(q) {
  return fetchJSON(`${BASE}/locate?q=${encodeURIComponent(q)}`)
}

export function getSyncStatus() {
  return fetchJSON(`${BASE}/sync/status`)
}

export function search(q, { inbox, page = 1, perPage = 50 } = {}) {
  const params = new URLSearchParams({ q, page, per_page: perPage })
  if (inbox) params.set('inbox', inbox)
  return fetchJSON(`${BASE}/search?${params}`)
}
