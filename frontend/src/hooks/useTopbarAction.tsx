/* Contextual primary action in the top bar: pages register an action and it
   renders in the Topbar; registering nothing shows the default. */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';

export interface TopbarAction {
  label: string;
  onClick: () => void;
}

export interface TopbarActionApi {
  action: TopbarAction | null;
  register: (action: TopbarAction | null) => void;
}

const TopbarActionContext = createContext<TopbarActionApi | null>(null);
export { TopbarActionContext };

export function TopbarActionProvider({ children }: { children: ReactNode }) {
  const [action, setAction] = useState<TopbarAction | null>(null);
  const register = useCallback((a: TopbarAction | null) => setAction(a), []);
  const value = useMemo(() => ({ action, register }), [action, register]);
  return (
    <TopbarActionContext.Provider value={value}>
      {children}
    </TopbarActionContext.Provider>
  );
}

/** Pages call this to place their primary action in the top bar. */
export function useTopbarAction(action: TopbarAction | null): void {
  const ctx = useContext(TopbarActionContext);
  const register = ctx?.register;
  useEffect(() => {
    register?.(action);
    return () => register?.(null);
  }, [register, action]);
}

/** The top bar reads the currently registered action. */
export function useTopbarActionValue(): TopbarAction | null {
  const ctx = useContext(TopbarActionContext);
  return ctx?.action ?? null;
}
