#!/usr/bin/env python3
"""Global, repository-configured front end for the open asset resolver."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import open_asset_catalog as engine

PROVIDERS_PATH = Path("AssetSources/providers.json")
MANIFEST_PATH = Path("AssetSources/open-assets.json")
LOCK_PATH = Path("AssetSources/open-assets.lock.json")
RESOLUTION_RE = re.compile(r"^(\d{1,2})k$", re.IGNORECASE)
KINDS = {"model", "material", "hdri"}


class ConfigError(RuntimeError):
    pass


def load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigError(f"Missing configuration file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ConfigError(f"Top level of {path} must be an object")
    return value


def resolution_number(value: str) -> int:
    match = RESOLUTION_RE.fullmatch(value.strip())
    if not match:
        raise ConfigError(f"Invalid resolution '{value}'. Use values such as 1k or 2k.")
    return int(match.group(1))


def load_registry(path: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    raw = load(path)
    if raw.get("schemaVersion") != 1:
        raise ConfigError("providers.json must use schemaVersion 1")
    policy = raw.get("policy")
    providers = raw.get("providers")
    if not isinstance(policy, dict) or not isinstance(providers, dict) or not providers:
        raise ConfigError("providers.json requires policy and providers objects")
    order = policy.get("preferredProviderOrder")
    if not isinstance(order, list) or not all(isinstance(item, str) for item in order):
        raise ConfigError("policy.preferredProviderOrder must be an array")

    normalized: dict[str, dict[str, Any]] = {}
    for provider_id, provider in providers.items():
        if not isinstance(provider_id, str) or not isinstance(provider, dict):
            raise ConfigError("Provider entries must be objects")
        provider_id = provider_id.lower()
        api = provider.get("api")
        kinds = provider.get("supportedKinds")
        formats = provider.get("preferredFormats")
        if not isinstance(api, dict) or not isinstance(api.get("assets"), str):
            raise ConfigError(f"Provider {provider_id} requires api.assets")
        if provider_id == "polyhaven" and not isinstance(api.get("files"), str):
            raise ConfigError("Poly Haven requires api.files")
        if provider.get("authentication") != "none":
            raise ConfigError(f"Provider {provider_id} must be keyless")
        if not str(provider.get("license", "")).startswith("CC0"):
            raise ConfigError(f"Provider {provider_id} is not configured as CC0")
        if not isinstance(kinds, list) or not set(kinds).issubset(KINDS):
            raise ConfigError(f"Provider {provider_id} has invalid supportedKinds")
        if not isinstance(formats, dict):
            raise ConfigError(f"Provider {provider_id} requires preferredFormats")
        normalized[provider_id] = provider

    for provider_id in order:
        if provider_id.lower() not in normalized:
            raise ConfigError(f"Preferred provider is missing: {provider_id}")
    return policy, normalized


def configure_engine(providers: dict[str, dict[str, Any]]) -> None:
    polyhaven = providers.get("polyhaven")
    ambientcg = providers.get("ambientcg")
    if polyhaven:
        engine.POLYHAVEN_ASSETS = polyhaven["api"]["assets"]
        engine.POLYHAVEN_FILES = polyhaven["api"]["files"]
    if ambientcg:
        engine.AMBIENTCG_ASSETS = ambientcg["api"]["assets"]
    engine.SUPPORTED_PROVIDERS = {
        provider_id
        for provider_id, provider in providers.items()
        if provider.get("enabled") is True
    }


def normalized_manifest(
    manifest: dict[str, Any], policy: dict[str, Any], providers: dict[str, dict[str, Any]]
) -> dict[str, Any]:
    if manifest.get("schemaVersion") != 1 or not isinstance(manifest.get("assets"), list):
        raise ConfigError("open-assets.json requires schemaVersion 1 and an assets array")

    default_resolution = str(policy.get("defaultResolution", "2k")).lower()
    maximum_resolution = str(policy.get("maximumResolution", default_resolution)).lower()
    default_max = policy.get("defaultMaxDownloadBytes", 104_857_600)
    if not isinstance(default_max, int) or default_max <= 0:
        raise ConfigError("policy.defaultMaxDownloadBytes must be a positive integer")
    maximum_number = resolution_number(maximum_resolution)
    resolution_number(default_resolution)

    normalized_assets: list[dict[str, Any]] = []
    targets: set[str] = set()
    for index, raw in enumerate(manifest["assets"]):
        if not isinstance(raw, dict):
            raise ConfigError(f"assets[{index}] must be an object")
        if raw.get("enabled", True) is False:
            normalized_assets.append(raw)
            continue
        provider_id = str(raw.get("provider", "")).strip().lower()
        provider = providers.get(provider_id)
        if not provider or provider.get("enabled") is not True:
            raise ConfigError(f"assets[{index}] uses an unknown or disabled provider: {provider_id}")
        kind = str(raw.get("kind", "")).strip().lower()
        if kind not in provider["supportedKinds"]:
            raise ConfigError(f"Provider {provider_id} does not support kind '{kind}'")
        resolution = str(raw.get("resolution", default_resolution)).strip().lower()
        if resolution_number(resolution) > maximum_number:
            raise ConfigError(
                f"assets[{index}].resolution {resolution} exceeds global maximum {maximum_resolution}"
            )
        formats = provider["preferredFormats"].get(kind)
        if not isinstance(formats, list) or not formats:
            raise ConfigError(f"Provider {provider_id} has no formats configured for {kind}")
        allowed_formats = [str(value).lower() for value in formats]
        preferred_format = str(raw.get("format", allowed_formats[0])).strip().lower()
        if preferred_format not in allowed_formats:
            raise ConfigError(
                f"assets[{index}].format '{preferred_format}' is not allowed for {provider_id}/{kind}"
            )
        max_bytes = raw.get("maxDownloadBytes", default_max)
        if not isinstance(max_bytes, int) or max_bytes <= 0 or max_bytes > default_max:
            raise ConfigError(f"assets[{index}].maxDownloadBytes must be 1..{default_max}")
        target = str(raw.get("target") or f"{provider_id}/{raw.get('id', '')}").strip()
        if target.lower() in targets:
            raise ConfigError(f"Duplicate target path: {target}")
        targets.add(target.lower())
        normalized_assets.append(
            {
                **raw,
                "provider": provider_id,
                "kind": kind,
                "resolution": resolution,
                "format": preferred_format,
                "target": target,
                "maxDownloadBytes": max_bytes,
            }
        )

    return {
        "schemaVersion": 1,
        "defaults": {
            "resolution": default_resolution,
            "maxDownloadBytes": default_max,
        },
        "assets": normalized_assets,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--providers", type=Path, default=PROVIDERS_PATH)
    commands = parser.add_subparsers(dest="command", required=True)

    validate = commands.add_parser("validate")
    validate.add_argument("--manifest", type=Path, default=MANIFEST_PATH)

    resolve = commands.add_parser("resolve")
    resolve.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    resolve.add_argument("--lock", type=Path, default=LOCK_PATH)

    search = commands.add_parser("search")
    search.add_argument("--provider", default="auto")
    search.add_argument("--kind", choices=sorted(KINDS))
    search.add_argument("--query", required=True)
    search.add_argument("--limit", type=int, default=10)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        policy, providers = load_registry(args.providers)
        configure_engine(providers)
        if args.command in {"validate", "resolve"}:
            manifest = normalized_manifest(load(args.manifest), policy, providers)
            enabled = engine.validate_manifest(manifest)
            if args.command == "validate":
                print(
                    f"Open asset configuration valid: {len(providers)} provider(s), "
                    f"{len(enabled)} enabled asset(s)"
                )
                return 0
            lock = engine.resolve_manifest(manifest)
            for asset in lock.get("assets", []):
                provider = providers[asset["provider"]]
                asset["source"] = str(provider["websiteAsset"]).format(asset_id=asset["id"])
                asset["license"] = provider["license"]
                asset["credit"] = provider.get("credit", provider.get("displayName", asset["provider"]))
            engine.write_json(args.lock, lock)
            print(f"Resolved {len(lock.get('assets', []))} asset(s) to {args.lock}")
            return 0

        limit = min(max(args.limit, 1), 50)
        requested = args.provider.lower()
        provider_ids = (
            [str(value).lower() for value in policy["preferredProviderOrder"]]
            if requested == "auto"
            else [requested]
        )
        results: list[dict[str, Any]] = []
        for provider_id in provider_ids:
            provider = providers.get(provider_id)
            if not provider or provider.get("enabled") is not True:
                if requested != "auto":
                    raise ConfigError(f"Unknown or disabled provider: {provider_id}")
                continue
            if args.kind and args.kind not in provider["supportedKinds"]:
                continue
            remaining = limit - len(results)
            if provider_id == "polyhaven":
                found = engine.search_polyhaven(args.query, args.kind, remaining)
            elif provider_id == "ambientcg":
                found = engine.search_ambientcg(args.query, args.kind, remaining)
            else:
                continue
            results.extend(found)
            if len(results) >= limit:
                break
        print(json.dumps({"results": results[:limit]}, indent=2, ensure_ascii=False))
        return 0
    except (ConfigError, engine.CatalogError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
