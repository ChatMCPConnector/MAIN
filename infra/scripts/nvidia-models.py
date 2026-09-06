#!/usr/bin/env python3
"""Neueste NVIDIA-Modelle von build.nvidia.com, neueste zuerst (Default: nur FREE).

Datenquellen (alle oeffentlich, kein API-Key noetig):
  1. https://build.nvidia.com/models.md  -> Vollindex (~200 Eintraege)
  2. <modell>.md je Eintrag              -> Frontmatter (updated, publisher, ...)
     `updated` ist das einzige verlaessliche "neuste"-Datum fuer alle Modelle.
     (Die integrate-API liefert nur einen Dummy-`created`-Wert.)
  3. HTML-Katalog (nimType-Attribut)     -> "Free Endpoint"-Flag (Ausschnitt,
     ca. 24 aktuellste Preview-Modelle; Rest = Status unbekannt).
  4. optional --api                      -> Live-Check auf
     https://integrate.api.nvidia.com/v1/models
     (Key aus $NVIDIA_API_KEY oder ~/.config/landscape/nvidia-nim.key).

Cache: ~/.cache/nvidia-models-cache.json (24h) -> Erstlauf ~1 Min,
Folgeläufe sofort. --no-cache erzwingt Neuabruf.

Verwendung:
  python3 scripts/nvidia-models.py                 # Top 15 freie, neueste zuerst
  python3 scripts/nvidia-models.py -n 30           # Top 30
  python3 scripts/nvidia-models.py --include-paid  # auch Status-unbekannte/bez.
  python3 scripts/nvidia-models.py --api           # + Live-Check auf der API
  python3 scripts/nvidia-models.py -v              # Details/Fehler anzeigen
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
import urllib.request

INDEX_URL = "https://build.nvidia.com/models.md"
CATALOG_URL = "https://build.nvidia.com/models?filters=nimType%3Anim_type_preview"
API_URL = "https://integrate.api.nvidia.com/v1/models"
KEY_FILE = os.path.expanduser("~/.config/landscape/nvidia-nim.key")
CACHE_FILE = os.path.expanduser("~/.cache/nvidia-models-cache.json")
CACHE_TTL = 24 * 3600
NEG_TTL = 3600  # fehlgeschlagene Slugs so lange nicht erneut versuchen
VERBOSE = False


def note(msg):
    if VERBOSE:
        print(msg, file=sys.stderr)
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

INDEX_RE = re.compile(r"^- \[(.+?)\]\(/qc69jvmznzxy/(.+?)\.md\)"
                      r"(?:\s*[—–-]\s*(.*))?$", re.M)
GENERIC_DESC = "Experience the leading models to build"
ENTRY_RE = re.compile(
    r'\\"resourceType\\":\\"ENDPOINT\\",\\"resourceId\\":\\"([^\\]+)\\",'
    r'\\"msgTimestamp\\":(\d+)'
)
NIMTYPE_RE = re.compile(r'\\"key\\":\\"nimType\\",\\"values\\":\[(.*?)\]')
HTML_LABELS_RE = re.compile(
    r'\\"value\\":\\"nimType/endpoint\\",\\"display\\":\\"NIM Type\\",'
    r'\\"resourceType\\":\\"ENDPOINT\\",\\"labels\\":\[(.*?)\]')
HTML_UPDATED_RE = re.compile(r'\\"updatedDate\\":\\"([^\\]+)\\"')
HTML_PUB_RE = re.compile(r'\\"publisher\\":\\"([^\\]+)\\"')
HTML_DESC_RE = re.compile(r'<meta\s+property="og:description"\s+content="([^"]+)"')
FREE_MARKER = 'Free Endpoint'  # ohne Quotes: Payload ist backslash-escaped


def _fetch_curl(url):
    if not shutil.which("curl"):
        return None
    r = subprocess.run(["curl", "-sS", "--compressed", "-m", "40",
                        "-A", UA, url],
                       capture_output=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError(f"curl: {r.stderr.decode()[:200]}")
    return r.stdout.decode("utf-8", errors="ignore")


def _fetch_urllib(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as res:
        return res.read().decode("utf-8", errors="ignore")


def fetch_text(url, min_len=500, tries=4):
    # build.nvidia.com drosselt Python-Clients teils mit leeren 200ern
    # -> curl zuerst (browserveraehnlicher), urllib als Fallback, Retry mit Backoff
    last_err = None
    for attempt in range(1, tries + 1):
        try:
            try:
                text = _fetch_curl(url)
            except Exception:
                text = None
            if text is None:
                text = _fetch_urllib(url)
            if len(text) >= min_len:
                return text
            last_err = f"zu kurz ({len(text)} Bytes)"
        except Exception as e:
            last_err = repr(e)
        time.sleep(2 * attempt)
    raise RuntimeError(f"Abruf fehlgeschlagen nach {tries}x {url}: {last_err}")


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


def load_cache():
    try:
        with open(CACHE_FILE) as f:
            c = json.load(f)
        if time.time() - c.get("fetched_at", 0) < CACHE_TTL:
            return (c.get("models", {}), set(c.get("free_names", [])),
                    c.get("failed", {}))
    except Exception:
        pass
    return {}, set(), {}


def save_cache(models, free_names, failed):
    try:
        os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
        with open(CACHE_FILE, "w") as f:
            json.dump({"fetched_at": time.time(), "models": models,
                       "free_names": sorted(free_names),
                       "failed": failed}, f)
    except Exception as e:
        note(f"Hinweis: Cache schreiben fehlgeschlagen: {e!r}")


def fetch_model_html(slug):
    # Fallback fuer Slugs ohne statische .md-Seite (nur JS-Shell):
    # nimType-Labels + updatedDate sind im HTML eingebettet.
    html = fetch_text(f"https://build.nvidia.com/qc69jvmznzxy/{slug}",
                      min_len=20000)
    m = HTML_LABELS_RE.search(html)
    free = bool(m and "nim_type_preview" in m.group(1))
    dates = HTML_UPDATED_RE.findall(html)
    if not dates:
        return None
    pub = HTML_PUB_RE.findall(html)
    desc = HTML_DESC_RE.findall(html)
    import html as _html
    return {"slug": slug, "title": slug,
            "publisher": pub[0] if pub else "?",
            "updated": max(dates), "description": _html.unescape(desc[0])
            if desc else "",
            "canonical": "", "free": free, "src": "html"}


def fetch_model_page(slug):
    url = f"https://build.nvidia.com/qc69jvmznzxy/{slug}.md"
    try:
        fm = parse_frontmatter(fetch_text(url))
        if not fm.get("updated"):
            raise ValueError("kein Frontmatter (nur JS-Shell?)")
        return {"slug": slug, "title": fm.get("title", slug),
                "publisher": fm.get("publisher", "?"),
                "updated": fm.get("updated", ""),
                "description": fm.get("description", "")[:100],
                "canonical": fm.get("canonical", ""),
                "free": None, "src": "md"}
    except Exception:
        pass
    try:
        return fetch_model_html(slug)
    except Exception as e:
        note(f"Hinweis: {slug}: {e!r}")
        return None


def fetch_free_names():
    # nimType-Bloecke stehen strikt abwechselnd EP/NT im Dokument
    try:
        html = fetch_text(CATALOG_URL, min_len=50000, tries=2)
    except Exception as e:
        print(f"Hinweis: FREE-Flags nicht ladbar: {e!r}", file=sys.stderr)
        return set()
    entries = ENTRY_RE.findall(html)
    nimtypes = NIMTYPE_RE.findall(html)
    free = set()
    for i, (rid, _ts) in enumerate(entries):
        if i < len(nimtypes) and FREE_MARKER in nimtypes[i]:
            _org, _, name = rid.partition("/")
            free.add(name)
    return free


def api_id(canonical, slug, publisher):
    m = re.match(r"https://build\.nvidia\.com/([^/]+)/([^/]+)/?$", canonical or "")
    if m:
        return f"{m.group(1)}/{m.group(2)}"
    return f"{publisher}/{slug}"


def fetch_api_ids():
    key = os.environ.get("NVIDIA_API_KEY")
    if not key and os.path.exists(KEY_FILE):
        with open(KEY_FILE) as f:
            key = f.read().strip()
    if not key:
        return None
    req = urllib.request.Request(API_URL, headers={
        "User-Agent": UA, "Authorization": "Bearer " + key})
    with urllib.request.urlopen(req, timeout=30) as res:
        data = json.load(res)
    return {m["id"] for m in data.get("data", [])}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-n", "--top", type=int, default=15)
    ap.add_argument("--include-paid", action="store_true",
                    help="auch Modelle ohne FREE-Flag listen (Default: nur freie)")
    ap.add_argument("--api", action="store_true",
                    help="zusaetzlich Live-Status auf integrate-API pruefen")
    ap.add_argument("--no-cache", action="store_true",
                    help="Cache ignorieren und alles neu laden")
    ap.add_argument("-v", "--verbose", action="store_true",
                    help="Details und Fehler-Hinweise anzeigen")
    args = ap.parse_args()
    global VERBOSE
    VERBOSE = args.verbose

    try:
        entries = INDEX_RE.findall(fetch_text(INDEX_URL, min_len=5000))
    except Exception as e:
        print(f"FEHLER Index: {e!r}", file=sys.stderr)
        return 1
    slugs = sorted({slug for _name, slug, _desc in entries})
    index_desc = {slug: desc.strip() for _name, slug, desc in entries if desc}
    print(f"Index: {len(slugs)} Modelle, lade Details "
          f"(Cache: {'aus' if args.no_cache else 'an'}) ...", file=sys.stderr)

    cached, cached_free, failed = {}, set(), {}
    if not args.no_cache:
        cached, cached_free, failed = load_cache()
    now = time.time()
    # kürzlich fehlgeschlagene Slugs nicht erneut quälen (Negativ-Cache)
    todo = [s for s in slugs
            if s not in cached and failed.get(s, 0) < now - NEG_TTL]
    skipped = len(slugs) - len(cached) - len(todo)
    models = {s: cached[s] for s in slugs if s in cached}
    if todo:
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
            for slug, info in zip(todo, ex.map(fetch_model_page, todo)):
                if info:
                    models[slug] = info
                    failed.pop(slug, None)
                else:
                    failed[slug] = now
    free_names = set(cached_free) | fetch_free_names()
    if not args.no_cache:
        save_cache(models, free_names, failed)
    if not models:
        print("Keine Modell-Details ladbar.", file=sys.stderr)
        return 1

    rows = []
    for slug, m in models.items():
        try:
            day = m["updated"][:10]
            ts = datetime.datetime.fromisoformat(
                m["updated"].replace("Z", "+00:00")).timestamp()
        except Exception:
            continue
        flag = m.get("free")
        if flag is None:  # .md-Seiten tragen kein FREE-Flag -> Slice fragen
            flag = slug in free_names
        desc = m.get("description", "") or index_desc.get(slug, "")
        if desc.startswith(GENERIC_DESC):  # Boilerplate -> Index-Text nehmen
            desc = index_desc.get(slug, "")
        rows.append({"date": day, "ts": ts, "slug": slug,
                     "pub": m.get("publisher", "?"),
                     "id": api_id(m.get("canonical", ""), slug,
                                  m.get("publisher", "?")),
                     "free": flag,
                     "desc": desc})
    rows.sort(key=lambda r: -r["ts"])
    if not args.include_paid:
        rows = [r for r in rows if r["free"]]

    live = None
    if args.api:
        try:
            live = fetch_api_ids()
        except Exception as e:
            print(f"Hinweis: API-Check fehlgeschlagen: {e!r}", file=sys.stderr)

    scope = "nur FREE" if not args.include_paid else "inkl. bezahlt/unbekannt"
    print(f"{'#':>3} {'Datum':10}  {'Modell-ID':<42}  Beschreibung ({scope})")
    for i, r in enumerate(rows[:args.top], 1):
        line = f"{i:>3} {r['date']:10}  {r['id']:<42.42}"
        if args.include_paid:
            line += " [FREE]" if r["free"] else " [?]"
        if live is not None:
            line += " [live]" if r["id"] in live else " [kein API]"
        if r.get("desc"):
            line += f"  {r['desc'][:62]}"
        print(line)
    if not args.include_paid:
        extra = f", {skipped} übersprungen" if skipped else ""
        print(f"\n({len(rows)} freie von {len(models)} geladenen{extra}; "
              f"FREE-Status aus nimType, Rest mit --include-paid)",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
