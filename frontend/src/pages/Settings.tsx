/* Settings & About — read-only honesty contract: connector health, model and
   mode status, declared boundary, flags with explanations, retention note,
   full academic title and research-prototype identity. */
import { useQuery } from '@tanstack/react-query';
import {
  BookOpen,
  CheckCircle2,
  Flag,
  Lock,
  Scale,
  Server,
  ShieldCheck,
  XCircle,
} from 'lucide-react';
import { api } from '../api/client';
import type { Capabilities } from '../api/types';
import { StatusPill } from '../components/StatusPill';
import { ErrorState } from '../components/ErrorState';
import { LoadingSkeleton } from '../components/LoadingSkeleton';
import { useHealth } from '../hooks/useHealth';
import { useAuth } from '../hooks/AuthProvider';
import { humanize } from '../lib/format';

const FLAG_EXPLANATIONS: Record<string, string> = {
  selective_repair:
    'Experimental selective summary repair. When false, the Repair Lab is read-only: everything downstream of a deletion is conservatively invalidated. Enable with ENABLE_SELECTIVE_REPAIR=true on the backend.',
  semantic_cache:
    'Semantic answer cache (meaning-equivalent questions served without re-retrieval). When false only the exact-match cache is active.',
  pending_jobs:
    'Number of backend jobs currently queued or running (ingest, delete, repair, evaluate). Shown live — this is how the console exposes honest pending work.',
};

export function Settings() {
  const capsQuery = useQuery<Capabilities>({
    queryKey: ['capabilities'],
    queryFn: () => api.get<Capabilities>('/system/capabilities'),
    staleTime: 60_000,
  });
  const health = useHealth();
  const { user } = useAuth();

  if (capsQuery.isLoading) {
    return <LoadingSkeleton variant="lines" rows={8} label="Loading capabilities" />;
  }
  if (capsQuery.isError || !capsQuery.data) {
    return (
      <ErrorState
        error={capsQuery.error}
        onRetry={() => void capsQuery.refetch()}
        title="Capabilities unavailable"
        hint="This page is generated from GET /system/capabilities — the honesty contract itself."
      />
    );
  }

  const caps = capsQuery.data;

  return (
    <div className="stack">
      <header>
        <h1 className="page-title">Settings &amp; About</h1>
        <p className="page-sub" style={{ marginBottom: 0 }}>
          Everything on this page comes from the backend's declared capabilities.
          It is read-only by design — the console never claims more than the
          system does.
        </p>
      </header>

      <section className="hero" style={{ padding: '26px 28px' }}>
        <div className="row" style={{ gap: 14 }}>
          <span className="brand-mark" style={{ width: 46, height: 46, fontSize: 16 }}>
            TV
          </span>
          <div>
            <h2 style={{ marginBottom: 4 }}>{caps.system}</h2>
            <p className="muted" style={{ fontSize: 14 }}>
              {caps.tagline}
            </p>
          </div>
        </div>
        <hr className="divider" />
        <div className="row" style={{ gap: 8, marginBottom: 8 }}>
          <BookOpen aria-hidden="true" size={15} style={{ color: 'var(--accent)' }} />
          <strong style={{ fontSize: 13 }}>Academic title</strong>
        </div>
        <p style={{ fontSize: 14.5, lineHeight: 1.6, maxWidth: '80ch' }}>
          {caps.academic_title}
        </p>
        <div className="callout accent" style={{ marginTop: 16 }}>
          <ShieldCheck aria-hidden="true" />
          <div className="callout-body">
            <div className="callout-title">Research prototype</div>
            This system is a research prototype (declared:{' '}
            <span className="mono">is_research_prototype = {String(caps.is_research_prototype)}</span>).
            No model unlearning, legal compliance or certified security is
            claimed. You are signed in as <strong>{user?.username}</strong> with
            the <strong>{user?.role}</strong> role.
          </div>
        </div>
      </section>

      <div className="grid-2">
        {/* connectors */}
        <section className="panel" aria-label="Connector health">
          <div className="panel-head">
            <h3>
              <Server aria-hidden="true" /> Connector health
            </h3>
            <StatusPill
              status={health.status === 'ok' ? 'ok' : health.status === 'degraded' ? 'degraded' : 'unavailable'}
              label={health.status === 'ok' ? 'all connectors ok' : health.status === 'degraded' ? 'degraded' : 'API unreachable'}
            />
          </div>
          <div className="list-tight">
            {Object.entries(caps.connectors).map(([name, ok]) => (
              <div className="list-item" key={name}>
                <span className="grow">{humanize(name)}</span>
                <span className={`chip ${ok ? 'chip-accent' : 'chip-danger'}`}>
                  {ok ? (
                    <>
                      <CheckCircle2 aria-hidden="true" /> ok
                    </>
                  ) : (
                    <>
                      <XCircle aria-hidden="true" /> unavailable
                    </>
                  )}
                </span>
              </div>
            ))}
          </div>
          <p className="tiny" style={{ marginTop: 10 }}>
            Live probes run every 15 seconds in the top bar; this list reflects
            the backend's own declaration at page load.
          </p>
        </section>

        {/* models & modes */}
        <section className="panel" aria-label="Models and operating modes">
          <div className="panel-head">
            <h3>
              <Lock aria-hidden="true" /> Models &amp; operating modes
            </h3>
          </div>
          <dl className="kv">
            {Object.entries(caps.embedding).map(([k, v]) => (
              <FragmentRow key={`emb-${k}`} group={`embedding.${k}`} value={String(v)} />
            ))}
            {Object.entries(caps.llm).map(([k, v]) => (
              <FragmentRow key={`llm-${k}`} group={`llm.${k}`} value={String(v)} />
            ))}
            {Object.entries(caps.operating_modes).map(([k, v]) => (
              <FragmentRow key={`mode-${k}`} group={humanize(k)} value={String(v)} />
            ))}
          </dl>
        </section>
      </div>

      {/* flags */}
      <section className="panel" aria-label="Feature flags">
        <div className="panel-head">
          <h3>
            <Flag aria-hidden="true" /> Flags
          </h3>
        </div>
        <div className="list-tight">
          {Object.entries(caps.flags).map(([name, value]) => (
            <div className="list-item" key={name}>
              <div className="grow">
                <div className="row" style={{ gap: 8, marginBottom: 4 }}>
                  <span className="mono" style={{ fontWeight: 600 }}>
                    {name}
                  </span>
                  <StatusPill
                    status={
                      typeof value === 'boolean' ? String(value) : 'unknown'
                    }
                    label={String(value)}
                  />
                </div>
                <span className="tiny">
                  {FLAG_EXPLANATIONS[name] ??
                    'Backend feature flag — see the API contract for its effect.'}
                </span>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* declared boundary */}
      <section className="panel" aria-label="Declared boundary">
        <div className="panel-head">
          <h3>
            <Scale aria-hidden="true" /> Declared boundary — the honesty contract
          </h3>
        </div>
        <p className="muted" style={{ fontSize: 13, marginBottom: 14 }}>
          Rendered in full, verbatim from the backend. Every guarantee in this
          console is limited to exactly this boundary.
        </p>
        <ol className="list-tight" style={{ paddingLeft: 20 }}>
          {caps.boundary.map((b, i) => (
            <li key={i} style={{ paddingLeft: 6, fontSize: 13.5, lineHeight: 1.6 }}>
              {b}
            </li>
          ))}
        </ol>
      </section>

      {/* retention */}
      <section className="panel" aria-label="Retention note">
        <div className="panel-head">
          <h3>
            <ShieldCheck aria-hidden="true" /> Retention
          </h3>
        </div>
        <p style={{ fontSize: 13.5, lineHeight: 1.7 }}>
          Removed artifacts (chunk text, vectors, invalidated summaries) are not
          restorable from the console — deletion requests keep only metadata,
          lineage and verification evidence, including tombstones that block
          re-publication of the removed content. Audit events and deletion
          reports are retained as the accountability record; they contain no
          document text. Content already disclosed to users (answers they saw,
          copies they made) is outside every system's reach — see the declared
          boundary above.
        </p>
      </section>
    </div>
  );
}

function FragmentRow({ group, value }: { group: string; value: string }) {
  return (
    <>
      <dt>{group}</dt>
      <dd>{value}</dd>
    </>
  );
}
