const BASE = import.meta.env.VITE_API ?? ''

async function get(path, params) {
  const qs = new URLSearchParams(
    Object.entries(params ?? {}).filter(([, v]) => v !== null && v !== undefined && v !== '')
  )
  const res = await fetch(`${BASE}${path}?${qs}`)
  if (!res.ok) throw new Error(`${path} → ${res.status}`)
  return res.json()
}

export const fetchGraph = (q, viewer, people = 26) => get('/api/graph', { q, viewer, people })
export const fetchViewers = () => get('/api/viewers', { limit: 8 })
export const fetchHealth = () => get('/api/health')
