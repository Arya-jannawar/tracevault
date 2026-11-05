/* App shell: providers + routing. Queries default to retry:false so an API
   outage renders honest error states instead of hanging spinners. */
import { useMemo, type ReactNode } from 'react';
import {
  BrowserRouter,
  Navigate,
  Route,
  Routes,
} from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ToastProvider } from './hooks/ToastProvider';
import { AuthProvider, useAuth } from './hooks/AuthProvider';
import { TopbarActionProvider } from './hooks/useTopbarAction';
import { Layout } from './components/Layout';
import { EmptyState } from './components/EmptyState';
import { Login } from './pages/Login';
import { Overview } from './pages/Overview';
import { Documents } from './pages/Documents';
import { DocumentDetail } from './pages/DocumentDetail';
import { Playground } from './pages/Playground';
import { ProvenanceExplorer } from './pages/ProvenanceExplorer';
import { DeletionCenter } from './pages/DeletionCenter';
import { DeletionDetail } from './pages/DeletionDetail';
import { RepairLab } from './pages/RepairLab';
import { Audit } from './pages/Audit';
import { EvaluationLab } from './pages/EvaluationLab';
import { Settings } from './pages/Settings';

function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) {
    return (
      <div className="full-center">
        <div className="row" style={{ gap: 12, color: 'var(--text-2)' }}>
          <span className="spinner" aria-hidden="true" />
          <span>Restoring your session…</span>
        </div>
      </div>
    );
  }
  if (!user) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

function NotFound() {
  return (
    <EmptyState
      tone="info"
      title="This page does not exist"
      actions={
        <a className="btn btn-primary" href="/">
          Back to Overview
        </a>
      }
    >
      The route you followed isn't part of the TraceVault console.
    </EmptyState>
  );
}

export default function App() {
  const queryClient = useMemo(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            retry: false,
            refetchOnWindowFocus: false,
            staleTime: 15_000,
          },
          mutations: { retry: false },
        },
      }),
    [],
  );

  return (
    <QueryClientProvider client={queryClient}>
      <ToastProvider>
        <BrowserRouter>
          <AuthProvider>
            <TopbarActionProvider>
              <Routes>
                <Route path="/login" element={<Login />} />
                <Route
                  element={
                    <RequireAuth>
                      <Layout />
                    </RequireAuth>
                  }
                >
                  <Route index element={<Overview />} />
                  <Route path="/documents" element={<Documents />} />
                  <Route path="/documents/:id" element={<DocumentDetail />} />
                  <Route path="/playground" element={<Playground />} />
                  <Route path="/provenance" element={<ProvenanceExplorer />} />
                  <Route path="/deletions" element={<DeletionCenter />} />
                  <Route path="/deletions/:id" element={<DeletionDetail />} />
                  <Route path="/repair" element={<RepairLab />} />
                  <Route path="/audit" element={<Audit />} />
                  <Route path="/evaluation" element={<EvaluationLab />} />
                  <Route path="/settings" element={<Settings />} />
                  <Route path="*" element={<NotFound />} />
                </Route>
              </Routes>
            </TopbarActionProvider>
          </AuthProvider>
        </BrowserRouter>
      </ToastProvider>
    </QueryClientProvider>
  );
}
