/* Service health: GET /health/ready polled every 15s.
   checks values are booleans (or strings); anything falsy/degraded is a failing connector. */
import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import type { HealthOut } from '../api/types';

export type HealthState = {
  status: 'ok' | 'degraded' | 'down' | 'loading';
  failing: string[];
  healthy: string[];
};

export function useHealth(): HealthState {
  const query = useQuery<HealthOut>({
    queryKey: ['health', 'ready'],
    queryFn: () => api.get<HealthOut>('/health/ready'),
    refetchInterval: 15_000,
    refetchOnWindowFocus: false,
    retry: false,
    staleTime: 10_000,
  });

  const data = query.data;
  if (query.isLoading) return { status: 'loading', failing: [], healthy: [] };
  if (query.isError || !data) return { status: 'down', failing: [], healthy: [] };

  const failing: string[] = [];
  const healthy: string[] = [];
  for (const [name, value] of Object.entries(data.checks ?? {})) {
    const ok = value === true || value === 'ok' || value === 'healthy';
    (ok ? healthy : failing).push(name);
  }
  return {
    status: data.status === 'ok' && failing.length === 0 ? 'ok' : 'degraded',
    failing,
    healthy,
  };
}
