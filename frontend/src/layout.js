import Graph from 'graphology'
import forceAtlas2 from 'graphology-layout-forceatlas2'
import circular from 'graphology-layout/circular.js'

/** Deterministic 2D layout of a /api/graph payload → Map<id, {x, y}>.
 *  Same recipe as the Network view, so both views agree on where a node lives. */
export function layoutPositions(data) {
  const graph = new Graph({ type: 'undirected', multi: false })
  data.nodes.forEach((n) => graph.addNode(n.id))
  data.edges.forEach((e) => {
    if (graph.hasNode(e.source) && graph.hasNode(e.target) && !graph.hasEdge(e.source, e.target)) {
      graph.addEdge(e.source, e.target)
    }
  })
  circular.assign(graph)
  forceAtlas2.assign(graph, {
    iterations: 260,
    settings: { ...forceAtlas2.inferSettings(graph), gravity: 1.1, scalingRatio: 12 },
  })
  const pos = new Map()
  graph.forEachNode((id, attrs) => pos.set(id, { x: attrs.x, y: attrs.y }))
  return pos
}
