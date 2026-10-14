import { createContext, useContext, useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { ArrowRight, CircleAlert, LoaderCircle, LockKeyhole, ShieldCheck } from 'lucide-react';
import { request, setSessionToken } from './api';
import type { AuthSession, AuthUser } from './api';

interface AuthContextValue { user: AuthUser; canManage: boolean; canMutate: boolean; signOut: () => Promise<void> }
const AuthContext = createContext<AuthContextValue | null>(null);
export function useAuth() { const context = useContext(AuthContext); if (!context) throw new Error('Authentication context unavailable'); return context; }

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [setup, setSetup] = useState(false);
  const [error, setError] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    request<{ setup_required: boolean }>('/auth/status').then(status => { if (active) setSetup(status.setup_required); }).catch(e => { if (active) setError(e.message); });
    request<AuthSession>('/auth/me').then(session => { if (active) { setUser(session.user); setSessionToken(session.csrf_token); } }).catch(() => {}).finally(() => { if (active) setLoading(false); });
    const expired = () => { setUser(null); setError('Your session has ended. Sign in again to continue.'); };
    window.addEventListener('cloudsentinel-session-expired', expired);
    return () => { active = false; window.removeEventListener('cloudsentinel-session-expired', expired); };
  }, []);
  async function login() {
    setBusy(true); setError('');
    try {
      const session = await request<AuthSession>('/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) });
      setSessionToken(session.csrf_token); setUser(session.user); setPassword(''); setSetup(false);
    } catch (e) { setError((e as Error).message); setPassword(''); }
    finally { setBusy(false); }
  }
  async function signOut() {
    await request('/auth/logout', { method: 'POST' });
    setSessionToken(''); setUser(null); setError('');
  }
  if (loading) return <div className="auth-loading"><LoaderCircle className="spinning" size={28} /><span>Opening your secure workspace…</span></div>;
  if (user) return <AuthContext.Provider value={{ user, canManage: user.role === 'admin', canMutate: user.role !== 'viewer', signOut }}>{children}</AuthContext.Provider>;
  return <div className="auth-screen"><section className="auth-story"><div className="auth-brand"><ShieldCheck size={32} /><strong>CloudSentinel</strong></div><div><span className="eyebrow">A CLEARER VIEW OF CLOUD SECURITY</span><h1>Your security workspace.<br />Protected from the start.</h1><p>Review cloud configurations, investigate unusual activity, and keep monitoring in one place.</p><div className="auth-capabilities"><span><ShieldCheck size={17} />Explainable findings</span><span><LockKeyhole size={17} />Role-based access</span><span><ShieldCheck size={17} />Read-only cloud collection</span></div></div><small>Phase 3 · Monitoring and access controls</small></section><section className="auth-panel"><div className="auth-form"><span className="auth-lock"><LockKeyhole size={23} /></span><span className="eyebrow">CLOUD SECURITY WORKSPACE</span><h2>{setup ? 'Set up your first account' : 'Welcome back.'}</h2><p>{setup ? 'Create the first administrator from your local terminal, then sign in with your chosen credentials.' : 'Sign in to review findings and manage your cloud security.'}</p>{setup && <div className="setup-instructions"><code>make create-admin</code><small>The command prompts for your credentials locally. No default password is provided.</small></div>}{error && <div className="auth-error" role="alert"><CircleAlert size={17} /><span>{error}</span></div>}<form onSubmit={e => { e.preventDefault(); void login(); }}><label>Username<input value={username} onChange={e => setUsername(e.target.value)} autoComplete="username" autoCapitalize="none" maxLength={80} required disabled={busy} placeholder="Your username" /></label><label>Password<input value={password} onChange={e => setPassword(e.target.value)} type="password" autoComplete="current-password" maxLength={256} required disabled={busy} placeholder="Your password" /></label><button className="button primary" disabled={busy}>{busy ? <LoaderCircle className="spinning" size={17} /> : <ArrowRight size={17} />}{busy ? 'Signing in…' : 'Sign in to workspace'}</button></form><p className="auth-footnote">Credentials and cloud tokens stay under your control. Contact your administrator if you need access.</p></div></section></div>;
}
