import { useCallback, useEffect, useMemo, useState } from 'react'
import GraphView from './GraphView'
import SurfaceView from './SurfaceView'
import { fetchGraph, fetchHealth, fetchViewers } from './api'
import { TYPE_COLOR } from './theme'

const EXAMPLES = [
  'graph neural networks recommender systems',
  'kubernetes rust distributed systems',
  'design systems user research',
  'payments risk modeling',
  'genomics bioinformatics',
]

export default function App() {
  const [query, setQuery] = useState(EXAMPLES[0])
  const [submitted, setSubmitted] = useState(EXAMPLES[0])
  const [viewer, setViewer] = useState('')
  const [viewers, setViewers] = useState([])
  const [health, setHealth] = useState(null)
  const [data, setData] = useState(null)
  const [selected, setSelected] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)
  const [view, setView] = useState('network')

  useEffect(() => {
    fetchViewers().then((r) => setViewers(r.viewers)).catch(() => {})
    fetchHealth().then(setHealth).catch(() => {})
  }, [])

  useEffect(() => {
    let live = true
    setLoading(true)
    setError(null)
    fetchGraph(submitted, viewer)
      .then((r) => {
        if (!live) return
        setData(r)
        setSelected(null)
      })
      .catch((e) => live && setError(e.message))
      .finally(() => live && setLoading(false))
    return () => {
      live = false
    }
  }, [submitted, viewer])

  const results = data?.results ?? []
  const byId = useMemo(() => new Map(results.map((r) => [r.id, r])), [results])
  const onSelectNode = useCallback((id) => setSelected(byId.get(id) ?? null), [byId])

  return (
    <div className="app">
      <header>
        <div className="brand">
          <span className="dot" /> NexusRank
        </div>
        <form
          className="searchbar"
          onSubmit={(e) => {
            e.preventDefault()
            setSubmitted(query.trim() || EXAMPLES[0])
          }}
        >
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search people by skill, company, or topic…"
            aria-label="Search query"
          />
          <select value={viewer} onChange={(e) => setViewer(e.target.value)} aria-label="Viewer">
            <option value="">No viewer (global)</option>
            {viewers.map((v) => (
              <option key={v.id} value={v.id}>
                as {v.name}
              </option>
            ))}
          </select>
          <button type="submit">Rank</button>
        </form>
        <div className="stats">
          {health ? `${health.nodes} nodes · ${health.edges} edges` : '…'}
        </div>
      </header>

      <div className="examples">
        {EXAMPLES.map((e) => (
          <button
            key={e}
            className={e === submitted ? 'chip active' : 'chip'}
            onClick={() => {
              setQuery(e)
              setSubmitted(e)
            }}
          >
            {e}
          </button>
        ))}
      </div>

      <main>
        <aside>
          {error && <p className="error">{error}</p>}
          {data?.seeds?.length > 0 && (
            <div className="seeds concepts">
              <h2>Query concepts</h2>
              <div className="chips">
                {data.seeds.map((s) => (
                  <span key={s.id} className="seed" style={{ borderColor: TYPE_COLOR[s.type] }}>
                    {s.name}
                  </span>
                ))}
              </div>
            </div>
          )}
          <h2>
            Recommended people {loading && <span className="spin">·</span>}
          </h2>
          <ol className="results">
            {results.map((r, i) => (
              <li
                key={r.id}
                className={selected?.id === r.id ? 'result sel' : 'result'}
                onClick={() => setSelected(selected?.id === r.id ? null : r)}
              >
                <div className="rank">{i + 1}</div>
                <div className="body">
                  <div className="name">{r.name}</div>
                  <div className="meta">{r.meta}</div>
                  <div className="bars">
                    <Bar label="graph" value={r.graph_score} color="#37c39b" />
                    <Bar label="text" value={r.lexical_score} color="#4c8dff" />
                  </div>
                  {selected?.id === r.id && (
                    <div className="why">
                      <PathChain path={r.path} why={r.why} />
                    </div>
                  )}
                </div>
                <div className="score">{r.score.toFixed(3)}</div>
              </li>
            ))}
          </ol>
        </aside>

        <section className="canvas-wrap">
          <div className="viewtabs">
            {['network', 'surface'].map((v) => (
              <button
                key={v}
                className={view === v ? 'tab active' : 'tab'}
                onClick={() => setView(v)}
              >
                {v === 'network' ? 'Network' : 'Surface'}
              </button>
            ))}
          </div>
          {view === 'surface' ? (
            <SurfaceView data={data} selected={selected} onSelectNode={onSelectNode} />
          ) : (
            <>
          <GraphView data={data} selected={selected} onSelectNode={onSelectNode} />
          <div className="legend">
            {Object.entries(TYPE_COLOR).map(([t, c]) => (
              <span key={t}>
                <i style={{ background: c }} /> {t}
              </span>
            ))}
            <span className="hint">
              {selected ? 'showing evidence path — click again to clear' : 'click a result or node'}
            </span>
          </div>
            </>
          )}
        </section>
      </main>
    </div>
  )
}

function Bar({ label, value, color }) {
  return (
    <div className="bar" title={`${label} ${value.toFixed(3)}`}>
      <span className="bar-label">{label}</span>
      <span className="track">
        <span className="fill" style={{ width: `${Math.min(100, value * 100)}%`, background: color }} />
      </span>
    </div>
  )
}

function PathChain({ path, why }) {
  if (!path?.length) return <p>{why}</p>
  return (
    <div className="chain">
      {path.map((h, i) => (
        <span key={i} className="hop">
          <em>{h.label}</em> → <b>{h.dst.split(':')[0]}</b> {h.weight.toFixed(2)}
        </span>
      ))}
      <p className="chain-text">{why}</p>
    </div>
  )
}
