/* Route-level error boundary: an unexpected render crash shows a recoverable
   state instead of a blank page. */
import { Component, type ErrorInfo, type ReactNode } from 'react';
import { ErrorState } from './ErrorState';

interface Props {
  children: ReactNode;
}
interface State {
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Surfaced in the UI; no silent swallow.
    console.error('TraceVault UI crashed:', error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="full-center">
          <div style={{ width: 'min(560px, 100%)' }}>
            <ErrorState
              error={this.state.error}
              title="This view crashed"
              hint="Reload the page or go back. If it persists, check the browser console and backend logs."
            />
            <div className="row" style={{ justifyContent: 'center', marginTop: 14 }}>
              <button
                type="button"
                className="btn"
                onClick={() => window.location.reload()}
              >
                Reload TraceVault
              </button>
            </div>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
