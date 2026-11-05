/* Auth context: resolves the session once via GET /auth/me, exposes
   login/logout. 401s elsewhere redirect via the api client. */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { api, ApiError } from '../api/client';
import type { User } from '../api/types';

interface AuthApi {
  user: User | null;
  loading: boolean;
  login: (username: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthApi | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const queryClient = useQueryClient();

  useEffect(() => {
    let cancelled = false;
    api
      .get<User>('/auth/me', undefined, true)
      .then((u) => {
        if (!cancelled) setUser(u);
      })
      .catch(() => {
        if (!cancelled) setUser(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(async (username: string, password: string) => {
    try {
      const u = await api.post<User>(
        '/auth/login',
        { username, password },
        { skipAuthRedirect: true },
      );
      setUser(u);
    } catch (err) {
      // Re-throw for the login page to render; normalise non-API errors.
      if (err instanceof ApiError) throw err;
      throw new ApiError(0, {
        code: 'network_error',
        message: 'Cannot reach the TraceVault API.',
      });
    }
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.post<{ ok: boolean }>('/auth/logout', undefined, {
        skipAuthRedirect: true,
      });
    } catch {
      // best-effort — clear locally regardless
    }
    setUser(null);
    queryClient.clear();
  }, [queryClient]);

  const value = useMemo(
    () => ({ user, loading, login, logout }),
    [user, loading, login, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthApi {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>');
  return ctx;
}
