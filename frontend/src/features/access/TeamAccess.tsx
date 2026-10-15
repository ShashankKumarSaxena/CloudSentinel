import { CircleAlert, Plus, RefreshCw, ShieldCheck } from 'lucide-react';
import { useEffect, useState } from 'react';
import type { AuditRecord, AuthUser } from '../../shared/api/client';
import { request } from '../../shared/api/client';
import { dateTime } from '../../shared/ui/components';
import { useAuth } from '../auth/AuthProvider';

function ErrorNotice({ message }: { message: string }) {
  return message ? (
    <div className="error-banner" role="alert">
      <CircleAlert size={18} />
      <p>{message}</p>
    </div>
  ) : null;
}

export function TeamAccess() {
  const { user, canManage, signOut, oidcEnabled } = useAuth();
  const [users, setUsers] = useState<AuthUser[]>([]);
  const [audit, setAudit] = useState<AuditRecord[]>([]);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [username, setUsername] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [password, setPassword] = useState('');
  const [subject, setSubject] = useState('');
  const [role, setRole] = useState<AuthUser['role']>('viewer');
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  async function load() {
    if (!canManage) return;
    try {
      const [a, b] = await Promise.all([
        request<AuthUser[]>('/users'),
        request<AuditRecord[]>('/audit'),
      ]);
      setUsers(a);
      setAudit(b);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  useEffect(() => {
    void load();
  }, [canManage]);
  async function createUser() {
    setBusy(true);
    setError('');
    try {
      await request('/users', {
        method: 'POST',
        body: JSON.stringify({
          username,
          display_name: displayName,
          password: subject ? null : password,
          oidc_subject: subject || null,
          role,
        }),
      });
      setUsername('');
      setDisplayName('');
      setPassword('');
      setSubject('');
      await load();
    } catch (e) {
      setError((e as Error).message);
      setPassword('');
    } finally {
      setBusy(false);
    }
  }
  async function updateUser(target: AuthUser, changes: object) {
    setBusy(true);
    setError('');
    try {
      await request(`/users/${target.id}`, { method: 'PATCH', body: JSON.stringify(changes) });
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function changePassword() {
    setBusy(true);
    setError('');
    try {
      await request('/auth/password', {
        method: 'POST',
        body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }),
      });
      window.dispatchEvent(new Event('cloudsentinel-session-expired'));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setCurrentPassword('');
      setNewPassword('');
      setBusy(false);
    }
  }
  return (
    <>
      <ErrorNotice message={error} />
      <div className="ml-notice">
        <ShieldCheck size={20} />
        <div>
          <strong>
            {user.display_name} · {user.role}
          </strong>
          <p>
            Administrators manage accounts, models, and schedules. Analysts scan and triage. Viewers
            inspect the shared workspace. Roles are enforced by the API.
          </p>
        </div>
      </div>
      {canManage && (
        <>
          <section className="panel collection-form settings-form">
            <h2>Create a workspace account</h2>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                void createUser();
              }}
            >
              <label>
                Username
                <input
                  required
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  minLength={3}
                  maxLength={60}
                  pattern="[a-zA-Z0-9_.-]+"
                  autoComplete="off"
                />
              </label>
              <label>
                Display name
                <input
                  required
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  maxLength={80}
                />
              </label>
              {oidcEnabled && (
                <label>
                  Corporate subject (optional)
                  <input
                    value={subject}
                    onChange={(event) => {
                      setSubject(event.target.value);
                      setPassword('');
                    }}
                    maxLength={255}
                    placeholder="Exact subject from the configured identity provider"
                  />
                </label>
              )}
              {!subject && (
                <label>
                  Initial password
                  <input
                    required
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    minLength={12}
                    maxLength={256}
                    autoComplete="new-password"
                  />
                </label>
              )}
              <label>
                Role
                <select value={role} onChange={(e) => setRole(e.target.value as AuthUser['role'])}>
                  <option value="viewer">Viewer</option>
                  <option value="analyst">Analyst</option>
                  <option value="admin">Administrator</option>
                </select>
              </label>
              <button className="button primary" disabled={busy}>
                <Plus size={15} />
                Create account
              </button>
            </form>
          </section>
          <section className="panel">
            <div className="panel-heading">
              <h2>Workspace accounts</h2>
              <span className="subtle-tag">{users.length} accounts</span>
            </div>
            <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Account</th>
                    <th>Role</th>
                    <th>Sign-in</th>
                    <th>Status</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((u) => (
                    <tr key={u.id}>
                      <td>
                        <span className="resource-cell">
                          {u.display_name}
                          <small>{u.username}</small>
                        </span>
                      </td>
                      <td>
                        {u.id === user.id ? (
                          <span className="capitalize">{u.role}</span>
                        ) : (
                          <select
                            className="table-select"
                            value={u.role}
                            disabled={busy}
                            aria-label={`Role for ${u.username}`}
                            onChange={(e) => void updateUser(u, { role: e.target.value })}
                          >
                            <option value="viewer">Viewer</option>
                            <option value="analyst">Analyst</option>
                            <option value="admin">Administrator</option>
                          </select>
                        )}
                      </td>
                      <td>{u.sso_only ? 'Corporate identity' : 'Local password'}</td>
                      <td>{u.enabled ? 'Enabled' : 'Disabled'}</td>
                      <td>
                        {u.id !== user.id ? (
                          <button
                            className="button secondary small"
                            disabled={busy}
                            onClick={() => void updateUser(u, { enabled: !u.enabled })}
                          >
                            {u.enabled ? 'Disable access' : 'Enable access'}
                          </button>
                        ) : (
                          <span className="subtle-tag">Your account</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
      {user.sso_only ? (
        <section className="panel collection-form settings-form">
          <h2>Corporate access</h2>
          <p>
            Your password and multifactor authentication are managed by your identity provider.
            Workspace roles remain controlled by your administrator.
          </p>
        </section>
      ) : (
        <section className="panel collection-form settings-form">
          <h2>Change your password</h2>
          <p>A password change signs out all sessions for your account.</p>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              void changePassword();
            }}
          >
            <label>
              Current password
              <input
                required
                type="password"
                value={currentPassword}
                onChange={(e) => setCurrentPassword(e.target.value)}
                autoComplete="current-password"
                maxLength={256}
              />
            </label>
            <label>
              New password
              <input
                required
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                autoComplete="new-password"
                minLength={12}
                maxLength={256}
              />
            </label>
            <button className="button primary" disabled={busy}>
              Update password
            </button>
            <button
              className="button secondary"
              type="button"
              onClick={() => void signOut().catch((e) => setError(e.message))}
            >
              Sign out
            </button>
          </form>
        </section>
      )}
      {canManage && (
        <section className="panel feature-panel">
          <div className="panel-heading">
            <div>
              <h2>Operational audit log</h2>
              <p>Latest 200 access and workspace actions</p>
            </div>
            <button className="text-button" onClick={() => void load()}>
              Refresh <RefreshCw size={13} />
            </button>
          </div>
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Action</th>
                  <th>Actor</th>
                  <th>Target</th>
                  <th>Recorded</th>
                </tr>
              </thead>
              <tbody>
                {audit.map((a) => (
                  <tr key={a.id}>
                    <td>{a.action}</td>
                    <td>{a.actor}</td>
                    <td>{a.target ? a.target.slice(0, 16) : '—'}</td>
                    <td>{dateTime(a.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </>
  );
}
