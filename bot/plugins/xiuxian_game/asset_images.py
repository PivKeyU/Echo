from __future__ import annotations

import hashlib
import re
from pathlib import Path


STATIC_URL_PREFIX = "/plugins/xiuxian/static/generated"
STATIC_ASSET_DIR = Path(__file__).resolve().parent / "static" / "generated"
SUPPORTED_KINDS = {"artifact", "pill", "talisman", "material", "technique", "scene", "boss"}


def normalize_asset_kind(kind: str | None) -> str:
    normalized = str(kind or "").strip().lower().replace("_", "-")
    aliases = {
        "artifacts": "artifact",
        "weapon": "artifact",
        "weapons": "artifact",
        "pills": "pill",
        "talismans": "talisman",
        "materials": "material",
        "techniques": "technique",
        "scenes": "scene",
        "secret-realm": "scene",
        "secret-realm-scene": "scene",
        "bosses": "boss",
    }
    normalized = aliases.get(normalized, normalized)
    return normalized if normalized in SUPPORTED_KINDS else "material"


def asset_digest(kind: str | None, name: str | None) -> str:
    normalized_kind = normalize_asset_kind(kind)
    normalized_name = str(name or "").strip() or normalized_kind
    return hashlib.sha1(f"{normalized_kind}:{normalized_name}".encode("utf-8")).hexdigest()[:14]


def asset_filename(kind: str | None, name: str | None) -> str:
    return f"{asset_digest(kind, name)}.png"


def generated_asset_url(kind: str | None, name: str | None) -> str:
    normalized_kind = normalize_asset_kind(kind)
    return f"{STATIC_URL_PREFIX}/{normalized_kind}/{asset_filename(normalized_kind, name)}"


def generated_asset_path(kind: str | None, name: str | None) -> Path:
    normalized_kind = normalize_asset_kind(kind)
    return STATIC_ASSET_DIR / normalized_kind / asset_filename(normalized_kind, name)


def generic_asset_name(kind: str | None, quality: str | int | None = None) -> str:
    normalized_kind = normalize_asset_kind(kind)
    raw_quality = str(quality or "").strip()
    safe_quality = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "-", raw_quality).strip("-")
    return f"generic-{normalized_kind}-{safe_quality or 'default'}"


def generic_asset_url(kind: str | None, quality: str | int | None = None) -> str:
    normalized_kind = normalize_asset_kind(kind)
    return generated_asset_url(normalized_kind, generic_asset_name(normalized_kind, quality))


def resolve_image_url(
    image_url: str | None,
    *,
    kind: str,
    name: str | None,
    quality: str | int | None = None,
) -> str:
    explicit = str(image_url or "").strip()
    if explicit:
        return explicit

    exact_path = generated_asset_path(kind, name)
    if exact_path.exists():
        return generated_asset_url(kind, name)

    quality_path = generated_asset_path(kind, generic_asset_name(kind, quality))
    if quality_path.exists():
        return generic_asset_url(kind, quality)

    return generic_asset_url(kind, None)
