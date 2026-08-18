import { useEffect, useRef } from 'react'
import Graph from 'graphology'
import forceAtlas2 from 'graphology-layout-forceatlas2'
import circular from 'graphology-layout/circular'
import Sigma from 'sigma'
import { DIM, HIGHLIGHT, SEED_RING, TYPE_COLOR } from './theme'

/** Sigma canvas. Layout is recomputed when the graph payload changes;
 *  highlighting is done with reducers so selection never re-runs the layout. */
export default function GraphView({ data, selected, onSelectNode }) {
  const container = useRef(null)
  const sigmaRef = useRef(null)
  const focus = useRef({ nodes: new Set(), edges: new Set() })

  useEffect(() => {
    if (!container.current || !data) return
    const graph = new Graph({ type: 'undirected', multi: false })
    const maxScore = Math.max(...data.nodes.map((n) => n.score ?? 0), 1e-9)

    data.nodes.forEach((n) => {
      graph.addNode(n.id, {
        label: n.label,
        nodeType: n.type,
        meta: n.meta,
        seed: n.seed,
        score: n.score ?? 0,
        color: TYPE_COLOR[n.type] ?? '#888',
        size: n.type === 'person' ? 4 + 12 * Math.sqrt((n.score ?? 0) / maxScore) : n.seed ? 8 : 5,
      })
    })
    data.edges.forEach((e) => {
      if (graph.hasNode(e.source) && graph.hasNode(e.target) && !graph.hasEdge(e.source, e.target)) {
        graph.addEdge(e.source, e.target, {
          size: 0.6 + 1.6 * e.weight,
          color: 'rgba(150,160,180,0.35)',
          edgeType: e.type,
          label: e.label,
        })
      }
    })

    circular.assign(graph)
    forceAtlas2.assign(graph, {
      iterations: 260,
      settings: { ...forceAtlas2.inferSettings(graph), gravity: 1.1, scalingRatio: 12 },
    })

    const renderer = new Sigma(graph, container.current, {
      renderEdgeLabels: false,
      labelRenderedSizeThreshold: 7,
      labelFont: 'ui-sans-serif, system-ui',
      labelColor: { color: '#c9d3e4' },
      defaultEdgeColor: 'rgba(150,160,180,0.3)',
    })

    renderer.setSetting('nodeReducer', (id, attrs) => {
      const { nodes } = focus.current
      const active = nodes.size === 0 || nodes.has(id)
      return {
        ...attrs,
        color: !active ? DIM : nodes.has(id) ? HIGHLIGHT : attrs.seed ? SEED_RING : attrs.color,
        zIndex: active ? 1 : 0,
        size: nodes.has(id) ? attrs.size * 1.5 : attrs.size,
        label: active ? attrs.label : '',
      }
    })
    renderer.setSetting('edgeReducer', (id, attrs) => {
      const { edges } = focus.current
      if (edges.size === 0) return attrs
      const on = edges.has(id)
      return { ...attrs, color: on ? HIGHLIGHT : DIM, size: on ? attrs.size * 2.4 : 0.3, hidden: false }
    })

    renderer.on('clickNode', ({ node }) => onSelectNode?.(node))
    sigmaRef.current = renderer
    return () => {
      renderer.kill()
      sigmaRef.current = null
    }
  }, [data, onSelectNode])

  // Selection → highlight the explanation path.
  useEffect(() => {
    const renderer = sigmaRef.current
    if (!renderer) return
    const graph = renderer.getGraph()
    const nodes = new Set()
    const edges = new Set()
    if (selected) {
      const hops = selected.path ?? []
      if (hops.length) {
        nodes.add(hops[0].src)
        hops.forEach((h) => {
          nodes.add(h.src)
          nodes.add(h.dst)
          if (graph.hasNode(h.src) && graph.hasNode(h.dst)) {
            const e = graph.edge(h.src, h.dst) ?? graph.edge(h.dst, h.src)
            if (e) edges.add(e)
          }
        })
      }
      if (graph.hasNode(selected.id)) nodes.add(selected.id)
    }
    focus.current = { nodes, edges }
    renderer.refresh()
  }, [selected])

  return <div className="graph-canvas" ref={container} />
}
