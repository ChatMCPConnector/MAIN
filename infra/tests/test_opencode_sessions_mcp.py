"""Tests fuer den dual-schema opencode-sessions MCP-Adapter.

Die Fixtures bauen minimale v1-/v2-Datenbanken in tmp_path. Sie enthalten
nur die Spalten, die der Adapter tatsaechlich liest; echte Sessions oder
persoenliche DBs werden nicht angefasst.
"""

import json
import os
import sqlite3
import subprocess
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "infra/mcp/opencode-sessions-mcp.js"

V1_SCHEMA = """
CREATE TABLE project (id TEXT PRIMARY KEY, worktree TEXT);
CREATE TABLE session (
  id TEXT PRIMARY KEY, project_id TEXT, slug TEXT, directory TEXT, title TEXT,
  version TEXT, parent_id TEXT, model TEXT, agent TEXT, cost REAL,
  tokens_input INTEGER, tokens_output INTEGER, tokens_reasoning INTEGER,
  share_url TEXT, time_created INTEGER, time_updated INTEGER
);
CREATE TABLE message (
  id TEXT PRIMARY KEY, session_id TEXT, time_created INTEGER,
  time_updated INTEGER, data TEXT
);
CREATE TABLE part (
  id TEXT PRIMARY KEY, message_id TEXT, session_id TEXT,
  time_created INTEGER, time_updated INTEGER, data TEXT
);
CREATE TABLE todo (session_id TEXT, content TEXT);
CREATE TABLE session_share (session_id TEXT);
CREATE TABLE event (aggregate_id TEXT);
CREATE TABLE event_sequence (aggregate_id TEXT);
"""

V2_SCHEMA = """
CREATE TABLE project (id TEXT PRIMARY KEY, worktree TEXT);
CREATE TABLE session_v2 (
  id TEXT PRIMARY KEY, project_id TEXT, slug TEXT, directory TEXT, title TEXT,
  version TEXT, parent_id TEXT, model TEXT, agent TEXT, cost REAL,
  tokens_input INTEGER, tokens_output INTEGER, tokens_reasoning INTEGER,
  share_url TEXT, time_created INTEGER, time_updated INTEGER
);
CREATE TABLE session_message (
  id TEXT PRIMARY KEY, session_id TEXT, type TEXT, seq INTEGER,
  time_created INTEGER, time_updated INTEGER, data TEXT
);
"""

NOW = int(time.time() * 1000)


def create_db(path: Path, schema: str) -> None:
    con = sqlite3.connect(path)
    con.executescript(schema)
    con.execute("INSERT INTO project (id, worktree) VALUES ('proj', '/tmp/project')")
    con.commit()
    con.close()


def insert_session(
    path: Path,
    session_id: str,
    directory: str,
    *,
    v2: bool,
    title: str = "Test Session",
    model: str = "glm2api/glm-5.3",
    share_url: str | None = None,
) -> None:
    con = sqlite3.connect(path)
    con.execute(
        f"""INSERT INTO {"session_v2" if v2 else "session"}
           (id, project_id, slug, directory, title, version, model, agent, cost,
            tokens_input, tokens_output, tokens_reasoning, share_url,
            time_created, time_updated)
           VALUES (?, 'proj', ?, ?, ?, ?, ?, 'build', 0, 10, 20, 0, ?, ?, ?)""",
        (session_id, session_id.lower(), directory, title, "2.1.2" if v2 else "1.18.32",
         model, share_url, NOW, NOW),
    )
    con.commit()
    con.close()


def insert_v1_content(path: Path, session_id: str, text: str) -> None:
    con = sqlite3.connect(path)
    con.execute(
        "INSERT INTO message (id, session_id, time_created, time_updated, data) VALUES (?, ?, ?, ?, ?)",
        ("msg_" + session_id, session_id, NOW, NOW, json.dumps({"role": "user", "text": text})),
    )
    con.execute(
        "INSERT INTO part (id, message_id, session_id, time_created, time_updated, data) VALUES (?, ?, ?, ?, ?, ?)",
        ("prt_" + session_id, "msg_" + session_id, session_id, NOW, NOW, json.dumps({"text": text})),
    )
    con.commit()
    con.close()


def insert_v2_content(path: Path, session_id: str, text: str, parts: int = 2) -> None:
    content = [{"type": "text", "text": text}]
    content.extend({"type": "tool"} for _ in range(parts - 1))
    con = sqlite3.connect(path)
    con.execute(
        """INSERT INTO session_message
           (id, session_id, type, seq, time_created, time_updated, data)
           VALUES (?, ?, 'user', 1, ?, ?, ?)""",
        ("msg_" + session_id, session_id, NOW, NOW, json.dumps({"content": content})),
    )
    con.commit()
    con.close()


def count(path: Path, table: str, column: str, value: str) -> int:
    con = sqlite3.connect(path)
    row = con.execute(f"SELECT count(*) FROM {table} WHERE {column}=?", (value,)).fetchone()
    con.close()
    return row[0]


class Mcp:
    def __init__(self, db: Path, cwd: Path):
        cwd.mkdir(parents=True, exist_ok=True)
        env = {
            **os.environ,
            "OPENCODE_DB": str(db),
            "HOME": str(cwd.parent / "home"),
        }
        env.pop("OPENCODE_PID", None)
        self.proc = subprocess.Popen(
            ["node", str(SERVER)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=cwd,
            env=env,
        )
        self.stdin = self.proc.stdin
        self.stdout = self.proc.stdout
        self.stderr = self.proc.stderr
        assert self.stdin is not None and self.stdout is not None and self.stderr is not None
        self.seq = 0
        init = self.rpc("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "1"},
        })
        assert init["result"]["serverInfo"]["name"] == "opencode-sessions"
        self.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        self.stdin.flush()

    def rpc(self, method: str, params: dict | None = None) -> dict:
        self.seq += 1
        request = {"jsonrpc": "2.0", "id": self.seq, "method": method}
        if params is not None:
            request["params"] = params
        self.stdin.write(json.dumps(request) + "\n")
        self.stdin.flush()
        line = self.stdout.readline()
        if not line:
            raise AssertionError(f"MCP-Server beendet: {self.stderr.read()}")
        return json.loads(line)

    def tool(self, name: str, args: dict | None = None) -> dict:
        result = self.rpc("tools/call", {"name": name, "arguments": args or {}})
        if "error" in result:
            raise AssertionError(f"{name}: {result['error']}")
        return json.loads(result["result"]["content"][0]["text"])

    def close(self) -> None:
        self.stdin.close()
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()


@pytest.fixture
def paths(tmp_path: Path) -> dict[str, Path]:
    return {
        "v1": tmp_path / "v1.db",
        "v2": tmp_path / "v2.db",
        "project": tmp_path / "project",
        "cwd": tmp_path / "cwd",
    }


def test_v1_schema(paths: dict[str, Path]) -> None:
    db = paths["v1"]
    create_db(db, V1_SCHEMA)
    sid = "ses_v1"
    insert_session(db, sid, str(paths["project"]), v2=False)
    insert_v1_content(db, sid, "needle v1")

    m = Mcp(db, paths["cwd"])
    try:
        stats = m.tool("db_stats")
        assert stats["schema"] == "v1"
        assert (stats["sessions"], stats["messages"], stats["parts"], stats["events"]) == (1, 1, 1, 0)

        listed = m.tool("list_sessions")
        assert listed[0]["id"] == sid
        assert listed[0]["messages"] == 1
        assert listed[0]["model"] == "glm2api/glm-5.3"

        info = m.tool("session_info", {"session_id": sid})
        assert info["title"] == "Test Session"
        assert info["messages"] == 1
        assert info["todos"] == 0

        found = m.tool("search_sessions", {"query": "needle v1"})
        assert [x["id"] for x in found] == [sid]
    finally:
        m.close()


def test_v1_delete(paths: dict[str, Path]) -> None:
    db = paths["v1"]
    create_db(db, V1_SCHEMA)
    sid = "ses_v1_delete"
    insert_session(db, sid, str(paths["project"]), v2=False)
    insert_v1_content(db, sid, "delete me")
    con = sqlite3.connect(db)
    con.execute("INSERT INTO event (aggregate_id) VALUES ('ses_orphan')")
    con.execute("INSERT INTO event_sequence (aggregate_id) VALUES ('ses_orphan')")
    con.commit()
    con.close()

    m = Mcp(db, paths["cwd"])
    try:
        preview = m.tool("delete_preview", {"keep_active": False})
        assert preview["would_delete"] == 1
        no_confirm = m.rpc("tools/call", {"name": "delete_sessions", "arguments": {"delete_ids": [sid]}})
        assert "error" in no_confirm
        result = m.tool("delete_sessions", {"confirm": True, "delete_ids": [sid], "keep_active": False})
        assert result["deleted"] == 1
        assert result["orphan_events_removed"] == 2
    finally:
        m.close()

    assert count(db, "session", "id", sid) == 0
    assert count(db, "message", "session_id", sid) == 0
    assert count(db, "part", "session_id", sid) == 0


def test_v2_schema_without_legacy_tables(paths: dict[str, Path]) -> None:
    db = paths["v2"]
    create_db(db, V2_SCHEMA)
    sid = "ses_v2"
    model = json.dumps({"providerID": "glm2api", "modelID": "glm-5.3"})
    insert_session(db, sid, str(paths["project"]), v2=True, model=model)
    insert_v2_content(db, sid, "needle v2", parts=3)

    m = Mcp(db, paths["cwd"])
    try:
        stats = m.tool("db_stats")
        assert stats["schema"] == "v2"
        assert (stats["sessions"], stats["messages"], stats["parts"], stats["events"]) == (1, 1, 3, 0)

        listed = m.tool("list_sessions")
        assert listed[0]["model"] == {"providerID": "glm2api", "modelID": "glm-5.3"}

        info = m.tool("session_info", {"session_id": sid})
        assert info["messages"] == 1
        assert info["todos"] == 0
        assert info["model"] == {"providerID": "glm2api", "modelID": "glm-5.3"}

        found = m.tool("search_sessions", {"query": "needle v2"})
        assert [x["id"] for x in found] == [sid]

        result = m.tool("delete_sessions", {"confirm": True, "delete_ids": [sid], "keep_active": False})
        assert result["deleted"] == 1
    finally:
        m.close()

    assert count(db, "session_v2", "id", sid) == 0
    assert count(db, "session_message", "session_id", sid) == 0


def test_v2_migrated_session_deletes_legacy_rows(paths: dict[str, Path]) -> None:
    db = paths["v2"]
    create_db(db, V2_SCHEMA + V1_SCHEMA.split("CREATE TABLE project (id TEXT PRIMARY KEY, worktree TEXT);", 1)[1])
    sid = "ses_v2_migrated"
    insert_session(db, sid, str(paths["project"]), v2=True)
    insert_session(db, sid, str(paths["project"]), v2=False)
    insert_v1_content(db, sid, "legacy")
    insert_v2_content(db, sid, "migrated")

    m = Mcp(db, paths["cwd"])
    try:
        result = m.tool("delete_sessions", {"confirm": True, "delete_ids": [sid], "keep_active": False})
        assert result["deleted"] == 1
    finally:
        m.close()

    for table, column in [
        ("session", "id"), ("session_v2", "id"),
        ("message", "session_id"), ("part", "session_id"),
        ("session_message", "session_id"),
    ]:
        assert count(db, table, column, sid) == 0


def test_v2_current_session_is_protected(paths: dict[str, Path]) -> None:
    db = paths["v2"]
    create_db(db, V2_SCHEMA)
    sid = "ses_v2_current"
    insert_session(db, sid, str(paths["cwd"]), v2=True)

    m = Mcp(db, paths["cwd"])
    try:
        preview = m.tool("delete_preview", {"directory": str(paths["cwd"]), "keep_active": False})
        assert preview["would_delete"] == 0
        assert preview["would_keep"] == 1
        assert sid in preview["protected"]

        result = m.tool("delete_sessions", {"confirm": True, "delete_ids": [sid], "keep_active": False})
        assert result["deleted"] == 0
        assert result["skipped_protected"] == 1
    finally:
        m.close()

    assert count(db, "session_v2", "id", sid) == 1


def test_v2_shared_session_protection_can_be_overridden(paths: dict[str, Path]) -> None:
    db = paths["v2"]
    create_db(db, V2_SCHEMA + "CREATE TABLE session_share (session_id TEXT);")
    sid = "ses_v2_shared"
    insert_session(db, sid, str(paths["project"]), v2=True, share_url="https://opencode.ai/s/test")
    con = sqlite3.connect(db)
    con.execute("INSERT INTO session_share (session_id) VALUES (?)", (sid,))
    con.commit()
    con.close()

    m = Mcp(db, paths["cwd"])
    try:
        preview = m.tool("delete_preview", {"keep_active": False})
        assert preview["would_delete"] == 0
        assert sid in preview["protected"]

        result = m.tool("delete_sessions", {
            "confirm": True, "delete_ids": [sid], "keep_active": False, "keep_shared": True,
        })
        assert result["deleted"] == 1
    finally:
        m.close()

    assert count(db, "session_v2", "id", sid) == 0
    assert count(db, "session_share", "session_id", sid) == 0
