#!/usr/bin/env node
/**
 * opencode-sessions MCP server (local, stdio).
 *
 * Verwaltet opencode-Sessions direkt in der SQLite-DB
 * (~/.local/share/opencode/opencode.db) — ohne den langsamen Umweg
 * über die opencode-API/CLI. Nutzt nur Node >= 18 und den sqlite3-CLI.
 *
 * Sicherheit:
 *  - DELETE nur nach explizitem confirm=true UND mit Kill-Schutz:
 *    aktive Prozesse (min. der eigene opencode-Prozess) dürfen nicht
 *    ihr eigenes Fenster (Session) verlieren.
 *  - Die Session des Aufrufers wird nie gelöscht (auto-detect via
 *    OPENCODE_PID -> neueste Session des Verzeichnisses).
 */
"use strict";

const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const VERSION = "1.0.0";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function findDb() {
  const override = process.env.OPENCODE_DB;
  if (override) return override;
  return path.join(
    os.homedir(),
    ".local/share/opencode/opencode.db",
  );
}

const DB = findDb();

/** Sicheres SQL-Literal (Inline-Escaping, sqlite3-CLI bindet keine ?-Parameter). */
function lit(v) {
  if (v === null || v === undefined) return "NULL";
  if (typeof v === "number") return String(v);
  if (typeof v === "boolean") return v ? "1" : "0";
  return "'" + String(v).replace(/'/g, "''") + "'";
}

/** Ersetzt ?-Platzhalter durch Literale. Platzhalter in LIKE-Mustern werden verschont. */
function bind(sqlText, params) {
  return sqlText.replace(/\?/g, () => lit(params.shift()));
}

function sql(sqlText, ...params) {
  const flat = params.flat(Infinity);
  const query = bind(sqlText, [...flat]);
  const res = spawnSync(
    "sqlite3",
    ["-json", "-batch", DB],
    { input: query, encoding: "utf8", maxBuffer: 64 * 1024 * 1024, timeout: 120000 },
  );
  if (res.error) throw new Error(`sqlite3 nicht aufrufbar: ${res.error.message}`);
  if (res.status !== 0) {
    throw new Error(`sqlite3 Fehler: ${(res.stderr || "").trim() || "unbekannt"}`);
  }
  const out = (res.stdout || "").trim();
  if (!out) return [];
  try {
    const parsed = JSON.parse(out);
    return Array.isArray(parsed) ? parsed : [parsed];
  } catch {
    return out.split("\n").filter(Boolean).map((l) => {
      try { return JSON.parse(l); } catch { return { raw: l }; }
    });
  }
}

function sqlRun(sqlText) {
  const res = spawnSync("sqlite3", ["-batch", DB], {
    input: sqlText, encoding: "utf8", maxBuffer: 64 * 1024 * 1024, timeout: 120000,
  });
  if (res.error) throw new Error(`sqlite3 nicht aufrufbar: ${res.error.message}`);
  if (res.status !== 0) throw new Error(`sqlite3 Fehler: ${(res.stderr || "").trim()}`);
  return (res.stdout || "").trim();
}

const esc = (v) => String(v).replace(/'/g, "''");
const q = (v) => `'${esc(v)}'`;

function ensureDb() {
  if (!fs.existsSync(DB)) {
    throw new Error(`DB nicht gefunden: ${DB} (läuft opencode in diesem Codespace?)`);
  }
}

// --- Kill-Schutz: welche Sessions gehören zu laufenden opencode-Prozessen? ---

function activeOpencodePids() {
  // Läuft unter Linux via /proc — kein ps-parsing
  const pids = [];
  try {
    for (const entry of fs.readdirSync("/proc")) {
      if (!/^\d+$/.test(entry)) continue;
      let cmdline = "";
      try { cmdline = fs.readFileSync(`/proc/${entry}/cmdline`, "utf8"); } catch { continue; }
      if (cmdline.includes("opencode")) pids.push(Number(entry));
    }
  } catch {
    /* non-linux: ignore */
  }
  if (process.env.OPENCODE_PID && /^\d+$/.test(process.env.OPENCODE_PID)) {
    pids.push(Number(process.env.OPENCODE_PID));
  }
  return pids;
}

/** Map: pid -> { sessionId, cwd, startedAt } für laufende opencode-Prozesse. */
function activeSessions() {
  const result = new Map();
  for (const pid of activeOpencodePids()) {
    let cwd = null;
    try { cwd = fs.readlinkSync(`/proc/${pid}/cwd`); } catch { continue; }
    let startedAt = null;
    try {
      const st = fs.statSync(`/proc/${pid}`);
      startedAt = Math.round(st.mtimeMs);
    } catch { /* ignore */ }
    result.set(pid, { pid, cwd, startedAt });
  }
  return result;
}

/**
 * Schätzt, welche Session-ID zu einem laufenden Prozess gehört:
 * neueste Session im cwd des Prozesses (Lösung über Zeitstempel).
 */
function guessActiveSessionIds() {
  const ids = new Set();
  const procs = activeSessions();
  if (procs.size === 0) return ids;
  // Sessions nach Verzeichnis gruppiert, neueste zuerst
  const byDir = new Map();
  try {
    const rows = sql("SELECT id, directory, time_updated, time_created FROM session ORDER BY time_updated DESC, time_created DESC");
    for (const r of rows) {
      if (!byDir.has(r.directory)) byDir.set(r.directory, r);
    }
  } catch { return ids; }
  for (const p of procs.values()) {
    if (p.cwd && byDir.get(p.cwd)) ids.add(byDir.get(p.cwd).id);
  }
  return ids;
}

function callerSessionId() {
  // neueste Session im cwd des MCP-aufrufenden opencode-Prozesses
  if (process.env.OPENCODE_PID && /^\d+$/.test(process.env.OPENCODE_PID)) {
    try {
      const cwd = fs.readlinkSync(`/proc/${process.env.OPENCODE_PID}/cwd`) || process.cwd();
      const rows = sql("SELECT id, directory FROM session WHERE directory = ? ORDER BY time_updated DESC, time_created DESC LIMIT 1", cwd);
      if (rows.length) return rows[0].id;
    } catch { /* fall through */ }
  }
  const cwd = process.cwd();
  try {
    const rows = sql("SELECT id FROM session WHERE directory = ? ORDER BY time_updated DESC, time_created DESC LIMIT 1", cwd);
    if (rows.length) return rows[0].id;
  } catch { /* ignore */ }
  return null;
}

// ---------------------------------------------------------------------------
// Tools
// ---------------------------------------------------------------------------

function toolListSessions(args) {
  ensureDb();
  const directory = args.directory || null;
  const projectFilter = args.project || null;
  let where = [];
  const params = [];
  if (directory) { where.push("s.directory = ?"); params.push(directory); }
  if (projectFilter) { where.push("p.worktree = ?"); params.push(projectFilter); }
  const whereSql = where.length ? "WHERE " + where.join(" AND ") : "";

  const rows = sql(
    `SELECT s.id, s.title, s.directory, s.agent, s.model,
            (SELECT count(*) FROM message m WHERE m.session_id = s.id) as message_count,
            s.time_created, s.time_updated
     FROM session s JOIN project p ON p.id = s.project_id ${whereSql}
     ORDER BY s.time_updated DESC, s.time_created DESC LIMIT ?`,
    ...params, Math.min(Number(args.limit) || 100, 500));

  const active = guessActiveSessionIds();
  const mine = callerSessionId();
  const now = Date.now();
  return rows.map((r) => ({
    id: r.id,
    title: r.title || "",
    directory: r.directory,
    agent: r.agent || null,
    model: r.model || null,
    messages: r.message_count,
    created: new Date(Number(r.time_created)).toISOString(),
    updated: new Date(Number(r.time_updated)).toISOString(),
    age_days: Math.round(((now - Number(r.time_updated)) / 86400000) * 10) / 10,
    active: active.has(r.id),
    is_current_session: r.id === mine,
  }));
}

function toolDeleteSessions(args) {
  ensureDb();
  if (args.confirm !== true) {
    throw new Error("confirm=true erforderlich (Batch-Löschung). Erst list_sessions + delete_preview nutzen.");
  }
  const keepActive = args.keep_active !== false; // default true
  const keepShared = args.keep_shared === true; // default: shared sind ungeschützt? nein — default protect
  const olderThanDays = args.older_than_days ?? null;
  const keepIds = args.keep_ids || [];
  const deleteIds = args.delete_ids || [];
  const directory = args.directory || null;

  const protectedIds = new Set();
  if (keepActive) {
    for (const id of guessActiveSessionIds()) protectedIds.add(id);
  }
  const mine = callerSessionId();
  if (mine) protectedIds.add(mine);

  // shared sessions: opencode-share Links — standardmäßig schützen
  let sharedIds = new Set();
  try {
    for (const r of sql("SELECT session_id FROM session_share")) sharedIds.add(r.session_id);
  } catch { /* table may not exist */ }
  if (args.keep_shared === true) {
    // explizit: shared NICHT schützen
  } else {
    for (const id of sharedIds) protectedIds.add(id);
  }
  for (const id of keepIds) protectedIds.add(id);

  // Zielmenge bestimmen
  let targets = [];
  if (deleteIds.length) {
    targets = sql(`SELECT id, title FROM session WHERE id IN (${deleteIds.map(q).join(",")})`);
  } else {
    let where = [];
    const params = [];
    if (directory) { where.push("directory = ?"); params.push(directory); }
    if (olderThanDays != null) {
      where.push("time_updated < ?");
      params.push(Date.now() - Number(olderThanDays) * 86400000);
    }
    const whereSql = where.length ? "WHERE " + where.join(" AND ") : "";
    targets = sql(`SELECT id, title FROM session ${whereSql}`, ...params);
  }

  const victims = targets.filter((t) => !protectedIds.has(t.id));
  const skipped = targets.filter((t) => protectedIds.has(t.id));

  let orphansRemoved = 0;
  if (victims.length) {
    const idList = victims.map((v) => q(v.id)).join(",");
    // Kaskade über alle session-bezogenen Tabellen
    sqlRun(`
      BEGIN;
      DELETE FROM part WHERE message_id IN (SELECT id FROM message WHERE session_id IN (${idList}));
      DELETE FROM message WHERE session_id IN (${idList});
      DELETE FROM session_message WHERE session_id IN (${idList});
      DELETE FROM session_input WHERE session_id IN (${idList});
      DELETE FROM session_context_epoch WHERE session_id IN (${idList});
      DELETE FROM session_share WHERE session_id IN (${idList});
      DELETE FROM todo WHERE session_id IN (${idList});
      DELETE FROM event WHERE aggregate_id IN (${idList});
      DELETE FROM event_sequence WHERE aggregate_id IN (${idList});
      DELETE FROM session WHERE id IN (${idList});
      COMMIT;
    `);
  }

  // Events: opencode schreibt pro Message viele Events mit aggregate_id = session_id.
  // Nach Session-Löschung bleiben sonst Orphan-Events zurück (Hauptursache der DB-Größe).
  const evOrphans = sql(`SELECT count(*) as c FROM event e WHERE e.aggregate_id LIKE 'ses_%' AND NOT EXISTS (SELECT 1 FROM session s WHERE s.id = e.aggregate_id)`)[0].c;
  const seqOrphans = sql(`SELECT count(*) as c FROM event_sequence es WHERE es.aggregate_id LIKE 'ses_%' AND NOT EXISTS (SELECT 1 FROM session s WHERE s.id = es.aggregate_id)`)[0].c;
  if (evOrphans > 0) {
    sqlRun(`DELETE FROM event WHERE aggregate_id LIKE 'ses_%' AND aggregate_id NOT IN (SELECT id FROM session)`);
    orphansRemoved += evOrphans;
  }
  if (seqOrphans > 0) {
    sqlRun(`DELETE FROM event_sequence WHERE aggregate_id LIKE 'ses_%' AND aggregate_id NOT IN (SELECT id FROM session)`);
    orphansRemoved += seqOrphans;
  }
  sqlRun("VACUUM;");

  return {
    deleted: victims.length,
    deleted_sessions: victims.slice(0, 50).map((v) => ({ id: v.id, title: v.title || "" })),
    skipped_protected: skipped.length,
    protected_current_session: !!mine,
    orphan_events_removed: orphansRemoved,
  };
}

function toolDeletePreview(args) {
  ensureDb();
  const keepActive = args.keep_active !== false;
  const olderThanDays = args.older_than_days ?? null;
  const directory = args.directory || null;
  const keepIds = args.keep_ids || [];

  const protectedIds = new Set();
  if (keepActive) for (const id of guessActiveSessionIds()) protectedIds.add(id);
  const mine = callerSessionId();
  if (mine) protectedIds.add(mine);
  let sharedIds = new Set();
  try {
    for (const r of sql("SELECT session_id FROM session_share")) sharedIds.add(r.session_id);
  } catch { /* ignore */ }
  if (args.keep_shared !== true) for (const id of sharedIds) protectedIds.add(id);
  for (const id of keepIds) protectedIds.add(id);

  let where = [];
  const params = [];
  if (directory) { where.push("directory = ?"); params.push(directory); }
  if (olderThanDays != null) {
    where.push("time_updated < ?");
    params.push(Date.now() - Number(olderThanDays) * 86400000);
  }
  const whereSql = where.length ? "WHERE " + where.join(" AND ") : "";
  const targets = sql(`SELECT id, title, time_updated FROM session ${whereSql}`, ...params);
  const victims = targets.filter((t) => !protectedIds.has(t.id));
  const skipped = targets.filter((t) => protectedIds.has(t.id));
  return {
    would_delete: victims.length,
    would_keep: skipped.length,
    victims: victims.slice(0, 100).map((v) => ({
      id: v.id,
      title: v.title || "",
      updated: new Date(Number(v.time_updated)).toISOString(),
    })),
    protected: [...protectedIds].filter((id) => skipped.some((s) => s.id === id)),
  };
}

function toolSessionInfo(args) {
  ensureDb();
  const id = args.session_id;
  if (!id) throw new Error("session_id erforderlich");
  const s = sql("SELECT * FROM session WHERE id = ?", id);
  if (!s.length) throw new Error(`Session ${id} nicht gefunden`);
  const sess = s[0];
  const msgCount = sql("SELECT count(*) as c FROM message WHERE session_id = ?", id)[0].c;
  const first = sql("SELECT time_created FROM message WHERE session_id = ? ORDER BY time_created ASC LIMIT 1", id)[0];
  const last = sql("SELECT data FROM message WHERE session_id = ? ORDER BY time_created DESC LIMIT 1", id)[0];
  const todoCount = sql("SELECT count(*) as c FROM todo WHERE session_id = ?", id)[0].c;
  return {
    id: sess.id,
    title: sess.title || "",
    directory: sess.directory,
    parent_id: sess.parent_id || null,
    model: sess.model || null,
    agent: sess.agent || null,
    messages: msgCount,
    todos: todoCount,
    cost: sess.cost,
    tokens: {
      input: sess.tokens_input,
      output: sess.tokens_output,
      reasoning: sess.tokens_reasoning,
    },
    created: new Date(Number(sess.time_created)).toISOString(),
    updated: new Date(Number(sess.time_updated)).toISOString(),
    share_url: sess.share_url || null,
  };
}

function toolSearchSessions(args) {
  ensureDb();
  const term = (args.query || "").trim();
  if (!term) throw new Error("query erforderlich");
  const like = `%${term.replace(/[%_]/g, (m) => "\\" + m)}%`;
  const rows = sql(
    `SELECT s.id, s.title, s.directory, s.time_updated
     FROM session s
     WHERE (s.title LIKE ? ESCAPE '\\' OR s.id IN (
       SELECT m.session_id FROM message m
       JOIN part p ON p.message_id = m.id
       WHERE p.data LIKE ? ESCAPE '\\'
     ))
     ORDER BY s.time_updated DESC LIMIT ?`,
    like, like, [Math.min(Number(args.limit) || 30, 100)]);
  const mine = callerSessionId();
  return rows.map((r) => ({
    id: r.id,
    title: r.title || "",
    directory: r.directory,
    updated: new Date(Number(r.time_updated)).toISOString(),
    is_current_session: r.id === mine,
  }));
}

function toolDbStats(args) {
  ensureDb();
  const sessions = sql("SELECT count(*) as c FROM session")[0].c;
  const messages = sql("SELECT count(*) as c FROM message")[0].c;
  const parts = sql("SELECT count(*) as c FROM part")[0].c;
  const events = sql("SELECT count(*) as c FROM event")[0].c;
  let dbSize = null;
  try { dbSize = fs.statSync(DB).size; } catch { /* ignore */ }
  return {
    db_path: DB,
    db_size_mb: dbSize ? Math.round(dbSize / 1048576 * 10) / 10 : null,
    sessions, messages, parts, events,
    active_opencode_processes: activeOpencodePids().length,
    current_session_id: callerSessionId(),
    version: VERSION,
  };
}

// ---------------------------------------------------------------------------
// MCP protocol (stdio JSON-RPC)
// ---------------------------------------------------------------------------

const TOOLS = [
  {
    name: "list_sessions",
    description: "Listet opencode-Sessions aus der lokalen opencode.db auf (neueste zuerst). Zeigt active/is_current_session je Session. Filter: directory, project (worktree), limit.",
    inputSchema: {
      type: "object",
      properties: {
        directory: { type: "string", description: "Nur Sessions in diesem Verzeichnis (z.B. /workspaces/MAIN)" },
        project: { type: "string", description: "Filter nach Project-Worktree" },
        limit: { type: "number", description: "Max. Ergebnisse (default 100, max 500)" },
      },
    },
  },
  {
    name: "delete_preview",
    description: "Trockenlauf: zeigt, welche Sessions bei delete_sessions gelöscht bzw. geschützt würden (aktive Sessions + aktuelle Session + geteilte Sessions sind geschützt).",
    inputSchema: {
      type: "object",
      properties: {
        older_than_days: { type: "number", description: "Nur Sessions, die länger als X Tage nicht aktualisiert wurden" },
        directory: { type: "string", description: "Nur Sessions in diesem Verzeichnis" },
        keep_ids: { type: "array", items: { type: "string" }, description: "Zusätzlich zu schützende Session-IDs" },
        keep_active: { type: "boolean", description: "Laufende opencode-Prozesse schützen (default true)" },
        keep_shared: { type: "boolean", description: "true = geteilte Sessions trotzdem löschen (default: geschützt)" },
      },
    },
  },
  {
    name: "delete_sessions",
    description: "Löscht opencode-Sessions kaskadierend aus der DB (part, message, session_message, session_input, session_context_epoch, session_share, todo, event, event_sequence) + VACUUM. Schützt automatisch die aktuelle Session und aktive Sessions, sofern nicht anders gewünscht. VORSICHT: unwiderruflich. Immer erst delete_preview laufen lassen.",
    inputSchema: {
      type: "object",
      properties: {
        confirm: { type: "boolean", description: "Muss true sein, sonst kein Löschvorgang" },
        older_than_days: { type: "number", description: "Nur Sessions älter als X Tage (nach letztem Update)" },
        directory: { type: "string", description: "Nur Sessions in diesem Verzeichnis" },
        delete_ids: { type: "array", items: { type: "string" }, description: "Explizite Session-IDs zum Löschen" },
        keep_ids: { type: "array", items: { type: "string" }, description: "Session-IDs, die geschützt bleiben" },
        keep_active: { type: "boolean", description: "Aktive Sessions schützen (default true)" },
        keep_shared: { type: "boolean", description: "true = geteilte Sessions (share-Links) trotzdem löschen (default: geschützt)" },
      },
      required: ["confirm"],
    },
  },
  {
    name: "session_info",
    description: "Details zu einer Session: Nachrichten, Tokens, Kosten, Modell, Share-URL.",
    inputSchema: {
      type: "object",
      properties: {
        session_id: { type: "string" },
      },
      required: ["session_id"],
    },
  },
  {
    name: "search_sessions",
    description: "Sucht Sessions nach Titel oder Message-Inhalt (Volltext über part.data).",
    inputSchema: {
      type: "object",
      properties: {
        query: { type: "string" },
        limit: { type: "number" },
      },
      required: ["query"],
    },
  },
  {
    name: "db_stats",
    description: "Statistik über die opencode.db: Anzahl Sessions/Messages/Parts/Events, DB-Größe, aktive Prozesse, aktuelle Session-ID.",
    inputSchema: { type: "object", properties: {} },
  },
];

const methods = {
  "initialize": (params) => ({
    protocolVersion: params.protocolVersion || "2024-11-05",
    capabilities: { tools: {} },
    serverInfo: { name: "opencode-sessions", version: VERSION },
  }),
  "tools/list": () => ({ tools: TOOLS }),
  "tools/call": (params) => {
    const name = params.name;
    let args = params.arguments || {};
    // opencode übergibt Argumente teils als JSON-String
    if (typeof args === "string") {
      try { args = JSON.parse(args); } catch { args = {}; }
    }
    const fn = {
      "list_sessions": toolListSessions,
      "delete_preview": toolDeletePreview,
      "delete_sessions": toolDeleteSessions,
      "session_info": toolSessionInfo,
      "search_sessions": toolSearchSessions,
      "db_stats": toolDbStats,
    }[name];
    if (!fn) throw new Error(`Unbekanntes Tool: ${name}`);
    const result = fn(args);
    return {
      content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
    };
  },
  "ping": () => ({}),
};

let buffer = "";
process.stdin.setEncoding("utf8");
process.stdin.on("data", (chunk) => {
  buffer += chunk;
  let idx;
  while ((idx = buffer.indexOf("\n")) >= 0) {
    const line = buffer.slice(0, idx).trim();
    buffer = buffer.slice(idx + 1);
    if (!line) continue;
    handleLine(line);
  }
});
process.stdin.on("end", () => process.exit(0));

function send(obj) {
  process.stdout.write(JSON.stringify(obj) + "\n");
}

function handleLine(line) {
  let msg;
  try { msg = JSON.parse(line); } catch { return; }
  const { id, method, params } = msg;
  if (method === "notifications/initialized" || method === "notifications/cancelled") return;
  try {
    const handler = methods[method];
    if (!handler) throw new Error(`Methode nicht unterstützt: ${method}`);
    const result = handler(params || {});
    if (id !== undefined) send({ jsonrpc: "2.0", id, result });
  } catch (err) {
    if (id !== undefined) {
      send({
        jsonrpc: "2.0", id,
        error: { code: -32000, message: err.message || String(err) },
      });
    }
  }
}
