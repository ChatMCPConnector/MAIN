#!/usr/bin/env python3
"""Kostenlose LLM-Modelle von Cline und NVIDIA NIM, vereint in einem Skript.

FRAGEN (2026-09-26): Es gab zwei getrennte Skripte mit demselben Zweck und
unterschiedlichen Reifegraden. Zwei Dateien, zwei Caches, zwei Ausgabeformate
und zwei Sortierungen — und die Antwort auf "welches kostenlose Modell ist neu"
musste man je nach Anbieter anders zusammensuchen. Ab jetzt EIN Skript, EIN
Aufruf, EINE Spaltenordnung, EINE Altersregel.

Anbieter und woher deren Daten kommen:

  cline   JSON-API, zwei Quellen:
            1. GET /ai/cline/recommended-models -> Block "free" (= das, was die
               Cline-CLI im Picker als FREE zeigt)
            2. GET /ai/cline/models -> created, context_length, pricing
          Alter: Cline fuehrt created nur fuer 1 von 6 Free-Modellen, darum
          zusaetzlich eine first_seen-Registry (siehe unten).

  nvidia  HTML-Scraping ueber build.nvidia.com:
            1. /models.md -> Vollindex der Slugs
            2. <slug>.md  -> Frontmatter mit `updated` (das einzige verlaessliche
               Datum fuer alle Modelle; die integrate-API liefert nur einen
               Dummy-created)
            3. Katalog-HTML (nimType-Attribut) -> "Free Endpoint"-Flag
          Alter: `updated` aus dem Frontmatter, also ein echtes Datum.

Warum zwei so verschiedene Wege: nvidia liefert eine Dokumentationsseite ohne
API, cline eine API ohne brauchbare Modellhistorie. Beides in eine Funktion zu
zwingen wuerde bedeuten, den billigen JSON-Abruf mit dem teuren HTML-Scraping
zu verheiraten. Der gemeinsame Teil ist deshalb bewusst duenn: fetch_models()
normalisiert nur, was beide brauchen (id, ts, free, desc, provider).

GEMEINSAME REGELN:

  * Default zeigt nur KOSTENLOSE Modelle der LETZTEN 14 TAGE, neueste zuerst.
    14 statt 7, weil manche Promotions rund zwei Wochen laufen — ein kuerzeres
    Fenster blendet Modelle aus, die noch aktiv sind.
  * `--all` hebt beide Filter auf.
  * `--days N` verstellt das Fenster, `--days 0` schaltet es ab.
  * Sortierung ist ueberall "neuestes Datum zuerst", wie es das nvidia-Skript
    schon tat.

SPEZIFIK CLINE — die Verfuegbarkeitsfrage, die sonst niemand beantworten kann:
  stealth/*      geht ueber die Cline-API, also in opencode verwendbar
  cline-free/*   HTTP 403 "only available via Cline product surfaces", also auf
                 IDE-Extension und Cline-CLI beschraenkt. In opencode nicht
                 konfigurierbar, egal welcher Key und egal was in opencode.json
                 steht — generell unbrauchbar, nicht nur schwer einstellbar.
  Namen aehnlich, Verfuegbarkeit voellig verschieden. Deshalb sind die
  CLI-only-Modelle im Default ausgeblendet und tauchen mit `--all` auf.

  Alter: Cline fuehrt fuer 5 der 6 Free-Modelle KEIN created (die
  cline-free/* stehen in keinem Katalog). Deshalb haelt das Skript eine
  first_seen-Registry: beim ersten Lauf notiert, altert NICHT (anders als die
  Probes) und ueberlebt das Verschwinden eines Modells. In der Spalte "Quelle"
  unterscheidbar: `Cline` = herstellerseitig belegt, `erstmals` = "seit wann WIR
  es kennen", nicht "seit wann es existiert" — ohne diese Kennzeichnung liest
  man die zweite Angabe als Erstellungsdatum.

NICHT enthalten: die 17 `:free`-Modelle im Cline-Katalog (OpenRouter-
Passthrough, ebenfalls 0 USD, aber Dauerbestand — u.a. Nemotron, das bei
praktisch jedem Anbieter steht). Sie sind nicht sinnvoll nach "neu" zu filtern
und liegen in der Qualitaet unter den Promotions-Modellen.

Caches (bewusst getrennt, unterschiedliche Haltezeiten):
  ~/.cache/nvidia-models-cache.json  Modellseiten 24 h, first_seen entfaellt
  ~/.cache/cline-models-cache.json   Probes 1 h, first_seen ungekuerzt
Die Modelllisten selbst werden IMMER frisch geholt — Modelle rotieren, ein
Cache wuerde neue Anbieter-Modelle tagelang unterschlagen.

Keys: Cline $CLINE_API_KEY oder ~/.config/landscape/cline.key,
       NVIDIA $NVIDIA_API_KEY oder ~/.config/landscape/nvidia-nim.key

Verwendung:
  free-models                        # beide Anbieter, gratis + <= 14 Tage
  free-models cline                  # nur Cline
  free-models nvidia                 # nur NVIDIA
  free-models --days 30              # juenger als 30 Tage
  free-models --all                  # alles, auch bezahlte/CLI-only
  free-models nvidia --api           # NVIDIA: Live-Check gegen die integrate-API
  free-models --emit-config          # Cline: Snippet fuer .opencode/opencode.json
  free-models --no-cache             # Cache ignorieren
  free-models -v                     # Details/Fehler
"""
import argparse
import concurrent.futures
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
OPENCODE_JSON = os.path.join(REPO_ROOT, ".opencode", "opencode.json")
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/131.0 Safari/537.36")
VERBOSE = False
DEFAULT_DAYS = 14

# --------------------------------------------------------------------------
# Cline
# --------------------------------------------------------------------------
CLINE_BASE = "https://api.cline.bot/api/v1"
CLINE_LIST_URL = f"{CLINE_BASE}/ai/cline/recommended-models"
CLINE_CATALOG_URL = f"{CLINE_BASE}/ai/cline/models"
CLINE_CHAT_URL = f"{CLINE_BASE}/chat/completions"
CLINE_KEY_FILE = os.path.expanduser("~/.config/landscape/cline.key")
CLINE_CACHE = os.path.expanduser("~/.cache/cline-models-cache.json")
CLINE_CACHE_TTL = 3600

# Reasoning-Modelle schreiben zuerst ins Reasoning-Feld, und das kostet
# Budget. Zu knapp gewaehlt gibt es zwei Fehlerbilder, gemessen an
# stealth/pixel-canary MIT Tool-Spec:
#   max_tokens=256  -> HTTP 500 "inference request failed: failed to invoke
#                      model 'stealth/pixel-canary'"
#   max_tokens=512  -> HTTP 200, finish=tool_calls
#   max_tokens=1024 -> HTTP 200, finish=tool_calls
# Ohne Tool-Spec liefert dieselbe Ursache HTTP 500 "empty response content"
# (1 bzw. 16 Tokens) — so hat keys.sh doctor den funktionierenden Key als tot
# gemeldet. Grundwert grosszuegig, und bei genau diesen zwei Fehlerbildern
# EINmal mehr Budget. Ein fester Wert allein waere bei der naechsten
# unbekannten Reasoning-Laenge wieder zu knapp.
CLINE_PROBE_TOKENS = 1024
CLINE_PROBE_TOKENS_RETRY = 2048
CLINE_RETRY_ON = ("empty response content", "inference request failed")
CLINE_PROBE_TIMEOUT = 120
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

# --------------------------------------------------------------------------
# NVIDIA NIM
# --------------------------------------------------------------------------
NV_INDEX_URL = "https://build.nvidia.com/models.md"
NV_CATALOG_URL = ("https://build.nvidia.com/models"
                  "?filters=nimType%3Anim_type_preview")
NV_API_URL = "https://integrate.api.nvidia.com/v1/models"
NV_KEY_FILE = os.path.expanduser("~/.config/landscape/nvidia-nim.key")
NV_CACHE = os.path.expanduser("~/.cache/nvidia-models-cache.json")
NV_CACHE_TTL = 24 * 3600
NV_NEG_TTL = 3600

NV_INDEX_RE = re.compile(r"^- \[(.+?)\]\(/qc69jvmznzxy/(.+?)\.md\)"
                         r"(?:\s*[—–-]\s*(.*))?$", re.M)
NV_GENERIC_DESC = "Experience the leading models to build"
NV_ENTRY_RE = re.compile(
    r'\\"resourceType\\":\\"ENDPOINT\\",\\"resourceId\\":\\"([^\\]+)\\",'
    r'\\"msgTimestamp\\":(\d+)'
)
NV_NIMTYPE_RE = re.compile(r'\\"key\\":\\"nimType\\",\\"values\\":\[(.*?)\]')
NV_HTML_LABELS_RE = re.compile(
    r'\\"value\\":\\"nimType/endpoint\\",\\"display\\":\\"NIM Type\\",'
    r'\\"resourceType\\":\\"ENDPOINT\\",\\"labels\\":\[(.*?)\]')
NV_HTML_UPDATED_RE = re.compile(r'\\"updatedDate\\":\\"([^\\]+)\\"')
NV_HTML_PUB_RE = re.compile(r'\\"publisher\\":\\"([^\\]+)\\"')
NV_HTML_DESC_RE = re.compile(
    r'<meta\s+property="og:description"\s+content="([^"]+)"')
NV_FREE_MARKER = "Free Endpoint"  # ohne Quotes: Payload ist backslash-escaped


def note(msg):
    if VERBOSE:
        print(msg, file=sys.stderr)


def read_key(provider):
    env, path = {
        "cline": ("CLINE_API_KEY", CLINE_KEY_FILE),
        "nvidia": ("NVIDIA_API_KEY", NV_KEY_FILE),
    }[provider]
    key = os.environ.get(env)
    if not key and os.path.exists(path):
        with open(path) as f:
            key = f.read().strip()
    return key


def age_days(ts, now=None):
    if not ts:
        return None
    return ((now or time.time()) - ts) / 86400.0


def day_of(ts):
    if not ts:
        return "-", "-"
    return (datetime.datetime.fromtimestamp(ts, datetime.UTC).strftime("%Y-%m-%d"),
            f"{age_days(ts):.0f}T")


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------
def _curl(url, extra=()):
    if not shutil.which("curl"):
        return None
    r = subprocess.run(["curl", "-sS", "--compressed", "-m", "40", "-A", UA,
                        *extra, url], capture_output=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError(f"curl: {r.stderr.decode()[:200]}")
    return r.stdout.decode("utf-8", errors="ignore")


def fetch_text(url, min_len=500, tries=4):
    # build.nvidia.com drosselt Python-Clients teils mit leeren 200ern
    # -> curl zuerst (browserveraehnlicher), urllib als Fallback, Retry mit Backoff
    last_err = None
    for attempt in range(1, tries + 1):
        try:
            try:
                text = _curl(url)
            except Exception:
                text = None
            if text is None:
                req = urllib.request.Request(url, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=30) as res:
                    text = res.read().decode("utf-8", errors="ignore")
            if len(text) >= min_len:
                return text
            last_err = f"zu kurz ({len(text)} Bytes)"
        except Exception as e:
            last_err = repr(e)
        time.sleep(2 * attempt)
    raise RuntimeError(f"Abruf fehlgeschlagen nach {tries}x {url}: {last_err}")


def json_request(url, data=None, headers=None, timeout=60):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    req.add_header("User-Agent", UA)
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return json.load(res)


def parse_frontmatter(md):
    m = re.match(r"\s*---\s*\n(.*?)\n---\s*\n", md, re.S)
    if not m:
        return {}
    out = {}
    for line in m.group(1).splitlines():
        kv = re.match(r'(\w+):\s*"(.*)"\s*$', line.strip())
        if kv:
            out[kv.group(1)] = kv.group(2)
    return out


# --------------------------------------------------------------------------
# Cache-Helfer (pro Provider getrennte Dateien, unterschiedliche TTLs)
# --------------------------------------------------------------------------
def cache_read(path):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}


def cache_write(path, data):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f)
    except Exception as e:
        note(f"Hinweis: Cache schreiben fehlgeschlagen ({path}): {e!r}")


def read_whitelist():
    try:
        with open(OPENCODE_JSON) as f:
            cfg = json.load(f)
        return set(cfg.get("provider", {}).get("cline", {})
                   .get("whitelist", []))
    except Exception as e:
        note(f"Hinweis: opencode.json nicht lesbar: {e!r}")
        return set()


# --------------------------------------------------------------------------
# Cline
# --------------------------------------------------------------------------
def cline_free_list():
    data = json_request(CLINE_LIST_URL, headers={"Accept": "application/json"})
    return [{"id": m["id"], "desc": m.get("desc") or m.get("description") or ""}
            for m in data.get("free", [])]


def cline_catalog_meta(key):
    """created/context_length/pricing je ID. Optional: kann fehlen."""
    try:
        data = json_request(CLINE_CATALOG_URL,
                            headers={"Authorization": "Bearer " + key,
                                     "Accept": "application/json"},
                            timeout=45).get("data", [])
    except Exception as e:
        note(f"Hinweis: Cline-Katalog-Metadaten nicht ladbar: {e!r}")
        return {}
    return {m.get("id"): m for m in data}


def cline_probe(model_id, key, max_tokens=CLINE_PROBE_TOKENS):
    """API-erreichbar? Tool-Call? echte Kosten? (usage.cost)"""
    payload = json.dumps({
        "model": model_id,
        # Absichtlich kurz: der Probe soll nur beweisen, dass das Modell
        # antwortet, Tools aufruft und nichts kostet.
        "messages": [{"role": "user", "content": "Read /etc/hostname."}],
        "tools": TOOL_SPEC,
        "max_tokens": max_tokens,
    }).encode()
    headers = {"Authorization": "Bearer " + key,
               "Content-Type": "application/json"}
    try:
        res = json_request(CLINE_CHAT_URL, data=payload, headers=headers,
                           timeout=CLINE_PROBE_TIMEOUT)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        if e.code == 403 and "Cline product surfaces" in body:
            return {"status": "cli_only"}
        if e.code == 500 and any(s in body for s in CLINE_RETRY_ON):
            if max_tokens < CLINE_PROBE_TOKENS_RETRY:
                note(f"  {model_id}: 500 bei max_tokens={max_tokens} "
                     f"(Reasoning-Budget) -> Retry mit "
                     f"{CLINE_PROBE_TOKENS_RETRY}")
                return cline_probe(model_id, key, CLINE_PROBE_TOKENS_RETRY)
            return {"status": "empty", "http": e.code}
        return {"status": "http_%d" % e.code, "err": body[:120]}
    except Exception as e:
        return {"status": "net", "err": repr(e)[:120]}
    choices = res.get("data", {}).get("choices") or [{}]
    msg = choices[0].get("message", {}) if choices else {}
    return {"status": "ok", "tool": bool(msg.get("tool_calls")),
            "cost": res.get("data", {}).get("usage", {}).get("cost")}


def _load_cline_probes(fresh):
    if not fresh:
        return {}
    c = cache_read(CLINE_CACHE)
    if time.time() - c.get("fetched_at", 0) < CLINE_CACHE_TTL:
        return dict(c.get("probes", {}))
    return {}


def fetch_cline_models(args, now):
    """-> (rows, usable_rows) mit normalisierten Feldern."""
    key = read_key("cline")
    models = cline_free_list()
    if not models:
        raise RuntimeError("Cline meldet keine Free-Modelle")
    note(f"cline: {len(models)} Free-Modelle gelistet")

    first_seen = dict(cache_read(CLINE_CACHE).get("first_seen", {}))
    probes = {}
    if not args.no_probe and not key:
        note("cline: kein Key — nur Liste, kein Probe "
             "($CLINE_API_KEY oder ~/.config/landscape/cline.key)")
    elif not args.no_probe:
        cached = _load_cline_probes(not args.no_cache)
        live = {m["id"] for m in models}
        # Verwaiste Probes verwerfen: rotierte Modelle wuerden sonst ewig
        # im Cache liegen und die Datei unbegrenzt wachsen.
        probes = {k: v for k, v in cached.items() if k in live}
        todo = [m for m in models if m["id"] not in cached]
        note(f"cline: {len(todo)} Probes (Cache: "
             f"{'aus' if args.no_cache else 'an'})")
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
            futs = {ex.submit(cline_probe, m["id"], key): m["id"] for m in todo}
            for fut in concurrent.futures.as_completed(futs):
                mid = futs[fut]
                try:
                    probes[mid] = fut.result()
                except Exception as e:
                    probes[mid] = {"status": "net", "err": repr(e)[:120]}

    # first_seen: nur unbekanntes bekommt "jetzt". Altert absichtlich nicht und
    # ueberlebt das Verschwinden — sonst waere die Angabe nach einer Rotation
    # wertlos, also genau dann, wenn man sie braucht.
    added = [m["id"] for m in models if m["id"] not in first_seen]
    for m in models:
        first_seen.setdefault(m["id"], now)
    if added:
        note(f"cline: first_seen neu fuer {len(added)}: {', '.join(added)}")
    if not args.no_cache:
        cache_write(CLINE_CACHE, {"fetched_at": time.time(),
                                   "probes": probes,
                                   "first_seen": first_seen})

    meta = cline_catalog_meta(key) if key else {}
    configured = read_whitelist()
    rows = []
    for m in models:
        p = probes.get(m["id"], {})
        c = meta.get(m["id"], {})
        created = c.get("created")
        ts, src = (created, "Cline") if created else \
                  (first_seen.get(m["id"]), "erstmals")
        rows.append({
            "provider": "cline", "id": m["id"], "desc": m["desc"],
            "ts": ts, "date_src": src, "age": age_days(ts, now),
            "free": True, "status": p.get("status", "unbekannt"),
            "tool": p.get("tool"), "cost": p.get("cost"),
            "ctx": c.get("context_length"),
            "configured": m["id"] in configured,
        })
    return rows


# --------------------------------------------------------------------------
# NVIDIA NIM
# --------------------------------------------------------------------------
def nv_api_id(canonical, slug, publisher):
    m = re.match(r"https://build\.nvidia\.com/([^/]+)/([^/]+)/?$", canonical or "")
    return f"{m.group(1)}/{m.group(2)}" if m else f"{publisher}/{slug}"


def nv_page_html(slug):
    """Fallback fuer Slugs ohne statische .md-Seite (nur JS-Shell)."""
    html = fetch_text(f"https://build.nvidia.com/qc69jvmznzxy/{slug}", min_len=20000)
    m = NV_HTML_LABELS_RE.search(html)
    free = bool(m and "nim_type_preview" in m.group(1))
    dates = NV_HTML_UPDATED_RE.findall(html)
    if not dates:
        return None
    pub = NV_HTML_PUB_RE.findall(html)
    desc = NV_HTML_DESC_RE.findall(html)
    import html as _html
    return {"slug": slug, "publisher": pub[0] if pub else "?",
            "updated": max(dates),
            "description": _html.unescape(desc[0]) if desc else "",
            "canonical": "", "free": free}


def nv_page(slug):
    try:
        fm = parse_frontmatter(fetch_text(
            f"https://build.nvidia.com/qc69jvmznzxy/{slug}.md"))
        if not fm.get("updated"):
            raise ValueError("kein Frontmatter (nur JS-Shell?)")
        return {"slug": slug, "publisher": fm.get("publisher", "?"),
                "updated": fm["updated"], "description": fm.get("description", "")[:100],
                "canonical": fm.get("canonical", ""), "free": None}
    except Exception:
        pass
    try:
        return nv_page_html(slug)
    except Exception as e:
        note(f"Hinweis: {slug}: {e!r}")
        return None


def nv_free_names():
    """Slugs mit 'Free Endpoint'-Flag aus dem Katalog-HTML."""
    try:
        html = fetch_text(NV_CATALOG_URL, min_len=50000, tries=2)
    except Exception as e:
        print(f"Hinweis: FREE-Flags nicht ladbar: {e!r}", file=sys.stderr)
        return set()
    entries = NV_ENTRY_RE.findall(html)
    nimtypes = NV_NIMTYPE_RE.findall(html)
    free = set()
    for i, (rid, _ts) in enumerate(entries):
        if i < len(nimtypes) and NV_FREE_MARKER in nimtypes[i]:
            _org, _, name = rid.partition("/")
            free.add(name)
    return free


def nv_api_ids(key):
    if not key:
        return None
    try:
        req = urllib.request.Request(NV_API_URL, headers={
            "User-Agent": UA, "Authorization": "Bearer " + key})
        with urllib.request.urlopen(req, timeout=30) as res:
            return {m["id"] for m in json.load(res).get("data", [])}
    except Exception as e:
        print(f"Hinweis: NVIDIA-API-Check fehlgeschlagen: {e!r}", file=sys.stderr)
        return None


def fetch_nvidia_models(args, now):
    key = read_key("nvidia")
    entries = NV_INDEX_RE.findall(fetch_text(NV_INDEX_URL, min_len=5000))
    slugs = sorted({slug for _n, slug, _d in entries})
    index_desc = {slug: d.strip() for _n, slug, d in entries if d}
    note(f"nvidia: {len(slugs)} Modelle im Index")

    cached = {} if args.no_cache else cache_read(NV_CACHE)
    now_s = time.time()
    if not args.no_cache and \
            now_s - cached.get("fetched_at", 0) >= NV_CACHE_TTL:
        cached = {}
    models = {s: cached["models"][s] for s in slugs
              if s in cached.get("models", {})}
    failed = {k: v for k, v in cached.get("failed", {}).items() if k in slugs}
    todo = [s for s in slugs
            if s not in models and failed.get(s, 0) < now_s - NV_NEG_TTL]
    if todo:
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
            for slug, info in zip(todo, ex.map(nv_page, todo)):
                if info:
                    models[slug] = info
                    failed.pop(slug, None)
                else:
                    failed[slug] = now_s
    free_names = set(cached.get("free_names", [])) | nv_free_names()
    if not args.no_cache:
        cache_write(NV_CACHE, {"fetched_at": now_s, "models": models,
                               "free_names": sorted(free_names),
                               "failed": failed})
    if not models:
        raise RuntimeError("keine NVIDIA-Modell-Details ladbar")

    # --api: Live-Abgleich gegen die integrate-API. Ein Modell kann im
    # Doku-Index stehen und trotzdem nicht abrufbar sein; die API ist die
    # belastbare Aussage. Ohne Key oder bei Fehler bleibt live = None und die
    # Spalte entfaellt, statt etwas zu behaupten.
    live = nv_api_ids(key) if args.api else None
    if args.api and live is None:
        print("Hinweis: --api ohne Ergebnis (kein Key oder Netzfehler); "
              "'live'-Spalte entfaellt.", file=sys.stderr)

    rows = []
    for slug, m in models.items():
        try:
            ts = datetime.datetime.fromisoformat(
                m["updated"].replace("Z", "+00:00")).timestamp()
        except Exception:
            continue
        flag = m.get("free")
        if flag is None:  # .md-Seiten tragen kein FREE-Flag -> Slice fragen
            flag = slug in free_names
        desc = m.get("description", "") or index_desc.get(slug, "")
        if desc.startswith(NV_GENERIC_DESC):
            desc = index_desc.get(slug, "")
        mid = nv_api_id(m.get("canonical", ""), slug, m.get("publisher", "?"))
        rows.append({
            "provider": "nvidia", "id": mid, "desc": desc, "ts": ts,
            "date_src": "NVIDIA", "age": age_days(ts, now), "free": bool(flag),
            "pub": m.get("publisher", "?"),
            "live": (mid in live) if live is not None else None,
        })
    return rows


# --------------------------------------------------------------------------
# Zentrale Funktion
# --------------------------------------------------------------------------
def fetch_models(providers, args, now=None):
    """Holt die Modelle der genannten Anbieter und normalisiert sie.

    Rueckgabe: Liste normalisierter Zeilen mit den Feldern
    provider, id, ts, age, free, desc, date_src — plus providereigene
    Extras (status/tool/cost/ctx bei cline, pub bei nvidia).

    Der gemeinsame Teil ist absichtlich duenn: die beiden Anbieter haben
    voellig verschiedene Abrufwege (JSON-API vs. HTML-Scraping) und
    unterschiedliche belastbare Altersquellen. Was sie gemeinsam haben, ist die
    Form der Antwort — das ist hier normalisiert, nicht der Abruf.
    """
    now = now or time.time()
    rows = []
    for p in providers:
        try:
            rows.extend(fetch_cline_models(args, now) if p == "cline"
                        else fetch_nvidia_models(args, now))
        except Exception as e:
            print(f"FEHLER {p}: {e!r}", file=sys.stderr)
    rows.sort(key=lambda r: -(r["ts"] or 0))
    return rows


# --------------------------------------------------------------------------
# Ausgabe
# --------------------------------------------------------------------------
CLINE_LABEL = {"ok": "nutzbar", "cli_only": "NUR Cline-CLI", "empty": "leer(500)"}


def apply_filters(rows, args, now):
    """Default: nur kostenlos, nur <= --days Tage. --all hebt beides auf.

    Gibt (gefiltert, ungefiltert_nutzbar) zurueck: --emit-config rechnet auf dem
    ungefilterten Stand, denn ein nutzbares, aber aelteres Modell ist in
    opencode weiterhin nutzbar und muss weiterhin vorgeschlagen werden. Der
    Altersfilter ist eine Lesehilfe, keine Nutzungsgrenze.
    """
    usable_all = [r for r in rows if r.get("status") in (None, "ok")]
    if args.all:
        return list(rows), usable_all
    out = []
    for r in rows:
        if r["provider"] == "cline" and args.no_probe is False and \
                r.get("status") not in (None, "ok"):
            continue
        if not r["free"]:
            continue
        if args.days > 0 and r["age"] is not None and r["age"] > args.days:
            continue
        out.append(r)
    return out, usable_all


def render(rows, args):
    if not rows:
        print("Keine Modelle nach den Filtern uebrig (mit --all alles).",
              file=sys.stderr)
        return
    lean = not args.all
    live_col = any(r.get("live") is not None for r in rows)
    head = (f"{'#':>3}  {'Anbieter':<8} {'Modell-ID':<42} {'seit':<11} "
            f"{'Alter':<6} {'Quelle':<9}")
    if lean:
        print(head + f" {'ctx':<8} tool cfg  Beschreibung"
              + ("  live" if live_col else ""))
    else:
        print(head + f" {'FREE':<5} {'Status':<14} {'tool':<5} cost "
                      f"cfg  Beschreibung"
                      + ("  live" if live_col else ""))
    for i, r in enumerate(rows[:args.top], 1):
        day, age = day_of(r["ts"])
        tool = "ok" if r.get("tool") else "-"
        cfg = "ja" if r.get("configured") else "nein"
        ctx = (f"{r['ctx']//1000}k" if r.get("ctx") else "-")
        line = (f"{i:>3}  {r['provider']:<8} {r['id']:<42} {day:<11} {age:<6} "
                f"{r['date_src']:<9} ")
        if lean:
            line += f"{ctx:<8} {tool:<4} {cfg:<4} {r['desc'][:26]}"
        else:
            label = CLINE_LABEL.get(r.get("status"),
                                    r.get("status") or "n/a")
            cost = r.get("cost")
            costs = ("0" if cost == 0 else
                     (f"{cost:.5f}" if isinstance(cost, float) else "-"))
            free = "ja" if r["free"] else "nein"
            line += (f"{free:<5} {label:<14} {tool:<5} {costs:<5} {cfg:<4} "
                     f"{r['desc'][:26]}")
        if live_col:
            lv = r.get("live")
            line += f"  {'live' if lv else ('kein API' if lv is False else '-')}"
        print(line)


def emit_config(usable_all):
    missing = [r for r in usable_all if not r.get("configured")]
    if not missing:
        print("\n# alle nutzbaren Free-Modelle sind bereits konfiguriert",
              file=sys.stderr)
        return 0
    print("\n// fuer .opencode/opencode.json, provider.cline:")
    print('"whitelist": [')
    for r in usable_all:
        if r.get("configured"):
            print(f'  "{r["id"]}",')
    for r in missing:
        print(f'  "{r["id"]}",')
    print("]")
    print("\n// und unter \"models\":", file=sys.stderr)
    for r in missing:
        print(f'"{r["id"]}": {{"name": "{r["desc"] or r["id"]}", '
              f'"tool_call": true}},')
    return 0


def main():
    ap = argparse.ArgumentParser(
        description="Kostenlose Modelle von Cline und NVIDIA NIM, "
                    "neueste zuerst.")
    ap.add_argument("provider", nargs="?", default="alle",
                    choices=["alle", "cline", "nvidia"],
                    help="welcher Anbieter (Default: beide)")
    ap.add_argument("-n", "--top", type=int, default=40)
    ap.add_argument("--days", type=float, default=DEFAULT_DAYS, metavar="TAGE",
                    help=f"nur Modelle, die hoechstens TAGE Tage alt sind "
                         f"(Default: {DEFAULT_DAYS}, 0 = alle)")
    ap.add_argument("--all", action="store_true",
                    help="keine Filter: alles, jedes Alter, auch bezahlte")
    ap.add_argument("--api", action="store_true",
                    help="NVIDIA: Live-Check gegen die integrate-API")
    ap.add_argument("--no-probe", action="store_true",
                    help="Cline: nur Liste, keine LLM-Calls (kein Key noetig)")
    ap.add_argument("--emit-config", action="store_true",
                    help="Cline: Snippet fuer .opencode/opencode.json")
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    global VERBOSE
    VERBOSE = args.verbose

    providers = ["cline", "nvidia"] if args.provider == "alle" \
        else [args.provider]
    if args.emit_config and (args.no_probe or not read_key("cline")):
        print("FEHLER: --emit-config braucht Cline-Probe-Ergebnisse "
              "(Key noetig, kein --no-probe).", file=sys.stderr)
        return 1

    now = time.time()
    rows = fetch_models(providers, args, now)
    if not rows:
        print("Keine Modelle geladen.", file=sys.stderr)
        return 1
    total = len(rows)
    shown, usable_all = apply_filters(rows, args, now)
    if args.all:
        render(shown, args)
    else:
        by = {}
        for r in shown:
            by[r["provider"]] = by.get(r["provider"], 0) + 1
        print(f"{total} geladen, {len(shown)} passen "
              f"(kostenlos, <= {args.days:g} Tage): "
              f"{', '.join(f'{k} {v}' for k, v in sorted(by.items())) or '—'}. "
              f"Alles: --all", file=sys.stderr)
        render(shown, args)
    return emit_config(usable_all) if args.emit_config else 0


if __name__ == "__main__":
    sys.exit(main())
