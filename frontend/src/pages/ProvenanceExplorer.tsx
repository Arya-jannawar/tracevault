/* Provenance Explorer — bounded graph view with direction/transitive/depth
   controls, node inspector, missing-provenance banner, legend, and a
   keyboard-accessible dependency TABLE alternative. */
import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { AlertTriangle, Focus, Network, Search, Table2 } from 'lucide-react';
import { api } from '../api/client';
import type {
  DependencyTable,
  DocumentOut,
  ProvenanceGraph,
  ProvenanceNode,
} from '../api/types';
import { GraphView, nodeColor } from '../components/GraphView';
import { NODE_TYPE_LABELS } from '../components/GraphView';
import { StatusPill } from '../components/StatusPill';
import { EmptyState } from '../components/EmptyState';
import { ErrorState } from '../components/ErrorState';
import { LoadingSkeleton } from '../components/LoadingSkeleton';
import { humanize, shortId } from '../lib/format';

type Direction = 'dependants' | 'dependencies';

export function ProvenanceExplorer() {
  const [params, setParams] = useSearchParams();
  const [docSearch, setDocSearch] = useState('');
  const [direction, setDirection] = useState<Direction>('dependants');
  const [transitive, setTransitive] = useState(true);
  const [depth, setDepth] = useState(6);
  const [selected, setSelected] = useState<ProvenanceNode | null>(null);

  const rootParam = params.get('root') ?? '';
  const [rootInput, setRootInput] = useState(rootParam);
  useEffect(() => setRootInput(rootParam), [rootParam]);

  const docsQuery = useQuery<DocumentOut[]>({
    queryKey: ['documents', 'provenance-picker'],
    queryFn: () => api.get<DocumentOut[]>('/documents', { page: 1, page_size: 100 }),
  });
  const docs = docsQuery.data ?? [];
  const filteredDocs = docs.filter((d) =>
    d.title.toLowerCase().includes(docSearch.trim().toLowerCase()),
  );

  const setRoot = (root: string) => {
    const next = new URLSearchParams(params);
    if (root) next.set('root', root);
    else next.delete('root');
    setParams(next, { replace: true });
    setSelected(null);
  };

  const graphQuery = useQuery<ProvenanceGraph>({
    queryKey: ['provenance', { root: rootParam, direction, transitive, depth }],
    queryFn: () =>
      api.get<ProvenanceGraph>('/provenance', {
        root: rootParam,
        direction,
        include_transitive: transitive,
        depth,
      }),
    enabled: !!rootParam,
  });

  const graph = graphQuery.data;
  const nodes = graph?.nodes ?? [];
  const edges = graph?.edges ?? [];

  const missingProvenance = nodes.filter((n) => n.provenance_status === 'unknown');

  // The dependency table operates on an artifact id: prefer the clicked node,
  // else the resolved root artifact (first document_version node or the root itself).
  const tableArtifactId =
    selected?.id ??
    (rootParam && !rootParam.startsWith('document:')
      ? rootParam
      : (nodes.find((n) => n.type === 'document_version')?.id ?? null));

  const depQuery = useQuery<DependencyTable>({
    queryKey: ['provenance-deps', tableArtifactId],
    queryFn: () => api.get<DependencyTable>(`/provenance/dependencies/${tableArtifactId}`),
    enabled: !!tableArtifactId,
  });

  return (
    <div className="stack">
      <header>
        <h1 className="page-title">Provenance Explorer</h1>
        <p className="page-sub" style={{ marginBottom: 0 }}>
          Every artifact is traced to the document version that produced it.
          Start from a document (or any artifact id) and walk the recorded
          dependency edges — bounded to 12 hops, exactly as stored.
        </p>
      </header>

      <section className="panel panel-flat" aria-label="Graph controls">
        <div className="graph-controls">
          <div className="field" style={{ maxWidth: 320, marginBottom: 0 }}>
            <label htmlFor="prov-doc-search">Root: pick a document</label>
            <div className="row" style={{ gap: 8 }}>
              <input
                id="prov-doc-search"
                className="input input-sm"
                placeholder="Filter documents…"
                value={docSearch}
                onChange={(e) => setDocSearch(e.target.value)}
                style={{ flex: 1 }}
              />
            </div>
          </div>

          <div className="field" style={{ maxWidth: 280, marginBottom: 0 }}>
            <label htmlFor="prov-root">or artifact id / document:&lt;uuid&gt;</label>
            <form
              className="row"
              style={{ gap: 8 }}
              onSubmit={(e) => {
                e.preventDefault();
                setRoot(rootInput.trim());
              }}
            >
              <input
                id="prov-root"
                className="input input-sm mono"
                placeholder="document:…"
                value={rootInput}
                onChange={(e) => setRootInput(e.target.value)}
                style={{ flex: 1 }}
              />
              <button type="submit" className="btn btn-sm" aria-label="Load graph for this root">
                <Search aria-hidden="true" size={14} /> Load
              </button>
            </form>
          </div>

          <div className="field" style={{ marginBottom: 0 }}>
            <label>Direction</label>
            <div className="seg-group" role="group" aria-label="Traversal direction">
              <button
                type="button"
                aria-pressed={direction === 'dependants'}
                onClick={() => setDirection('dependants')}
              >
                Dependants ↓
              </button>
              <button
                type="button"
                aria-pressed={direction === 'dependencies'}
                onClick={() => setDirection('dependencies')}
              >
                Dependencies ↑
              </button>
            </div>
          </div>

          <div className="field" style={{ marginBottom: 0 }}>
            <label>Scope</label>
            <div className="seg-group" role="group" aria-label="Direct or transitive">
              <button
                type="button"
                aria-pressed={transitive}
                onClick={() => setTransitive(true)}
              >
                Transitive
              </button>
              <button
                type="button"
                aria-pressed={!transitive}
                onClick={() => setTransitive(false)}
              >
                Direct only
              </button>
            </div>
          </div>

          <div className="depth-ctrl" style={{ marginBottom: 4 }}>
            <label htmlFor="prov-depth" style={{ fontSize: 12, color: 'var(--text-2)', whiteSpace: 'nowrap' }}>
              Depth
            </label>
            <input
              id="prov-depth"
              type="range"
              min={1}
              max={12}
              value={depth}
              onChange={(e) => setDepth(Number(e.target.value))}
            />
            <span className="depth-val num" aria-hidden="true">
              {depth}
            </span>
          </div>
        </div>

        {/* document quick-pick results */}
        {docSearch.trim() !== '' && (
          <div style={{ padding: '10px 18px', borderBottom: '1px solid var(--border)' }}>
            {filteredDocs.length === 0 ? (
              <p className="tiny">No documents match “{docSearch}”.</p>
            ) : (
              <div className="row wrap" style={{ gap: 8 }}>
                {filteredDocs.slice(0, 8).map((d) => (
                  <button
                    key={d.id}
                    type="button"
                    className="btn btn-sm"
                    onClick={() => {
                      setRoot(`document:${d.id}`);
                      setDocSearch('');
                    }}
                    title={d.title}
                  >
                    <Network aria-hidden="true" size={13} /> {d.title}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {missingProvenance.length > 0 && (
          <div className="callout warning" style={{ margin: '14px 18px 0' }} role="alert">
            <AlertTriangle aria-hidden="true" />
            <div className="callout-body">
              <div className="callout-title">Missing provenance</div>
              {missingProvenance.length} node
              {missingProvenance.length === 1 ? ' has' : 's have'} provenance_status
              “unknown” — TraceVault cannot vouch for how{' '}
              {missingProvenance.length === 1 ? 'it was' : 'they were'} produced.
              Treat those artifacts with suspicion.
            </div>
          </div>
        )}

        <div className="graph-layout">
          <div style={{ padding: 14, minWidth: 0 }}>
            {!rootParam ? (
              <EmptyState
                icon={<Network aria-hidden="true" />}
                title="Choose a starting point"
              >
                Pick a document above or enter an artifact id. Deletion decisions
                and coverage warnings are computed from exactly this graph.
              </EmptyState>
            ) : graphQuery.isLoading ? (
              <LoadingSkeleton variant="panel" label="Loading provenance graph" />
            ) : graphQuery.isError ? (
              <ErrorState
                error={graphQuery.error}
                onRetry={() => void graphQuery.refetch()}
                title="Graph could not be loaded"
                hint="Check the root id — it must be an artifact id or document:<uuid>."
              />
            ) : nodes.length === 0 ? (
              <EmptyState
                icon={<Network aria-hidden="true" />}
                title="No artifacts in this direction"
              >
                Nothing is registered {direction === 'dependants' ? 'downstream of' : 'upstream of'}{' '}
                this root within {depth} hop{depth === 1 ? '' : 's'}.
              </EmptyState>
            ) : (
              <GraphView
                nodes={nodes}
                edges={edges}
                rootId={nodes[0]?.id ?? null}
                selectedId={selected?.id}
                onNodeClick={setSelected}
                height={520}
              />
            )}
          </div>

          {/* inspector */}
          <aside className="inspector" aria-label="Node inspector">
            {selected ? (
              <>
                <div className="row" style={{ marginBottom: 12 }}>
                  <span
                    className="lg-dot"
                    style={{ background: nodeColor(selected.type), width: 12, height: 12, borderRadius: 4 }}
                  />
                  <strong>{NODE_TYPE_LABELS[selected.type] ?? humanize(selected.type)}</strong>
                </div>
                <dl className="kv">
                  <dt>Artifact</dt>
                  <dd className="mono">{shortId(selected.id, 14)}</dd>
                  <dt>Lifecycle</dt>
                  <dd>
                    <StatusPill status={selected.lifecycle_state} />
                  </dd>
                  <dt>Version</dt>
                  <dd className="num">{selected.version}</dd>
                  <dt>Provenance</dt>
                  <dd>
                    <StatusPill
                      status={selected.provenance_status}
                      label={
                        selected.provenance_status === 'registered'
                          ? 'registered'
                          : selected.provenance_status
                      }
                    />
                  </dd>
                  {selected.document_id && (
                    <>
                      <dt>Document</dt>
                      <dd className="mono">{shortId(selected.document_id, 10)}…</dd>
                    </>
                  )}
                  {selected.document_version_id && (
                    <>
                      <dt>Src version</dt>
                      <dd className="mono">{shortId(selected.document_version_id, 10)}…</dd>
                    </>
                  )}
                </dl>
                {Object.keys(selected.meta ?? {}).length > 0 && (
                  <>
                    <hr className="divider" />
                    <div className="tiny" style={{ marginBottom: 6 }}>
                      Meta keys
                    </div>
                    <div className="json-view" style={{ maxHeight: 180, overflowY: 'auto' }}>
                      {Object.entries(selected.meta)
                        .map(([k, v]) => {
                          const shown =
                            typeof v === 'string' && v.length > 80
                              ? `${v.slice(0, 77)}…`
                              : JSON.stringify(v);
                          return `${k}: ${shown}`;
                        })
                        .join('\n')}
                    </div>
                  </>
                )}
                <hr className="divider" />
                <button
                  type="button"
                  className="btn btn-sm"
                  onClick={() => setRoot(selected.id)}
                >
                  <Focus aria-hidden="true" size={13} /> Focus graph here
                </button>
              </>
            ) : (
              <p className="muted" style={{ fontSize: 13 }}>
                Click a node in the graph to inspect its type, lifecycle state,
                version and provenance status.
              </p>
            )}
          </aside>
        </div>
      </section>

      {/* -------- dependency table alternative -------- */}
      <section className="panel" aria-label="Dependency table alternative">
        <div className="panel-head">
          <h3>
            <Table2 aria-hidden="true" /> Dependency table
          </h3>
          <span className="tiny">
            keyboard-accessible alternative to the graph · GET
            /provenance/dependencies/{tableArtifactId ? shortId(tableArtifactId, 8) : '{artifact_id}'}
          </span>
        </div>
        {!tableArtifactId ? (
          <EmptyState icon={<Table2 aria-hidden="true" />} title="No artifact selected">
            Load a graph and click a node (or use a non-document root) to list
            its direct dependencies and dependants as tables.
          </EmptyState>
        ) : depQuery.isLoading ? (
          <LoadingSkeleton variant="table" rows={3} label="Loading dependency table" />
        ) : depQuery.isError ? (
          <ErrorState
            error={depQuery.error}
            onRetry={() => void depQuery.refetch()}
            title="Dependency table unavailable"
          />
        ) : (
          <DependencyTables table={depQuery.data!} />
        )}
      </section>
    </div>
  );
}

function DependencyTables({ table }: { table: DependencyTable }) {
  return (
    <div className="grid-2">
      <DepTable title="Dependencies (inputs this artifact was built from)" rows={table.dependencies} />
      <DepTable title="Dependants (artifacts built from this one)" rows={table.dependants} />
      <div className="tiny" style={{ gridColumn: '1 / -1' }}>
        Focused artifact: <span className="mono">{table.artifact.id}</span> ·{' '}
        {humanize(table.artifact.type)} · {table.artifact.state}
      </div>
    </div>
  );
}

function DepTable({
  title,
  rows,
}: {
  title: string;
  rows: DependencyTable['dependencies'];
}) {
  return (
    <div>
      <div className="section-title">{title}</div>
      {rows.length === 0 ? (
        <p className="tiny">None recorded.</p>
      ) : (
        <div className="table-scroll">
          <table className="data">
            <caption className="visually-hidden">{title}</caption>
            <thead>
              <tr>
                <th scope="col">Type</th>
                <th scope="col">State</th>
                <th scope="col">Artifact</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id}>
                  <td>
                    <span
                      className="lg-dot"
                      style={{
                        display: 'inline-block',
                        background: nodeColor(r.type),
                        marginRight: 8,
                      }}
                      aria-hidden="true"
                    />
                    {humanize(r.type)}
                  </td>
                  <td>
                    <StatusPill status={r.state} />
                  </td>
                  <td className="mono tiny">{r.id}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
