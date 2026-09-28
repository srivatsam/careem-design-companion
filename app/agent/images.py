"""Perfume imagery: deterministic SVG bottle art per perfume, optionally upgraded to a generated PNG
via an Azure OpenAI image deployment (cached on disk so each perfume is generated once)."""
from __future__ import annotations

import hashlib
import logging
import os
import threading
from pathlib import Path

from app.config import settings
from app.data import taxonomy as tx

log = logging.getLogger("images")

FAMILY_PALETTE = {
    "floral":   ("#f6d7e2", "#c86b8f", "#7a2e4d"),
    "fresh":    ("#dff3ec", "#4fb08c", "#1f5f48"),
    "aquatic":  ("#d9ebf7", "#4f97c8", "#1f4f78"),
    "green":    ("#e2efd3", "#7aa85a", "#3d5c26"),
    "fruity":   ("#fbe3cf", "#e58a4a", "#8a4116"),
    "gourmand": ("#f3e2d0", "#b8804d", "#5c3a1a"),
    "woody":    ("#e8dccb", "#8a6a4f", "#3f2c1c"),
    "amber":    ("#f4e1c6", "#c9903f", "#6b4413"),
}
SHAPES = ["rect", "round", "tall", "flask", "square"]


def _svg(p: dict) -> str:
    light, mid, dark = FAMILY_PALETTE.get(p["family"], FAMILY_PALETTE["amber"])
    h = int(hashlib.sha1(p["perfume_id"].encode()).hexdigest(), 16)
    shape = SHAPES[h % len(SHAPES)]
    liquid = 0.45 + (h >> 8) % 40 / 100.0
    initials = "".join(w[0] for w in p["name"].split()[:2]).upper()
    brand = p["brand_name"][:26]
    name = p["name"][:28]
    if shape == "rect":
        body = f'<rect x="70" y="95" width="120" height="150" rx="14" fill="{light}" stroke="{dark}" stroke-width="3"/>'
        fill = f'<rect x="73" y="{95 + 150 * (1 - liquid):.0f}" width="114" height="{150 * liquid - 3:.0f}" rx="12" fill="{mid}" opacity="0.85"/>'
    elif shape == "round":
        body = f'<circle cx="130" cy="170" r="72" fill="{light}" stroke="{dark}" stroke-width="3"/>'
        fill = f'<path d="M62 {170 + 72 * (1 - 2 * liquid):.0f} A72 72 0 0 0 198 {170 + 72 * (1 - 2 * liquid):.0f} Z" fill="{mid}" opacity="0.85"/><circle cx="130" cy="170" r="72" fill="none" stroke="{dark}" stroke-width="3"/>'
    elif shape == "tall":
        body = f'<rect x="90" y="80" width="80" height="170" rx="18" fill="{light}" stroke="{dark}" stroke-width="3"/>'
        fill = f'<rect x="93" y="{80 + 170 * (1 - liquid):.0f}" width="74" height="{170 * liquid - 3:.0f}" rx="15" fill="{mid}" opacity="0.85"/>'
    elif shape == "flask":
        body = f'<path d="M110 95 h40 v40 l38 60 a20 20 0 0 1 -18 30 h-80 a20 20 0 0 1 -18 -30 l38 -60 z" fill="{light}" stroke="{dark}" stroke-width="3"/>'
        fill = f'<path d="M84 190 h92 l12 20 a10 10 0 0 1 -10 15 h-96 a10 10 0 0 1 -10 -15 z" fill="{mid}" opacity="0.85"/>'
    else:
        body = f'<rect x="65" y="110" width="130" height="130" rx="8" fill="{light}" stroke="{dark}" stroke-width="3"/>'
        fill = f'<rect x="68" y="{110 + 130 * (1 - liquid):.0f}" width="124" height="{130 * liquid - 3:.0f}" rx="6" fill="{mid}" opacity="0.85"/>'
    cap = f'<rect x="112" y="52" width="36" height="44" rx="6" fill="{dark}"/><rect x="104" y="90" width="52" height="10" rx="3" fill="{dark}"/>'
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 260 320" width="260" height="320" role="img" aria-label="{name}">
<defs><linearGradient id="bg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fbf8f3"/><stop offset="1" stop-color="{light}"/></linearGradient></defs>
<rect width="260" height="320" rx="20" fill="url(#bg)"/>
<ellipse cx="130" cy="262" rx="80" ry="10" fill="{dark}" opacity="0.12"/>
{cap}{body}{fill}
<rect x="88" y="150" width="84" height="46" rx="6" fill="#fffdf9" stroke="{dark}" stroke-width="1.5" opacity="0.95"/>
<text x="130" y="169" text-anchor="middle" font-family="Georgia, 'Times New Roman', serif" font-size="15" fill="{dark}" font-weight="bold">{initials}</text>
<text x="130" y="187" text-anchor="middle" font-family="Helvetica, Arial, sans-serif" font-size="8" fill="{dark}" letter-spacing="1">{brand.upper()[:18]}</text>
<text x="130" y="296" text-anchor="middle" font-family="Helvetica, Arial, sans-serif" font-size="12" fill="{dark}">{name}</text>
</svg>'''


def _escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def svg_for(p: dict) -> str:
    safe = dict(p)
    safe["name"] = _escape(p["name"])
    safe["brand_name"] = _escape(p["brand_name"])
    return _svg(safe)


# ---------------------------------------------------------------- generated PNGs (optional)
_cache_dir = Path(os.environ.get("IMAGE_CACHE_DIR", "data/images"))
_inflight: set[str] = set()
_lock = threading.Lock()


def image_deployment() -> str:
    return os.environ.get("AZURE_OPENAI_IMAGE_DEPLOYMENT", "").strip()


def png_path(perfume_id: str) -> Path:
    return _cache_dir / f"{perfume_id}.png"


def cached_png(perfume_id: str) -> Path | None:
    p = png_path(perfume_id)
    return p if p.exists() and p.stat().st_size > 0 else None


def _prompt(p: dict) -> str:
    notes = ", ".join(dict.fromkeys(n["note"] for n in p["notes"]))[:200]
    fam = tx.label("families", p["family"], "en").lower()
    return (f"Elegant product photograph of a perfume bottle for a {fam} fragrance with notes of {notes}. "
            "Studio lighting, soft neutral background, subtle props hinting at the notes, no text, no logos, no people, "
            "square composition, photorealistic.")


def request_generation(p: dict) -> None:
    """Generate the PNG in a background thread once; safe to call repeatedly."""
    if not image_deployment() or not settings.azure_openai_endpoint or not settings.azure_openai_api_key:
        return
    pid = p["perfume_id"]
    if cached_png(pid):
        return
    with _lock:
        if pid in _inflight:
            return
        _inflight.add(pid)

    def work():
        try:
            from openai import AzureOpenAI
            client = AzureOpenAI(api_key=settings.azure_openai_api_key, api_version=settings.azure_openai_api_version,
                                 azure_endpoint=settings.azure_openai_endpoint)
            _cache_dir.mkdir(parents=True, exist_ok=True)
            result = client.images.generate(model=image_deployment(), prompt=_prompt(p), n=1, size="1024x1024")
            data = result.data[0]
            if getattr(data, "b64_json", None):
                import base64
                png_path(pid).write_bytes(base64.b64decode(data.b64_json))
            elif getattr(data, "url", None):
                import httpx
                png_path(pid).write_bytes(httpx.get(data.url, timeout=60).content)
        except Exception as exc:  # never break the app over imagery
            log.warning("image generation failed for %s: %s", pid, exc)
        finally:
            with _lock:
                _inflight.discard(pid)

    threading.Thread(target=work, daemon=True).start()
