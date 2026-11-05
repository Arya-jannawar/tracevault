/* Fixed desktop sidebar with the TV brand mark and grouped navigation.
   Collapses into an overlay drawer on mobile (state owned by Layout). */
import { NavLink } from 'react-router-dom';
import {
  BarChart3,
  FileText,
  LayoutDashboard,
  ListChecks,
  MessageSquareText,
  Network,
  Settings,
  ShieldAlert,
  Wrench,
} from 'lucide-react';
import type { ReactNode } from 'react';

interface NavEntry {
  to: string;
  label: string;
  icon: ReactNode;
}

const SECTIONS: { heading?: string; items: NavEntry[] }[] = [
  {
    heading: 'Workspace',
    items: [
      { to: '/', label: 'Overview', icon: <LayoutDashboard /> },
      { to: '/documents', label: 'Documents', icon: <FileText /> },
      { to: '/playground', label: 'RAG Playground', icon: <MessageSquareText /> },
    ],
  },
  {
    heading: 'Lineage',
    items: [{ to: '/provenance', label: 'Provenance Explorer', icon: <Network /> }],
  },
  {
    heading: 'Lifecycle',
    items: [
      { to: '/deletions', label: 'Deletion Center', icon: <ShieldAlert /> },
      { to: '/repair', label: 'Repair Lab', icon: <Wrench /> },
    ],
  },
  {
    heading: 'Evidence',
    items: [
      { to: '/audit', label: 'Verification & Audit', icon: <ListChecks /> },
      { to: '/evaluation', label: 'Evaluation Lab', icon: <BarChart3 /> },
      { to: '/settings', label: 'Settings & About', icon: <Settings /> },
    ],
  },
];

export function Sidebar({
  onNavigate,
}: {
  onNavigate?: () => void;
}) {
  return (
    <aside className="sidebar" aria-label="Primary navigation">
      <div className="sidebar-brand">
        <span className="brand-mark" aria-hidden="true">
          TV
        </span>
        <div>
          <div className="brand-name">TraceVault</div>
          <div className="brand-sub">Research console</div>
        </div>
      </div>

      <nav className="sidebar-nav">
        {SECTIONS.map((section) => (
          <div key={section.heading ?? 'main'}>
            {section.heading && (
              <div className="nav-section" aria-hidden="true">
                {section.heading}
              </div>
            )}
            {section.items.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === '/'}
                className={({ isActive }) =>
                  `nav-item ${isActive ? 'active' : ''}`
                }
                onClick={onNavigate}
              >
                {item.icon}
                {item.label}
              </NavLink>
            ))}
          </div>
        ))}
      </nav>

      <div className="sidebar-foot">
        Provenance-aware deletion for privacy-preserving RAG.
        <br />
        <strong style={{ color: 'var(--text-2)' }}>Research prototype</strong> — not a
        compliance product.
      </div>
    </aside>
  );
}
