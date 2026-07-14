import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import axe from "axe-core";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import type { OwnerSnapshot } from "./types";

const OWNER_VALUE = "owner-console-test-token-000000000001";
const NEW_GRANT_VALUE = "new-grant-console-token-00000000001";

const SNAPSHOT: OwnerSnapshot = {
  housefile: {
    schema: "ths/0.1",
    rev: "A",
    dwelling: { name: "Threshold Demo House (Synthetic)" },
    zones: [
      { id: "kitchen", name: "Kitchen", access: "open", boundary: [0, 0, 150, 100] },
      { id: "workshop", name: "Workshop", access: "no-go", boundary: [150, 0, 150, 100] },
    ],
    systems: [],
    inventory: [],
    quirks: [],
    policies: {
      quietHours: { start: "21:30", end: "06:30", timezone: "Etc/UTC" },
      teleop: "per-session",
      residency: "local-first",
    },
  },
  grants: [
    {
      id: "g-neo",
      name: "NEO Unit 04",
      kind: "humanoid",
      scopes: ["read:layout"],
      zones: ["kitchen"],
      window: "standing",
      expires: "revocable",
      status: "active",
      issued: "2026-07-13T09:12:00Z",
    },
  ],
  status: {
    health: {
      service: "up",
      release_stage: "pre-alpha",
      armed: false,
      interlock: "simulated_latched",
      interlock_state: "ARMED",
      physical_stop_verified: false,
      timing_scope: "simulated_software_path_only",
      ledger: "persistent_jsonl_configured",
      ledger_availability: "not_probed",
      grant_store: "authoritative_digest_only_configured",
      grant_store_availability: "not_probed",
      adapters: [],
      demo_mode: true,
    },
    display: { state: "ARMED" },
    active_grants: 1,
  },
  ledger: [
    { ts: "2026-07-13T09:12:00Z", type: "GRANT", agent: "g-neo", detail: "grant issued" },
  ],
};

function response(payload: unknown, status = 200): Promise<Response> {
  return Promise.resolve(new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  }));
}

function deferred<T>() {
  let resolve!: (value: T | PromiseLike<T>) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, reject, resolve };
}

async function connect(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText("Owner token"), OWNER_VALUE);
  await user.click(screen.getByRole("button", { name: "Connect locally" }));
}

describe("owner console", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  it("keeps the owner token out of storage, URLs, and rendered text", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockImplementationOnce(() => response(SNAPSHOT));
    const localStorageSpy = vi.spyOn(Storage.prototype, "setItem");
    const user = userEvent.setup();
    render(<App />);

    expect(screen.getByLabelText("Owner token")).toHaveAttribute("autocomplete", "off");
    await connect(user);

    expect(await screen.findByText("Threshold Demo House (Synthetic)")).toBeInTheDocument();
    const [url, init] = fetchMock.mock.calls[0];
    const headers = new Headers(init?.headers);
    expect(String(url)).toBe("/api/owner/snapshot?ledger_limit=100");
    expect(String(url)).not.toContain(OWNER_VALUE);
    expect(headers.get("X-Threshold-Owner-Token")).toBe(OWNER_VALUE);
    expect(document.body).not.toHaveTextContent(OWNER_VALUE);
    expect(localStorageSpy).not.toHaveBeenCalled();
  });

  it("shows a bounded error and retries without reflecting transport details", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockRejectedValueOnce(new Error(`network ${OWNER_VALUE}`));
    fetchMock.mockImplementationOnce(() => response(SNAPSHOT));
    const user = userEvent.setup();
    render(<App />);

    await connect(user);
    expect(await screen.findByRole("heading", { name: "Connection failed" })).toBeInTheDocument();
    expect(screen.getByText("The loopback node could not be reached.")).toBeInTheDocument();
    expect(document.body).not.toHaveTextContent(OWNER_VALUE);

    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Threshold Demo House (Synthetic)")).toBeInTheDocument();
  });

  it("cannot repopulate a locked console from a late snapshot", async () => {
    const pending = deferred<Response>();
    vi.mocked(fetch).mockImplementationOnce(() => pending.promise);
    const user = userEvent.setup();
    render(<App />);

    await connect(user);
    await user.click(await screen.findByRole("button", { name: "Cancel and lock" }));
    pending.resolve(await response(SNAPSHOT));

    await waitFor(() => {
      expect(screen.getByLabelText("Owner token")).toBeInTheDocument();
      expect(screen.queryByText("Threshold Demo House (Synthetic)")).not.toBeInTheDocument();
    });
  });

  it("renders the TRIPPED state and explains the simulation boundary", async () => {
    const tripped: OwnerSnapshot = {
      ...SNAPSHOT,
      status: {
        ...SNAPSHOT.status,
        health: { ...SNAPSHOT.status.health, interlock_state: "TRIPPED" },
        display: { state: "TRIPPED" },
        active_grants: 0,
      },
      grants: [{ ...SNAPSHOT.grants[0], status: "suspended" }],
    };
    vi.mocked(fetch).mockImplementationOnce(() => response(tripped));
    const user = userEvent.setup();
    render(<App />);

    await connect(user);

    expect(await screen.findByRole("alert")).toHaveTextContent("Simulated interlock TRIPPED");
    expect(screen.getByRole("alert")).toHaveTextContent("No physical stop is verified");
    expect(screen.getByRole("button", { name: "Re-arm simulation" })).toBeInTheDocument();
    const result = await axe.run(document.body);
    expect(result.violations).toEqual([]);
  });

  it("issues a grant with a header-only credential and then refreshes", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockImplementationOnce(() => response(SNAPSHOT))
      .mockImplementationOnce(() => response({ grant: SNAPSHOT.grants[0], credential_registered: true }, 201))
      .mockImplementationOnce(() => response(SNAPSHOT));
    const user = userEvent.setup();
    render(<App />);
    await connect(user);

    await user.click(screen.getByRole("button", { name: "Grants" }));
    await user.click(screen.getByRole("button", { name: "Issue grant" }));
    expect(screen.getByLabelText(/Distinct grant token/)).toHaveAttribute("autocomplete", "off");
    await user.type(screen.getByLabelText("Name"), "Synthetic Courier");
    await user.type(screen.getByLabelText(/Distinct grant token/), NEW_GRANT_VALUE);
    await user.click(screen.getByRole("checkbox", { name: /Kitchen/ }));
    await user.click(screen.getByRole("button", { name: "Issue without returning credential" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    const [url, init] = fetchMock.mock.calls[1];
    const headers = new Headers(init?.headers);
    expect(String(url)).toBe("/api/grants");
    expect(String(url)).not.toContain(NEW_GRANT_VALUE);
    expect(headers.get("X-Threshold-New-Grant-Token")).toBe(NEW_GRANT_VALUE);
    expect(String(init?.body)).not.toContain(NEW_GRANT_VALUE);
    expect(document.body).not.toHaveTextContent(NEW_GRANT_VALUE);
  });

  it("revokes a public grant projection and refreshes", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockImplementationOnce(() => response(SNAPSHOT))
      .mockImplementationOnce(() => response({ grant: { ...SNAPSHOT.grants[0], status: "revoked" }, changed: true }))
      .mockImplementationOnce(() => response(SNAPSHOT));
    const user = userEvent.setup();
    render(<App />);
    await connect(user);

    await user.click(screen.getByRole("button", { name: "Grants" }));
    await user.click(screen.getByRole("button", { name: "Revoke grant" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(3));
    expect(String(fetchMock.mock.calls[1][0])).toBe("/api/grants/g-neo/revoke");
    expect(fetchMock.mock.calls[1][1]?.method).toBe("POST");
  });

  it("hides stale grant state when a mutation succeeds but refresh fails", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockImplementationOnce(() => response(SNAPSHOT))
      .mockImplementationOnce(() => response({ grant: { ...SNAPSHOT.grants[0], status: "revoked" }, changed: true }))
      .mockRejectedValueOnce(new Error("synthetic refresh failure"))
      .mockImplementationOnce(() => response({
        ...SNAPSHOT,
        grants: [{ ...SNAPSHOT.grants[0], status: "revoked" }],
        status: { ...SNAPSHOT.status, active_grants: 0 },
      }));
    const user = userEvent.setup();
    render(<App />);
    await connect(user);

    await user.click(screen.getByRole("button", { name: "Grants" }));
    await user.click(screen.getByRole("button", { name: "Revoke grant" }));

    expect(await screen.findByRole("heading", { name: "Connection failed" })).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Node state is unknown");
    expect(screen.queryByText("NEO Unit 04")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("NEO Unit 04")).toBeInTheDocument();
    expect(screen.getByText("REVOKED")).toBeInTheDocument();
  });

  it("stays locked when a late mutation response arrives", async () => {
    const pendingMutation = deferred<Response>();
    const fetchMock = vi.mocked(fetch);
    fetchMock
      .mockImplementationOnce(() => response(SNAPSHOT))
      .mockImplementationOnce(() => pendingMutation.promise);
    const user = userEvent.setup();
    render(<App />);
    await connect(user);

    await user.click(screen.getByRole("button", { name: "Grants" }));
    await user.click(screen.getByRole("button", { name: "Revoke grant" }));
    await user.click(await screen.findByRole("button", { name: "Cancel and lock" }));
    pendingMutation.resolve(await response({ changed: true }));

    await waitFor(() => {
      expect(screen.getByLabelText("Owner token")).toBeInTheDocument();
      expect(fetchMock).toHaveBeenCalledTimes(2);
      expect(screen.queryByText("NEO Unit 04")).not.toBeInTheDocument();
    });
  });

  it("has no detectable accessibility violations on the authentication surface", async () => {
    render(<App />);
    const result = await axe.run(document.body);
    expect(result.violations).toEqual([]);
  });

  it("has no detectable accessibility violations on the connected blueprint", async () => {
    vi.mocked(fetch).mockImplementationOnce(() => response(SNAPSHOT));
    const user = userEvent.setup();
    render(<App />);

    await connect(user);
    expect(await screen.findByText("Threshold Demo House (Synthetic)")).toBeInTheDocument();

    const result = await axe.run(document.body);
    expect(result.violations).toEqual([]);
  });

  it("has no detectable accessibility violations on grant issue and ledger views", async () => {
    vi.mocked(fetch).mockImplementationOnce(() => response(SNAPSHOT));
    const user = userEvent.setup();
    render(<App />);

    await connect(user);
    await screen.findByText("Threshold Demo House (Synthetic)");
    await user.click(screen.getByRole("button", { name: "Grants" }));
    await user.click(screen.getByRole("button", { name: "Issue grant" }));
    expect((await axe.run(document.body)).violations).toEqual([]);

    await user.click(screen.getByRole("button", { name: "Ledger" }));
    expect((await axe.run(document.body)).violations).toEqual([]);
  });
});
