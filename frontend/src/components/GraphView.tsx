/* React Flow wrapper for provenance graphs.
   Node colors: document_version=cyan, chunk=violet, summary=lime,
   answer=amber, cache_entry=coral, vector=slate. */
import { useEffect, useMemo } from 'react';
import {
  Background,
  BackgroundVariant,
  Controls,
  ReactFlow,
  ReactFlowProvider,
  useNodesState,
  useEdgesState,
  useReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import type { ProvenanceEdge, ProvenanceNode } from '../api/types';
import { layoutGraph } from '../lib/layout';
import { humanize, shortId } from '../lib/format';

export const NODE_TYPE_COLORS: Record<string, string> = {
  document_version: '#45D9F5',
  chunk: '#A99BFF',
  summary: '#C7FF5E',
  answer: '#FFBE55',
  cache_entry: '#FF6B75',
  vector: '#6B7A93',
};

export function nodeColor(type: string): string {
  return NODE_TYPE_COLORS[type] ?? '#6B7A93';
}

export const NODE_TYPE_LABELS: Record<string, string> = {
  document_version: 'Document version',
  chunk: 'Chunk',
  vector: 'Vector',
  summary: 'Summary',
  answer: 'Answer',
  cache_entry: 'Cache entry',
};

interface TvNodeData extends Record<string, unknown> {
  typeLabel: string;
  color: string;
  title: string;
  sub: string;
  state: string;
}

function TvNode({ data, selected }: NodeProps<Node<TvNodeData>>) {
  return (
    <div className={`tv-node ${selected ? 'selected' : ''}`}>
      <div className="tvn-head">
        <span className="tvn-swatch" style={{ background: data.color }} />
        <span className="tvn-type">{data.typeLabel}</span>
      </div>
      <div className="tvn-title">{data.title}</div>
      <div className="tvn-sub">
        <span>{data.state}</span>
        {data.sub ? <span>· {data.sub}</span> : null}
      </div>
    </div>
  );
}

// Module-level nodeTypes — React Flow warns (console.error) if this identity changes.
const nodeTypes = { tv: TvNode };

function nodeTitle(n: ProvenanceNode): string {
  const meta = n.meta ?? {};
  switch (n.type) {
    case 'document_version':
      return `v${n.version}`;
    case 'chunk':
      return `chunk #${String(meta['index'] ?? '?')}`;
    case 'summary':
      return `summary v${n.version}`;
    case 'answer':
      return typeof meta['question'] === 'string'
        ? shortId(String(meta['question']), 26)
        : `answer v${n.version}`;
    case 'cache_entry':
      return typeof meta['cache_type'] === 'string'
        ? `${String(meta['cache_type'])} cache`
        : 'cache entry';
    case 'vector':
      return `vector (${String(meta['dim'] ?? '—')}d)`;
    default:
      return shortId(n.id, 10);
  }
}

function toFlowNodes(
  provenance: ProvenanceNode[],
  edges: ProvenanceEdge[],
  rootId: string | null,
  selectedId: string | null | undefined,
): Node<TvNodeData>[] {
  const positions = layoutGraph(provenance, edges, rootId);
  return provenance.map((n) => {
    const pos = positions.get(n.id) ?? { x: 0, y: 0 };
    return {
      id: n.id,
      type: 'tv' as const,
      position: pos,
      selected: selectedId === n.id,
      data: {
        typeLabel: humanize(n.type),
        color: nodeColor(n.type),
        title: nodeTitle(n),
        sub: n.provenance_status !== 'registered' ? n.provenance_status : '',
        state: n.lifecycle_state,
      },
    };
  });
}

function toFlowEdges(edges: ProvenanceEdge[]): Edge[] {
  return edges.map((e, i) => ({
    id: `e-${e.parent}-${e.child}-${i}`,
    source: e.parent,
    target: e.child,
    type: 'smoothstep',
    label: undefined,
    animated: false,
    style: { stroke: 'rgba(168,181,202,0.35)', strokeWidth: 1.4 },
  }));
}

function GraphInner({
  provNodes,
  provEdges,
  rootId,
  selectedId,
  onNodeClick,
  height,
  mini,
}: {
  provNodes: ProvenanceNode[];
  provEdges: ProvenanceEdge[];
  rootId: string | null;
  selectedId?: string | null;
  onNodeClick?: (node: ProvenanceNode) => void;
  height?: number;
  mini?: boolean;
}) {
  const [nodes, setNodes, onNodesChange] = useNodesState<Node<TvNodeData>>(
    toFlowNodes(provNodes, provEdges, rootId, selectedId),
  );
  const [edges, , onEdgesChange] = useEdgesState<Edge>(
    toFlowEdges(provEdges),
  );
  const { fitView } = useReactFlow();

  useEffect(() => {
    setNodes(toFlowNodes(provNodes, provEdges, rootId, selectedId));
  }, [provNodes, provEdges, rootId, selectedId, setNodes]);

  useEffect(() => {
    const t = window.setTimeout(() => void fitView({ padding: 0.18, duration: 200 }), 30);
    return () => window.clearTimeout(t);
  }, [fitView, provNodes.length]);

  const byId = useMemo(() => {
    const m = new Map<string, ProvenanceNode>();
    for (const n of provNodes) m.set(n.id, n);
    return m;
  }, [provNodes]);

  return (
    <ReactFlow
      nodes={nodes}
      edges={edges}
      onNodesChange={onNodesChange}
      onEdgesChange={onEdgesChange}
      nodeTypes={nodeTypes}
      fitView
      fitViewOptions={{ padding: 0.18 }}
      minZoom={0.2}
      maxZoom={1.6}
      nodesDraggable={!mini}
      nodesConnectable={false}
      elementsSelectable={!mini}
      panOnScroll={!mini}
      zoomOnScroll={!mini}
      preventScrolling={!mini}
      proOptions={{ hideAttribution: true }}
      style={{ height: height ?? (mini ? 260 : 520) }}
      onNodeClick={(_, node) => {
        const n = byId.get(node.id);
        if (n && onNodeClick) onNodeClick(n);
      }}
      aria-label="Provenance graph"
    >
      <Background variant={BackgroundVariant.Dots} gap={22} size={1} color="rgba(168,181,202,0.1)" />
      {!mini && <Controls showInteractive={false} position="bottom-right" />}
    </ReactFlow>
  );
}

export function GraphLegend() {
  const types = Object.entries(NODE_TYPE_LABELS);
  return (
    <div className="graph-legend">
      {types.map(([type, label]) => (
        <span className="lg-item" key={type}>
          <span className="lg-dot" style={{ background: nodeColor(type) }} />
          {label}
        </span>
      ))}
      <span className="lg-item tiny" style={{ marginLeft: 'auto' }}>
        edge = recorded dependency
      </span>
    </div>
  );
}

export function GraphView({
  nodes,
  edges,
  rootId = null,
  selectedId,
  onNodeClick,
  height,
  mini = false,
  withLegend = true,
}: {
  nodes: ProvenanceNode[];
  edges: ProvenanceEdge[];
  rootId?: string | null;
  selectedId?: string | null;
  onNodeClick?: (node: ProvenanceNode) => void;
  height?: number;
  mini?: boolean;
  withLegend?: boolean;
}) {
  return (
    <div className="graph-wrap">
      <ReactFlowProvider>
        <GraphInner
          provNodes={nodes}
          provEdges={edges}
          rootId={rootId}
          selectedId={selectedId}
          onNodeClick={onNodeClick}
          height={height}
          mini={mini}
        />
      </ReactFlowProvider>
      {withLegend && <GraphLegend />}
    </div>
  );
}
