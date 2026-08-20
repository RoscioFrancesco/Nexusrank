import { useCallback, useEffect, useMemo, useState } from 'react'
import GraphView from './GraphView'
import ProfileEditor from './ProfileEditor'
import SurfaceView from './SurfaceView'
import { clearMyNetwork, fetchGraph, fetchHealth, fetchState, fetchSuggestions, fetchViewers, importLinkedIn, searchPeople, setDataset } from './api'
import { TYPE_COLOR } from './theme'

const DEFAULT_QUERY = 'network'

export default function App() {
  const [query, setQuery] = useState(DEFAULT_QUERY)
  const [submitted, setSubmitted] = useState(DEFAULT_QUERY)
  const [viewer, setViewer] = useState('')
  const [viewers, setViewers] = useState([])
  const [health, setHealth] = useState(null)
  const [data, setData] = useState(null)
  const [selected, setSelected] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)
  const [view, setView] = useState('network')
  const [editing, setEditing] = useState(undefined) // undefined = closed, null = add
  const [reload, setReload] = useState(0)
  const [dataset, setDatasetName] = useState('demo')
  const [examples, setExamples] = useState([])
  const [personQuery, setPersonQuery] = useState('')
  const [peopleMatches, setPeopleMatches] = useState([])

  useEffect(() => {
    fetchViewers().then((r) => setViewers(r.viewers)).catch(() => {})
    fetchHealth().then((h) => {
      setHealth(h)
      if (h.active_dataset) setDatasetName(h.active_dataset)
    }).catch(() => {})
    fetchState().then((s) => setDatasetName(s.active_dataset)).catch(() => {})
    fetchSuggestions().then((r) => {
      setExamples(r.suggestions ?? [])
      if (r.suggestions?.[0]) {
        setQuery(r.suggestions[0])
        setSubmitted(r.suggestions[0])
      }
    }).catch(() => {})
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
  }, [submitted, viewer, reload])

  useEffect(() => {
    let live = true
    const q = personQuery.trim()
    if (!q) {
      setPeopleMatches([])
      return () => { live = false }
    }
    const t = setTimeout(() => {
      searchPeople(q)
        .then((r) => live && setPeopleMatches(r.people ?? []))
        .catch(() => live && setPeopleMatches([]))
    }, 160)
    return () => {
      live = false
      clearTimeout(t)
    }
  }, [personQuery, dataset, reload])

  const results = data?.results ?? []
  const byId = useMemo(() => new Map(results.map((r) => [r.id, r])), [results])
  const onSelectNode = useCallback((id) => setSelected(byId.get(id) ?? null), [byId])
  const runRank = useCallback((value = query) => {
    const next = value.trim() || examples[0] || DEFAULT_QUERY
    setQuery(next)
    setSubmitted(next)
    setReload((n) => n + 1)
  }, [examples, query])

  const refresh = async ({ focusFirstSuggestion = false } = {}) => {
    setReload((n) => n + 1)
    fetchViewers().then((r) => setViewers(r.viewers)).catch(() => {})
    fetchHealth().then(setHealth).catch(() => {})
    fetchSuggestions().then((r) => {
      const next = r.suggestions ?? []
      setExamples(next)
      if (focusFirstSuggestion && next[0]) {
        setQuery(next[0])
        setSubmitted(next[0])
      }
    }).catch(() => {})
  }

  const onImport = async (fileList) => {
    const files = Array.from(fileList ?? [])
    if (!files.length) return
    setError(null)
    try {
      const payload = files.length === 1
        ? { content: await files[0].text() }
        : { files: await Promise.all(files.map(async (f) => ({
            name: f.webkitRelativePath || f.name,
            content: await f.text(),
          }))) }
      await importLinkedIn(payload)
      setDatasetName('my')
      setViewer('')
      await refresh({ focusFirstSuggestion: true })
    } catch (e) {
      setError(e.message)
    }
  }

  const switchDataset = async (next) => {
    setDatasetName(next)
    try {
      await setDataset(next)
      await refresh()
    } catch (e) {
      setError(e.message)
    }
  }

  const clearNetwork = async () => {
    if (!confirm('Clear My Network? This deletes imported contacts, manual people, enrichment, and generated relations. Demo data stays separate.')) return
    try {
      await clearMyNetwork()
      setDatasetName('demo')
      await refresh()
    } catch (e) {
      setError(e.message)
    }
  }

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
            runRank()
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
        <button className="ghost" onClick={() => setEditing(null)}>
          Add person
        </button>
        <label className="ghost import">
          Import CSVs
          <input
            type="file"
            accept=".csv,text/csv"
            multiple
            onChange={(e) => {
              onImport(e.target.files)
              e.target.value = ''
            }}
          />
        </label>
        <label className="ghost import">
          Import Folder
          <input
            type="file"
            multiple
            webkitdirectory=""
            directory=""
            onChange={(e) => {
              onImport(e.target.files)
              e.target.value = ''
            }}
          />
        </label>
        <select value={dataset} onChange={(e) => switchDataset(e.target.value)} aria-label="Dataset">
          <option value="demo">Demo Network</option>
          <option value="my">My Network</option>
        </select>
        <button className="ghost" onClick={clearNetwork}>Clear My Network</button>
        <div className="stats">
          {health ? `${health.nodes} nodes · ${health.edges} edges · ${health.imported_network ?? 0} imported` : '…'}
        </div>
      </header>

      <div className="examples">
        {examples.map((e) => (
          <button
            key={e}
            className={e === submitted ? 'chip active' : 'chip'}
            onClick={() => {
              runRank(e)
            }}
          >
            {e}
          </button>
        ))}
      </div>

      <main>
        <aside>
          {error && <p className="error">{error}</p>}
          <div className="people-search">
            <input
              value={personQuery}
              onChange={(e) => setPersonQuery(e.target.value)}
              placeholder="Find a person by name, company, or role…"
              aria-label="Find people"
            />
            {peopleMatches.length > 0 && (
              <ol className="people-matches">
                {peopleMatches.map((p) => (
                  <li key={p.id}>
                    <button
                      onClick={() => {
                        runRank(p.name)
                      }}
                    >
                      <b>{p.name}</b>
                      <span>{p.meta}</span>
                    </button>
                    <button className="ghost small" onClick={() => setEditing(p.id)}>
                      Edit
                    </button>
                  </li>
                ))}
              </ol>
            )}
          </div>
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
          {!loading && results.length === 0 && (
            <p className="empty">
              No contacts yet. Use <b>Add person</b> to create one, then enrich it with
              education, experience, skills, activities and projects.
            </p>
          )}
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
                  <button
                    className="ghost small enrich"
                    onClick={(e) => {
                      e.stopPropagation()
                      setEditing(r.id)
                    }}
                  >
                    Enrich profile
                  </button>
                </div>
                <div className="side">
                  <span className="score">{r.score.toFixed(3)}</span>
                </div>
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

      {editing !== undefined && (
        <ProfileEditor
          personId={editing}
          onClose={() => setEditing(undefined)}
          onSaved={refresh}
        />
      )}
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
