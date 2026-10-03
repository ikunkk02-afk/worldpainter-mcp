from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def box_blur(values: np.ndarray, radius: int) -> np.ndarray:
    radius = max(1, int(radius))
    padded = np.pad(values, radius, mode="edge")
    integral = np.pad(padded, ((1, 0), (1, 0)), mode="constant").cumsum(0, dtype=np.float64).cumsum(1)
    size = radius * 2 + 1
    total = integral[size:, size:] - integral[:-size, size:] - integral[size:, :-size] + integral[:-size, :-size]
    return (total / float(size * size)).astype(np.float32)


def region_mask(meta: dict[str, int], region: dict[str, Any] | None, mask_path: str | None) -> np.ndarray:
    width, height = meta["width"], meta["height"]
    origin_x, origin_y = meta["x"], meta["y"]
    if region is None:
        mask = np.ones((height, width), dtype=np.float32)
    else:
        kind = region.get("type", "rectangle")
        image = Image.new("L", (width, height), 0)
        draw = ImageDraw.Draw(image)
        if kind == "rectangle":
            x = int(region["x"]) - origin_x
            y = int(region["y"]) - origin_y
            draw.rectangle((x, y, x + int(region["width"]) - 1, y + int(region["height"]) - 1), fill=255)
        elif kind == "circle":
            cx = float(region["center_x"]) - origin_x
            cy = float(region["center_y"]) - origin_y
            r = float(region["radius"])
            draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=255)
        elif kind == "polygon":
            points = [(float(p[0]) - origin_x, float(p[1]) - origin_y) for p in region["points"]]
            draw.polygon(points, fill=255)
        else:
            raise ValueError(f"Unsupported region type: {kind}")
        mask = np.asarray(image, dtype=np.float32) / 255.0
    feather = int((region or {}).get("feather", 0))
    if feather > 0:
        mask = box_blur(mask, feather).clip(0.0, 1.0)
    if mask_path:
        external = Image.open(mask_path).convert("L").resize((width, height), Image.Resampling.BILINEAR)
        mask *= np.asarray(external, dtype=np.float32) / 255.0
    return mask


def slope(values: np.ndarray) -> np.ndarray:
    gy, gx = np.gradient(values)
    return np.hypot(gx, gy)


def summarize(values: np.ndarray, sea_level: float | None = None) -> dict[str, Any]:
    s = slope(values)
    result: dict[str, Any] = {
        "width": int(values.shape[1]), "height": int(values.shape[0]),
        "height_min": float(np.min(values)), "height_max": float(np.max(values)),
        "height_mean": float(np.mean(values)), "height_std": float(np.std(values)),
        "slope_mean": float(np.mean(s)), "slope_p50": float(np.percentile(s, 50)),
        "slope_p95": float(np.percentile(s, 95)), "slope_max": float(np.max(s)),
    }
    if sea_level is not None:
        result["below_sea_fraction"] = float(np.mean(values <= sea_level))
        result["coast_band_fraction"] = float(np.mean(np.abs(values - sea_level) <= 3.0))
    return result


def apply_operations(source: np.ndarray, operations: list[dict[str, Any]], mask: np.ndarray,
                     min_height: float, max_height: float) -> np.ndarray:
    current = source.astype(np.float32, copy=True)
    for operation in operations:
        name = operation["type"]
        strength = float(operation.get("strength", 1.0))
        if name == "smooth":
            candidate = current
            for _ in range(int(operation.get("passes", 1))):
                candidate = box_blur(candidate, int(operation.get("radius", 2)))
            candidate = current + (candidate - current) * strength
        elif name == "raise_lower":
            candidate = current + float(operation.get("delta", 1.0)) * strength
        elif name == "ridge_valley":
            base = box_blur(current, int(operation.get("radius", 6)))
            scale = max(0.01, float(operation.get("scale", 4.0)))
            contrast = np.tanh((current - base) / scale)
            candidate = current + contrast * strength
        elif name == "erosion":
            candidate = current.copy()
            talus = float(operation.get("talus", 1.5))
            for _ in range(int(operation.get("iterations", 6))):
                local = box_blur(candidate, 1)
                excess = np.maximum(np.abs(candidate - local) - talus, 0.0)
                candidate += np.sign(local - candidate) * excess * min(0.5, strength * 0.15)
            # A small deterministic valley carve gives diffusion a more natural drainage feel.
            curvature = candidate - box_blur(candidate, int(operation.get("channel_radius", 4)))
            candidate -= np.maximum(-curvature, 0.0) * float(operation.get("channel_strength", 0.08))
        elif name == "slope_limit":
            candidate = current.copy()
            limit = max(0.01, float(operation.get("max_slope", 2.0)))
            for _ in range(int(operation.get("iterations", 8))):
                local = box_blur(candidate, 1)
                candidate = local + np.clip(candidate - local, -limit, limit)
            candidate = current + (candidate - current) * strength
        elif name == "coastline_soften":
            sea = float(operation["sea_level"])
            band = max(0.1, float(operation.get("width", 6.0)))
            smooth = box_blur(current, int(operation.get("radius", 4)))
            coast_weight = np.clip(1.0 - np.abs(current - sea) / band, 0.0, 1.0)
            candidate = current + (smooth - current) * coast_weight * strength
        else:
            raise ValueError(f"Unsupported height operation: {name}")
        current = current + (candidate - current) * mask
        np.clip(current, min_height, max_height - 1, out=current)
    return current


def render_height(values: np.ndarray, output: str | Path) -> None:
    low, high = float(values.min()), float(values.max())
    normalized = np.zeros_like(values, dtype=np.uint8) if high <= low else ((values - low) * 255 / (high - low)).astype(np.uint8)
    Image.fromarray(normalized, "L").save(output)


def render_delta(before: np.ndarray, after: np.ndarray, output: str | Path) -> None:
    delta = after - before
    scale = max(float(np.max(np.abs(delta))), 0.001)
    rgb = np.zeros((*delta.shape, 3), dtype=np.uint8)
    positive = np.clip(delta / scale, 0, 1)
    negative = np.clip(-delta / scale, 0, 1)
    rgb[..., 0] = (negative * 255).astype(np.uint8)
    rgb[..., 1] = (np.minimum(positive, negative) * 80).astype(np.uint8)
    rgb[..., 2] = (positive * 255).astype(np.uint8)
    Image.fromarray(rgb, "RGB").save(output)
