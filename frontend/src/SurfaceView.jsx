import { useEffect, useMemo, useRef } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { layoutPositions } from './layout'
import { N, Z_SCALE, buildSurface } from './surfaceField'
import { HIGHLIGHT, SEED_RING, TYPE_COLOR } from './theme'

const QUERY_COLOR = 0xffd166
const CAM0 = new THREE.Vector3(1.7, -2.05, 1.55)

/** Terrain colour ramp: low = deep blue, high = warm. */
function ramp(t) {
  const cold = new THREE.Color(0x111c2e)
  const mid = new THREE.Color(0x2a6f9e)
  const warm = new THREE.Color(0x8fe3c4)
  return t < 0.5
    ? cold.clone().lerp(mid, t * 2)
    : mid.clone().lerp(warm, (t - 0.5) * 2)
}

export default function SurfaceView({ data, selected, onSelectNode }) {
  const mount = useRef(null)
  const tip = useRef(null)
  const qlabel = useRef(null)
  const api = useRef(null)

  // Recomputed only when the query, the seed set or the result scores change.
  const surface = useMemo(() => {
    if (!data?.nodes?.length) return null
    const pos = layoutPositions(data)
    const top = (data.results ?? []).slice(0, 10)
    const topIds = new Map(top.map((r, i) => [r.id, i]))
    const byId = new Map(data.nodes.map((n) => [n.id, n]))
    const items = []
    for (const n of data.nodes) {
      const p = pos.get(n.id)
      if (!p || (!n.seed && !topIds.has(n.id))) continue
      items.push({
        id: n.id,
        label: n.label,
        type: n.type,
        meta: n.meta,
        seed: !!n.seed,
        rank: topIds.has(n.id) ? topIds.get(n.id) + 1 : null,
        score: n.score ?? 0,
        x: p.x,
        y: p.y,
      })
    }
    const built = buildSurface(items)
    if (!built) return null
    const visible = new Set(items.map((i) => i.id))
    const edges = (data.edges ?? []).filter(
      (e) => visible.has(e.source) && visible.has(e.target) && byId.has(e.source)
    )
    return { ...built, edges }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    data?.query,
    JSON.stringify((data?.seeds ?? []).map((s) => s.id)),
    JSON.stringify((data?.results ?? []).slice(0, 10).map((r) => [r.id, r.score])),
  ])

  useEffect(() => {
    const host = mount.current
    if (!host || !surface) return

    const scene = new THREE.Scene()
    scene.background = new THREE.Color(0x0d1117)
    const camera = new THREE.PerspectiveCamera(45, 1, 0.01, 100)
    camera.up.set(0, 0, 1)
    camera.position.copy(CAM0)
    const renderer = new THREE.WebGLRenderer({ antialias: true })
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2))
    host.appendChild(renderer.domElement)

    const controls = new OrbitControls(camera, renderer.domElement)
    controls.enableDamping = true
    controls.dampingFactor = 0.09
    controls.target.set(0, 0, 0.18)

    scene.add(new THREE.AmbientLight(0xffffff, 0.55))
    const sun = new THREE.DirectionalLight(0xffffff, 1.1)
    sun.position.set(1.5, -1.2, 2.5)
    scene.add(sun)

    // ---- terrain ---------------------------------------------------------
    const geo = new THREE.PlaneGeometry(2, 2, N - 1, N - 1)
    const posAttr = geo.attributes.position
    const colors = new Float32Array(posAttr.count * 3)
    for (let j = 0; j < N; j++) {
      for (let k = 0; k < N; k++) {
        // PlaneGeometry rows run from +y to -y; our grid runs -y to +y.
        const vi = j * N + k
        const u = surface.U[(N - 1 - j) * N + k]
        posAttr.setZ(vi, Z_SCALE * u)
        const c = ramp(u)
        colors[vi * 3] = c.r
        colors[vi * 3 + 1] = c.g
        colors[vi * 3 + 2] = c.b
      }
    }
    geo.setAttribute('color', new THREE.BufferAttribute(colors, 3))
    geo.computeVertexNormals()
    const terrain = new THREE.Mesh(
      geo,
      new THREE.MeshLambertMaterial({ vertexColors: true, side: THREE.DoubleSide })
    )
    scene.add(terrain)
    const mesh = new THREE.LineSegments(
      new THREE.WireframeGeometry(geo),
      new THREE.LineBasicMaterial({ color: 0x9fb4d0, transparent: true, opacity: 0.07 })
    )
    scene.add(mesh)

    // ---- markers ---------------------------------------------------------
    const zOf = (x, y) => surface.height(x, y) + 0.035
    const pickable = []
    const nodePos = new Map()

    for (const s of surface.sources) {
      const z = zOf(s.x, s.y)
      nodePos.set(s.id, new THREE.Vector3(s.x, s.y, z))
      const isTop3 = s.rank !== null && s.rank <= 3
      const r = s.seed ? 0.032 : 0.016 + 0.026 * s.z + (isTop3 ? 0.008 : 0)
      const color = new THREE.Color(s.seed ? SEED_RING : TYPE_COLOR[s.type] ?? '#4c8dff')
      const marker = new THREE.Mesh(
        new THREE.SphereGeometry(r, 20, 14),
        new THREE.MeshLambertMaterial({ color, emissive: color.clone().multiplyScalar(0.35) })
      )
      marker.position.set(s.x, s.y, z)
      marker.userData = { ...s, baseColor: color.getHex(), baseScale: 1 }
      scene.add(marker)
      pickable.push(marker)
      if (s.seed) {
        const ring = new THREE.Mesh(
          new THREE.TorusGeometry(r * 2.1, r * 0.22, 8, 36),
          new THREE.MeshBasicMaterial({ color: SEED_RING })
        )
        ring.position.set(s.x, s.y, z)
        scene.add(ring)
      }
      // stem to the terrain keeps the height readable at oblique angles
      const stem = new THREE.Line(
        new THREE.BufferGeometry().setFromPoints([
          new THREE.Vector3(s.x, s.y, 0),
          new THREE.Vector3(s.x, s.y, z),
        ]),
        new THREE.LineBasicMaterial({ color: color.getHex(), transparent: true, opacity: 0.28 })
      )
      scene.add(stem)
    }

    // QUERY marker: tallest, largest, always labelled.
    const q = surface.query
    const qz = zOf(q.x, q.y) + 0.06
    const qmark = new THREE.Mesh(
      new THREE.ConeGeometry(0.055, 0.14, 4),
      new THREE.MeshLambertMaterial({ color: QUERY_COLOR, emissive: 0x4a3a10 })
    )
    qmark.rotation.x = -Math.PI / 2
    qmark.position.set(q.x, q.y, qz + 0.07)
    scene.add(qmark)
    scene.add(
      new THREE.Line(
        new THREE.BufferGeometry().setFromPoints([
          new THREE.Vector3(q.x, q.y, 0),
          new THREE.Vector3(q.x, q.y, qz),
        ]),
        new THREE.LineBasicMaterial({ color: QUERY_COLOR })
      )
    )

    // ---- edges among visible nodes ---------------------------------------
    const pts = []
    for (const e of surface.edges) {
      const a = nodePos.get(e.source)
      const b = nodePos.get(e.target)
      if (a && b) pts.push(a, b)
    }
    if (pts.length) {
      scene.add(
        new THREE.LineSegments(
          new THREE.BufferGeometry().setFromPoints(pts),
          new THREE.LineBasicMaterial({ color: 0xaebdd4, transparent: true, opacity: 0.32 })
        )
      )
    }

    // ---- interaction -----------------------------------------------------
    const ray = new THREE.Raycaster()
    const ndc = new THREE.Vector2()
    let hovered = null
    const onMove = (ev) => {
      const rect = renderer.domElement.getBoundingClientRect()
      ndc.x = ((ev.clientX - rect.left) / rect.width) * 2 - 1
      ndc.y = -((ev.clientY - rect.top) / rect.height) * 2 + 1
      ray.setFromCamera(ndc, camera)
      const hit = ray.intersectObjects(pickable, false)[0]
      hovered = hit ? hit.object : null
      const el = tip.current
      if (!el) return
      if (hovered) {
        const d = hovered.userData
        el.style.display = 'block'
        el.style.left = `${ev.clientX - rect.left + 12}px`
        el.style.top = `${ev.clientY - rect.top + 10}px`
        el.firstChild.textContent = d.seed ? d.label : `#${d.rank} ${d.label}`
        el.lastChild.textContent = d.seed ? 'Query concept' : d.meta ?? ''
      } else {
        el.style.display = 'none'
      }
    }
    const onClick = () => {
      if (hovered) onSelectNode?.(hovered.userData.id)
    }
    renderer.domElement.addEventListener('pointermove', onMove)
    renderer.domElement.addEventListener('click', onClick)

    const resize = () => {
      const w = host.clientWidth
      const h = host.clientHeight
      if (!w || !h) return
      camera.aspect = w / h
      camera.updateProjectionMatrix()
      renderer.setSize(w, h, false)
    }
    resize()
    const ro = new ResizeObserver(resize)
    ro.observe(host)

    const qWorld = new THREE.Vector3()
    let raf = 0
    const tick = () => {
      controls.update()
      renderer.render(scene, camera)
      const el = qlabel.current
      if (el) {
        qWorld.set(q.x, q.y, qz + 0.17).project(camera)
        el.style.left = `${((qWorld.x + 1) / 2) * host.clientWidth}px`
        el.style.top = `${((1 - qWorld.y) / 2) * host.clientHeight}px`
      }
      raf = requestAnimationFrame(tick)
    }
    tick()

    api.current = {
      reset() {
        camera.position.copy(CAM0)
        controls.target.set(0, 0, 0.18)
        controls.update()
      },
      highlight(id) {
        for (const m of pickable) {
          const on = m.userData.id === id
          m.material.color.setHex(on ? Number(`0x${HIGHLIGHT.slice(1)}`) : m.userData.baseColor)
          m.scale.setScalar(on ? 1.7 : 1)
        }
      },
    }

    return () => {
      cancelAnimationFrame(raf)
      ro.disconnect()
      renderer.domElement.removeEventListener('pointermove', onMove)
      renderer.domElement.removeEventListener('click', onClick)
      controls.dispose()
      scene.traverse((o) => {
        o.geometry?.dispose()
        o.material?.dispose()
      })
      renderer.dispose()
      host.removeChild(renderer.domElement)
      api.current = null
    }
  }, [surface, onSelectNode])

  useEffect(() => {
    api.current?.highlight(selected?.id ?? null)
  }, [selected, surface])

  if (!surface) return <div className="graph-canvas surface-empty">no surface yet</div>

  return (
    <div className="surface-wrap">
      <div className="graph-canvas" ref={mount} />
      <div className="surface-tip" ref={tip}>
        <b />
        <span />
      </div>
      <div className="query-label" ref={qlabel}>
        QUERY: {data.query}
      </div>
      <div className="legend surface-legend">
        <span>
          <i style={{ background: '#8fe3c4' }} /> height = query relevance
        </span>
        <span>
          <i style={{ background: '#ffd166' }} /> query · query concepts
        </span>
        <span>
          <i style={{ background: '#4c8dff' }} /> recommended people
        </span>
        <button className="reset" onClick={() => api.current?.reset()}>
          reset view
        </button>
      </div>
      <div className="surface-caption">
        <b>Query-conditioned relevance field</b>
        <span>
          Terrain height is derived from the existing hybrid ranking and smoothed with a
          screened diffusion equation.
        </span>
      </div>
    </div>
  )
}
