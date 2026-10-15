import { ArrowRight, CircleAlert, LoaderCircle, LockKeyhole, ShieldCheck } from 'lucide-react';
import type { ReactNode } from 'react';
import { createContext, useContext, useEffect, useState } from 'react';
import type { AuthSession, AuthUser } from '../../shared/api/client';
import { ApiError, request, setSessionToken } from '../../shared/api/client';

interface AuthContextValue {
  user: AuthUser;
  mode: 'demo' | 'production';
  oidcEnabled: boolean;
  canManage: boolean;
  canMutate: boolean;
  signOut: () => Promise<void>;
}
const AuthContext = createContext<AuthContextValue | null>(null);
export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error('Authentication context unavailable');
  return context;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [setup, setSetup] = useState(false);
  const [mode, setMode] = useState<'demo' | 'production'>('demo');
  const [oidc, setOidc] = useState(false);
  const [error, setError] = useState(
    new URLSearchParams(window.location.search).has('login_error')
      ? 'Corporate sign-in failed. Contact your administrator to verify your identity mapping.'
      : '',
  );
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    // Resolve mode and session together so a production session never briefly
    // mounts the application with demo defaults.
    Promise.all([
      request<{ setup_required: boolean; mode: 'demo' | 'production'; oidc_enabled: boolean }>(
        '/auth/status',
      ),
      request<AuthSession>('/auth/me').catch((error) => {
        if (error instanceof ApiError && error.status === 401) return null;
        throw error;
      }),
    ])
      .then(([status, session]) => {
        if (!active) return;
        setSetup(status.setup_required);
        setMode(status.mode);
        setOidc(status.oidc_enabled);
        if (session) {
          setUser(session.user);
          setSessionToken(session.csrf_token);
        }
      })
      .catch((error) => {
        if (active) setError(error.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    const expired = () => {
      setUser(null);
      setError('Your session has ended. Sign in again to continue.');
    };
    window.addEventListener('cloudsentinel-session-expired', expired);
    return () => {
      active = false;
      window.removeEventListener('cloudsentinel-session-expired', expired);
    };
  }, []);
  async function login() {
    setBusy(true);
    setError('');
    try {
      const session = await request<AuthSession>('/auth/login', {
        method: 'POST',
        body: JSON.stringify({ username, password }),
      });
      setSessionToken(session.csrf_token);
      setUser(session.user);
      setPassword('');
      setSetup(false);
    } catch (e) {
      setError((e as Error).message);
      setPassword('');
    } finally {
      setBusy(false);
    }
  }
  async function signOut() {
    await request('/auth/logout', { method: 'POST' });
    setSessionToken('');
    setUser(null);
    setError('');
  }
  if (loading)
    return (
      <div className="auth-loading">
        <LoaderCircle className="spinning" size={28} />
        <span>Opening your secure workspace…</span>
      </div>
    );
  if (user)
    return (
      <AuthContext.Provider
        value={{
          user,
          mode,
          oidcEnabled: oidc,
          canManage: user.role === 'admin',
          canMutate: user.role !== 'viewer',
          signOut,
        }}
      >
        {children}
      </AuthContext.Provider>
    );
  return (
    <div className="auth-screen">
      <section className="auth-story">
        <div className="auth-brand">
          <ShieldCheck size={32} />
          <strong>CloudSentinel</strong>
        </div>
        <div>
          <span className="eyebrow">A CLEARER VIEW OF CLOUD SECURITY</span>
          <h1>
            Your security workspace.
            <br />
            Protected from the start.
          </h1>
          <p>
            Review cloud configurations, investigate unusual activity, and keep monitoring in one
            place.
          </p>
          <div className="auth-capabilities">
            <span>
              <ShieldCheck size={17} />
              Explainable findings
            </span>
            <span>
              <LockKeyhole size={17} />
              Role-based access
            </span>
            <span>
              <ShieldCheck size={17} />
              Read-only cloud collection
            </span>
          </div>
        </div>
        <small>
          {mode === 'demo'
            ? 'Demo workspace · Synthetic data'
            : 'Organization workspace · Approved access'}
        </small>
      </section>
      <section className="auth-panel">
        <div className="auth-form">
          <span className="auth-lock">
            <LockKeyhole size={23} />
          </span>
          <span className="eyebrow">CLOUD SECURITY WORKSPACE</span>
          <h2>{setup ? 'Set up your first account' : 'Welcome back.'}</h2>
          <p>
            {setup
              ? 'Create the first administrator from your local terminal, then sign in with your chosen credentials.'
              : 'Sign in to review findings and manage your cloud security.'}
          </p>
          {setup && (
            <div className="setup-instructions">
              <code>
                {mode === 'demo'
                  ? 'make create-admin'
                  : 'Use the administrator bootstrap command in your deployment guide.'}
              </code>
              <small>
                The command prompts for your credentials locally. No default password is provided.
              </small>
            </div>
          )}
          {error && (
            <div className="auth-error" role="alert">
              <CircleAlert size={17} />
              <span>{error}</span>
            </div>
          )}
          {oidc && !setup && (
            <a className="button primary sso-button" href="/api/v1/auth/oidc/start">
              <LockKeyhole size={17} />
              Continue with corporate sign-in
            </a>
          )}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void login();
            }}
          >
            <label>
              Username
              <input
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                autoCapitalize="none"
                maxLength={80}
                required
                disabled={busy}
                placeholder="Your username"
              />
            </label>
            <label>
              Password
              <input
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                type="password"
                autoComplete="current-password"
                maxLength={256}
                required
                disabled={busy}
                placeholder="Your password"
              />
            </label>
            <button className="button primary" disabled={busy}>
              {busy ? <LoaderCircle className="spinning" size={17} /> : <ArrowRight size={17} />}
              {busy ? 'Signing in…' : 'Sign in to workspace'}
            </button>
          </form>
          <p className="auth-footnote">
            Credentials and cloud tokens stay under your control. Contact your administrator if you
            need access.
          </p>
        </div>
      </section>
    </div>
  );
}
