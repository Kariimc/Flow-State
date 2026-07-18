"""Turn the source brand JPEGs (exported with a baked-in transparency
checkerboard) into clean transparent PNGs and the app's .ico files.

The -FS source art was exported as JPEG, so the "transparent" areas are a
flat gray checkerboard rather than a real alpha channel. This script removes
that checkerboard two ways:

* Isolated subjects on a checker field (tray crystal, F wordmark, waveform)
  are colour-keyed: the checker is low-saturation and sits at two gray
  luminances, so we flood the border-connected checker to alpha 0.
* Framed subjects whose body shares the checker's colour (the rounded-square
  desktop icon, the stadium pills) can't be colour-keyed - the body reads as
  checker. Those are masked by shape instead, keeping every original pixel.

Run from the repo root:  python assets/build_assets.py
Outputs: assets/*.png (committed) and, when --icons is passed or the app calls
build_icons(), models/flow.ico + models/flow-tray.ico.
"""
import os
from collections import deque

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def _load_rgb(name):
    return np.asarray(Image.open(os.path.join(HERE, name)).convert("RGB")).astype(np.int16)


def _checker_mask(a, tol=28):
    """Boolean mask of checker-like pixels: gray, at one of two corner shades."""
    h, w, _ = a.shape
    corners = np.concatenate([
        a[0:70, 0:70].reshape(-1, 3), a[0:70, w-70:w].reshape(-1, 3),
        a[h-70:h, 0:70].reshape(-1, 3), a[h-70:h, w-70:w].reshape(-1, 3),
    ])
    lum_c = corners.mean(axis=1)
    thr = (lum_c.min() + lum_c.max()) / 2
    lo = lum_c[lum_c <= thr].mean()
    hi = lum_c[lum_c > thr].mean()
    lo, hi = min(lo, hi), max(lo, hi)
    tol = max(9, min(tol, (hi - lo) * 0.75))
    lum = a.mean(axis=2)
    sat = a.max(axis=2) - a.min(axis=2)
    return (sat <= 24) & (lum >= lo - tol) & (lum <= hi + tol)


def _border_component(mask):
    """Keep only the part of `mask` connected to the image border (8-conn)."""
    h, w = mask.shape
    out = np.zeros_like(mask)
    seen = np.zeros_like(mask)
    dq = deque()
    for x in range(w):
        dq.append((0, x)); dq.append((h - 1, x))
    for y in range(h):
        dq.append((y, 0)); dq.append((y, w - 1))
    while dq:
        y, x = dq.popleft()
        if seen[y, x]:
            continue
        seen[y, x] = True
        if not mask[y, x]:
            continue
        out[y, x] = True
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                ny, nx = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx < w and not seen[ny, nx]:
                    dq.append((ny, nx))
    return out


def _to_rgba(a, alpha):
    return Image.fromarray(np.dstack([a.astype(np.uint8), alpha.astype(np.uint8)]), "RGBA")


def key_color(name, tol=28, glob=False):
    """Colour-key the checker (border-connected, or global for closed shapes)."""
    a = _load_rgb(name)
    checker = _checker_mask(a, tol)
    bg = checker if glob else _border_component(checker)
    img = _to_rgba(a, np.where(bg, 0, 255))
    return img.crop(img.getbbox())


def _content_bbox(a, tol=28):
    """Tight bbox of the framed subject. Uses coordinate percentiles so the
    soft drop shadow (a sparse fringe) doesn't inflate the box past the frame."""
    bg = _border_component(_checker_mask(a, tol))
    ys, xs = np.where(~bg)
    x0, x1 = np.percentile(xs, [0.3, 99.7])
    y0, y1 = np.percentile(ys, [0.3, 99.7])
    return int(x0), int(y0), int(x1) + 1, int(y1) + 1


def mask_shape(name, kind, tol=28, inset=0.015):
    """Crop to the framed subject and apply a stadium/rounded-rect alpha mask.
    `inset` pulls the mask slightly inside the crop so no shadow/checker halo
    survives at the corners."""
    a = _load_rgb(name)
    x0, y0, x1, y1 = _content_bbox(a, tol)
    crop = Image.fromarray(a[y0:y1, x0:x1].astype(np.uint8), "RGB").convert("RGBA")
    w, h = crop.size
    ss = 4  # supersample the mask for smooth edges
    m = int(round(min(w, h) * inset)) * ss
    mask = Image.new("L", (w * ss, h * ss), 0)
    d = ImageDraw.Draw(mask)
    box = (m, m, w * ss - 1 - m, h * ss - 1 - m)
    r = (h * ss) // 2 if kind == "stadium" else int(min(w, h) * ss * 0.22)
    d.rounded_rectangle(box, radius=r, fill=255)
    mask = mask.resize((w, h), Image.LANCZOS)
    crop.putalpha(mask)
    return crop.crop(crop.getbbox())


def _square(img, pad=0.06):
    """Center the art on a square transparent canvas with a little breathing room."""
    w, h = img.size
    side = int(max(w, h) * (1 + pad))
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.alpha_composite(img, ((side - w) // 2, (side - h) // 2))
    return canvas


def build_pngs():
    out = {}
    out["flow-icon.png"] = _square(mask_shape("desktop-icon.jpg", "roundrect", inset=0.03), 0.04)
    out["flow-tray.png"] = _square(key_color("tray-icon.jpg"), 0.08)
    out["flow-wordmark.png"] = key_color("hub-header.jpg")
    out["waveform.png"] = key_color("waveform.jpg", glob=True)
    out["pill-light.png"] = mask_shape("pill-light.jpg", "stadium", inset=0.02)
    out["pill-dark.png"] = mask_shape("pill-dark.jpg", "stadium", inset=0.02)
    for fname, img in out.items():
        img.save(os.path.join(HERE, fname))
        print(f"  assets/{fname}  {img.size}")
    # Header-sized wordmark: Tk's PhotoImage can't scale, so ship it pre-sized.
    wm = out["flow-wordmark.png"]
    h72 = 72
    wm72 = wm.resize((round(wm.width * h72 / wm.height), h72), Image.LANCZOS)
    wm72.save(os.path.join(HERE, "flow-wordmark-72.png"))
    print(f"  assets/flow-wordmark-72.png  {wm72.size}")
    return out


def build_icons(dest=None):
    """Write models/flow.ico and models/flow-tray.ico from the committed PNGs.
    Returns True on success. Safe to call at app startup; no-op-friendly."""
    dest = dest or os.path.join(ROOT, "models")
    os.makedirs(dest, exist_ok=True)
    plans = [
        ("flow-icon.png", "flow.ico", [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]),
        ("flow-tray.png", "flow-tray.ico", [(256, 256), (64, 64), (48, 48), (32, 32), (16, 16)]),
    ]
    ok = True
    for src, ico, sizes in plans:
        p = os.path.join(HERE, src)
        if not os.path.exists(p):
            ok = False
            continue
        img = Image.open(p).convert("RGBA")
        side = max(img.size)
        canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        canvas.alpha_composite(img, ((side - img.size[0]) // 2, (side - img.size[1]) // 2))
        canvas.save(os.path.join(dest, ico), sizes=sizes)
        print(f"  models/{ico}  {sizes[0]}..{sizes[-1]}")
    return ok


if __name__ == "__main__":
    print("Building transparent PNGs...")
    build_pngs()
    print("Building .ico files...")
    build_icons()
    print("Done.")
