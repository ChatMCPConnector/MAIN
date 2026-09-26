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
  3. GET https://api.cline.bot/api/v1/ai/cline/models  -> Anreicherung:
     created, expiration_date, context_length, pricing. Deckt die Free-
     Modelle nur teilweise ab (aktuell 1 von 6), ist also optional: faellt
     der Aufruf aus, laeuft alles ohne die Spalten 'seit' (Cline) und 'ctx'.
  4. .opencode/opencode.json -> provider.cline.whitelist: was bereits
     konfiguriert ist.

Der entscheidende Unterschied, den dieses Skript sichtbar macht:
  stealth/*      -> ueber die API nutzbar, also in opencode verwendbar
  cline-free/*   -> HTTP 403 "only available via Cline product surfaces",
                    d.h. auf IDE-Extension und Cline-CLI beschraenkt.
                    In opencode NICHT verwendbar, egal was man einstellt.
Namen aehnlich, Verfuegbarkeit voellig verschieden.

Umfang: bewusst NUR der Cline-Free-Block (Promotions-Modelle, die in der
Cline-CLI als FREE markiert sind). Der Katalog enthaelt zusaetzlich 17
`:free`-Modelle mit ebenfalls 0 USD Kosten — andere Familie
(OpenRouter-Passthrough), unter anderem Nemotron, das bei praktisch jedem
Anbieter steht. Die werden nicht gelistet, weil sie sich nicht sinnvoll nach
"neu" filtern lassen (sie sind Dauerbestand) und weil die Qualitaet deutlich
unter den Promotions-Modellen liegt.

Alter ("seit"/"Alter"): Cline fuehrt fuer 5 der 6 Free-Modelle KEIN created
— die cline-free/* stehen in keinem Katalog, und der free-Block liefert nur
id/name/desc. Deshalb gibt es zwei Quellen, in der Spalte "Quelle" erkennbar:
  Cline     = Cline-eigenes created aus dem Katalog (nur space-bunny-alpha)
  erstmals   = von uns beim ersten Lauf notiert (first_seen im Cache) —
              die Angabe gilt ab dem Tag, seitdem dieses Skript laeuft, und
              ist "seit wann wir es kennen", nicht "seit wann es existiert".
first_seen ueberlebt bewusst das Verschwinden eines Modells (anders als die
Probes), sonst waere die Angabe nach einer Rotation wertlos.

Cache: ~/.cache/cline-models-cache.json. Probes 1 h (teuer,Live-Calls).
first_seen: ungekuerzt. Die Modellliste wird immer frisch geholt, weil
Free-Modelle rotieren und ein Cache sie tagelang unterschlaege.

Key: $CLINE_API_KEY oder ~/.config/landscape/cline.key.

Verwendung:
  python3 infra/scripts/cline-models.py              # Free-Modelle + Status
  python3 infra/scripts/cline-models.py -n 50        # mehr Zeilen
  python3 infra/scripts/cline-models.py --max-age 3  # nur juengere als 3 Tage
  python3 infra/scripts/cline-models.py --min-age 7  # nur aeltere als 7 Tage
  python3 infra/scripts/cline-models.py --no-probe   # nur Liste, kein LLM-Call
  python3 infra/scripts/cline-models.py --emit-config  # Snippet fuer opencode.json
  python3 infra/scripts/cline-models.py -v           # Details/Fehler
"""
import argparse
import concurrent.futures
import datetime
import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = "https://api.cline.bot/api/v1"
LIST_URL = f"{BASE}/ai/cline/recommended-models"
# Reicherer Katalog als /v1/models: liefert created, expiration_date,
# context_length und pricing je Modell. Deckt die Free-Modelle allerdings
# nur teilweise ab — von den 6 steht aktuell nur stealth/space-bunny-alpha
# drin, die cline-free/* fehlen komplett. Deshalb ist er nur eine Anreicherung
# und nicht die Quelle fuer die Liste.
CATALOG_URL = f"{BASE}/ai/cline/models"
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

# Reasoning-Modelle schreiben zuerst ins Reasoning-Feld, und das kostet
# Budget. Zu knapp gewaehlt gibt es zwei verschiedene Fehlerbilder, beide
# gemessen an stealth/pixel-canary MIT Tool-Spec:
#   max_tokens=256  -> HTTP 500 "inference request failed: failed to invoke
#                      model 'stealth/pixel-canary'"
#   max_tokens=512  -> HTTP 200, finish=tool_calls (reasoning 70 Zeichen)
#   max_tokens=1024 -> HTTP 200, finish=tool_calls
# Ohne Tool-Spec sieht es harmloser aus, liefert aber bei 1 resp. 16 Tokens
# HTTP 500 "empty response content" (dieselbe Ursache, anderes Symptom — so
# hat keys.sh doctor den funktionierenden Key als tot gemeldet).
# Deshalb: grosszuegiger Grundwert, und bei genau diesen beiden Fehlerbildern
# EINmal mit mehr Budget wiederholen. Ein fester Wert allein waere an der
# naechsten unbekannten Reasoning-Laenge wieder zu knapp.
PROBE_MAX_TOKENS = 1024
PROBE_MAX_TOKENS_RETRY = 2048
# Fehlerbilder, die auf zu knappes Reasoning-Budget hindeuten und deshalb
# eskalieren. Alles andere (403, 401, Netz) wird nicht erneut versucht.
RETRY_ON = ("empty response content", "inference request failed")

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


def fetch_catalog_meta(key):
    """Metadaten je Modell-ID: created, context_length, pricing.

    Optional: der Aufruf kann fehlschlagen oder die Free-Modelle nicht
    enthalten. Beides ist kein Fehler — die Ausgabe funktioniert ohne diese
    Anreicherung, nur die Spalten 'seit' und 'ctx' fallen dann spaerlicher aus.
    """
    try:
        data = _request(CATALOG_URL,
                        headers={"Authorization": "Bearer " + key,
                                 "Accept": "application/json"},
                        timeout=45).get("data", [])
    except Exception as e:
        note(f"Hinweis: Katalog-Metadaten nicht ladbar: {e!r}")
        return {}
    out = {}
    for m in data:
        out[m.get("id")] = {
            "created": m.get("created"),
            "expires": m.get("expiration_date"),
            "ctx": m.get("context_length"),
            "pricing": m.get("pricing"),
        }
    return out


def age_days(ts, now=None):
    if not ts:
        return None
    return ((now or time.time()) - ts) / 86400.0


def probe(model_id, key, max_tokens=PROBE_MAX_TOKENS):
    """Prueft ein Modell live: API-erreichbar, Tool-Call, tatsaechliche Kosten.

    'cli_only' ist der Normalfall fuer cline-free/*: HTTP 403 mit dem Text
    "only available via Cline product surfaces". Das ist kein Fehler, sondern
    die dokumentierte Beschraenkung — deshalb eigener Status statt Exception.
    Ein 500 mit "empty response content" oder "inference request failed" wird
    genau einmal mit mehr Reasoning-Budget wiederholt (siehe PROBE_MAX_TOKENS).
    """
    payload = json.dumps({
        "model": model_id,
        "messages": [{"role": "user",
                      "content": "Read /etc/hostname with the read tool."}],
        "tools": TOOL_SPEC,
        "max_tokens": max_tokens,
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
        if e.code == 500 and any(s in body for s in RETRY_ON):
            if max_tokens < PROBE_MAX_TOKENS_RETRY:
                note(f"  {model_id}: 500 bei max_tokens={max_tokens} "
                     f"(Reasoning-Budget) -> Retry mit "
                     f"{PROBE_MAX_TOKENS_RETRY}")
                return probe(model_id, key, PROBE_MAX_TOKENS_RETRY)
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
    """Liest den Cache OHNE Alterspruefung und liefert (probes, first_seen).

    Bewusst getrennt von der TTL: die Probes sind teuer und altern schnell
    (CACHE_TTL), die first_seen-Datenbank nicht — sie ist die einzige
    datierte Quelle fuer die cline-free/*-Modelle, und ein abgelaufener
    Eintrag ist dort wertvoller als ein neuer (sonst waere "Alter" nach
    jeder Cache-Frist wieder 0). Deshalb prueft der Aufrufer die TTL fuer
    die Probes selbst, statt sie hier zu verstecken.
    """
    try:
        with open(CACHE_FILE) as f:
            c = json.load(f)
        return dict(c.get("probes", {})), dict(c.get("first_seen", {}))
    except Exception:
        return {}, {}


def load_fresh_probes(probes):
    """Probes nur uebernehmen, wenn der Cache noch nicht abgelaufen ist."""
    try:
        with open(CACHE_FILE) as f:
            c = json.load(f)
        if time.time() - c.get("fetched_at", 0) < CACHE_TTL:
            return dict(c.get("probes", {}))
    except Exception:
        pass
    return {}


def save_cache(probes, first_seen):
    try:
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        with open(CACHE_FILE, "w") as f:
            json.dump({"fetched_at": time.time(), "probes": probes,
                       "first_seen": first_seen}, f)
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
    ap.add_argument("--min-age", type=float, metavar="TAGE",
                    help="nur Modelle aelter als TAGE Tage (neuere ausblenden)")
    ap.add_argument("--max-age", type=float, metavar="TAGE",
                    help="nur Modelle juenger als TAGE Tage (alte ausblenden)")
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
    # first_seen wird IMMER geladen, unabhaengig von --no-probe und vom Key.
    # Sonst waere im --no-probe-Lauf fuer die cline-free/* jedes Alter 0
    # ("soeben gesehen"), und ein --min-age-Filter wuerde sie faelschlich
    # alle als "neu" behandeln bzw. alle verschlucken.
    _, first_seen = load_cache()
    probes = {}
    if args.no_probe:
        print("kein Probe (--no-probe)", file=sys.stderr)
        # Probes nicht anfassen: --no-probe soll den Cache nicht leeren.
        probes = {} if args.no_cache else load_fresh_probes({})
    elif not key:
        print("kein Key gefunden — nur Liste, kein Probe. "
              "Setze CLINE_API_KEY oder lege ~/.config/landscape/cline.key an.",
              file=sys.stderr)
    else:
        cached = {} if args.no_cache else load_fresh_probes({})
        todo = [m for m in models if m["id"] not in cached]
        # Nur Eintraege fuer aktuell gelistete Modelle uebernehmen. Cline
        # rotiert seine Free-Modelle, und ein Modell, das von der API
        # verschwindet, wuerde sonst fuer immer im Cache liegen: die Anzeige
        # ist zwar nur die frische Liste (kein sichtbarer Fehler), aber die
        # Datei waechst unbegrenzt und ein spaeter wiederkehrendes Modell
        # wuerde ein uraltes, nicht mehr gueltiges Probe-Ergebnis treffen.
        # first_seen wird bewusst NICHT beschieden: das Datum, seit dem ein
        # Modell bei uns laeuft, soll ueber Verschwinden hinweg erhalten
        # bleiben.
        live = {m["id"] for m in models}
        probes = {k: v for k, v in cached.items() if k in live}
        note(f"Probe: {len(todo)} von {len(models)} (Cache: "
             f"{'aus' if args.no_cache else 'an'}, "
             f"{len(cached) - len(probes)} verwaist verworfen)")
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

    # First-Seen-Registry: nur was noch nicht bekannt ist, bekommt "jetzt".
    # Das ist die einzige datierte Quelle fuer die cline-free/*-Modelle, weil
    # Cline sie in keinem Katalog fuehrt (kein created, kein expiration_date).
    now = time.time()
    added = [m["id"] for m in models if m["id"] not in first_seen]
    for m in models:
        first_seen.setdefault(m["id"], now)
    if added:
        note(f"first_seen neu: {len(added)} -> {', '.join(added)}")
    if not args.no_cache:
        save_cache(probes, first_seen)

    meta = fetch_catalog_meta(key) if key else {}
    configured = read_whitelist()
    rows = []
    for m in models:
        p = probes.get(m["id"], {})
        c = meta.get(m["id"], {})
        # Cline-eigenes created ist belastbarer als unsere Beobachtung, aber
        # nur fuer die wenigen Modelle, die im Katalog stehen. Quelle des
        # Datums wird deshalb in der Spalte kenntlich gemacht.
        created = c.get("created")
        if created:
            seen, seen_src = created, "Cline"
        else:
            seen, seen_src = first_seen.get(m["id"]), "erstmals"
        rows.append({
            "id": m["id"], "desc": m["desc"],
            "status": p.get("status", "unbekannt"),
            "tool": p.get("tool"), "cost": p.get("cost"),
            "configured": m["id"] in configured,
            "seen": seen, "seen_src": seen_src,
            "age": age_days(seen, now),
            "ctx": c.get("ctx"),
            "price": c.get("pricing"),
        })
    # Neueste zuerst, wie nvidia-models.py nach Datum sortiert. Modelle ganz
    # ohne Datumsangabe landen hinten, statt eine 0 zu behaupten.
    rows.sort(key=lambda r: -(r["seen"] or 0))

    # Altersfilter. first_seen ist immer befuellt (aus dem Cache geladen, oder
    # im allerersten Lauf auf "jetzt" gesetzt), deshalb kann hier kein Datum
    # fehlen und ein Filter kann nichts stillschweigend verschlucken.
    if args.min_age is not None or args.max_age is not None:
        keep = []
        for r in rows:
            if r["age"] is None:
                keep.append(r)
                continue
            if args.min_age is not None and r["age"] < args.min_age:
                continue
            if args.max_age is not None and r["age"] > args.max_age:
                continue
            keep.append(r)
        hidden = len(rows) - len(keep)
        rows = keep
        if hidden:
            print(f"Altersfilter: {hidden} Modelle ausgeblendet "
                  f"(--min-age/--max-age)", file=sys.stderr)

    def age_cell(r):
        if r["seen"] is None:
            return "-", "-"
        day = datetime.datetime.fromtimestamp(
            r["seen"], datetime.UTC).strftime("%Y-%m-%d")
        return day, f"{r['age']:.0f}T"

    if args.no_probe:
        print(f"{'#':>3}  {'Modell-ID':<44} {'seit':<11} {'Alter':<6} "
              f"{'Quelle':<9} cfg  Beschreibung")
        for i, r in enumerate(rows[:args.top], 1):
            day, age = age_cell(r)
            mark = "ja" if r["configured"] else "nein"
            print(f"{i:>3}  {r['id']:<44} {day:<11} {age:<6} "
                  f"{r['seen_src']:<9} {mark:<4} {r['desc'][:34]}")
    else:
        print(f"{'#':>3}  {'Modell-ID':<44} {'seit':<11} {'Alter':<6} "
              f"{'Quelle':<9} {'Status':<14} {'tool':<5} {'cost':<7} cfg  "
              f"Beschreibung")
        for i, r in enumerate(rows[:args.top], 1):
            day, age = age_cell(r)
            label = STATUS_LABEL.get(r["status"], r["status"])
            tool = "ok" if r["tool"] else "-"
            cost = ("0" if r["cost"] == 0 else
                    (f"{r['cost']:.5f}" if isinstance(r["cost"], float)
                     else "-"))
            cfg = "ja" if r["configured"] else "nein"
            print(f"{i:>3}  {r['id']:<44} {day:<11} {age:<6} "
                  f"{r['seen_src']:<9} {label:<14} {tool:<5} "
                  f"{cost:<7} {cfg:<4} {r['desc'][:32]}")

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
