import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Activity,
  AlertTriangle,
  Clock3,
  House,
  KeyRound,
  LockKeyhole,
  Map as MapIcon,
  Plus,
  Power,
  RefreshCw,
  RotateCcw,
  ScrollText,
  ShieldCheck,
  X,
} from "lucide-react";
import {
  ApiError,
  fetchSnapshot,
  issueGrant,
  rearmInterlock,
  revokeGrant,
  tripInterlock,
} from "./api";
import { Blueprint } from "./components/Blueprint";
import type { GrantIssuePayload, OwnerSnapshot, PublicGrant } from "./types";

type Tab = "blueprint" | "grants" | "ledger";
type Phase = "locked" | "loading" | "ready" | "error";

export const MINIMUM_LOADING_VISIBLE_MS = 700;

const SCOPE_OPTIONS = [
  ["read:layout", "Layout"],
  ["read:systems", "Systems"],
  ["read:inventory", "Inventory"],
  ["command:navigate", "Navigate"],
  ["command:manipulate", "Manipulate"],
] as const;

const EMPTY_GRANT: GrantIssuePayload = {
  name: "",
  kind: "agent",
  scopes: ["read:layout"],
  zones: [],
  window: "standing",
  expires: "revocable",
};

function messageFor(error: unknown): string {
  return error instanceof ApiError
    ? error.message
    : "The owner console could not complete the request.";
}

function waitForLoadingVisibility(signal: AbortSignal): Promise<void> {
  if (signal.aborted) return Promise.resolve();

  return new Promise((resolve) => {
    let timeout = 0;
    const finish = () => {
      window.clearTimeout(timeout);
      signal.removeEventListener("abort", finish);
      resolve();
    };
    timeout = window.setTimeout(finish, MINIMUM_LOADING_VISIBLE_MS);
    signal.addEventListener("abort", finish, { once: true });
  });
}

function StatusChip({ value }: { value: string }) {
  const tone = value === "TRIPPED" ? "danger" : value === "ARMED" ? "good" : "neutral";
  return <span className={`status-chip ${tone}`}>{value}</span>;
}

function GrantCard({
  grant,
  busy,
  onRevoke,
}: {
  grant: PublicGrant;
  busy: boolean;
  onRevoke: (grant: PublicGrant) => void;
}) {
  return (
    <article className="grant-card">
      <div className="grant-card-heading">
        <div>
          <p className="eyebrow">{grant.kind}</p>
          <h3>{grant.name}</h3>
          <p className="mono subtle">{grant.id}</p>
        </div>
        <StatusChip value={grant.status.toUpperCase()} />
      </div>
      <dl className="grant-meta">
        <div><dt>Window</dt><dd>{grant.window}</dd></div>
        <div><dt>Expires</dt><dd>{grant.expires}</dd></div>
        <div><dt>Zones</dt><dd>{grant.zones.join(", ") || "None"}</dd></div>
      </dl>
      <div className="chip-row" aria-label={`${grant.name} scopes`}>
        {grant.scopes.map((scope) => <span className="scope-chip" key={scope}>{scope}</span>)}
      </div>
      <button
        className="button danger-button"
        type="button"
        disabled={busy || grant.status !== "active"}
        onClick={() => onRevoke(grant)}
      >
        Revoke grant
      </button>
    </article>
  );
}

export function App() {
  const [tokenDraft, setTokenDraft] = useState("");
  const [ownerToken, setOwnerToken] = useState("");
  const [snapshot, setSnapshot] = useState<OwnerSnapshot | null>(null);
  const [phase, setPhase] = useState<Phase>("locked");
  const [error, setError] = useState("");
  const [tab, setTab] = useState<Tab>("blueprint");
  const [actionBusy, setActionBusy] = useState(false);
  const [issueOpen, setIssueOpen] = useState(false);
  const [newGrantToken, setNewGrantToken] = useState("");
  const [grantDraft, setGrantDraft] = useState<GrantIssuePayload>(EMPTY_GRANT);
  const requestGeneration = useRef(0);
  const activeController = useRef<AbortController | null>(null);

  const beginRequest = useCallback(() => {
    activeController.current?.abort();
    const controller = new AbortController();
    const generation = requestGeneration.current + 1;
    requestGeneration.current = generation;
    activeController.current = controller;
    return { controller, generation };
  }, []);

  const requestIsCurrent = useCallback(
    (generation: number) => requestGeneration.current === generation,
    [],
  );

  useEffect(() => () => {
    requestGeneration.current += 1;
    activeController.current?.abort();
    activeController.current = null;
  }, []);

  const load = useCallback(async (token: string): Promise<boolean> => {
    const { controller, generation } = beginRequest();
    setError("");
    setSnapshot(null);
    setPhase("loading");
    const loadingVisible = waitForLoadingVisibility(controller.signal);
    try {
      const next = await fetchSnapshot(token, controller.signal);
      await loadingVisible;
      if (!requestIsCurrent(generation)) return false;
      setSnapshot(next);
      setPhase("ready");
      return true;
    } catch (loadError) {
      await loadingVisible;
      if (!requestIsCurrent(generation)) return false;
      setSnapshot(null);
      setError(messageFor(loadError));
      setPhase("error");
      return false;
    } finally {
      if (activeController.current === controller) activeController.current = null;
    }
  }, [beginRequest, requestIsCurrent]);

  const connect = async (event: FormEvent) => {
    event.preventDefault();
    const token = tokenDraft;
    setTokenDraft("");
    setOwnerToken(token);
    await load(token);
  };

  const lock = () => {
    requestGeneration.current += 1;
    activeController.current?.abort();
    activeController.current = null;
    setOwnerToken("");
    setTokenDraft("");
    setNewGrantToken("");
    setGrantDraft(EMPTY_GRANT);
    setSnapshot(null);
    setError("");
    setIssueOpen(false);
    setActionBusy(false);
    setPhase("locked");
  };

  const refresh = useCallback(async () => {
    if (ownerToken) await load(ownerToken);
  }, [load, ownerToken]);

  const runAction = async (
    action: (signal: AbortSignal) => Promise<unknown>,
  ): Promise<boolean> => {
    const { controller, generation } = beginRequest();
    setError("");
    setSnapshot(null);
    setPhase("loading");
    setActionBusy(true);
    const loadingVisible = waitForLoadingVisibility(controller.signal);
    try {
      await action(controller.signal);
      if (!requestIsCurrent(generation)) return false;
      const next = await fetchSnapshot(ownerToken, controller.signal);
      await loadingVisible;
      if (!requestIsCurrent(generation)) return false;
      setSnapshot(next);
      setPhase("ready");
      return true;
    } catch (actionError) {
      await loadingVisible;
      if (!requestIsCurrent(generation)) return false;
      setSnapshot(null);
      setError(`Node state is unknown until a fresh owner snapshot succeeds. ${messageFor(actionError)}`);
      setPhase("error");
      return false;
    } finally {
      if (requestIsCurrent(generation)) setActionBusy(false);
      if (activeController.current === controller) activeController.current = null;
    }
  };

  const toggleScope = (scope: string) => {
    setGrantDraft((draft) => ({
      ...draft,
      scopes: draft.scopes.includes(scope)
        ? draft.scopes.filter((item) => item !== scope)
        : [...draft.scopes, scope],
    }));
  };

  const toggleZone = (zoneId: string) => {
    setGrantDraft((draft) => ({
      ...draft,
      zones: draft.zones.includes(zoneId)
        ? draft.zones.filter((item) => item !== zoneId)
        : [...draft.zones, zoneId],
    }));
  };

  const submitGrant = async (event: FormEvent) => {
    event.preventDefault();
    const credential = newGrantToken;
    setNewGrantToken("");
    const succeeded = await runAction((signal) => (
      issueGrant(ownerToken, credential, grantDraft, signal)
    ));
    if (succeeded) {
      setGrantDraft(EMPTY_GRANT);
      setIssueOpen(false);
    }
  };

  const eligibleZones = useMemo(
    () => snapshot?.housefile.zones.filter((zone) => zone.access !== "no-go") ?? [],
    [snapshot],
  );

  if (phase === "locked" || (!snapshot && phase !== "loading" && phase !== "error")) {
    return (
      <main className="auth-layout">
        <section className="auth-card" aria-labelledby="auth-title">
          <div className="brand-mark"><ShieldCheck aria-hidden="true" /></div>
          <p className="eyebrow">THS-0.1 · loopback owner surface</p>
          <h1 id="auth-title">Threshold</h1>
          <p className="auth-subtitle">The housefile stays owner-held. Authenticate to inspect this local node.</p>
          <form onSubmit={connect} className="auth-form" autoComplete="off">
            <label htmlFor="owner-token">Owner token</label>
            <input
              id="owner-token"
              type="password"
              value={tokenDraft}
              onChange={(event) => setTokenDraft(event.target.value)}
              autoComplete="off"
              spellCheck={false}
              minLength={32}
              maxLength={512}
              required
            />
            <button className="button primary-button" type="submit">
              <LockKeyhole aria-hidden="true" /> Connect locally
            </button>
          </form>
          <p className="security-note">
            Kept in page memory only—never browser storage, cookies, URLs, screenshots, or build artifacts.
          </p>
        </section>
      </main>
    );
  }

  if (!snapshot) {
    return (
      <main className="auth-layout">
        <section
          className="auth-card"
          aria-atomic="true"
          aria-busy={phase === "loading"}
          aria-live="polite"
          role={phase === "loading" ? "status" : undefined}
        >
          {phase === "loading" ? (
            <>
              <RefreshCw className="spin large-icon" aria-hidden="true" />
              <h1>Verifying local state</h1>
              <p className="subtle">Loading a fresh owner snapshot without persisting credentials.</p>
              <button className="button secondary-button" type="button" onClick={lock}>
                <LockKeyhole aria-hidden="true" /> Cancel and lock
              </button>
            </>
          ) : (
            <>
              <AlertTriangle className="large-icon danger-ink" aria-hidden="true" />
              <h1>Connection failed</h1>
              <p role="alert">{error}</p>
              <div className="button-row">
                <button className="button primary-button" type="button" onClick={() => void refresh()}>
                  <RefreshCw aria-hidden="true" /> Retry
                </button>
                <button className="button secondary-button" type="button" onClick={lock}>
                  Use another token
                </button>
              </div>
            </>
          )}
        </section>
      </main>
    );
  }

  const tripped = snapshot.status.health.interlock_state === "TRIPPED";
  const activeGrants = snapshot.grants.filter((grant) => grant.status === "active").length;

  return (
    <div className="app-shell">
      <header className="site-header">
        <div className="brand-block">
          <p className="eyebrow">Project · local owner console</p>
          <h1>Threshold</h1>
          <p className="mono subtle">the housefile · owner-held · policy decisions durably logged</p>
        </div>
        <div className="header-actions">
          <StatusChip value={snapshot.status.health.interlock_state} />
          <button className="icon-button" type="button" onClick={() => void refresh()} aria-label="Refresh owner snapshot">
            <RefreshCw className={phase === "loading" ? "spin" : ""} aria-hidden="true" />
          </button>
          <button className="button secondary-button compact" type="button" onClick={lock}>
            <LockKeyhole aria-hidden="true" /> Lock
          </button>
        </div>
      </header>

      {tripped && (
        <section className="trip-banner" role="alert">
          <AlertTriangle aria-hidden="true" />
          <div>
            <strong>Simulated interlock TRIPPED</strong>
            <p>Commands and new grants are denied. Re-arm never restores suspended grants. No physical stop is verified.</p>
          </div>
          <button
            className="button light-button"
            type="button"
            disabled={actionBusy}
            onClick={() => void runAction((signal) => rearmInterlock(ownerToken, signal))}
          >
            <RotateCcw aria-hidden="true" /> Re-arm simulation
          </button>
        </section>
      )}

      {error && snapshot && (
        <div className="inline-error" role="alert">
          <AlertTriangle aria-hidden="true" />
          <span>{error}</span>
          <button type="button" onClick={() => setError("")} aria-label="Dismiss error"><X aria-hidden="true" /></button>
        </div>
      )}

      <nav className="tabs" aria-label="Owner console sections">
        {([
          ["blueprint", "Blueprint", MapIcon],
          ["grants", "Grants", KeyRound],
          ["ledger", "Ledger", ScrollText],
        ] as const).map(([id, label, Icon]) => (
          <button
            type="button"
            key={id}
            className={tab === id ? "active" : ""}
            aria-current={tab === id ? "page" : undefined}
            onClick={() => setTab(id)}
          >
            <Icon aria-hidden="true" /> {label}
          </button>
        ))}
      </nav>

      <main className="content">
        {tab === "blueprint" && (
          <section aria-labelledby="blueprint-heading">
            <div className="section-heading">
              <div>
                <p className="eyebrow">Canonical snapshot · revision {snapshot.housefile.rev}</p>
                <h2 id="blueprint-heading">{snapshot.housefile.dwelling.name}</h2>
              </div>
              <span className="scope-chip">{snapshot.housefile.schema}</span>
            </div>

            <div className="metric-grid">
              <article><House aria-hidden="true" /><span>Zones</span><strong>{snapshot.housefile.zones.length}</strong></article>
              <article><KeyRound aria-hidden="true" /><span>Active grants</span><strong>{activeGrants}</strong></article>
              <article><Activity aria-hidden="true" /><span>Display</span><strong>{snapshot.status.display.state}</strong></article>
              <article><Clock3 aria-hidden="true" /><span>Quiet hours</span><strong>{snapshot.housefile.policies.quietHours.start}–{snapshot.housefile.policies.quietHours.end}</strong></article>
            </div>

            <article className="panel blueprint-panel">
              <div className="panel-heading">
                <div><p className="eyebrow">Owner authority</p><h3>Access blueprint</h3></div>
                <span className="mono subtle">{snapshot.housefile.policies.quietHours.timezone}</span>
              </div>
              <Blueprint zones={snapshot.housefile.zones} />
            </article>

            <div className="split-panels">
              <article className="panel">
                <p className="eyebrow">Node state</p>
                <dl className="definition-list">
                  <div><dt>Release</dt><dd>{snapshot.status.health.release_stage}</dd></div>
                  <div><dt>Grant store</dt><dd>{snapshot.status.health.grant_store_availability}</dd></div>
                  <div><dt>Ledger</dt><dd>{snapshot.status.health.ledger_availability}</dd></div>
                  <div><dt>Demo mode</dt><dd>{snapshot.status.health.demo_mode ? "Enabled" : "Disabled"}</dd></div>
                </dl>
              </article>
              <article className="panel">
                <p className="eyebrow">Simulated appliance</p>
                <h3>{tripped ? "Latch requires owner review" : "Software latch armed"}</h3>
                <p className="subtle">Timing is simulated software-path evidence only. Physical stop is not verified.</p>
                {!tripped && (
                  <button
                    className="button danger-button"
                    type="button"
                    disabled={actionBusy}
                    onClick={() => void runAction((signal) => tripInterlock(ownerToken, signal))}
                  >
                    <Power aria-hidden="true" /> Trip simulated interlock
                  </button>
                )}
              </article>
            </div>
          </section>
        )}

        {tab === "grants" && (
          <section aria-labelledby="grants-heading">
            <div className="section-heading">
              <div><p className="eyebrow">Public projections only</p><h2 id="grants-heading">Grants</h2></div>
              <button
                className="button primary-button"
                type="button"
                disabled={tripped}
                onClick={() => setIssueOpen((open) => !open)}
              >
                {issueOpen ? <X aria-hidden="true" /> : <Plus aria-hidden="true" />}
                {issueOpen ? "Close" : "Issue grant"}
              </button>
            </div>

            {issueOpen && (
              <form className="panel issue-form" onSubmit={submitGrant} autoComplete="off">
                <div className="panel-heading"><div><p className="eyebrow">Memory-only credential</p><h3>New grant</h3></div></div>
                <div className="form-grid">
                  <label>Name<input value={grantDraft.name} maxLength={128} required onChange={(event) => setGrantDraft({ ...grantDraft, name: event.target.value })} /></label>
                  <label>Kind<select value={grantDraft.kind} onChange={(event) => setGrantDraft({ ...grantDraft, kind: event.target.value as GrantIssuePayload["kind"] })}><option value="agent">Agent</option><option value="humanoid">Humanoid</option><option value="human">Human</option></select></label>
                  <label className="wide">Distinct grant token<input type="password" value={newGrantToken} minLength={32} maxLength={512} autoComplete="off" spellCheck={false} required onChange={(event) => setNewGrantToken(event.target.value)} /><small>Sent once in a request header, then cleared from this page.</small></label>
                  <label>Window<input value={grantDraft.window} maxLength={128} required onChange={(event) => setGrantDraft({ ...grantDraft, window: event.target.value })} /></label>
                  <label>Expires<input value={grantDraft.expires} maxLength={64} required onChange={(event) => setGrantDraft({ ...grantDraft, expires: event.target.value })} /></label>
                </div>
                <fieldset><legend>Scopes</legend><div className="choice-grid">{SCOPE_OPTIONS.map(([scope, label]) => <label className="choice" key={scope}><input type="checkbox" checked={grantDraft.scopes.includes(scope)} onChange={() => toggleScope(scope)} /><span><strong>{label}</strong><small>{scope}</small></span></label>)}</div></fieldset>
                <fieldset><legend>Zones</legend><div className="choice-grid">{eligibleZones.map((zone) => <label className="choice" key={zone.id}><input type="checkbox" checked={grantDraft.zones.includes(zone.id)} onChange={() => toggleZone(zone.id)} /><span><strong>{zone.name}</strong><small>{zone.access}</small></span></label>)}</div></fieldset>
                <button className="button primary-button" type="submit" disabled={actionBusy || grantDraft.scopes.length === 0 || grantDraft.zones.length === 0}>{actionBusy ? <RefreshCw className="spin" aria-hidden="true" /> : <KeyRound aria-hidden="true" />} Issue without returning credential</button>
              </form>
            )}

            <div className="grant-grid">
              {snapshot.grants.map((grant) => (
                <GrantCard
                  key={grant.id}
                  grant={grant}
                  busy={actionBusy}
                  onRevoke={(selected) => void runAction((signal) => revokeGrant(ownerToken, selected.id, signal))}
                />
              ))}
            </div>
          </section>
        )}

        {tab === "ledger" && (
          <section aria-labelledby="ledger-heading">
            <div className="section-heading">
              <div><p className="eyebrow">Bounded newest-first view</p><h2 id="ledger-heading">Audit ledger</h2></div>
              <span className="scope-chip">{snapshot.ledger.length} / 100</span>
            </div>
            <div className="table-shell">
              <table>
                <caption className="sr-only">Bounded owner audit ledger entries</caption>
                <thead><tr><th>Time</th><th>Event</th><th>Agent</th><th>Detail</th></tr></thead>
                <tbody>
                  {snapshot.ledger.map((entry, index) => (
                    <tr key={`${entry.ts}-${entry.type}-${index}`}>
                      <td className="mono">{entry.ts}</td>
                      <td><span className={`event-chip event-${entry.type.toLowerCase()}`}>{entry.type}</span></td>
                      <td>{entry.agent}</td>
                      <td>{entry.detail}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {snapshot.ledger.length === 0 && <p className="empty-state">No durable ledger entries are available.</p>}
            </div>
          </section>
        )}
      </main>

      <footer>
        <span>Local-first pre-alpha</span>
        <span>Owner token: memory only</span>
        <span>Physical safety: not verified</span>
      </footer>
    </div>
  );
}
