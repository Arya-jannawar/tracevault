/* Simple layered layout for provenance graphs: BFS depth from the root sets
   the column, siblings are stacked vertically. Deterministic and dependency-free. */
import type { ProvenanceEdge, ProvenanceNode } from '../api/types';

export interface LaidOutNode {
  id: string;
  x: number;
  y: number;
}

const COL_W = 250;
const ROW_H = 118;

export function layoutGraph(
  nodes: ProvenanceNode[],
  edges: ProvenanceEdge[],
  rootId: string | null,
): Map<string, { x: number; y: number }> {
  const positions = new Map<string, { x: number; y: number }>();
  if (nodes.length === 0) return positions;

  // adjacency (undirected BFS so the root column is correct for both directions)
  const adj = new Map<string, string[]>();
  for (const n of nodes) adj.set(n.id, []);
  for (const e of edges) {
    if (adj.has(e.parent) && adj.has(e.child)) {
      adj.get(e.parent)!.push(e.child);
      adj.get(e.child)!.push(e.parent);
    }
  }

  const start = rootId && adj.has(rootId) ? rootId : nodes[0].id;
  const depth = new Map<string, number>([[start, 0]]);
  const queue = [start];
  while (queue.length > 0) {
    const cur = queue.shift()!;
    for (const nb of adj.get(cur) ?? []) {
      if (!depth.has(nb)) {
        depth.set(nb, depth.get(cur)! + 1);
        queue.push(nb);
      }
    }
  }

  // any node unreachable from root (shouldn't happen) goes to a final column
  let maxDepth = 0;
  for (const n of nodes) {
    if (!depth.has(n.id)) depth.set(n.id, -1);
    maxDepth = Math.max(maxDepth, depth.get(n.id)!);
  }

  const perColumn = new Map<number, string[]>();
  for (const n of nodes) {
    const d = depth.get(n.id) ?? maxDepth + 1;
    const list = perColumn.get(d) ?? [];
    list.push(n.id);
    perColumn.set(d, list);
  }

  for (const [d, ids] of perColumn) {
    const colHeight = (ids.length - 1) * ROW_H;
    ids.forEach((id, i) => {
      positions.set(id, {
        x: d < 0 ? (maxDepth + 1) * COL_W : d * COL_W,
        y: i * ROW_H - colHeight / 2,
      });
    });
  }
  return positions;
}
