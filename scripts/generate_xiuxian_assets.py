from __future__ import annotations

import ast
import math
import random
import struct
import sys
import zlib
import importlib.util
from hashlib import sha256
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

ASSET_IMAGE_MODULE_PATH = ROOT / "bot/plugins/xiuxian_game/asset_images.py"
asset_spec = importlib.util.spec_from_file_location("xiuxian_asset_images", ASSET_IMAGE_MODULE_PATH)
if asset_spec is None or asset_spec.loader is None:
    raise RuntimeError(f"无法加载资源路径模块：{ASSET_IMAGE_MODULE_PATH}")
asset_images = importlib.util.module_from_spec(asset_spec)
asset_spec.loader.exec_module(asset_images)

SUPPORTED_KINDS = asset_images.SUPPORTED_KINDS
generated_asset_path = asset_images.generated_asset_path
generic_asset_name = asset_images.generic_asset_name
normalize_asset_kind = asset_images.normalize_asset_kind

WIDTH = 480
HEIGHT = 300
CATALOG_FILES = [
    ROOT / "bot/plugins/xiuxian_game/service.py",
    *sorted((ROOT / "bot/plugins/xiuxian_game/features/catalog").glob("*.py")),
]
GENERIC_QUALITIES = [
    None,
    "凡品",
    "下品",
    "中品",
    "上品",
    "极品",
    "仙品",
    "先天至宝",
    "炼气",
    "筑基",
    "结丹",
    "元婴",
    "化神",
    "须弥",
]

QUALITY_PALETTES: dict[str, tuple[tuple[int, int, int], tuple[int, int, int], tuple[int, int, int]]] = {
    "凡品": ((58, 71, 78), (119, 132, 122), (188, 194, 178)),
    "下品": ((23, 82, 86), (42, 144, 132), (136, 218, 198)),
    "中品": ((21, 76, 122), (55, 141, 210), (175, 218, 255)),
    "上品": ((105, 74, 22), (205, 157, 64), (255, 224, 142)),
    "极品": ((106, 35, 85), (211, 89, 151), (255, 184, 221)),
    "仙品": ((61, 42, 128), (146, 107, 232), (234, 214, 255)),
    "先天至宝": ((92, 52, 15), (242, 188, 76), (255, 252, 210)),
}
KIND_TINTS: dict[str, tuple[int, int, int]] = {
    "artifact": (230, 126, 74),
    "pill": (139, 92, 246),
    "talisman": (236, 185, 92),
    "material": (63, 201, 181),
    "technique": (100, 181, 246),
    "scene": (89, 196, 160),
    "boss": (229, 82, 82),
}


class Image:
    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self.pixels = bytearray(width * height * 3)

    def set(self, x: int, y: int, color: tuple[int, int, int]) -> None:
        if 0 <= x < self.width and 0 <= y < self.height:
            index = (y * self.width + x) * 3
            self.pixels[index:index + 3] = bytes(color)

    def blend(self, x: int, y: int, color: tuple[int, int, int], alpha: float) -> None:
        if not (0 <= x < self.width and 0 <= y < self.height):
            return
        alpha = max(0.0, min(1.0, alpha))
        index = (y * self.width + x) * 3
        inv = 1.0 - alpha
        self.pixels[index] = int(self.pixels[index] * inv + color[0] * alpha)
        self.pixels[index + 1] = int(self.pixels[index + 1] * inv + color[1] * alpha)
        self.pixels[index + 2] = int(self.pixels[index + 2] * inv + color[2] * alpha)

    def save_png(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        rows = bytearray()
        stride = self.width * 3
        for y in range(self.height):
            rows.append(0)
            start = y * stride
            rows.extend(self.pixels[start:start + stride])
        compressed = zlib.compress(bytes(rows), level=9)

        def chunk(kind: bytes, data: bytes) -> bytes:
            return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

        payload = b"".join([
            b"\x89PNG\r\n\x1a\n",
            chunk(b"IHDR", struct.pack(">IIBBBBB", self.width, self.height, 8, 2, 0, 0, 0)),
            chunk(b"IDAT", compressed),
            chunk(b"IEND", b""),
        ])
        path.write_bytes(payload)


def mix(left: tuple[int, int, int], right: tuple[int, int, int], amount: float) -> tuple[int, int, int]:
    amount = max(0.0, min(1.0, amount))
    return tuple(int(left[i] * (1 - amount) + right[i] * amount) for i in range(3))


def lighten(color: tuple[int, int, int], amount: float) -> tuple[int, int, int]:
    return mix(color, (255, 255, 255), amount)


def darken(color: tuple[int, int, int], amount: float) -> tuple[int, int, int]:
    return mix(color, (0, 0, 0), amount)


def seeded_rng(kind: str, name: str) -> random.Random:
    seed = int.from_bytes(sha256(f"{kind}:{name}".encode("utf-8")).digest()[:8], "big")
    return random.Random(seed)


def infer_quality(item: dict[str, Any]) -> str:
    raw = item.get("rarity") or item.get("quality_label") or item.get("realm_stage") or item.get("min_realm_stage")
    if raw in QUALITY_PALETTES:
        return str(raw)
    level = int(item.get("quality_level") or 0)
    by_level = {
        1: "凡品",
        2: "下品",
        3: "中品",
        4: "上品",
        5: "极品",
        6: "仙品",
        7: "先天至宝",
    }
    return by_level.get(level, "中品")


def palette_for(kind: str, quality: str) -> tuple[tuple[int, int, int], tuple[int, int, int], tuple[int, int, int]]:
    base = QUALITY_PALETTES.get(quality, QUALITY_PALETTES["中品"])
    tint = KIND_TINTS.get(kind, (204, 167, 114))
    return (
        mix(base[0], tint, 0.18),
        mix(base[1], tint, 0.24),
        mix(base[2], tint, 0.18),
    )


def draw_background(img: Image, rng: random.Random, palette: tuple[tuple[int, int, int], tuple[int, int, int], tuple[int, int, int]]) -> None:
    dark, mid, light = palette
    cx = rng.randint(110, 370)
    cy = rng.randint(70, 190)
    for y in range(img.height):
        vertical = y / max(img.height - 1, 1)
        for x in range(img.width):
            radial = math.hypot((x - cx) / img.width, (y - cy) / img.height)
            color = mix(dark, mid, 0.35 + vertical * 0.28)
            color = mix(color, light, max(0.0, 0.55 - radial * 1.45))
            if ((x * 17 + y * 29 + rng.randint(0, 7)) % 89) == 0:
                color = lighten(color, 0.18)
            img.set(x, y, color)
    for _ in range(42):
        x = rng.randint(0, img.width - 1)
        y = rng.randint(0, img.height - 1)
        radius = rng.randint(1, 3)
        draw_disc(img, x, y, radius, lighten(light, 0.25), rng.uniform(0.18, 0.45))


def draw_disc(img: Image, cx: int, cy: int, radius: int, color: tuple[int, int, int], alpha: float = 1.0) -> None:
    r2 = radius * radius
    for y in range(cy - radius, cy + radius + 1):
        for x in range(cx - radius, cx + radius + 1):
            d2 = (x - cx) * (x - cx) + (y - cy) * (y - cy)
            if d2 <= r2:
                edge = 1.0 - max(0.0, math.sqrt(d2) - radius + 1.0)
                img.blend(x, y, color, alpha * max(0.18, min(1.0, edge)))


def draw_ring(img: Image, cx: int, cy: int, radius: int, width: int, color: tuple[int, int, int], alpha: float = 1.0) -> None:
    outer = radius * radius
    inner = max(radius - width, 0) ** 2
    for y in range(cy - radius, cy + radius + 1):
        for x in range(cx - radius, cx + radius + 1):
            d2 = (x - cx) * (x - cx) + (y - cy) * (y - cy)
            if inner <= d2 <= outer:
                img.blend(x, y, color, alpha)


def draw_line(img: Image, x1: int, y1: int, x2: int, y2: int, color: tuple[int, int, int], width: int = 2, alpha: float = 1.0) -> None:
    steps = max(abs(x2 - x1), abs(y2 - y1), 1)
    for i in range(steps + 1):
        t = i / steps
        x = int(round(x1 * (1 - t) + x2 * t))
        y = int(round(y1 * (1 - t) + y2 * t))
        draw_disc(img, x, y, max(width // 2, 1), color, alpha)


def fill_polygon(img: Image, points: list[tuple[int, int]], color: tuple[int, int, int], alpha: float = 1.0) -> None:
    if len(points) < 3:
        return
    min_y = max(min(y for _, y in points), 0)
    max_y = min(max(y for _, y in points), img.height - 1)
    for y in range(min_y, max_y + 1):
        xs: list[float] = []
        for i, (x1, y1) in enumerate(points):
            x2, y2 = points[(i + 1) % len(points)]
            if y1 == y2:
                continue
            if min(y1, y2) <= y < max(y1, y2):
                xs.append(x1 + (y - y1) * (x2 - x1) / (y2 - y1))
        xs.sort()
        for i in range(0, len(xs) - 1, 2):
            left = max(int(math.ceil(xs[i])), 0)
            right = min(int(math.floor(xs[i + 1])), img.width - 1)
            for x in range(left, right + 1):
                img.blend(x, y, color, alpha)


def draw_sigil(img: Image, rng: random.Random, color: tuple[int, int, int]) -> None:
    cx, cy = img.width // 2, img.height // 2
    draw_ring(img, cx, cy, 106, 2, color, 0.22)
    draw_ring(img, cx, cy, 78, 1, color, 0.18)
    for idx in range(10):
        angle = idx * math.tau / 10 + rng.uniform(-0.05, 0.05)
        x1 = int(cx + math.cos(angle) * 76)
        y1 = int(cy + math.sin(angle) * 76)
        x2 = int(cx + math.cos(angle + math.pi) * 76)
        y2 = int(cy + math.sin(angle + math.pi) * 76)
        draw_line(img, x1, y1, x2, y2, color, 1, 0.08)


def draw_artifact(img: Image, rng: random.Random, palette: tuple[tuple[int, int, int], tuple[int, int, int], tuple[int, int, int]]) -> None:
    _, mid, light = palette
    cx = img.width // 2 + rng.randint(-18, 18)
    top = 54 + rng.randint(-8, 8)
    bottom = 244 + rng.randint(-8, 8)
    blade = lighten(light, 0.18)
    shadow = darken(mid, 0.35)
    fill_polygon(img, [(cx, top), (cx + 34, bottom - 74), (cx + 10, bottom - 34), (cx - 10, bottom - 34), (cx - 34, bottom - 74)], blade, 0.88)
    draw_line(img, cx, top + 18, cx, bottom - 40, lighten(blade, 0.3), 3, 0.75)
    draw_line(img, cx - 54, bottom - 36, cx + 54, bottom - 36, shadow, 12, 0.85)
    draw_line(img, cx, bottom - 34, cx, bottom + 18, shadow, 11, 0.9)
    draw_disc(img, cx, bottom + 25, 18, mid, 0.82)


def draw_material(img: Image, rng: random.Random, palette: tuple[tuple[int, int, int], tuple[int, int, int], tuple[int, int, int]]) -> None:
    dark, mid, light = palette
    base_y = 234
    for index in range(5):
        cx = 160 + index * 40 + rng.randint(-14, 14)
        height = rng.randint(70, 128)
        width = rng.randint(18, 34)
        top = base_y - height
        color = mix(mid, light, index / 5)
        fill_polygon(img, [(cx, top), (cx + width, base_y - 20), (cx + width // 2, base_y), (cx - width // 2, base_y), (cx - width, base_y - 20)], color, 0.86)
        draw_line(img, cx, top + 8, cx, base_y - 12, lighten(light, 0.18), 2, 0.65)
    draw_disc(img, img.width // 2, base_y - 8, 76, darken(dark, 0.08), 0.24)


def draw_pill(img: Image, rng: random.Random, palette: tuple[tuple[int, int, int], tuple[int, int, int], tuple[int, int, int]]) -> None:
    dark, mid, light = palette
    cx, cy = img.width // 2, img.height // 2
    for radius, alpha in [(86, 0.12), (68, 0.24), (52, 0.9)]:
        draw_disc(img, cx, cy, radius, mix(mid, light, 0.5), alpha)
    draw_disc(img, cx - 16, cy - 16, 20, lighten(light, 0.38), 0.58)
    for idx in range(6):
        angle = idx * math.tau / 6 + rng.uniform(-0.2, 0.2)
        draw_line(img, cx, cy, int(cx + math.cos(angle) * 96), int(cy + math.sin(angle) * 96), light, 2, 0.2)
    draw_ring(img, cx, cy, 56, 4, darken(dark, 0.1), 0.38)


def draw_talisman(img: Image, rng: random.Random, palette: tuple[tuple[int, int, int], tuple[int, int, int], tuple[int, int, int]]) -> None:
    dark, mid, light = palette
    x1, y1, x2, y2 = 156, 46, 324, 252
    paper = mix(light, (255, 237, 183), 0.42)
    fill_polygon(img, [(x1, y1 + 14), (x1 + 14, y1), (x2 - 14, y1), (x2, y1 + 14), (x2, y2 - 14), (x2 - 14, y2), (x1 + 14, y2), (x1, y2 - 14)], paper, 0.88)
    draw_line(img, x1 + 32, y1 + 52, x2 - 32, y1 + 52, dark, 4, 0.55)
    for row in range(5):
        y = y1 + 84 + row * 25
        draw_line(img, x1 + 42 + rng.randint(-6, 6), y, x2 - 42 + rng.randint(-6, 6), y + rng.randint(-8, 8), mid, 3, 0.58)
    draw_ring(img, (x1 + x2) // 2, (y1 + y2) // 2, 48, 3, mid, 0.34)


def draw_technique(img: Image, rng: random.Random, palette: tuple[tuple[int, int, int], tuple[int, int, int], tuple[int, int, int]]) -> None:
    dark, mid, light = palette
    fill_polygon(img, [(134, 74), (238, 44), (238, 230), (134, 254)], mix(mid, light, 0.25), 0.78)
    fill_polygon(img, [(242, 44), (348, 74), (348, 254), (242, 230)], mix(mid, light, 0.38), 0.78)
    draw_line(img, 240, 50, 240, 232, darken(dark, 0.18), 4, 0.7)
    for i in range(6):
        y = 92 + i * 22
        draw_line(img, 158, y + rng.randint(-3, 3), 214, y + rng.randint(-3, 3), light, 2, 0.42)
        draw_line(img, 266, y + rng.randint(-3, 3), 322, y + rng.randint(-3, 3), light, 2, 0.42)
    draw_ring(img, 240, 152, 82, 2, light, 0.16)


def draw_scene(img: Image, rng: random.Random, palette: tuple[tuple[int, int, int], tuple[int, int, int], tuple[int, int, int]]) -> None:
    dark, mid, light = palette
    fill_polygon(img, [(0, 244), (94, 136), (172, 244)], darken(mid, 0.3), 0.72)
    fill_polygon(img, [(118, 248), (236, 96), (356, 248)], mix(mid, light, 0.1), 0.76)
    fill_polygon(img, [(284, 248), (394, 126), (480, 248)], darken(mid, 0.12), 0.72)
    cx, cy = 240, 150
    draw_ring(img, cx, cy, 74, 8, light, 0.42)
    draw_ring(img, cx, cy, 48, 4, mid, 0.36)
    for _ in range(8):
        angle = rng.random() * math.tau
        draw_line(img, cx, cy, int(cx + math.cos(angle) * rng.randint(84, 116)), int(cy + math.sin(angle) * rng.randint(84, 116)), light, 1, 0.12)


def draw_boss(img: Image, rng: random.Random, palette: tuple[tuple[int, int, int], tuple[int, int, int], tuple[int, int, int]]) -> None:
    dark, mid, light = palette
    body = darken(dark, 0.28)
    cx, cy = img.width // 2, 164
    draw_disc(img, cx, cy + 30, 72, body, 0.86)
    draw_disc(img, cx, cy - 26, 54, body, 0.9)
    fill_polygon(img, [(cx - 42, cy - 58), (cx - 112, cy - 96), (cx - 68, cy - 28)], body, 0.78)
    fill_polygon(img, [(cx + 42, cy - 58), (cx + 112, cy - 96), (cx + 68, cy - 28)], body, 0.78)
    draw_disc(img, cx - 18, cy - 30, 6, light, 0.9)
    draw_disc(img, cx + 18, cy - 30, 6, light, 0.9)
    for side in (-1, 1):
        draw_line(img, cx + side * 22, cy + 18, cx + side * 74, cy + 68, mid, 4, 0.48)
    draw_ring(img, cx, cy + 4, 104, 3, mid, 0.2)


DRAWERS = {
    "artifact": draw_artifact,
    "material": draw_material,
    "pill": draw_pill,
    "talisman": draw_talisman,
    "technique": draw_technique,
    "scene": draw_scene,
    "boss": draw_boss,
}


def render_asset(kind: str, name: str, quality: str, path: Path) -> None:
    normalized_kind = normalize_asset_kind(kind)
    rng = seeded_rng(normalized_kind, name)
    palette = palette_for(normalized_kind, quality)
    img = Image(WIDTH, HEIGHT)
    draw_background(img, rng, palette)
    draw_sigil(img, rng, lighten(palette[2], 0.12))
    DRAWERS.get(normalized_kind, draw_material)(img, rng, palette)
    draw_ring(img, WIDTH // 2, HEIGHT // 2, 136, 3, lighten(palette[2], 0.08), 0.12)
    img.save_png(path)


def kind_from_container(name: str) -> str | None:
    upper = name.upper()
    if "BOSS" in upper:
        return "boss"
    if "SCENE" in upper:
        return "scene"
    if "MATERIAL" in upper:
        return "material"
    if "ARTIFACT" in upper:
        return "artifact"
    if "TALISMAN" in upper:
        return "talisman"
    if "TECHNIQUE" in upper:
        return "technique"
    if "PILL" in upper or "BLUEPRINT" in upper:
        return "pill"
    return None


def literal_dict(node: ast.AST) -> dict[str, Any] | None:
    if not isinstance(node, ast.Dict):
        return None
    try:
        value = ast.literal_eval(node)
    except Exception:
        return None
    return value if isinstance(value, dict) and str(value.get("name") or "").strip() else None


def collect_from_node(node: ast.AST, kind: str) -> list[tuple[str, str, dict[str, Any]]]:
    rows: list[tuple[str, str, dict[str, Any]]] = []
    if isinstance(node, ast.Dict):
        payload = literal_dict(node)
        if payload:
            rows.append((kind, str(payload["name"]).strip(), payload))
    elif isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        for item in node.elts:
            rows.extend(collect_from_node(item, kind))
    elif isinstance(node, ast.Call):
        for arg in node.args:
            if isinstance(arg, (ast.List, ast.Tuple, ast.Set, ast.Dict)):
                rows.extend(collect_from_node(arg, kind))
    return rows


class CatalogVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.rows: list[tuple[str, str, dict[str, Any]]] = []

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            if isinstance(target, ast.Name):
                kind = kind_from_container(target.id)
                if kind:
                    self.rows.extend(collect_from_node(node.value, kind))
        self.generic_visit(node)

    def visit_Expr(self, node: ast.Expr) -> None:
        call = node.value
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute) and call.func.attr in {"append", "extend"}:
            base = call.func.value
            if isinstance(base, ast.Name):
                kind = kind_from_container(base.id)
                if kind:
                    for arg in call.args:
                        self.rows.extend(collect_from_node(arg, kind))
        self.generic_visit(node)


def collect_catalog_rows() -> list[tuple[str, str, dict[str, Any]]]:
    rows: list[tuple[str, str, dict[str, Any]]] = []
    for path in CATALOG_FILES:
        if not path.exists():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        visitor = CatalogVisitor()
        visitor.visit(tree)
        rows.extend(visitor.rows)
    deduped: dict[tuple[str, str], dict[str, Any]] = {}
    for kind, name, payload in rows:
        deduped.setdefault((kind, name), payload)
    return [(kind, name, payload) for (kind, name), payload in sorted(deduped.items())]


def main() -> None:
    rows = collect_catalog_rows()
    generated = 0
    for kind in sorted(SUPPORTED_KINDS):
        for quality in GENERIC_QUALITIES:
            name = generic_asset_name(kind, quality)
            render_asset(kind, name, str(quality or "中品"), generated_asset_path(kind, name))
            generated += 1
    for kind, name, payload in rows:
        render_asset(kind, name, infer_quality(payload), generated_asset_path(kind, name))
        generated += 1
    print(f"generated {generated} xiuxian image assets from {len(rows)} catalog entries")


if __name__ == "__main__":
    main()
