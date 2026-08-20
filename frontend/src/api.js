const BASE = import.meta.env.VITE_API ?? ''
let token

async function get(path, params) {
  const qs = new URLSearchParams(
    Object.entries(params ?? {}).filter(([, v]) => v !== null && v !== undefined && v !== '')
  )
  return request(`${path}?${qs}`)
}

async function localToken() {
  if (token) return token
  const res = await fetch(`${BASE}/api/client-token`)
  if (!res.ok) throw new Error(await errorText(res, '/api/client-token'))
  token = (await res.json()).token
  return token
}

async function request(path, init = {}, retry = true) {
  const t = await localToken()
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { ...(init.headers ?? {}), 'X-NexusRank-Token': t },
  })
  if ((res.status === 401 || res.status === 403) && retry) {
    token = undefined
    return request(path, init, false)
  }
  if (!res.ok) throw new Error(await errorText(res, path))
  return res.json()
}

export const fetchGraph = (q, viewer, people = 26) => get('/api/graph', { q, viewer, people })
export const fetchViewers = () => get('/api/viewers', { limit: 8 })
export const fetchHealth = () => get('/api/health')
export const fetchState = () => get('/api/state')
export const fetchSuggestions = () => get('/api/suggestions', { limit: 12 })
export const searchPeople = (q) => get('/api/people', { q, limit: 12 })

export const getProfile = (id) => get(`/api/person/${encodeURIComponent(id)}/profile`)

async function send(path, method, body) {
  return request(path, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
}

async function errorText(res, path) {
  try {
    const body = await res.json()
    return `${path} → ${res.status}: ${body.detail ?? 'request failed'}`
  } catch {
    return `${path} → ${res.status}`
  }
}

export const saveProfile = (id, payload) =>
  send(`/api/person/${encodeURIComponent(id)}/profile`, 'PUT', payload)
export const deleteEnrichment = (id) =>
  send(`/api/person/${encodeURIComponent(id)}/enrichment`, 'DELETE')
export const addPerson = (payload) => send('/api/person', 'POST', payload)
export const deletePerson = (id) =>
  send(`/api/person/${encodeURIComponent(id)}`, 'DELETE')
export const importLinkedIn = (payload) => send('/api/import/linkedin', 'POST', payload)
export const setDataset = (active_dataset) => send('/api/state', 'PUT', { active_dataset })
export const clearMyNetwork = () => send('/api/my-network/clear', 'POST', { confirm: true })
