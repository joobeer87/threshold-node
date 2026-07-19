export type GrantStatus = "active" | "revoked" | "expired" | "suspended";
export type Access = "open" | "restricted" | "no-go";

export interface Zone {
  id: string;
  name: string;
  access: Access;
  boundary: [number, number, number, number];
  note?: string;
  outdoor?: boolean;
}

export interface Housefile {
  schema: string;
  rev: string;
  dwelling: { name: string };
  zones: Zone[];
  systems: Array<{
    id: string;
    name: string;
    zone: string;
    tag: string;
    detail: string;
  }>;
  inventory: Array<{
    id: string;
    name: string;
    zone: string;
    flags: string[];
    note?: string;
  }>;
  quirks: Array<{ id: string; zone: string; text: string }>;
  policies: {
    quietHours: { start: string; end: string; timezone: string };
    teleop: string;
    residency: string;
  };
}

export interface PublicGrant {
  id: string;
  name: string;
  kind: "humanoid" | "agent" | "human" | string;
  scopes: string[];
  zones: string[];
  window: string;
  expires: string;
  status: GrantStatus;
  issued: string;
}

export interface LedgerEntry {
  ts: string;
  type: string;
  agent: string;
  detail: string;
  tier?: string;
}

export interface HealthState {
  service: string;
  release_stage: string;
  armed: boolean;
  interlock: string;
  interlock_state: "ARMED" | "TRIPPED" | string;
  physical_stop_verified: false;
  timing_scope: string;
  ledger: string;
  ledger_availability: string;
  grant_store: string;
  grant_store_availability: string;
  adapters: string[];
  demo_mode: boolean;
}

export interface OwnerStatus {
  health: HealthState;
  display: { state: string; agent?: string };
  active_grants: number;
}

export interface OwnerSnapshot {
  housefile: Housefile;
  grants: PublicGrant[];
  status: OwnerStatus;
  ledger: LedgerEntry[];
}

export interface GrantIssuePayload {
  name: string;
  kind: "humanoid" | "agent" | "human";
  scopes: string[];
  zones: string[];
  window: string;
  expires: string;
}
