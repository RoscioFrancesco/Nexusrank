/** Surface View mathematics — pure, deterministic, VISUALIZATION ONLY.
 *  Relevance comes from the existing hybrid ranking (PPR + BM25 fusion); this
 *  module only turns those scores into a smooth height field. It must never
 *  feed back into ranking.
 */

export const N = 64
export const H = 2 / (N - 1)
export const SIGMA = 0.1
export const SIGMA_Q = 0.14
export const LAMBDA = 0.015
export const ITERATIONS = 60
export const A_QUERY = 1.25
export const Z_SCALE = 0.55

/** Map raw layout coordinates into [-1,1]^2 (degenerate axes collapse to 0). */
export function normalizePositions(items) {
  const xs = items.map((d) => d.x)
  const ys = items.map((d) => d.y)
  const scale = (v, lo, hi) => (hi - lo < 1e-9 ? 0 : (2 * (v - lo)) / (hi - lo) - 1)
  const [x0, x1] = [Math.min(...xs), Math.max(...xs)]
  const [y0, y1] = [Math.min(...ys), Math.max(...ys)]
  return items.map((d) => ({ ...d, x: scale(d.x, x0, x1), y: scale(d.y, y0, y1) }))
}

/** Seeds sit high by construction; other results scale with normalized score. */
export function amplitudes(items) {
  const scores = items.map((d) => d.score ?? 0)
  const sMin = Math.min(...scores)
  const sMax = Math.max(...scores)
  return items.map((d) => {
    const z = ((d.score ?? 0) - sMin) / (sMax - sMin + 1e-9)
    return { ...d, z, a: d.seed ? Math.max(0.75, z) : 0.25 + 0.75 * z }
  })
}

/** Score-weighted barycenter of the seeds; (0,0) when there are no seeds. */
export function queryPosition(sources) {
  const seeds = sources.filter((s) => s.seed)
  const w = seeds.reduce((t, s) => t + s.a, 0)
  if (!seeds.length || w < 1e-9) return { x: 0, y: 0 }
  return {
    x: seeds.reduce((t, s) => t + s.a * s.x, 0) / w,
    y: seeds.reduce((t, s) => t + s.a * s.y, 0) / w,
  }
}

const gridCoord = (i) => -1 + i * H

/** Gaussian deposition of every source plus the synthetic query source. */
export function sourceField(sources, q) {
  const F = new Float64Array(N * N)
  const twoS2 = 2 * SIGMA * SIGMA
  const twoQ2 = 2 * SIGMA_Q * SIGMA_Q
  for (let j = 0; j < N; j++) {
    const y = gridCoord(j)
    for (let k = 0; k < N; k++) {
      const x = gridCoord(k)
      let v = 0
      for (const s of sources) {
        const dx = x - s.x
        const dy = y - s.y
        v += s.a * Math.exp(-(dx * dx + dy * dy) / twoS2)
      }
      const qx = x - q.x
      const qy = y - q.y
      v += A_QUERY * Math.exp(-(qx * qx + qy * qy) / twoQ2)
      F[j * N + k] = v
    }
  }
  return F
}

/** Steady screened-Poisson u - lambda*Laplacian(u) = F, by Jacobi iteration. */
export function diffuse(F) {
  const c = LAMBDA / (H * H)
  const denom = 1 + 4 * c
  let u = Float64Array.from(F)
  let next = new Float64Array(N * N)
  for (let it = 0; it < ITERATIONS; it++) {
    for (let j = 1; j < N - 1; j++) {
      for (let k = 1; k < N - 1; k++) {
        const i = j * N + k
        next[i] =
          (F[i] + c * (u[i + N] + u[i - N] + u[i + 1] + u[i - 1])) / denom
      }
    }
    copyBoundaries(next)
    const swap = u
    u = next
    next = swap
  }
  return u
}

/** Zero-Neumann-like boundary: copy the nearest interior value. */
function copyBoundaries(u) {
  for (let k = 0; k < N; k++) {
    u[k] = u[N + k]
    u[(N - 1) * N + k] = u[(N - 2) * N + k]
  }
  for (let j = 0; j < N; j++) {
    u[j * N] = u[j * N + 1]
    u[j * N + N - 1] = u[j * N + N - 2]
  }
}

export function normalizeField(u) {
  let lo = Infinity
  let hi = -Infinity
  for (const v of u) {
    if (v < lo) lo = v
    if (v > hi) hi = v
  }
  const span = hi - lo + 1e-9
  const U = new Float64Array(u.length)
  for (let i = 0; i < u.length; i++) U[i] = (u[i] - lo) / span
  return U
}

export function bilinearSample(U, x, y) {
  const fx = Math.min(Math.max((x + 1) / H, 0), N - 1)
  const fy = Math.min(Math.max((y + 1) / H, 0), N - 1)
  const k0 = Math.floor(fx)
  const j0 = Math.floor(fy)
  const k1 = Math.min(k0 + 1, N - 1)
  const j1 = Math.min(j0 + 1, N - 1)
  const tx = fx - k0
  const ty = fy - j0
  const top = U[j0 * N + k0] * (1 - tx) + U[j0 * N + k1] * tx
  const bot = U[j1 * N + k0] * (1 - tx) + U[j1 * N + k1] * tx
  return top * (1 - ty) + bot * ty
}

/**
 * @param items {Array<{id,x,y,score,seed}>} visible seeds + top results with
 *   layout coordinates from the Network view's graph.
 * @returns {{U, N, sources, query, height}} height(x,y) in world units.
 */
export function buildSurface(items) {
  if (!items?.length) return null
  const sources = amplitudes(normalizePositions(items))
  const query = queryPosition(sources)
  const U = normalizeField(diffuse(sourceField(sources, query)))
  return {
    U,
    N,
    sources,
    query: { ...query, a: A_QUERY },
    height: (x, y) => Z_SCALE * bilinearSample(U, x, y),
  }
}
