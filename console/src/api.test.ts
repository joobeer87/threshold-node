import { beforeEach, describe, expect, it, vi } from "vitest";
import { fetchSnapshot } from "./api";

const OWNER_VALUE = "owner-console-test-token-000000000001";

describe("owner API client", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
  });

  it("fails closed when credential-like fields appear", async () => {
    for (const field of [
      "api_key",
      "credential",
      "credential_digest",
      "credential_hash",
      "grant_credential_digest",
      "grant_token",
      "raw_token",
      "secret",
    ]) {
      vi.mocked(fetch).mockResolvedValueOnce(new Response(JSON.stringify({
        housefile: {},
        grants: [{ [field]: "synthetic-forbidden-value" }],
      }), { status: 200 }));

      await expect(fetchSnapshot(OWNER_VALUE)).rejects.toThrow(
        "The node returned a response with a forbidden field.",
      );
    }
  });

  it("does not reflect response bodies from failed requests", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(new Response(
      JSON.stringify({ detail: `unsafe ${OWNER_VALUE}` }),
      { status: 503 },
    ));

    await expect(fetchSnapshot(OWNER_VALUE)).rejects.toThrow(
      "The local node is unavailable or failed closed.",
    );
  });

  it("fails into the retry path on an incompatible successful snapshot", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(new Response(JSON.stringify({
      housefile: { schema: "ths/0.1" },
      grants: [],
      ledger: [],
      status: {},
    }), { status: 200 }));

    await expect(fetchSnapshot(OWNER_VALUE)).rejects.toThrow(
      "The node returned an incompatible owner snapshot.",
    );
  });

  it("fails closed on an unknown interlock state", async () => {
    const incompatible = {
      housefile: {
        schema: "ths/0.1",
        rev: "A",
        dwelling: { name: "Threshold Demo House (Synthetic)" },
        zones: [],
        systems: [],
        inventory: [],
        quirks: [],
        policies: {
          quietHours: { start: "21:30", end: "06:30", timezone: "Etc/UTC" },
          teleop: "per-session",
          residency: "local-first",
        },
      },
      grants: [],
      ledger: [],
      status: {
        health: {
          service: "up",
          release_stage: "pre-alpha",
          armed: false,
          interlock: "simulated_latched",
          interlock_state: "UNKNOWN",
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
        active_grants: 0,
      },
    };
    vi.mocked(fetch).mockResolvedValueOnce(new Response(JSON.stringify(incompatible), { status: 200 }));

    await expect(fetchSnapshot(OWNER_VALUE)).rejects.toThrow(
      "The node returned an incompatible owner snapshot.",
    );
  });
});
