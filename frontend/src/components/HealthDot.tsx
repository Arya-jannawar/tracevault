/* Live service health indicator in the top bar: polls /health/ready every 15s.
   green ok / amber degraded (naming the failing connector) / coral unreachable. */
import { useState } from 'react';
import { useHealth } from '../hooks/useHealth';
import { humanize } from '../lib/format';

const LABEL = {
  ok: 'Operational',
  degraded: 'Degraded',
  down: 'API unreachable',
  loading: 'Checking…',
} as const;

export function HealthDot() {
  const health = useHealth();
  const [open, setOpen] = useState(false);

  return (
    <div
      className={`health ${health.status}`}
      tabIndex={0}
      role="img"
      aria-label={`Service health: ${LABEL[health.status]}${
        health.failing.length
          ? ` — failing: ${health.failing.join(', ')}`
          : ''
      }`}
      onMouseEnter={() => setOpen(true)}
      onMouseLeave={() => setOpen(false)}
      onFocus={() => setOpen(true)}
      onBlur={() => setOpen(false)}
    >
      <span className="hdot" aria-hidden="true" />
      <span>{LABEL[health.status]}</span>
      {open && (
        <div className="health-pop">
          <div className="tiny" style={{ marginBottom: 6 }}>
            GET /api/v1/health/ready · every 15s
          </div>
          {health.status === 'down' ? (
            <div className="hrow">
              <span>API</span>
              <span className="chip chip-danger">unreachable</span>
            </div>
          ) : (
            <>
              {[...health.healthy, ...health.failing].map((name) => {
                const bad = health.failing.includes(name);
                return (
                  <div className="hrow" key={name}>
                    <span>{humanize(name)}</span>
                    <span className={`chip ${bad ? 'chip-danger' : 'chip-accent'}`}>
                      {bad ? 'degraded' : 'ok'}
                    </span>
                  </div>
                );
              })}
            </>
          )}
          {health.status === 'degraded' && health.failing.length > 0 && (
            <div className="tiny" style={{ marginTop: 6 }}>
              {humanize(health.failing[0])} connector failing — deletions and
              retrieval may be blocked.
            </div>
          )}
        </div>
      )}
    </div>
  );
}
