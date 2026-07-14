import type {
  GrantIssuePayload,
  OwnerSnapshot,
  PublicGrant,
} from "./types";

const API_PREFIX = "/api";
const FORBIDDEN_RESPONSE_KEYS = new Set([
  "apikey",
  "authorization",
  "bearer",
  "clientsecret",
  "credential",
  "credentialdigest",
  "credentialhash",
  "granttoken",
  "newgranttoken",
  "ownertoken",
  "password",
  "rawcredential",
  "rawtoken",
  "secret",
  "token",
]);

type JsonRecord = Record<string, unknown>;

function isForbiddenResponseKey(key: string): boolean {
  const normalized = key.toLowerCase().replace(/[^a-z0-9]/g, "");
  if (normalized === "credentialregistered") return false;
  return (
    FORBIDDEN_RESPONSE_KEYS.has(normalized)
    || normalized.includes("credential")
    || normalized.includes("token")
    || normalized.includes("apikey")
    || normalized.includes("authorization")
    || normalized.includes("password")
    || normalized.includes("secret")
    || normalized.includes("bearer")
  );
}

export class ApiError extends Error {
  readonly status: number | null;

  constructor(message: string, status: number | null = null) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function assertPublicPayload(value: unknown, depth = 0): void {
  if (depth > 24) {
    throw new ApiError("The node returned an invalid response.");
  }
  if (Array.isArray(value)) {
    value.forEach((item) => assertPublicPayload(item, depth + 1));
    return;
  }
  if (value === null || typeof value !== "object") {
    return;
  }
  for (const [key, item] of Object.entries(value)) {
    if (isForbiddenResponseKey(key)) {
      throw new ApiError("The node returned a response with a forbidden field.");
    }
    assertPublicPayload(item, depth + 1);
  }
}

function isRecord(value: unknown): value is JsonRecord {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

function optionalString(value: unknown): boolean {
  return value === undefined || typeof value === "string";
}

function isPublicGrant(value: unknown): value is PublicGrant {
  if (!isRecord(value)) return false;
  return (
    typeof value.id === "string"
    && typeof value.name === "string"
    && typeof value.kind === "string"
    && isStringArray(value.scopes)
    && isStringArray(value.zones)
    && typeof value.window === "string"
    && typeof value.expires === "string"
    && ["active", "revoked", "expired", "suspended"].includes(String(value.status))
    && typeof value.issued === "string"
  );
}

function isZone(value: unknown): boolean {
  if (!isRecord(value)) return false;
  return (
    typeof value.id === "string"
    && typeof value.name === "string"
    && ["open", "restricted", "no-go"].includes(String(value.access))
    && Array.isArray(value.boundary)
    && value.boundary.length === 4
    && value.boundary.every((item) => typeof item === "number" && Number.isFinite(item))
    && optionalString(value.note)
    && (value.outdoor === undefined || typeof value.outdoor === "boolean")
  );
}

function isHousefile(value: unknown): boolean {
  if (!isRecord(value) || !isRecord(value.dwelling) || !isRecord(value.policies)) {
    return false;
  }
  const quietHours = value.policies.quietHours;
  if (!isRecord(quietHours)) return false;
  return (
    typeof value.schema === "string"
    && typeof value.rev === "string"
    && typeof value.dwelling.name === "string"
    && Array.isArray(value.zones)
    && value.zones.every(isZone)
    && Array.isArray(value.systems)
    && value.systems.every((item) => (
      isRecord(item)
      && typeof item.id === "string"
      && typeof item.name === "string"
      && typeof item.zone === "string"
      && typeof item.tag === "string"
      && typeof item.detail === "string"
    ))
    && Array.isArray(value.inventory)
    && value.inventory.every((item) => (
      isRecord(item)
      && typeof item.id === "string"
      && typeof item.name === "string"
      && typeof item.zone === "string"
      && isStringArray(item.flags)
      && optionalString(item.note)
    ))
    && Array.isArray(value.quirks)
    && value.quirks.every((item) => (
      isRecord(item)
      && typeof item.id === "string"
      && typeof item.zone === "string"
      && typeof item.text === "string"
    ))
    && typeof quietHours.start === "string"
    && typeof quietHours.end === "string"
    && typeof quietHours.timezone === "string"
    && typeof value.policies.teleop === "string"
    && typeof value.policies.residency === "string"
  );
}

function isOwnerStatus(value: unknown): boolean {
  if (!isRecord(value) || !isRecord(value.health) || !isRecord(value.display)) {
    return false;
  }
  const health = value.health;
  return (
    health.service === "up"
    && health.release_stage === "pre-alpha"
    && health.armed === false
    && ["simulated_latched", "simulated_disabled"].includes(String(health.interlock))
    && ["ARMED", "TRIPPED"].includes(String(health.interlock_state))
    && health.physical_stop_verified === false
    && health.timing_scope === "simulated_software_path_only"
    && health.ledger === "persistent_jsonl_configured"
    && health.ledger_availability === "not_probed"
    && health.grant_store === "authoritative_digest_only_configured"
    && health.grant_store_availability === "not_probed"
    && isStringArray(health.adapters)
    && typeof health.demo_mode === "boolean"
    && ["ARMED", "READ", "DENY", "TRIPPED", "UNAVAILABLE"].includes(String(value.display.state))
    && optionalString(value.display.agent)
    && typeof value.active_grants === "number"
    && Number.isInteger(value.active_grants)
    && value.active_grants >= 0
  );
}

function isLedgerEntry(value: unknown): boolean {
  return (
    isRecord(value)
    && typeof value.ts === "string"
    && typeof value.type === "string"
    && typeof value.agent === "string"
    && typeof value.detail === "string"
    && optionalString(value.tier)
  );
}

function assertOwnerSnapshot(value: unknown): asserts value is OwnerSnapshot {
  if (
    !isRecord(value)
    || !isHousefile(value.housefile)
    || !Array.isArray(value.grants)
    || !value.grants.every(isPublicGrant)
    || !isOwnerStatus(value.status)
    || !Array.isArray(value.ledger)
    || !value.ledger.every(isLedgerEntry)
  ) {
    throw new ApiError("The node returned an incompatible owner snapshot.");
  }
}

function statusMessage(status: number): string {
  if (status === 401) return "Owner authentication was rejected.";
  if (status === 403) return "This browser origin is not permitted.";
  if (status === 404) return "The requested local resource was not found.";
  if (status === 409) return "The request conflicts with current node state.";
  if (status === 422) return "The submitted values were not accepted.";
  if (status === 423) return "The simulated interlock is tripped.";
  if (status === 503) return "The local node is unavailable or failed closed.";
  return "The local node request failed.";
}

async function requestJson<T>(
  path: string,
  ownerToken: string,
  init: RequestInit = {},
): Promise<T> {
  if (!ownerToken) {
    throw new ApiError("Enter the owner token to continue.");
  }
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  headers.set("X-Threshold-Owner-Token", ownerToken);
  if (init.body !== undefined) headers.set("Content-Type", "application/json");

  let response: Response;
  try {
    response = await fetch(`${API_PREFIX}${path}`, {
      ...init,
      headers,
      cache: "no-store",
      credentials: "omit",
      redirect: "error",
      referrerPolicy: "no-referrer",
    });
  } catch {
    throw new ApiError("The loopback node could not be reached.");
  }
  if (!response.ok) {
    throw new ApiError(statusMessage(response.status), response.status);
  }
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    throw new ApiError("The node returned an invalid response.", response.status);
  }
  assertPublicPayload(payload);
  return payload as T;
}

export async function fetchSnapshot(
  ownerToken: string,
  signal?: AbortSignal,
): Promise<OwnerSnapshot> {
  const result = await requestJson<unknown>(
    "/owner/snapshot?ledger_limit=100",
    ownerToken,
    { signal },
  );
  assertOwnerSnapshot(result);
  return result;
}

export async function issueGrant(
  ownerToken: string,
  newGrantToken: string,
  payload: GrantIssuePayload,
  signal?: AbortSignal,
): Promise<PublicGrant> {
  if (!newGrantToken) throw new ApiError("Enter a distinct grant token.");
  const result = await requestJson<unknown>(
    "/grants",
    ownerToken,
    {
      method: "POST",
      signal,
      headers: { "X-Threshold-New-Grant-Token": newGrantToken },
      body: JSON.stringify(payload),
    },
  );
  if (
    !isRecord(result)
    || result.credential_registered !== true
    || !isPublicGrant(result.grant)
  ) {
    throw new ApiError("The node returned an incompatible grant response.");
  }
  return result.grant;
}

export function revokeGrant(
  ownerToken: string,
  grantId: string,
  signal?: AbortSignal,
): Promise<unknown> {
  return requestJson(`/grants/${encodeURIComponent(grantId)}/revoke`, ownerToken, {
    method: "POST",
    signal,
  });
}

export function tripInterlock(ownerToken: string, signal?: AbortSignal): Promise<unknown> {
  return requestJson("/sim/interlock/trip", ownerToken, { method: "POST", signal });
}

export function rearmInterlock(ownerToken: string, signal?: AbortSignal): Promise<unknown> {
  return requestJson("/sim/interlock/rearm", ownerToken, { method: "POST", signal });
}
