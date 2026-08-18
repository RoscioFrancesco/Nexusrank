import assert from 'node:assert/strict'
import test from 'node:test'
import { N, buildSurface, bilinearSample } from './surfaceField.js'

const items = (boost = 1) => [
  { id: 'skill:a', x: -8, y: -6, score: 0, seed: true },
  { id: 'skill:b', x: 9, y: 7, score: 0, seed: true },
  { id: 'person:1', x: -7, y: -5, score: 1.0 * boost, seed: false },
  { id: 'person:2', x: 8, y: 6, score: 0.4, seed: false },
  { id: 'person:3', x: 0, y: 0, score: 0.1, seed: false },
]

test('normalized field is finite and inside [0,1]', () => {
  const { U } = buildSurface(items())
  for (const v of U) {
    assert.ok(Number.isFinite(v), 'field value must be finite')
    assert.ok(v >= 0 && v <= 1, `field value ${v} out of range`)
  }
  assert.ok(Math.max(...U) > 0.99 && Math.min(...U) < 0.01, 'field must be normalized')
})

test('output grid is 64x64', () => {
  const s = buildSurface(items())
  assert.equal(N, 64)
  assert.equal(s.N, 64)
  assert.equal(s.U.length, 64 * 64)
})

test('a stronger isolated source raises its local peak', () => {
  const base = [
    { id: 'p:far', x: -1, y: -1, score: 0, seed: false },
    { id: 'p:probe', x: 1, y: 1, score: 0.2, seed: false },
  ]
  const strong = [
    { id: 'p:far', x: -1, y: -1, score: 0, seed: false },
    { id: 'p:probe', x: 1, y: 1, score: 1.0, seed: false },
  ]
  const a = buildSurface(base)
  const b = buildSurface(strong)
  const probeA = a.sources.find((s) => s.id === 'p:probe')
  const probeB = b.sources.find((s) => s.id === 'p:probe')
  assert.ok(probeB.a > probeA.a, 'higher fused score must give a higher amplitude')
  assert.ok(
    bilinearSample(b.U, probeB.x, probeB.y) > bilinearSample(a.U, probeA.x, probeA.y),
    'higher amplitude must raise the local terrain height'
  )
})

test('identical inputs produce identical output', () => {
  const a = buildSurface(items())
  const b = buildSurface(items())
  assert.deepEqual(Array.from(a.U), Array.from(b.U))
  assert.deepEqual(a.query, b.query)
})
