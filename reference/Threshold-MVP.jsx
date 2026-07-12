import { useState, useEffect, useMemo } from "react";
import {
  Droplets, Zap, Wind, Bot, User, KeyRound, ScrollText, FileJson,
  Plus, X, Copy, Check, RotateCcw, Eye, ShieldAlert, Lock, Map as MapIcon
} from "lucide-react";

/* ────────────────────────────────────────────────────────────
   THRESHOLD · THS-0.1 — the housefile
   Owner-held · local-first · every access logged
   Core types first, logic second, chrome last.
──────────────────────────────────────────────────────────── */

const SCOPES = [
  { id: "read:layout",        label: "Layout",     hint: "zones, boundaries, no-go lines" },
  { id: "read:systems",       label: "Systems",    hint: "shutoffs, panels, filters" },
  { id: "read:inventory",     label: "Inventory",  hint: "objects, fragility flags" },
  { id: "command:navigate",   label: "Navigate",   hint: "may move through granted zones" },
  { id: "command:manipulate", label: "Manipulate", hint: "may touch non-flagged objects" },
];

const SEED_FILE = {
  schema: "ths/0.1",
  fixture: { synthetic: true, notice: "Fictional demo data only" },
  dwelling: { name: "Threshold Demo House", type: "synthetic", client: "SYNTHETIC FIXTURE" },
  zones: [
    { id: "kitchen",  name: "Kitchen",     access: "open",       x: 0,   y: 0,  w: 150, h: 100, note: "" },
    { id: "living",   name: "Living Room", access: "open",       x: 150, y: 0,  w: 150, h: 100, note: "" },
    { id: "utility",  name: "Utility",     access: "open",       x: 300, y: 0,  w: 100, h: 100, note: "Panel wall" },
    { id: "studio",   name: "Demo Studio", access: "restricted", x: 0,   y: 100, w: 130, h: 100, note: "Synthetic restricted-window example" },
    { id: "office",   name: "Office",      access: "open",       x: 130, y: 100, w: 130, h: 100, note: "" },
    { id: "workshop", name: "Workshop",    access: "no-go",      x: 260, y: 100, w: 140, h: 100, note: "Owner only. Precision equipment." },
  ],
  systems: [
    { id: "sys-water", name: "Demo water shutoff", zone: "utility", tag: "water", detail: "Synthetic marker W on the utility-room plan." },
    { id: "sys-power", name: "Demo breaker panel", zone: "utility", tag: "power", detail: "Synthetic circuit label K for the demo kitchen." },
    { id: "sys-hvac",  name: "Demo HVAC filter",   zone: "utility", tag: "hvac",  detail: "Synthetic maintenance marker H." },
  ],
  inventory: [
    { id: "inv-edge",      name: "Edge compute demo unit",     zone: "workshop", flags: ["do-not-touch", "high-value"], note: "Synthetic inventory item." },
    { id: "inv-sculpture", name: "Foam calibration sculpture", zone: "living",   flags: ["fragile"], note: "Synthetic fragile-object example." },
    { id: "inv-cookware",  name: "Demo cookware",              zone: "kitchen",  flags: ["never-soap"], note: "Synthetic handling-rule example." },
  ],
  quirks: [
    { id: "q1", zone: "kitchen", text: "Synthetic obstacle marker A requires a slower approach." },
    { id: "q2", zone: "living",  text: "Synthetic quiet-zone marker activates after 21:00." },
  ],
  policies: {
    quietHours: { start: "21:30", end: "06:30" },
    teleop: "per-session consent",
    residency: "local-first",
    safetyMeta: "fragility & no-go always transmit",
  },
};

const SEED_GRANTS = [
  {
    id: "g-neo", name: "NEO Unit 04", kind: "humanoid", vendor: "1X",
    scopes: ["read:layout", "read:inventory", "command:navigate", "command:manipulate"],
    zones: ["kitchen", "living", "office", "utility"],
    window: "standing · obeys quiet hours", expires: "revocable", status: "active", issued: "2026-07-13 09:12",
  },
  {
    id: "g-clean", name: "Sparkle Cleaning Co.", kind: "human", vendor: "",
    scopes: ["read:layout", "read:systems"],
    zones: ["kitchen", "living", "studio", "office", "utility"],
    window: "demo window", expires: "revocable", status: "active", issued: "2026-07-13 09:30",
  },
  {
    id: "g-plumb", name: "Plumber — one-time key", kind: "human", vendor: "",
    scopes: ["read:systems"],
    zones: ["utility"],
    window: "single visit", expires: "2026-07-13", status: "expired", issued: "2026-07-13 09:40",
  },
];

const SEED_AUDIT = [
  { id: "a1", ts: "2026-07-13 09:40", type: "GRANT",     agent: "Plumber — one-time key", detail: "systems @ utility · single visit" },
  { id: "a2", ts: "2026-07-13 09:42", type: "GRANT",     agent: "NEO Unit 04",            detail: "layout+inventory+nav+manip · 4 zones" },
  { id: "a3", ts: "2026-07-13 09:43", type: "READ",      agent: "NEO Unit 04",            detail: "pulled scoped housefile (layout)" },
  { id: "a4", ts: "2026-07-13 09:44", type: "DENY",      agent: "NEO Unit 04",            detail: "attempted zone:workshop → policy NO-GO" },
  { id: "a5", ts: "2026-07-13 09:45", type: "PROVISION", agent: "Owner",                  detail: "synthetic housefile rev A plotted · THS-0.1" },
];

/* ── scoped read: the whole thesis in one pure function ── */
function scopedView(file, grant) {
  if (!grant) return null;
  if (grant.status !== "active") {
    return { schema: file.schema, error: "grant_inactive", grant: grant.id, status: grant.status };
  }
  const zoneAllowed = (z) => grant.zones.includes(z.id);
  const out = {
    schema: file.schema,
    grant: { id: grant.id, agent: grant.name, scopes: grant.scopes, window: grant.window },
    policies: { quietHours: file.policies.quietHours, teleop: file.policies.teleop },
  };
  if (grant.scopes.includes("read:layout")) {
    out.zones = file.zones.map((z) => {
      if (z.access === "no-go") return { id: z.id, access: "no-go", boundary: [z.x, z.y, z.w, z.h] }; // boundary always transmits
      if (!zoneAllowed(z)) return { id: z.id, disclosed: false };
      return { id: z.id, name: z.name, access: z.access, boundary: [z.x, z.y, z.w, z.h], note: z.note || undefined };
    });
    out.quirks = file.quirks.filter((q) => zoneAllowed({ id: q.zone })).map((q) => ({ zone: q.zone, text: q.text }));
  }
  if (grant.scopes.includes("read:systems")) {
    out.systems = file.systems
      .filter((s) => grant.zones.includes(s.zone))
      .map((s) => ({ name: s.name, zone: s.zone, detail: s.detail }));
  }
  if (grant.scopes.includes("read:inventory")) {
    out.inventory = file.inventory
      .filter((i) => grant.zones.includes(i.zone))
      .map((i) => ({ name: i.name, zone: i.zone, flags: i.flags, note: i.note || undefined }));
  }
  // safety metadata transmits regardless of inventory scope
  out.safety = file.inventory
    .filter((i) => grant.zones.includes(i.zone))
    .filter((i) => i.flags.some((f) => f === "fragile" || f === "do-not-touch"))
    .map((i) => ({ zone: i.zone, flags: i.flags.filter((f) => f === "fragile" || f === "do-not-touch") }));
  out.capabilities = grant.scopes.filter((s) => s.startsWith("command:"));
  return out;
}

/* ── storage helpers (window.storage · never localStorage) ── */
async function loadKey(key, fallback) {
  try {
    const r = await window.storage.get(key);
    return r ? JSON.parse(r.value) : fallback;
  } catch {
    return fallback;
  }
}
function saveKey(key, value) {
  try {
    window.storage.set(key, JSON.stringify(value)).catch(() => {});
  } catch {}
}

const nowStamp = () => {
  const d = new Date();
  const p = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
};

/* ────────────────────────────────────────────────────────────
   UI
──────────────────────────────────────────────────────────── */

const ACCESS_COLOR = { open: "var(--line)", restricted: "var(--amber)", "no-go": "var(--alert)" };

const TAG_ICON = { water: Droplets, power: Zap, hvac: Wind };

function Chip({ children, tone = "line", solid = false }) {
  const c = tone === "amber" ? "var(--amber)" : tone === "alert" ? "var(--alert)" : "var(--line)";
  return (
    <span
      className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] tracking-wider uppercase"
      style={{
        fontFamily: "var(--mono)",
        color: solid ? "var(--paper)" : c,
        background: solid ? c : "transparent",
        border: `1px solid ${c}`,
        borderRadius: 2,
      }}
    >
      {children}
    </span>
  );
}

function SectionLabel({ children }) {
  return (
    <div className="flex items-center gap-2 mb-3">
      <span className="text-[10px] tracking-[0.25em] uppercase" style={{ fontFamily: "var(--mono)", color: "var(--dim)" }}>
        {children}
      </span>
      <div className="flex-1 h-px" style={{ background: "var(--faint)" }} />
    </div>
  );
}

function FloorPlan({ zones, clearance = null, selected, onSelect, animate }) {
  return (
    <svg viewBox="-6 -6 412 212" className={`w-full ${animate ? "plot" : ""}`} style={{ maxHeight: 300 }}>
      <defs>
        <pattern id="hatch" width="7" height="7" patternTransform="rotate(45)" patternUnits="userSpaceOnUse">
          <line x1="0" y1="0" x2="0" y2="7" stroke="var(--alert)" strokeWidth="1" opacity="0.55" />
        </pattern>
        <pattern id="hatchDim" width="7" height="7" patternTransform="rotate(45)" patternUnits="userSpaceOnUse">
          <line x1="0" y1="0" x2="0" y2="7" stroke="var(--dim)" strokeWidth="1" opacity="0.35" />
        </pattern>
      </defs>
      {/* outer wall */}
      <rect x="0" y="0" width="400" height="200" fill="none" stroke="var(--ink)" strokeWidth="2.5" className="pl" />
      {zones.map((z) => {
        let stroke = ACCESS_COLOR[z.access];
        let fill = "transparent";
        let dash = z.access === "restricted" ? "6 4" : "none";
        let dim = false;
        let tag = null;

        if (clearance) {
          const state = clearance[z.id]; // 'granted' | 'no-go' | 'undisclosed' | 'restricted'
          if (state === "no-go") { stroke = "var(--alert)"; fill = "url(#hatch)"; tag = "NO-GO"; }
          else if (state === "undisclosed") { stroke = "var(--dim)"; fill = "url(#hatchDim)"; dim = true; tag = "WITHHELD"; }
          else if (state === "restricted") { stroke = "var(--amber)"; dash = "6 4"; tag = "WINDOWED"; }
          else { stroke = "var(--ok)"; tag = "GRANTED"; }
        } else if (z.access === "no-go") {
          fill = "url(#hatch)";
        }

        const isSel = selected === z.id;
        return (
          <g key={z.id} onClick={() => onSelect && onSelect(z.id)} style={{ cursor: onSelect ? "pointer" : "default" }}>
            <rect x={z.x + 3} y={z.y + 3} width={z.w - 6} height={z.h - 6}
              fill={fill} stroke={stroke} strokeWidth={isSel ? 2.5 : 1.4} strokeDasharray={dash} className="pl" />
            <text x={z.x + 10} y={z.y + 18} fontSize="9.5" letterSpacing="1.5"
              fill={dim ? "var(--dim)" : "var(--ink)"} style={{ fontFamily: "var(--mono)", textTransform: "uppercase" }}>
              {clearance && clearance[z.id] === "undisclosed" ? "· · ·" : z.name}
            </text>
            {tag && (
              <text x={z.x + 10} y={z.y + z.h - 10} fontSize="7.5" letterSpacing="1.5"
                fill={stroke} style={{ fontFamily: "var(--mono)" }}>{tag}</text>
            )}
            {!clearance && z.access !== "open" && (
              <text x={z.x + 10} y={z.y + z.h - 10} fontSize="7.5" letterSpacing="1.5"
                fill={stroke} style={{ fontFamily: "var(--mono)", textTransform: "uppercase" }}>{z.access}</text>
            )}
          </g>
        );
      })}
      {/* system glyphs pinned to utility wall */}
      <g style={{ fontFamily: "var(--mono)" }}>
        <circle cx="384" cy="30" r="7" fill="var(--paper)" stroke="var(--line)" strokeWidth="1" />
        <text x="384" y="33" fontSize="7" textAnchor="middle" fill="var(--line)">W</text>
        <circle cx="384" cy="52" r="7" fill="var(--paper)" stroke="var(--line)" strokeWidth="1" />
        <text x="384" y="55" fontSize="7" textAnchor="middle" fill="var(--line)">P</text>
        <circle cx="384" cy="74" r="7" fill="var(--paper)" stroke="var(--line)" strokeWidth="1" />
        <text x="384" y="77" fontSize="7" textAnchor="middle" fill="var(--line)">H</text>
      </g>
    </svg>
  );
}

export default function Threshold() {
  const [loaded, setLoaded] = useState(false);
  const [file, setFile] = useState(SEED_FILE);
  const [grants, setGrants] = useState(SEED_GRANTS);
  const [audit, setAudit] = useState(SEED_AUDIT);
  const [tab, setTab] = useState("plan");
  const [selZone, setSelZone] = useState("workshop");
  const [selAgent, setSelAgent] = useState("g-neo");
  const [copied, setCopied] = useState(false);
  const [flash, setFlash] = useState(null);
  const [issuing, setIssuing] = useState(false);
  const [draft, setDraft] = useState({ name: "", kind: "agent", scopes: ["read:layout"], zones: ["kitchen"] });
  const [quirkDraft, setQuirkDraft] = useState("");

  useEffect(() => {
    (async () => {
      setFile(await loadKey("ths:file", SEED_FILE));
      setGrants(await loadKey("ths:grants", SEED_GRANTS));
      setAudit(await loadKey("ths:audit", SEED_AUDIT));
      setLoaded(true);
    })();
  }, []);

  const persistAll = (f = file, g = grants, a = audit) => {
    saveKey("ths:file", f); saveKey("ths:grants", g); saveKey("ths:audit", a);
  };

  const log = (type, agent, detail, g = grants, f = file) => {
    const entry = { id: `a-${Date.now()}`, ts: nowStamp(), type, agent, detail };
    const next = [entry, ...audit].slice(0, 60);
    setAudit(next); persistAll(f, g, next);
    return next;
  };

  const activeGrant = grants.find((g) => g.id === selAgent) || grants[0];
  const payload = useMemo(() => scopedView(file, activeGrant), [file, activeGrant]);

  const clearance = useMemo(() => {
    if (!activeGrant) return {};
    const m = {};
    for (const z of file.zones) {
      if (z.access === "no-go") m[z.id] = "no-go";
      else if (!activeGrant.zones.includes(z.id)) m[z.id] = "undisclosed";
      else if (z.access === "restricted") m[z.id] = "restricted";
      else m[z.id] = "granted";
    }
    return m;
  }, [file, activeGrant]);

  const revoke = (id) => {
    const g = grants.map((x) => (x.id === id ? { ...x, status: "revoked" } : x));
    setGrants(g);
    const name = grants.find((x) => x.id === id)?.name || id;
    log("REVOKE", name, "grant revoked by owner", g);
  };

  const connect = () => {
    if (!activeGrant) return;
    if (activeGrant.status !== "active") {
      log("DENY", activeGrant.name, `connection refused — grant ${activeGrant.status}`);
      setFlash({ tone: "alert", text: `Refused: grant is ${activeGrant.status}.` });
    } else {
      log("READ", activeGrant.name, `pulled scoped housefile (${activeGrant.scopes.filter(s=>s.startsWith("read")).length} scopes)`);
      setFlash({ tone: "ok", text: "Scoped housefile transmitted. Logged." });
    }
    setTimeout(() => setFlash(null), 2600);
  };

  const tryWorkshop = () => {
    if (!activeGrant) return;
    log("DENY", activeGrant.name, "attempted zone:workshop → policy NO-GO");
    setFlash({ tone: "alert", text: "Denied. Workshop is a no-go zone — boundary transmitted, interior withheld." });
    setTimeout(() => setFlash(null), 3200);
  };

  const issue = () => {
    if (!draft.name.trim() || draft.scopes.length === 0 || draft.zones.length === 0) {
      setFlash({ tone: "alert", text: "A grant needs a name, ≥1 scope, ≥1 zone." });
      setTimeout(() => setFlash(null), 2600);
      return;
    }
    const g = {
      id: `g-${Date.now()}`, name: draft.name.trim(), kind: draft.kind, vendor: "",
      scopes: draft.scopes, zones: draft.zones.filter((z) => file.zones.find((x) => x.id === z)?.access !== "no-go"),
      window: "standing", expires: "revocable", status: "active", issued: nowStamp(),
    };
    const next = [g, ...grants];
    setGrants(next);
    log("GRANT", g.name, `${g.scopes.length} scopes · ${g.zones.length} zones`, next);
    setIssuing(false);
    setDraft({ name: "", kind: "agent", scopes: ["read:layout"], zones: ["kitchen"] });
    setSelAgent(g.id);
  };

  const addQuirk = () => {
    if (!quirkDraft.trim()) return;
    const f = { ...file, quirks: [...file.quirks, { id: `q-${Date.now()}`, zone: selZone, text: quirkDraft.trim() }] };
    setFile(f); setQuirkDraft("");
    log("PROVISION", "Owner", `quirk added @ ${selZone}`, grants, f);
  };

  const resetAll = () => {
    setFile(SEED_FILE); setGrants(SEED_GRANTS); setAudit(SEED_AUDIT);
    saveKey("ths:file", SEED_FILE); saveKey("ths:grants", SEED_GRANTS); saveKey("ths:audit", SEED_AUDIT);
    setFlash({ tone: "ok", text: "Housefile re-plotted from seed." });
    setTimeout(() => setFlash(null), 2200);
  };

  const copyJson = async () => {
    try {
      await navigator.clipboard.writeText(JSON.stringify(file, null, 2));
      setCopied(true); setTimeout(() => setCopied(false), 1800);
    } catch {}
  };

  const zone = file.zones.find((z) => z.id === selZone);
  const zoneSystems = file.systems.filter((s) => s.zone === selZone);
  const zoneInv = file.inventory.filter((i) => i.zone === selZone);
  const zoneQuirks = file.quirks.filter((q) => q.zone === selZone);

  const TABS = [
    { id: "plan",   label: "Plan",       icon: MapIcon },
    { id: "grants", label: "Grants",     icon: KeyRound },
    { id: "agent",  label: "Agent view", icon: Eye },
    { id: "log",    label: "Log",        icon: ScrollText },
    { id: "export", label: "THS-0.1",    icon: FileJson },
  ];

  const EVT_TONE = { GRANT: "var(--ok)", READ: "var(--line)", DENY: "var(--alert)", REVOKE: "var(--amber)", PROVISION: "var(--dim)" };

  return (
    <div className="min-h-screen w-full" style={{ background: "var(--paper)", color: "var(--ink)", fontFamily: "var(--body)" }}>
      <style>{`
        :root{
          --paper:#0F2438; --paper2:#0B1D2E; --ink:#EAF4FB; --line:#9FC4DC;
          --dim:#5E7E93; --faint:rgba(159,196,220,.18); --amber:#FFB454; --alert:#FF7A59; --ok:#6FE0B8;
          --display:Impact,'Arial Narrow',sans-serif; --body:system-ui,sans-serif; --mono:ui-monospace,'SFMono-Regular',Consolas,monospace;
        }
        .bp-grid{background-image:linear-gradient(var(--faint) 1px,transparent 1px),linear-gradient(90deg,var(--faint) 1px,transparent 1px);background-size:28px 28px;}
        .plot .pl{stroke-dasharray:1200;stroke-dashoffset:1200;animation:plot 1.6s ease forwards;}
        @keyframes plot{to{stroke-dashoffset:0;}}
        @media (prefers-reduced-motion: reduce){.plot .pl{animation:none;stroke-dashoffset:0;}}
        input,select{outline:none;}
        ::selection{background:var(--amber);color:var(--paper);}
      `}</style>

      <div className="bp-grid min-h-screen">
        <div className="max-w-3xl mx-auto px-4 pb-16">

          {/* ── TITLE BLOCK ── */}
          <div className="mt-5 border" style={{ borderColor: "var(--line)" }}>
            <div className="flex items-stretch">
              <div className="px-4 py-3 border-r flex-1" style={{ borderColor: "var(--line)" }}>
                <div className="text-[10px] tracking-[0.3em] uppercase" style={{ fontFamily: "var(--mono)", color: "var(--dim)" }}>Project</div>
                <div className="leading-none mt-1" style={{ fontFamily: "var(--display)", fontSize: 38, fontWeight: 700, letterSpacing: "0.04em" }}>
                  THRESHOLD
                </div>
                <div className="text-[11px] mt-1" style={{ fontFamily: "var(--mono)", color: "var(--line)" }}>
                  the housefile · owner-held · local-first · every access logged
                </div>
              </div>
              <div className="hidden sm:block" style={{ fontFamily: "var(--mono)" }}>
                <div className="grid grid-cols-2 h-full text-[10px]">
                  {[["SHEET", "THS-0.1"], ["REV", "A"], ["DATE", "2026-07-13"], ["DRAWN", "DEMO"], ["CLIENT", file.dwelling.client], ["DWELLING", file.dwelling.name]].map(([k, v]) => (
                    <div key={k} className="px-3 py-1.5 border-l border-b last:border-b-0" style={{ borderColor: "var(--faint)" }}>
                      <span style={{ color: "var(--dim)" }}>{k} </span>
                      <span style={{ color: "var(--ink)" }}>{v}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
            <div className="sm:hidden px-4 py-1.5 border-t text-[10px] flex flex-wrap gap-x-4"
              style={{ borderColor: "var(--faint)", fontFamily: "var(--mono)", color: "var(--dim)" }}>
              <span>SHEET THS-0.1</span><span>REV A</span><span>2026-07-13</span><span style={{ color: "var(--ink)" }}>CLIENT: {file.dwelling.client}</span>
            </div>
          </div>

          {/* ── TABS ── */}
          <div className="flex gap-1 mt-4 overflow-x-auto pb-1">
            {TABS.map((t) => {
              const I = t.icon; const on = tab === t.id;
              return (
                <button key={t.id} onClick={() => setTab(t.id)}
                  className="flex items-center gap-1.5 px-3 py-2 text-[11px] uppercase tracking-widest whitespace-nowrap"
                  style={{
                    fontFamily: "var(--mono)",
                    color: on ? "var(--paper)" : "var(--line)",
                    background: on ? "var(--line)" : "transparent",
                    border: "1px solid var(--line)", borderRadius: 2,
                  }}>
                  <I size={13} strokeWidth={2} /> {t.label}
                </button>
              );
            })}
          </div>

          {flash && (
            <div className="mt-3 px-3 py-2 text-[12px] flex items-center gap-2"
              style={{ fontFamily: "var(--mono)", border: `1px solid ${flash.tone === "alert" ? "var(--alert)" : "var(--ok)"}`, color: flash.tone === "alert" ? "var(--alert)" : "var(--ok)", borderRadius: 2 }}>
              {flash.tone === "alert" ? <ShieldAlert size={14} /> : <Check size={14} />} {flash.text}
            </div>
          )}

          {!loaded ? (
            <div className="mt-10 text-[12px]" style={{ fontFamily: "var(--mono)", color: "var(--dim)" }}>plotting housefile…</div>
          ) : (
            <>
              {/* ══ PLAN ══ */}
              {tab === "plan" && (
                <div className="mt-5">
                  <FloorPlan zones={file.zones} selected={selZone} onSelect={setSelZone} animate />
                  <div className="flex flex-wrap gap-2 mt-1 text-[10px]" style={{ fontFamily: "var(--mono)", color: "var(--dim)" }}>
                    <span>W water shutoff</span><span>P breaker panel</span><span>H furnace</span>
                    <span className="ml-auto">tap a room to open its sheet</span>
                  </div>

                  {zone && (
                    <div className="mt-5 border p-4" style={{ borderColor: "var(--faint)", background: "var(--paper2)", borderRadius: 2 }}>
                      <div className="flex items-center justify-between gap-2 flex-wrap">
                        <div style={{ fontFamily: "var(--display)", fontSize: 24, fontWeight: 700, letterSpacing: "0.04em", textTransform: "uppercase" }}>
                          {zone.name}
                        </div>
                        <Chip tone={zone.access === "no-go" ? "alert" : zone.access === "restricted" ? "amber" : "line"} solid={zone.access !== "open"}>
                          {zone.access}
                        </Chip>
                      </div>
                      {zone.note && <div className="text-[12px] mt-1" style={{ color: "var(--amber)", fontFamily: "var(--mono)" }}>{zone.note}</div>}

                      {zoneSystems.length > 0 && (
                        <div className="mt-4">
                          <SectionLabel>Systems</SectionLabel>
                          {zoneSystems.map((s) => {
                            const I = TAG_ICON[s.tag] || Zap;
                            return (
                              <div key={s.id} className="flex gap-2.5 items-start py-1.5">
                                <I size={15} style={{ color: "var(--line)", marginTop: 2 }} />
                                <div>
                                  <div className="text-[13px] font-medium">{s.name}</div>
                                  <div className="text-[12px]" style={{ color: "var(--dim)" }}>{s.detail}</div>
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      )}

                      {zoneInv.length > 0 && (
                        <div className="mt-4">
                          <SectionLabel>Inventory</SectionLabel>
                          {zoneInv.map((i) => (
                            <div key={i.id} className="py-1.5">
                              <div className="flex items-center gap-2 flex-wrap">
                                <span className="text-[13px] font-medium">{i.name}</span>
                                {i.flags.map((f) => (
                                  <Chip key={f} tone={f === "do-not-touch" ? "alert" : "amber"}>{f}</Chip>
                                ))}
                              </div>
                              {i.note && <div className="text-[12px]" style={{ color: "var(--dim)" }}>{i.note}</div>}
                            </div>
                          ))}
                        </div>
                      )}

                      <div className="mt-4">
                        <SectionLabel>Quirks</SectionLabel>
                        {zoneQuirks.length === 0 && (
                          <div className="text-[12px]" style={{ color: "var(--dim)" }}>None recorded. Every house has at least one.</div>
                        )}
                        {zoneQuirks.map((q) => (
                          <div key={q.id} className="text-[12px] py-1" style={{ fontFamily: "var(--mono)", color: "var(--line)" }}>› {q.text}</div>
                        ))}
                        <div className="flex gap-2 mt-2">
                          <input value={quirkDraft} onChange={(e) => setQuirkDraft(e.target.value)}
                            placeholder={`Add a ${zone.name.toLowerCase()} quirk…`}
                            className="flex-1 bg-transparent text-[12px] px-2 py-1.5"
                            style={{ border: "1px solid var(--faint)", borderRadius: 2, color: "var(--ink)", fontFamily: "var(--mono)" }} />
                          <button onClick={addQuirk} className="px-3 text-[11px] uppercase tracking-widest"
                            style={{ fontFamily: "var(--mono)", border: "1px solid var(--line)", color: "var(--line)", borderRadius: 2 }}>
                            <Plus size={13} />
                          </button>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* ══ GRANTS ══ */}
              {tab === "grants" && (
                <div className="mt-5">
                  <div className="flex items-center justify-between">
                    <SectionLabel>Keys issued · {grants.filter((g) => g.status === "active").length} active</SectionLabel>
                  </div>
                  {grants.map((g) => (
                    <div key={g.id} className="border p-3.5 mb-3" style={{ borderColor: g.status === "active" ? "var(--faint)" : "transparent", background: "var(--paper2)", borderRadius: 2, opacity: g.status === "active" ? 1 : 0.55 }}>
                      <div className="flex items-center gap-2 flex-wrap">
                        {g.kind === "humanoid" ? <Bot size={16} style={{ color: "var(--line)" }} /> : g.kind === "human" ? <User size={16} style={{ color: "var(--line)" }} /> : <KeyRound size={16} style={{ color: "var(--line)" }} />}
                        <span className="text-[14px] font-semibold">{g.name}</span>
                        {g.vendor && <span className="text-[11px]" style={{ color: "var(--dim)", fontFamily: "var(--mono)" }}>{g.vendor}</span>}
                        <span className="ml-auto">
                          <Chip tone={g.status === "active" ? "line" : g.status === "revoked" ? "alert" : "amber"}>{g.status}</Chip>
                        </span>
                      </div>
                      <div className="flex flex-wrap gap-1.5 mt-2.5">
                        {g.scopes.map((s) => <Chip key={s} tone={s.startsWith("command") ? "amber" : "line"}>{s}</Chip>)}
                      </div>
                      <div className="text-[11px] mt-2.5 flex flex-wrap gap-x-4 gap-y-1" style={{ fontFamily: "var(--mono)", color: "var(--dim)" }}>
                        <span>zones: {g.zones.join(", ")}</span>
                        <span>window: {g.window}</span>
                        <span>expires: {g.expires}</span>
                      </div>
                      {g.status === "active" && (
                        <div className="flex gap-2 mt-3">
                          <button onClick={() => { setSelAgent(g.id); setTab("agent"); }}
                            className="px-3 py-1.5 text-[10px] uppercase tracking-widest"
                            style={{ fontFamily: "var(--mono)", border: "1px solid var(--line)", color: "var(--line)", borderRadius: 2 }}>
                            <Eye size={12} className="inline mr-1" />View as
                          </button>
                          <button onClick={() => revoke(g.id)}
                            className="px-3 py-1.5 text-[10px] uppercase tracking-widest"
                            style={{ fontFamily: "var(--mono)", border: "1px solid var(--alert)", color: "var(--alert)", borderRadius: 2 }}>
                            <X size={12} className="inline mr-1" />Revoke
                          </button>
                        </div>
                      )}
                    </div>
                  ))}

                  {!issuing ? (
                    <button onClick={() => setIssuing(true)}
                      className="w-full py-3 text-[11px] uppercase tracking-[0.2em]"
                      style={{ fontFamily: "var(--mono)", border: "1px dashed var(--line)", color: "var(--line)", borderRadius: 2 }}>
                      <Plus size={13} className="inline mr-1.5" />Issue new grant
                    </button>
                  ) : (
                    <div className="border p-4" style={{ borderColor: "var(--amber)", background: "var(--paper2)", borderRadius: 2 }}>
                      <SectionLabel>New grant</SectionLabel>
                      <div className="flex gap-2 flex-wrap">
                        <input value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })}
                          placeholder="Agent or visitor name"
                          className="flex-1 min-w-[180px] bg-transparent text-[13px] px-2.5 py-2"
                          style={{ border: "1px solid var(--faint)", borderRadius: 2, color: "var(--ink)" }} />
                        <select value={draft.kind} onChange={(e) => setDraft({ ...draft, kind: e.target.value })}
                          className="text-[12px] px-2 py-2"
                          style={{ background: "var(--paper)", border: "1px solid var(--faint)", borderRadius: 2, color: "var(--ink)", fontFamily: "var(--mono)" }}>
                          <option value="humanoid">humanoid</option>
                          <option value="agent">software agent</option>
                          <option value="human">human service</option>
                        </select>
                      </div>
                      <div className="text-[10px] mt-3 mb-1.5 uppercase tracking-widest" style={{ fontFamily: "var(--mono)", color: "var(--dim)" }}>Scopes</div>
                      <div className="flex flex-wrap gap-1.5">
                        {SCOPES.map((s) => {
                          const on = draft.scopes.includes(s.id);
                          return (
                            <button key={s.id} title={s.hint}
                              onClick={() => setDraft({ ...draft, scopes: on ? draft.scopes.filter((x) => x !== s.id) : [...draft.scopes, s.id] })}
                              className="px-2 py-1 text-[10px] uppercase tracking-wider"
                              style={{ fontFamily: "var(--mono)", border: `1px solid ${on ? "var(--amber)" : "var(--faint)"}`, color: on ? "var(--paper)" : "var(--dim)", background: on ? "var(--amber)" : "transparent", borderRadius: 2 }}>
                              {s.id}
                            </button>
                          );
                        })}
                      </div>
                      <div className="text-[10px] mt-3 mb-1.5 uppercase tracking-widest" style={{ fontFamily: "var(--mono)", color: "var(--dim)" }}>Zones · no-go can't be granted</div>
                      <div className="flex flex-wrap gap-1.5">
                        {file.zones.map((z) => {
                          const blocked = z.access === "no-go";
                          const on = draft.zones.includes(z.id);
                          return (
                            <button key={z.id} disabled={blocked}
                              onClick={() => setDraft({ ...draft, zones: on ? draft.zones.filter((x) => x !== z.id) : [...draft.zones, z.id] })}
                              className="px-2 py-1 text-[10px] uppercase tracking-wider"
                              style={{ fontFamily: "var(--mono)", border: `1px solid ${blocked ? "var(--alert)" : on ? "var(--line)" : "var(--faint)"}`, color: blocked ? "var(--alert)" : on ? "var(--paper)" : "var(--dim)", background: on && !blocked ? "var(--line)" : "transparent", borderRadius: 2, opacity: blocked ? 0.6 : 1, textDecoration: blocked ? "line-through" : "none" }}>
                              {z.name}
                            </button>
                          );
                        })}
                      </div>
                      <div className="flex gap-2 mt-4">
                        <button onClick={issue} className="px-4 py-2 text-[11px] uppercase tracking-widest font-medium"
                          style={{ fontFamily: "var(--mono)", background: "var(--amber)", color: "var(--paper)", borderRadius: 2, border: "1px solid var(--amber)" }}>
                          Issue grant
                        </button>
                        <button onClick={() => setIssuing(false)} className="px-4 py-2 text-[11px] uppercase tracking-widest"
                          style={{ fontFamily: "var(--mono)", border: "1px solid var(--faint)", color: "var(--dim)", borderRadius: 2 }}>
                          Cancel
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              )}

              {/* ══ AGENT VIEW ══ */}
              {tab === "agent" && (
                <div className="mt-5">
                  <div className="flex flex-wrap gap-1.5">
                    {grants.map((g) => (
                      <button key={g.id} onClick={() => setSelAgent(g.id)}
                        className="px-2.5 py-1.5 text-[11px] uppercase tracking-wider"
                        style={{ fontFamily: "var(--mono)", border: `1px solid ${selAgent === g.id ? "var(--amber)" : "var(--faint)"}`, color: selAgent === g.id ? "var(--amber)" : "var(--dim)", borderRadius: 2 }}>
                        {g.name}
                      </button>
                    ))}
                  </div>

                  <div className="mt-4">
                    <FloorPlan zones={file.zones} clearance={clearance} />
                  </div>

                  <div className="flex gap-2 mt-2 flex-wrap">
                    <button onClick={connect} className="px-4 py-2 text-[11px] uppercase tracking-widest font-medium"
                      style={{ fontFamily: "var(--mono)", background: "var(--line)", color: "var(--paper)", borderRadius: 2, border: "1px solid var(--line)" }}>
                      Connect as agent
                    </button>
                    <button onClick={tryWorkshop} className="px-4 py-2 text-[11px] uppercase tracking-widest"
                      style={{ fontFamily: "var(--mono)", border: "1px solid var(--alert)", color: "var(--alert)", borderRadius: 2 }}>
                      <Lock size={12} className="inline mr-1.5" />Attempt workshop entry
                    </button>
                  </div>

                  <div className="mt-4">
                    <SectionLabel>Exact payload this key receives — nothing more exists to it</SectionLabel>
                    <pre className="text-[10.5px] leading-relaxed p-3 overflow-auto"
                      style={{ fontFamily: "var(--mono)", background: "var(--paper2)", border: "1px solid var(--faint)", borderRadius: 2, maxHeight: 340, color: "var(--line)" }}>
{JSON.stringify(payload, null, 2)}
                    </pre>
                  </div>
                </div>
              )}

              {/* ══ LOG ══ */}
              {tab === "log" && (
                <div className="mt-5">
                  <SectionLabel>Access ledger · append-only · newest first</SectionLabel>
                  {audit.map((e) => (
                    <div key={e.id} className="flex gap-3 py-2 items-baseline border-b" style={{ borderColor: "var(--faint)" }}>
                      <span className="text-[10px] whitespace-nowrap" style={{ fontFamily: "var(--mono)", color: "var(--dim)" }}>{e.ts}</span>
                      <span className="text-[10px] w-[74px] uppercase tracking-wider" style={{ fontFamily: "var(--mono)", color: EVT_TONE[e.type] || "var(--line)" }}>{e.type}</span>
                      <span className="text-[12px] flex-1">
                        <span className="font-medium">{e.agent}</span>
                        <span style={{ color: "var(--dim)" }}> — {e.detail}</span>
                      </span>
                    </div>
                  ))}
                </div>
              )}

              {/* ══ EXPORT ══ */}
              {tab === "export" && (
                <div className="mt-5">
                  <SectionLabel>Full housefile · schema ths/0.1 · owner eyes only</SectionLabel>
                  <div className="flex gap-2 mb-3 flex-wrap">
                    <button onClick={copyJson} className="px-4 py-2 text-[11px] uppercase tracking-widest"
                      style={{ fontFamily: "var(--mono)", border: "1px solid var(--line)", color: "var(--line)", borderRadius: 2 }}>
                      {copied ? <Check size={12} className="inline mr-1.5" /> : <Copy size={12} className="inline mr-1.5" />}
                      {copied ? "Copied" : "Copy JSON"}
                    </button>
                    <button onClick={resetAll} className="px-4 py-2 text-[11px] uppercase tracking-widest"
                      style={{ fontFamily: "var(--mono)", border: "1px solid var(--amber)", color: "var(--amber)", borderRadius: 2 }}>
                      <RotateCcw size={12} className="inline mr-1.5" />Re-plot from seed
                    </button>
                  </div>
                  <pre className="text-[10.5px] leading-relaxed p-3 overflow-auto"
                    style={{ fontFamily: "var(--mono)", background: "var(--paper2)", border: "1px solid var(--faint)", borderRadius: 2, maxHeight: 420, color: "var(--line)" }}>
{JSON.stringify(file, null, 2)}
                  </pre>
                </div>
              )}
            </>
          )}

          <div className="mt-10 text-[10px] flex flex-wrap gap-x-4 gap-y-1" style={{ fontFamily: "var(--mono)", color: "var(--dim)" }}>
            <span>THRESHOLD v0.1</span>
            <span>the home's data belongs to the home</span>
            <span className="ml-auto" style={{ color: "var(--amber)" }}>synthetic reference · local-only demo</span>
          </div>
        </div>
      </div>
    </div>
  );
}
