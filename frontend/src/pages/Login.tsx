/* Login — bold branded split layout. Demo credentials come from
   `python -m app.bootstrap` output (backend/.local/credentials.txt). */
import { useState, type FormEvent } from 'react';
import { Navigate, useNavigate, useSearchParams } from 'react-router-dom';
import { Eye, EyeOff, GitBranch, Loader2, ShieldCheck, Sparkles } from 'lucide-react';
import { useAuth } from '../hooks/AuthProvider';
import { ApiError } from '../api/client';

export function Login() {
  const { user, loading, login } = useAuth();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPw, setShowPw] = useState(false);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const next = params.get('next') || '/';
  const safeNext = next.startsWith('/') && !next.startsWith('/login') ? next : '/';

  if (!loading && user) {
    return <Navigate to={safeNext} replace />;
  }

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setPending(true);
    try {
      await login(username.trim(), password);
      navigate(safeNext, { replace: true });
    } catch (err) {
      if (err instanceof ApiError) {
        setError(
          err.status === 401
            ? 'Invalid username or password.'
            : err.message,
        );
      } else {
        setError('Sign-in failed unexpectedly.');
      }
    } finally {
      setPending(false);
    }
  };

  return (
    <div className="login-shell">
      <div className="login-brand">
        <div>
          <div className="sidebar-brand" style={{ padding: 0 }}>
            <span className="brand-mark" aria-hidden="true">
              TV
            </span>
            <div>
              <div className="brand-name">TraceVault</div>
              <div className="brand-sub">Research console</div>
            </div>
          </div>
          <h1>Control what your AI remembers.</h1>
          <p className="lede">
            TraceVault governs the stored artifacts of retrieval-augmented
            generation — documents, chunks, vectors, summaries, answers and
            cache entries — with a provenance graph, a deletion fence, and
            recorded verification. It does not touch model weights.
          </p>
          <div className="brand-points">
            <div className="brand-point">
              <GitBranch aria-hidden="true" />
              <span>
                Every chunk, summary, answer and cache entry is traced back to
                the document version that produced it.
              </span>
            </div>
            <div className="brand-point">
              <ShieldCheck aria-hidden="true" />
              <span>
                Deletion runs as a fenced, five-step protocol with per-connector
                acknowledgement and verification checks.
              </span>
            </div>
            <div className="brand-point">
              <Sparkles aria-hidden="true" />
              <span>
                Honest boundaries: guarantees cover registered components only,
                and the system says so on every screen.
              </span>
            </div>
          </div>
        </div>
        <div className="tiny">
          Provenance-aware deletion and selective summary repair for
          privacy-preserving RAG systems · research prototype
        </div>
      </div>

      <div className="login-panel">
        <div className="login-card">
          <h2>Sign in</h2>
          <p className="muted" style={{ marginBottom: 22, fontSize: 13.5 }}>
            Use the operator or viewer account created at bootstrap.
          </p>

          <form onSubmit={onSubmit} noValidate>
            <div className="field">
              <label htmlFor="login-username">Username</label>
              <input
                id="login-username"
                className="input"
                autoComplete="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                disabled={pending}
                required
              />
            </div>
            <div className="field">
              <label htmlFor="login-password">Password</label>
              <div className="row" style={{ gap: 8 }}>
                <input
                  id="login-password"
                  className="input"
                  type={showPw ? 'text' : 'password'}
                  autoComplete="current-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  disabled={pending}
                  required
                  style={{ flex: 1 }}
                />
                <button
                  type="button"
                  className="btn"
                  style={{ minWidth: 44, padding: 0 }}
                  onClick={() => setShowPw((v) => !v)}
                  aria-label={showPw ? 'Hide password' : 'Show password'}
                >
                  {showPw ? <EyeOff aria-hidden="true" /> : <Eye aria-hidden="true" />}
                </button>
              </div>
            </div>

            {error && (
              <div className="field-error" role="alert" style={{ marginBottom: 14 }}>
                <span>{error}</span>
              </div>
            )}

            <button
              type="submit"
              className="btn btn-primary btn-lg"
              style={{ width: '100%' }}
              disabled={pending || !username || !password}
            >
              {pending ? (
                <>
                  <Loader2 className="spinner" aria-hidden="true" /> Signing in…
                </>
              ) : (
                'Sign in'
              )}
            </button>
          </form>

          <div className="demo-hint">
            <strong>Demo credentials:</strong> printed by{' '}
            <code>python -m app.bootstrap</code> and saved to{' '}
            <code>backend/.local/credentials.txt</code>. Sessions are HttpOnly
            cookies; every mutation additionally requires a CSRF header that
            this console sends for you.
          </div>
        </div>
      </div>
    </div>
  );
}
