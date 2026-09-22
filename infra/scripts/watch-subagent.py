#!/usr/bin/env python3
"""Live-Watcher für OpenCode-Subagenten (rein lesend, greift nicht in die Session ein)."""
import json
import sqlite3
import sys
import time

DB_PATH = "/home/vscode/.local/share/opencode/opencode.db"


def main():
    session_id = sys.argv[1] if len(sys.argv) > 1 else None

    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    c = conn.cursor()

    if not session_id:
        c.execute(
            "SELECT id, parent_id, agent, model FROM session "
            "WHERE parent_id IS NOT NULL "
            "ORDER BY time_created DESC LIMIT 1"
        )
        row = c.fetchone()
        if not row:
            print("Kein aktiver Subagent gefunden.")
            return
        session_id = row[0]
        print(f"📡 Beobachte neuesten Subagenten: {session_id} (Agent: {row[2]})", flush=True)
    else:
        print(f"📡 Beobachte Session: {session_id}", flush=True)

    seen_parts = set()
    print("Drücke Strg+C zum Beenden.\n" + "=" * 60, flush=True)

    try:
        while True:
            c.execute(
                "SELECT id, data FROM part WHERE session_id = ? ORDER BY time_created ASC",
                (session_id,),
            )
            rows = c.fetchall()
            for pid, pdata in rows:
                if pid in seen_parts:
                    continue
                seen_parts.add(pid)
                try:
                    d = json.loads(pdata)
                except Exception:
                    continue

                ptype = d.get("type")
                if ptype == "tool":
                    state = d.get("state", {})
                    status = state.get("status", "running")
                    tool = d.get("tool")
                    inp = str(state.get("input", ""))
                    if len(inp) > 120:
                        inp = inp[:117] + "..."
                    err = state.get("error", "")
                    symbol = "✓" if status == "completed" else ("✗" if status == "error" else "⏳")
                    print(f"[{symbol} {status:<9}] Tool: \033[1;36m{tool}\033[0m | Args: {inp}", flush=True)
                    if err:
                        print(f"           \033[31mFehler: {err[:120]}\033[0m", flush=True)
                elif ptype == "text":
                    txt = d.get("text", "").strip()
                    if txt:
                        first_line = txt.split("\n")[0]
                        print(f"💬 \033[1;32mAntwort:\033[0m {first_line[:120]}", flush=True)
                elif ptype == "step-start":
                    print(f"▶️  \033[33mNeuer Schritt gestartet (Modell denkt nach / Thinking...)...\033[0m", flush=True)

            time.sleep(1.5)
    except KeyboardInterrupt:
        print("\nWatcher beendet.")


if __name__ == "__main__":
    main()
