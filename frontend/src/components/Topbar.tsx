/* Compact top bar: breadcrumb, workspace label, live health, contextual
   primary action, user chip with logout. */
import { useContext } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { ChevronRight, LogOut, Menu } from 'lucide-react';
import { HealthDot } from './HealthDot';
import { useAuth } from '../hooks/AuthProvider';
import { TopbarActionContext } from '../hooks/useTopbarAction';
import type { TopbarActionApi } from '../hooks/useTopbarAction';
import { shortId } from '../lib/format';

interface Crumb {
  label: string;
  to?: string;
}

const ROUTE_LABELS: Record<string, string> = {
  '/': 'Overview',
  '/documents': 'Documents',
  '/playground': 'RAG Playground',
  '/provenance': 'Provenance Explorer',
  '/deletions': 'Deletion Center',
  '/repair': 'Repair Lab',
  '/audit': 'Verification & Audit',
  '/evaluation': 'Evaluation Lab',
  '/settings': 'Settings & About',
};

function crumbsFor(pathname: string): Crumb[] {
  const parts = pathname.split('/').filter(Boolean);
  if (parts.length === 0) return [{ label: 'Overview' }];
  const crumbs: Crumb[] = [];
  parts.forEach((part, i) => {
    const acc = `/${parts.slice(0, i + 1).join('/')}`;
    const known = ROUTE_LABELS[acc];
    if (known) {
      crumbs.push({ label: known, to: i === parts.length - 1 ? undefined : acc });
    } else if (i === 0) {
      crumbs.push({ label: part });
    } else {
      const parent = ROUTE_LABELS[`/${parts[0]}`];
      if (parent && i === 1) {
        crumbs.push({ label: parent, to: `/${parts[0]}` });
      }
      crumbs.push({ label: shortId(part, 10) });
    }
  });
  return crumbs;
}

export function Topbar({ onToggleSidebar }: { onToggleSidebar: () => void }) {
  const { pathname } = useLocation();
  const { user, logout } = useAuth();
  const crumbs = crumbsFor(pathname);
  const ctx = useContext(TopbarActionContext);
  const action = ctx?.action ?? null;

  return (
    <header className="topbar">
      <button
        type="button"
        className="icon-btn"
        onClick={onToggleSidebar}
        aria-label="Open navigation menu"
      >
        <Menu aria-hidden="true" />
      </button>

      <nav className="topbar-crumbs" aria-label="Breadcrumb">
        {crumbs.map((c, i) => (
          <span key={`${c.label}-${i}`} className="row" style={{ gap: 7 }}>
            {i > 0 && (
              <ChevronRight
                aria-hidden="true"
                size={13}
                style={{ color: 'var(--text-3)', flex: 'none' }}
              />
            )}
            {c.to ? (
              <Link to={c.to} className={i === 0 && crumbs.length > 1 ? 'crumb-parent' : ''}>
                {c.label}
              </Link>
            ) : (
              <span
                className={`${
                  i === crumbs.length - 1 ? 'crumb-current' : ''
                } ${i === 0 && crumbs.length > 1 ? 'crumb-parent' : ''}`}
              >
                {c.label}
              </span>
            )}
          </span>
        ))}
      </nav>

      <span className="topbar-workspace">
        <span
          aria-hidden="true"
          style={{
            width: 7,
            height: 7,
            borderRadius: '50%',
            background: 'var(--info)',
          }}
        />
        Workspace · default
      </span>

      <div className="topbar-spacer" />

      <HealthDot />

      {action && (
        <button type="button" className="btn btn-primary" onClick={action.onClick}>
          {action.label}
        </button>
      )}

      {user && (
        <div className="user-chip">
          <span className="avatar" aria-hidden="true">
            {user.username.slice(0, 2)}
          </span>
          <span className="user-name">{user.username}</span>
          <span className="role-tag">{user.role}</span>
          <button type="button" onClick={() => void logout()} aria-label="Sign out">
            <LogOut size={13} aria-hidden="true" style={{ display: 'inline' }} />
          </button>
        </div>
      )}
    </header>
  );
}
