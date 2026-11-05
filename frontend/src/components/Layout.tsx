/* App shell: fixed sidebar + top bar + routed content. Sidebar collapses into
   an overlay drawer below 820px. */
import { useEffect, useState } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { Topbar } from './Topbar';

export function Layout() {
  const [navOpen, setNavOpen] = useState(false);
  const location = useLocation();

  // close the mobile drawer whenever the route changes
  useEffect(() => {
    setNavOpen(false);
  }, [location.pathname]);

  return (
    <div className={`app-shell ${navOpen ? 'mobile-nav-open' : ''}`}>
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <Sidebar onNavigate={() => setNavOpen(false)} />
      {navOpen && (
        <button
          type="button"
          className="sidebar-backdrop"
          aria-label="Close navigation menu"
          onClick={() => setNavOpen(false)}
        />
      )}
      <div className="main-col">
        <Topbar onToggleSidebar={() => setNavOpen((v) => !v)} />
        <main className="content" id="main-content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
