#!/usr/bin/env python3
"""Cline-Free-Modelle live geprueft, mit Klarstellung API vs. CLI.

Warum ein eigenes Skript und nicht eine Erweiterung von nvidia-models.py:
der NVIDIA-Index ist HTML-Scraping ueber build.nvidia.com (models.md +
nimType-Attribute im Katalog-HTML). Cline liefert dagegen eine saubere
JSON-API mit einem eigenen Free-Block. Beide Wege haben nichts gemeinsam
ausser dem Ziel "welche Modelle sind gratis" — ein Vermischen wuerde zwei
völlig verschiedene Abrufwege in einer Funktion erzwingen.

Datenquellen:
  1. GET https://api.cline.bot/api/v1/ai/cline/recommended-models
     -> Bloecke "free", "recommended", "clinePass". Der "free"-Block ist
        die Quelle der Wahrheit fuer die Cline-CLI (er zeigt genau die
        Modelle, die dort im Picker als FREE markiert sind).
  2. POST .../chat/completions je Modell -> API-erreichbar? Tool-Call?
     Kosten? (usage.cost)
  3. .opencode/opencode.json -> provider.cline.whitelist: was bereits
     konfiguriert ist.

Der entscheidende Unterschied, den dieses Skript sichtbar macht:
  stealth/*      -> ueber die API nutzbar, also in opencode verwendbar
  cline-free/*   -> HTTP 403 "only available via Cline product surfaces",
                    d.h. auf IDE-Extension und Cline-CLI beschraenkt.
                    In opencode NICHT verwendbar, egal was man einstellt.
Namen aehnlich, Verfuegbarkeit voellig verschieden.

Cache: ~/.cache/cline-models-cache.json (1h) fuer die teuren Probes.
Die Modellliste wird immer frisch geholt (ein kleiner Request) — Free-Modelle
rotieren, ein 24h-Cache wuerde neue Modelle tagelang unterschlagen.

Key: $CLINE_API_KEY oder ~/.config/landscape/cline.key.

Verwendung:
  python3 infra/scripts/cline-models.py              # Free-Modelle + Status
  python3 infra/scripts/cline-models.py -n 50        # mehr Zeilen
  python3 infra/scripts/cline-models.py --no-probe   # nur Liste, kein LLM-Call
  python3 infra/scripts/cline-models.py --emit-config  # Snippet fuer opencode.json
  python3 infra/scripts/cline-models.py -v           # Details/Fehler
"""
import argparse
import concurrent.futures
import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = "https://api.cline.bot/api/v1"
LIST_URL = f"{BASE}/ai/cline/recommended-models"
CHAT_URL = f"{BASE}/chat/completions"
KEY_FILE = os.path.expanduser("~/.config/landscape/cline.key")
REPO_ROOT = os.path.expanduser("~/../..")
OPENCODE_JSON = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), ".opencode", "opencode.json")
CACHE_FILE = os.path.expanduser("~/.cache/cline-models-cache.json")
CACHE_TTL = 3600
PROBE_TIMEOUT = 120
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) " \
     "Chrome/131.0 Safari/537.36"
VERBOSE = False

# max_tokens MUSS grosszuegig sein: Reasoning-Modelle schreiben zuerst ins
# Reasoning-Feld. Bei kleinem Budget geht es komplett fuers Denken drauf, der
# content bleibt leer, und Cline antwortet HTTP 500 "empty response content".
# Gemessen an stealth/pixel-canary: 1 -> 500, 16 -> 500, 200 -> 200.
# Derselbe Fehler hat keys.sh doctor als "Key kaputt" gemeldet.
PROBE_MAX_TOKENS = 256

TOOL_SPEC = [{
    "type": "function",
    "function": {
        "name": "read",
        "description": "Read a file from disk",
        "parameters": {
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    },
}]


def note(msg):
    if VERBOSE:
        print(msg, file=sys.stderr)


def read_key():
    key = os.environ.get("CLINE_API_KEY")
    if not key and os.path.exists(KEY_FILE):
        with open(KEY_FILE) as f:
            key = f.read().strip()
    return key


def _request(url, data=None, headers=None, timeout=60):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    req.add_header("User-Agent", UA)
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return json.load(res)


def fetch_free_models():
    """Liefert [{id, name, desc}] aus dem free-Block der Cline-Empfehlungen."""
    data = _request(LIST_URL, headers={"Accept": "application/json"})
    free = data.get("free", [])
    return [{"id": m["id"], "name": m.get("name") or m["id"],
             "desc": m.get("desc") or m.get("description") or ""}
            for m in free]


def probe(model_id, key):
    """Prueft ein Modell live: API-erreichbar, Tool-Call, tatsaechliche Kosten.

    'cli_only' ist der Normalfall fuer cline-free/*: HTTP 403 mit dem Text
    "only available via Cline product surfaces". Das ist kein Fehler, sondern
    die dokumentierte Beschraenkung — deshalb eigener Status statt Exception.
    """
    payload = json.dumps({
        "model": model_id,
        "messages": [{"role": "user",
                      "content": "Read /etc/hostname with the read tool."}],
        "tools": TOOL_SPEC,
        "max_tokens": PROBE_MAX_TOKENS,
    }).encode()
    headers = {"Authorization": "Bearer " + key,
               "Content-Type": "application/json"}
    try:
        res = _request(CHAT_URL, data=payload, headers=headers,
                       timeout=PROBE_TIMEOUT)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        if e.code == 403 and "Cline product surfaces" in body:
            return {"status": "cli_only"}
        if e.code == 500 and "empty response content" in body:
            return {"status": "empty", "http": e.code}
        return {"status": "http_%d" % e.code, "err": body[:120]}
    except Exception as e:
        return {"status": "net", "err": repr(e)[:120]}

    choices = res.get("data", {}).get("choices") or [{}]
    msg = choices[0].get("message", {}) if choices else {}
    tool = bool(msg.get("tool_calls"))
    cost = res.get("data", {}).get("usage", {}).get("cost")
    return {"status": "ok", "tool": tool, "cost": cost}


def load_cache():
    try:
        with open(CACHE_FILE) as f:
            c = json.load(f)
        if time.time() - c.get("fetched_at", 0) < CACHE_TTL:
            return c.get("probes", {})
    except Exception:
        pass
    return {}


def save_cache(probes):
    try:
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        with open(CACHE_FILE, "w") as f:
            json.dump({"fetched_at": time.time(), "probes": probes}, f)
    except Exception as e:
        note(f"Hinweis: Cache schreiben fehlgeschlagen: {e!r}")


def read_whitelist():
    try:
        with open(OPENCODE_JSON) as f:
            cfg = json.load(f)
        return set(cfg.get("provider", {}).get("cline", {})
                   .get("whitelist", []))
    except Exception as e:
        note(f"Hinweis: opencode.json nicht lesbar: {e!r}")
        return set()


STATUS_LABEL = {
    "ok": "nutzbar",
    "cli_only": "NUR Cline-CLI",
    "empty": "leer(500)",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", "--top", type=int, default=40)
    ap.add_argument("--no-probe", action="store_true",
                    help="nur die Liste holen, keine LLM-Calls (kein Key noetig)")
    ap.add_argument("--emit-config", action="store_true",
                    help="opencode.json-Snippet fuer nutzbare, fehlende Modelle")
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    global VERBOSE
    VERBOSE = args.verbose

    try:
        models = fetch_free_models()
    except Exception as e:
        print(f"FEHLER: Modelliste nicht ladbar: {e!r}", file=sys.stderr)
        return 1
    if not models:
        print("FEHLER: Cline meldet keine Free-Modelle.", file=sys.stderr)
        return 1

    print(f"{len(models)} Free-Modelle von Cline", file=sys.stderr)
    key = read_key()
    probes = {}
    if args.no_probe:
        print("kein Probe (--no-probe)", file=sys.stderr)
    elif not key:
        print("kein Key gefunden — nur Liste, kein Probe. "
              "Setze CLINE_API_KEY oder lege ~/.config/landscape/cline.key an.",
              file=sys.stderr)
    else:
        cached = {} if args.no_cache else load_cache()
        todo = [m for m in models if m["id"] not in cached]
        probes = dict(cached)
        note(f"Probe: {len(todo)} von {len(models)} (Cache: "
             f"{'aus' if args.no_cache else 'an'})")
        # Wenige Threads: Cline drosselt, und die Probes dauern bei
        # Reasoning-Modellen teils 15+ s (Kaltstart).
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
            futs = {ex.submit(probe, m["id"], key): m["id"] for m in todo}
            for fut in concurrent.futures.as_completed(futs):
                mid = futs[fut]
                try:
                    probes[mid] = fut.result()
                except Exception as e:
                    probes[mid] = {"status": "net", "err": repr(e)[:120]}
                note(f"  {mid} -> {probes[mid]}")
        if not args.no_cache:
            save_cache(probes)

    configured = read_whitelist()
    rows = []
    for m in models:
        p = probes.get(m["id"], {})
        rows.append({
            "id": m["id"], "desc": m["desc"],
            "status": p.get("status", "unbekannt"),
            "tool": p.get("tool"), "cost": p.get("cost"),
            "configured": m["id"] in configured,
        })

    if args.no_probe:
        print(f"{'#':>3}  {'Modell-ID':<44} {'in opencode.json':<16} Beschreibung")
        for i, r in enumerate(rows[:args.top], 1):
            mark = "ja" if r["configured"] else "nein"
            print(f"{i:>3}  {r['id']:<44} {mark:<16} {r['desc'][:44]}")
    else:
        print(f"{'#':>3}  {'Modell-ID':<44} {'Status':<14} "
              f"{'tool':<5} {'cost':<7} cfg  Beschreibung")
        for i, r in enumerate(rows[:args.top], 1):
            label = STATUS_LABEL.get(r["status"], r["status"])
            tool = "ok" if r["tool"] else "-"
            cost = ("0" if r["cost"] == 0 else
                    (f"{r['cost']:.5f}" if isinstance(r["cost"], float)
                     else "-"))
            cfg = "ja" if r["configured"] else "nein"
            print(f"{i:>3}  {r['id']:<44} {label:<14} {tool:<5} "
                  f"{cost:<7} {cfg:<4} {r['desc'][:40]}")

    usable = [r for r in rows if r["status"] == "ok"]
    cli_only = [r for r in rows if r["status"] == "cli_only"]
    if not args.no_probe and key:
        print("", file=sys.stderr)
        print(f"{len(usable)} ueber die API nutzbar (opencode), "
              f"{len(cli_only)} nur in der Cline-CLI/IDE "
              f"(opencode.json kann sie nicht nutzen).", file=sys.stderr)

    if args.emit_config:
        if args.no_probe or not key:
            print("\nFEHLER: --emit-config braucht Probe-Ergebnisse, sonst ist "
                  "nicht\n       feststellbar welche Modelle ueberhaupt nutzbar "
                  "sind. Ohne\n       --no-probe aufrufen (Key noetig).",
                  file=sys.stderr)
            return 1
        missing = [r for r in usable if not r["configured"]]
        if not missing:
            print("\n# alle nutzbaren Free-Modelle sind bereits konfiguriert",
                  file=sys.stderr)
            return 0
        print("\n// fuer .opencode/opencode.json, provider.cline:")
        print('"whitelist": [')
        for r in rows:
            if r["configured"]:
                print(f'  "{r["id"]}",')
        for r in missing:
            print(f'  "{r["id"]}",')
        print("]")
        print("\n// und unter \"models\":", file=sys.stderr)
        for r in missing:
            print(f'"{r["id"]}": {{"name": "{r["desc"] or r["id"]}", '
                  f'"tool_call": true}},')
    return 0


if __name__ == "__main__":
    sys.exit(main())
