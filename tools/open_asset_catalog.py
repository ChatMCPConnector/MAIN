#!/usr/bin/env python3
"""Resolve and search CC0 assets from Poly Haven and ambientCG.

The Unity project keeps binary art out of Git. ChatGPT edits AssetSources/open-assets.json,
this resolver converts provider IDs into a small lock file, and Unity downloads only the
resolved files during CI builds.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

USER_AGENT = "NeonRift-GitHub-Open-Asset-Resolver/1.0"
POLYHAVEN_ASSETS = "https://api.polyhaven.com/assets"
POLYHAVEN_FILES = "https://api.polyhaven.com/files/{asset_id}"
AMBIENTCG_ASSETS = "https://ambientcg.com/api/v3/assets"
SUPPORTED_PROVIDERS = {"polyhaven", "ambientcg"}
SUPPORTED_KINDS = {"model", "material", "hdri"}
SAFE_TARGET = re.compile(r"^[A-Za-z0-9._/-]+$")
RESOLUTION_RE = re.compile(r"(?<![0-9])(\d{1,2})k(?![a-z0-9])", re.IGNORECASE)


class CatalogError(RuntimeError):
    pass


@dataclass(frozen=True)
class DownloadCandidate:
    url: str
    path_tokens: tuple[str, ...]
    size: int | None = None
    md5: str | None = None
    relative_path: str | None = None
    dependencies: tuple[dict[str, Any], ...] = ()

    @property
    def haystack(self) -> str:
        return " ".join((*self.path_tokens, self.url)).lower()


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CatalogError(f"Missing JSON file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise CatalogError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise CatalogError(f"Top level of {path} must be an object")
    return value


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def request_json(url: str) -> Any:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.load(response)
    except Exception as exc:
        raise CatalogError(f"Request failed: {url}: {exc}") from exc


def normalize_resolution(value: str | None, fallback: str = "2k") -> str:
    candidate = (value or fallback).strip().lower()
    if not re.fullmatch(r"\d{1,2}k", candidate):
        raise CatalogError(f"Invalid resolution '{value}'. Use values such as 1k, 2k or 4k.")
    return candidate


def validate_target(value: str) -> str:
    target = value.strip().replace("\\", "/").strip("/")
    if not target or not SAFE_TARGET.fullmatch(target):
        raise CatalogError(f"Unsafe or empty target path: {value!r}")
    parts = target.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise CatalogError(f"Unsafe target path: {value!r}")
    return target


def validate_manifest(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    if manifest.get("schemaVersion") != 1:
        raise CatalogError("open-assets.json must use schemaVersion 1")
    defaults = manifest.get("defaults") or {}
    if not isinstance(defaults, dict):
        raise CatalogError("defaults must be an object")
    default_resolution = normalize_resolution(defaults.get("resolution"), "2k")
    default_max = defaults.get("maxDownloadBytes", 104_857_600)
    if not isinstance(default_max, int) or default_max <= 0:
        raise CatalogError("defaults.maxDownloadBytes must be a positive integer")

    raw_assets = manifest.get("assets")
    if not isinstance(raw_assets, list):
        raise CatalogError("assets must be an array")

    normalized: list[dict[str, Any]] = []
    identities: set[tuple[str, str, str]] = set()
    for index, raw in enumerate(raw_assets):
        if not isinstance(raw, dict):
            raise CatalogError(f"assets[{index}] must be an object")
        if raw.get("enabled", True) is False:
            continue
        provider = str(raw.get("provider", "")).strip().lower()
        asset_id = str(raw.get("id", "")).strip()
        kind = str(raw.get("kind", "")).strip().lower()
        if provider not in SUPPORTED_PROVIDERS:
            raise CatalogError(f"assets[{index}].provider must be polyhaven or ambientcg")
        if not asset_id or not re.fullmatch(r"[A-Za-z0-9_-]+", asset_id):
            raise CatalogError(f"assets[{index}].id is missing or invalid")
        if kind not in SUPPORTED_KINDS:
            raise CatalogError(f"assets[{index}].kind must be model, material or hdri")
        resolution = normalize_resolution(raw.get("resolution"), default_resolution)
        preferred_format = str(raw.get("format", "")).strip().lower()
        if not preferred_format:
            preferred_format = "gltf" if kind == "model" else ("hdr" if kind == "hdri" else "png")
        target = validate_target(str(raw.get("target") or f"{provider}/{asset_id}"))
        max_bytes = raw.get("maxDownloadBytes", default_max)
        if not isinstance(max_bytes, int) or max_bytes <= 0:
            raise CatalogError(f"assets[{index}].maxDownloadBytes must be a positive integer")
        identity = (provider, asset_id.lower(), target.lower())
        if identity in identities:
            raise CatalogError(f"Duplicate enabled asset entry: {provider}/{asset_id} -> {target}")
        identities.add(identity)
        normalized.append(
            {
                "provider": provider,
                "id": asset_id,
                "kind": kind,
                "resolution": resolution,
                "format": preferred_format,
                "target": target,
                "maxDownloadBytes": max_bytes,
            }
        )
    return normalized


def iter_url_nodes(node: Any, path: tuple[str, ...] = ()) -> Iterable[DownloadCandidate]:
    if isinstance(node, dict):
        url = node.get("url") or node.get("downloadUrl") or node.get("download_url") or node.get("downloadLink")
        if isinstance(url, str) and url.startswith("https://"):
            size = node.get("size") or node.get("fileSize") or node.get("file_size")
            if not isinstance(size, int):
                size = None
            md5 = node.get("md5") if isinstance(node.get("md5"), str) else None
            relative_path = None
            for key in ("path", "fileName", "filename", "name"):
                if isinstance(node.get(key), str):
                    relative_path = node[key]
                    break
            dependencies = tuple(iter_dependencies(node.get("include") or node.get("dependencies")))
            yield DownloadCandidate(url, path, size, md5, relative_path, dependencies)
        for key, value in node.items():
            if key in {"url", "downloadUrl", "download_url", "downloadLink", "include", "dependencies"}:
                continue
            yield from iter_url_nodes(value, (*path, str(key)))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from iter_url_nodes(value, (*path, str(index)))


def iter_dependencies(node: Any, path: tuple[str, ...] = ()) -> Iterable[dict[str, Any]]:
    if isinstance(node, dict):
        url = node.get("url") or node.get("downloadUrl") or node.get("download_url") or node.get("downloadLink")
        if isinstance(url, str) and url.startswith("https://"):
            name = node.get("path") or node.get("fileName") or node.get("filename") or node.get("name")
            if not isinstance(name, str) or not name:
                name = path[-1] if path else basename_from_url(url)
            yield {
                "url": url,
                "path": sanitize_relative_file(name, url),
                "size": node.get("size") if isinstance(node.get("size"), int) else None,
                "md5": node.get("md5") if isinstance(node.get("md5"), str) else None,
            }
        for key, value in node.items():
            if key in {"url", "downloadUrl", "download_url", "downloadLink"}:
                continue
            yield from iter_dependencies(value, (*path, str(key)))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from iter_dependencies(value, (*path, str(index)))


def basename_from_url(url: str) -> str:
    path = urllib.parse.unquote(urllib.parse.urlparse(url).path)
    name = os.path.basename(path.rstrip("/"))
    return name or hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


def sanitize_relative_file(value: str | None, url: str) -> str:
    candidate = (value or basename_from_url(url)).replace("\\", "/").lstrip("/")
    parts = [part for part in candidate.split("/") if part not in {"", ".", ".."}]
    if not parts:
        return basename_from_url(url)
    cleaned = "/".join(re.sub(r"[^A-Za-z0-9._-]", "_", part) for part in parts)
    return cleaned


def resolution_value(text: str) -> int | None:
    match = RESOLUTION_RE.search(text)
    return int(match.group(1)) if match else None


def candidate_score(candidate: DownloadCandidate, request: dict[str, Any], archive_preferred: bool = False) -> tuple[int, int]:
    haystack = candidate.haystack
    requested_resolution = request["resolution"]
    requested_format = request["format"]
    score = 0
    if requested_resolution in haystack:
        score += 120
    candidate_resolution = resolution_value(haystack)
    requested_value = resolution_value(requested_resolution) or 2
    if candidate_resolution is not None:
        score -= abs(candidate_resolution - requested_value) * 8
        if candidate_resolution > requested_value:
            score -= 12
    format_aliases = {
        "gltf": ("gltf", ".glb", ".gltf"),
        "glb": ("glb", ".glb"),
        "jpg": ("jpg", "jpeg", "-jpg", "_jpg"),
        "jpeg": ("jpg", "jpeg"),
        "png": ("png", "-png", "_png"),
        "hdr": ("hdr", ".hdr"),
        "exr": ("exr", ".exr"),
        "fbx": ("fbx", ".fbx"),
        "obj": ("obj", ".obj"),
    }
    if any(alias in haystack for alias in format_aliases.get(requested_format, (requested_format,))):
        score += 80
    if archive_preferred and (".zip" in haystack or "zip" in candidate.path_tokens):
        score += 35
    if request["kind"] == "model" and ("gltf" in haystack or ".glb" in haystack):
        score += 35
    if request["kind"] == "hdri" and (".hdr" in haystack or ".exr" in haystack):
        score += 30
    if candidate.size is not None and candidate.size > request["maxDownloadBytes"]:
        score -= 10_000
    size_rank = -(candidate.size or 0)
    return score, size_rank


def lock_file(candidate: DownloadCandidate, *, path: str | None = None, extract: bool | None = None) -> dict[str, Any]:
    relative = sanitize_relative_file(path or candidate.relative_path, candidate.url)
    if extract is None:
        extract = relative.lower().endswith(".zip") or urllib.parse.urlparse(candidate.url).path.lower().endswith(".zip")
    result: dict[str, Any] = {
        "url": candidate.url,
        "path": relative,
        "extract": bool(extract),
    }
    if candidate.size is not None:
        result["size"] = candidate.size
    if candidate.md5:
        result["md5"] = candidate.md5
    return result


def choose_best(candidates: list[DownloadCandidate], request: dict[str, Any], archive_preferred: bool = False) -> DownloadCandidate:
    if not candidates:
        raise CatalogError(f"No downloadable files found for {request['provider']}/{request['id']}")
    ranked = sorted(candidates, key=lambda item: candidate_score(item, request, archive_preferred), reverse=True)
    best = ranked[0]
    score, _ = candidate_score(best, request, archive_preferred)
    if score < -1000:
        raise CatalogError(
            f"All matching downloads for {request['provider']}/{request['id']} exceed "
            f"maxDownloadBytes={request['maxDownloadBytes']}"
        )
    return best


def select_polyhaven_material_files(candidates: list[DownloadCandidate], request: dict[str, Any]) -> list[dict[str, Any]]:
    map_aliases = {
        "diff": ("diff", "albedo", "basecolor", "base_color"),
        "normal": ("nor_gl", "normal_gl", "normal"),
        "rough": ("rough", "roughness"),
        "ao": (" ao ", "_ao", "/ao", "ambientocclusion", "ambient_occlusion"),
        "metal": ("metallic", "_metal_", "-metal-", "/metal/"),
        "disp": ("disp", "height", "displacement"),
        "arm": (" arm ", "_arm", "/arm"),
    }
    selected: list[dict[str, Any]] = []
    used_urls: set[str] = set()
    for map_name, aliases in map_aliases.items():
        matching = [item for item in candidates if any(alias in f" {item.haystack} " for alias in aliases)]
        if not matching:
            continue
        if map_name == "normal":
            open_gl = [
                item
                for item in matching
                if any(alias in item.haystack for alias in ("nor_gl", "normal_gl", "opengl"))
            ]
            if open_gl:
                matching = open_gl
        best = choose_best(matching, request)
        if best.url in used_urls:
            continue
        used_urls.add(best.url)
        extension = os.path.splitext(basename_from_url(best.url))[1]
        selected.append(lock_file(best, path=f"{request['id']}_{map_name}{extension}"))
    if selected:
        return selected
    best = choose_best(candidates, request, archive_preferred=True)
    return [lock_file(best)]


def resolve_polyhaven(request: dict[str, Any]) -> dict[str, Any]:
    data = request_json(POLYHAVEN_FILES.format(asset_id=urllib.parse.quote(request["id"])))
    candidates = list(iter_url_nodes(data))
    if request["kind"] == "material":
        files = select_polyhaven_material_files(candidates, request)
    else:
        best = choose_best(candidates, request, archive_preferred=request["kind"] == "model")
        files = [lock_file(best)]
        existing_paths = {files[0]["path"].lower()}
        for dependency in best.dependencies:
            dep_candidate = DownloadCandidate(
                dependency["url"],
                ("dependency",),
                dependency.get("size"),
                dependency.get("md5"),
                dependency.get("path"),
            )
            dep_file = lock_file(dep_candidate, extract=False)
            if dep_file["path"].lower() not in existing_paths:
                existing_paths.add(dep_file["path"].lower())
                files.append(dep_file)
    total = sum(item.get("size", 0) for item in files)
    if total > request["maxDownloadBytes"]:
        raise CatalogError(
            f"Resolved Poly Haven asset {request['id']} is {total} bytes, above "
            f"maxDownloadBytes={request['maxDownloadBytes']}"
        )
    return {
        **request,
        "source": f"https://polyhaven.com/a/{request['id']}",
        "license": "CC0-1.0",
        "credit": "Powered by Poly Haven",
        "files": files,
    }


def resolve_ambientcg(request: dict[str, Any]) -> dict[str, Any]:
    params = urllib.parse.urlencode(
        {
            "id": request["id"],
            "limit": 1,
            "include": "type,title,url,downloads",
        }
    )
    data = request_json(f"{AMBIENTCG_ASSETS}?{params}")
    assets = data.get("assets") if isinstance(data, dict) else None
    if not isinstance(assets, list) or not assets:
        raise CatalogError(f"ambientCG asset not found: {request['id']}")
    asset = assets[0]
    downloads = asset.get("downloads") if isinstance(asset, dict) else None
    candidates = list(iter_url_nodes(downloads))
    candidates = [
        item
        for item in candidates
        if ".zip" in item.url.lower() or any("zip" in token.lower() for token in item.path_tokens)
    ] or list(iter_url_nodes(downloads))
    best = choose_best(candidates, request, archive_preferred=True)
    file = lock_file(best, extract=True)
    if file.get("size", 0) > request["maxDownloadBytes"]:
        raise CatalogError(
            f"Resolved ambientCG asset {request['id']} is {file['size']} bytes, above "
            f"maxDownloadBytes={request['maxDownloadBytes']}"
        )
    return {
        **request,
        "source": f"https://ambientcg.com/a/{request['id']}",
        "license": "CC0-1.0",
        "credit": "ambientCG",
        "files": [file],
    }


def resolve_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    requests = validate_manifest(manifest)
    resolved: list[dict[str, Any]] = []
    for request in requests:
        print(
            f"Resolving {request['provider']}/{request['id']} "
            f"({request['kind']}, {request['resolution']}, {request['format']})...",
            file=sys.stderr,
        )
        resolver = resolve_polyhaven if request["provider"] == "polyhaven" else resolve_ambientcg
        resolved.append(resolver(request))
    return {
        "schemaVersion": 1,
        "generatedAtUtc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "assets": resolved,
    }


def search_polyhaven(query: str, kind: str | None, limit: int) -> list[dict[str, Any]]:
    data = request_json(POLYHAVEN_ASSETS)
    if not isinstance(data, dict):
        raise CatalogError("Unexpected Poly Haven /assets response")
    kind_type = {"hdri": 0, "material": 1, "model": 2}.get(kind or "")
    words = [word.lower() for word in query.split() if word]
    results: list[tuple[int, dict[str, Any]]] = []
    for asset_id, metadata in data.items():
        if not isinstance(metadata, dict):
            continue
        if kind_type is not None and metadata.get("type") != kind_type:
            continue
        tags = metadata.get("tags") if isinstance(metadata.get("tags"), list) else []
        text = " ".join(
            [asset_id, str(metadata.get("name", "")), str(metadata.get("description", "")), str(metadata.get("category", "")), *map(str, tags)]
        ).lower()
        if not all(word in text for word in words):
            continue
        score = sum(8 if word in asset_id.lower() else 3 if word in str(metadata.get("name", "")).lower() else 1 for word in words)
        score += min(int(metadata.get("download_count", 0) or 0) // 10000, 10)
        results.append(
            (
                score,
                {
                    "provider": "polyhaven",
                    "id": asset_id,
                    "kind": {0: "hdri", 1: "material", 2: "model"}.get(metadata.get("type"), "unknown"),
                    "name": metadata.get("name"),
                    "category": metadata.get("category"),
                    "tags": tags,
                    "thumbnail": metadata.get("thumbnail_url"),
                    "source": f"https://polyhaven.com/a/{asset_id}",
                },
            )
        )
    results.sort(key=lambda pair: pair[0], reverse=True)
    return [item for _, item in results[:limit]]


def search_ambientcg(query: str, kind: str | None, limit: int) -> list[dict[str, Any]]:
    type_name = {"material": "material", "model": "3d-model", "hdri": "hdri"}.get(kind or "")
    params: dict[str, Any] = {
        "q": query,
        "limit": max(1, min(limit, 50)),
        "include": "type,title,url,tags,thumbnails,downloadStatistics",
    }
    if type_name:
        params["type"] = type_name
    data = request_json(f"{AMBIENTCG_ASSETS}?{urllib.parse.urlencode(params)}")
    assets = data.get("assets") if isinstance(data, dict) else None
    if not isinstance(assets, list):
        raise CatalogError("Unexpected ambientCG /assets response")
    results: list[dict[str, Any]] = []
    for asset in assets:
        if not isinstance(asset, dict):
            continue
        asset_id = str(asset.get("id", ""))
        results.append(
            {
                "provider": "ambientcg",
                "id": asset_id,
                "kind": kind or asset.get("type"),
                "name": asset.get("title") or asset_id,
                "tags": asset.get("tags"),
                "thumbnail": asset.get("thumbnails"),
                "source": asset.get("url") or f"https://ambientcg.com/a/{asset_id}",
            }
        )
    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate = subparsers.add_parser("validate", help="Validate the request manifest without network access")
    validate.add_argument("--manifest", type=Path, default=Path("AssetSources/open-assets.json"))

    resolve = subparsers.add_parser("resolve", help="Resolve provider IDs into download URLs and checksums")
    resolve.add_argument("--manifest", type=Path, default=Path("AssetSources/open-assets.json"))
    resolve.add_argument("--lock", type=Path, default=Path("AssetSources/open-assets.lock.json"))

    search = subparsers.add_parser("search", help="Search one provider and emit compact JSON results")
    search.add_argument("--provider", choices=sorted(SUPPORTED_PROVIDERS), required=True)
    search.add_argument("--query", required=True)
    search.add_argument("--kind", choices=sorted(SUPPORTED_KINDS))
    search.add_argument("--limit", type=int, default=10)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        if args.command == "validate":
            assets = validate_manifest(load_json(args.manifest))
            print(f"Open asset manifest valid: {len(assets)} enabled asset(s)")
            return 0
        if args.command == "resolve":
            lock = resolve_manifest(load_json(args.manifest))
            write_json(args.lock, lock)
            print(f"Resolved {len(lock['assets'])} asset(s) to {args.lock}")
            return 0
        if args.command == "search":
            limit = max(1, min(args.limit, 50))
            results = (
                search_polyhaven(args.query, args.kind, limit)
                if args.provider == "polyhaven"
                else search_ambientcg(args.query, args.kind, limit)
            )
            print(json.dumps({"results": results}, indent=2, ensure_ascii=False))
            return 0
        raise CatalogError(f"Unsupported command: {args.command}")
    except CatalogError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
