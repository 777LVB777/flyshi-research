"""A small, dependency-free SVG plotting helper for the paper figures.

matplotlib is not installed in this project's environments, and installing it would
be a download, so the figures are drawn directly as SVG (standard library only).
PNG copies are rendered from the SVG with macOS's own Quick Look (``qlmanage``) and
cropped with ``sips``; both ship with macOS and work offline.

Scope: what the finished-result figures need and nothing more. That is panels in
one figure; linear or log axes with "nice" ticks; categorical x axes; points,
lines, threshold lines, shaded bands, error bars, text and a legend.
"""

from __future__ import annotations

import math
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional, Sequence, Tuple
from xml.sax.saxutils import escape

FONT = "Helvetica, Arial, sans-serif"
#: Okabe-Ito colour-blind-safe palette
BLUE, ORANGE, GREEN, VERMILLION, PURPLE, SKY, YELLOW, GREY = (
    "#0072B2", "#E69F00", "#009E73", "#D55E00", "#CC79A7", "#56B4E9", "#F0E442", "#666666")


def nice_ticks(lo: float, hi: float, n: int = 5) -> List[float]:
    if hi <= lo:
        hi = lo + 1.0
    raw = (hi - lo) / max(n, 1)
    mag = 10 ** math.floor(math.log10(raw))
    step = next(m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw)
    start = math.ceil(lo / step - 1e-9) * step
    ticks, t = [], start
    while t <= hi + 1e-9 * step:
        ticks.append(round(t, 10))
        t += step
    return ticks


def fmt(v: float) -> str:
    if v == 0:
        return "0"
    if abs(v) >= 1000:
        return f"{v:,.0f}"
    if float(v).is_integer():
        return f"{v:.0f}"
    return f"{v:g}"


class Axes:
    def __init__(self, left: float, top: float, width: float, height: float) -> None:
        self.box = (left, top, width, height)
        self.items: List[tuple] = []
        self.xlim: Optional[Tuple[float, float]] = None
        self.ylim: Optional[Tuple[float, float]] = None
        self.ylog = False
        self.xcats: Optional[List[str]] = None
        self.xlabel = self.ylabel = self.title = ""
        self.legend_items: List[Tuple[str, str, str]] = []  # (label, kind, colour)
        self.legend_loc = "upper right"
        self.texts: List[tuple] = []
        self.yticks: Optional[List[float]] = None
        self.xticks: Optional[List[float]] = None

    # -- data -- #
    def scatter(self, xs, ys, color=BLUE, marker="o", size=4.0, label=None, opacity=1.0):
        self.items.append(("scatter", list(xs), list(ys), color, marker, size, opacity))
        if label:
            self.legend_items.append((label, "marker:" + marker, color))

    def line(self, xs, ys, color=BLUE, width=1.6, dash=None, label=None):
        self.items.append(("line", list(xs), list(ys), color, width, dash))
        if label:
            self.legend_items.append((label, "line:" + (dash or ""), color))

    def hline(self, y, color=GREY, width=1.2, dash="6 4", label=None):
        self.items.append(("hline", y, color, width, dash))
        if label:
            self.legend_items.append((label, "line:" + (dash or ""), color))

    def vline(self, x, color=GREY, width=1.2, dash="6 4", label=None):
        self.items.append(("vline", x, color, width, dash))
        if label:
            self.legend_items.append((label, "line:" + (dash or ""), color))

    def hband(self, y0, y1, color=GREY, opacity=0.12, label=None):
        self.items.append(("hband", y0, y1, color, opacity))
        if label:
            self.legend_items.append((label, "band", color))

    def vband(self, x0, x1, color=GREY, opacity=0.12, label=None):
        self.items.append(("vband", x0, x1, color, opacity))
        if label:
            self.legend_items.append((label, "band", color))

    def errorbar(self, xs, ys, lows, highs, color=BLUE, cap=4.0, width=1.4):
        self.items.append(("err", list(xs), list(ys), list(lows), list(highs), color, cap, width))

    def bar(self, xs, heights, width=0.6, color=BLUE, opacity=0.35, label=None):
        self.items.append(("bar", list(xs), list(heights), width, color, opacity))
        if label:
            self.legend_items.append((label, "band", color))

    def text(self, x, y, s, size=10, anchor="start", color="#222", data=True, weight="normal"):
        self.texts.append((x, y, s, size, anchor, color, data, weight))

    # -- scales -- #
    def _limits(self):
        xs, ys = [], []
        for it in self.items:
            k = it[0]
            if k in ("scatter", "line"):
                xs += it[1]
                ys += it[2]
            elif k == "hline":
                ys.append(it[1])
            elif k == "vline":
                xs.append(it[1])
            elif k == "hband":
                ys += [it[1], it[2]]
            elif k == "vband":
                xs += [it[1], it[2]]
            elif k == "err":
                xs += it[1]
                ys += it[3] + it[4]
            elif k == "bar":
                xs += it[1]
                ys += it[2] + [0.0]
        ys = [y for y in ys if y is not None and math.isfinite(y) and (not self.ylog or y > 0)]
        xs = [x for x in xs if x is not None and math.isfinite(x)]
        if self.xcats is not None:
            xl = (-0.6, len(self.xcats) - 0.4)
        elif self.xlim:
            xl = self.xlim
        else:
            lo, hi = (min(xs), max(xs)) if xs else (0, 1)
            pad = 0.06 * (hi - lo or 1)
            xl = (lo - pad, hi + pad)
        if self.ylim:
            yl = self.ylim
        elif self.ylog:
            lo, hi = (min(ys), max(ys)) if ys else (1, 10)
            yl = (10 ** math.floor(math.log10(lo)), 10 ** math.ceil(math.log10(hi)))
        else:
            lo, hi = (min(ys), max(ys)) if ys else (0, 1)
            pad = 0.08 * (hi - lo or 1)
            yl = (lo - pad, hi + pad)
        return xl, yl

    def _tx(self, x, xl):
        left, _, w, _ = self.box
        return left + (x - xl[0]) / (xl[1] - xl[0]) * w

    def _ty(self, y, yl):
        _, top, _, h = self.box
        if self.ylog:
            y = math.log10(max(y, 1e-300))
            lo, hi = math.log10(yl[0]), math.log10(yl[1])
        else:
            lo, hi = yl
        return top + h - (y - lo) / (hi - lo) * h

    # -- rendering -- #
    def render(self) -> List[str]:
        xl, yl = self._limits()
        left, top, w, h = self.box
        out: List[str] = [f'<clipPath id="c{id(self)}"><rect x="{left}" y="{top}" width="{w}" height="{h}"/></clipPath>']
        clip = f'clip-path="url(#c{id(self)})"'
        X = lambda v: self._tx(v, xl)  # noqa: E731
        Y = lambda v: self._ty(v, yl)  # noqa: E731
        # gridlines and ticks
        if self.ylog:
            yt = [10 ** e for e in range(int(round(math.log10(yl[0]))), int(round(math.log10(yl[1]))) + 1)]
        else:
            yt = self.yticks or nice_ticks(yl[0], yl[1])
        for t in yt:
            if yl[0] - 1e-12 <= t <= yl[1] + 1e-12:
                yy = Y(t)
                out.append(f'<line x1="{left}" y1="{yy:.2f}" x2="{left + w}" y2="{yy:.2f}" stroke="#e6e6e6" stroke-width="1"/>')
                out.append(f'<text x="{left - 6}" y="{yy + 3.5:.2f}" font-size="10.5" text-anchor="end" '
                           f'font-family="{FONT}" fill="#333">{escape(fmt(t))}</text>')
        if self.xcats is not None:
            for i, name in enumerate(self.xcats):
                xx = X(i)
                for j, part in enumerate(name.split("\n")):
                    out.append(f'<text x="{xx:.2f}" y="{top + h + 16 + 12 * j:.2f}" font-size="10.5" text-anchor="middle" '
                               f'font-family="{FONT}" fill="#333">{escape(part)}</text>')
        else:
            for t in (self.xticks or nice_ticks(xl[0], xl[1])):
                if xl[0] - 1e-12 <= t <= xl[1] + 1e-12:
                    xx = X(t)
                    out.append(f'<line x1="{xx:.2f}" y1="{top + h}" x2="{xx:.2f}" y2="{top + h + 4}" stroke="#333"/>')
                    out.append(f'<text x="{xx:.2f}" y="{top + h + 16}" font-size="10.5" text-anchor="middle" '
                               f'font-family="{FONT}" fill="#333">{escape(fmt(t))}</text>')
        # data
        for it in self.items:
            k = it[0]
            if k == "hband":
                y0, y1 = sorted((Y(it[1]), Y(it[2])))
                out.append(f'<rect x="{left}" y="{y0:.2f}" width="{w}" height="{y1 - y0:.2f}" fill="{it[3]}" '
                           f'fill-opacity="{it[4]}" {clip}/>')
            elif k == "vband":
                x0, x1 = sorted((X(it[1]), X(it[2])))
                out.append(f'<rect x="{x0:.2f}" y="{top}" width="{x1 - x0:.2f}" height="{h}" fill="{it[3]}" '
                           f'fill-opacity="{it[4]}" {clip}/>')
        for it in self.items:
            k = it[0]
            if k == "bar":
                _, xs, hs, bw, color, op = it
                for x, hh in zip(xs, hs):
                    x0, x1 = X(x - bw / 2), X(x + bw / 2)
                    y0, y1 = sorted((Y(0.0), Y(hh)))
                    out.append(f'<rect x="{x0:.2f}" y="{y0:.2f}" width="{x1 - x0:.2f}" height="{y1 - y0:.2f}" '
                               f'fill="{color}" fill-opacity="{op}" stroke="{color}" stroke-width="1" {clip}/>')
            elif k == "hline":
                yy = Y(it[1])
                dash = f' stroke-dasharray="{it[4]}"' if it[4] else ""
                out.append(f'<line x1="{left}" y1="{yy:.2f}" x2="{left + w}" y2="{yy:.2f}" stroke="{it[2]}" '
                           f'stroke-width="{it[3]}"{dash} {clip}/>')
            elif k == "vline":
                xx = X(it[1])
                dash = f' stroke-dasharray="{it[4]}"' if it[4] else ""
                out.append(f'<line x1="{xx:.2f}" y1="{top}" x2="{xx:.2f}" y2="{top + h}" stroke="{it[2]}" '
                           f'stroke-width="{it[3]}"{dash} {clip}/>')
            elif k == "line":
                _, xs, ys, color, width, dash = it
                pts = " ".join(f"{X(x):.2f},{Y(y):.2f}" for x, y in zip(xs, ys) if y is not None)
                d = f' stroke-dasharray="{dash}"' if dash else ""
                out.append(f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="{width}"{d} {clip}/>')
            elif k == "err":
                _, xs, ys, lo, hi, color, cap, width = it
                for x, y, a, b in zip(xs, ys, lo, hi):
                    xx = X(x)
                    out.append(f'<line x1="{xx:.2f}" y1="{Y(a):.2f}" x2="{xx:.2f}" y2="{Y(b):.2f}" stroke="{color}" '
                               f'stroke-width="{width}" {clip}/>')
                    for v in (a, b):
                        out.append(f'<line x1="{xx - cap:.2f}" y1="{Y(v):.2f}" x2="{xx + cap:.2f}" y2="{Y(v):.2f}" '
                                   f'stroke="{color}" stroke-width="{width}" {clip}/>')
            elif k == "scatter":
                _, xs, ys, color, marker, size, op = it
                for x, y in zip(xs, ys):
                    if y is None or (self.ylog and y <= 0):
                        continue
                    out.append(marker_svg(X(x), Y(y), marker, size, color, op))
        # frame
        out.append(f'<rect x="{left}" y="{top}" width="{w}" height="{h}" fill="none" stroke="#333" stroke-width="1"/>')
        for (x, y, s, size, anchor, color, data, weight) in self.texts:
            px, py = (X(x), Y(y)) if data else (left + x * w, top + y * h)
            out.append(f'<text x="{px:.2f}" y="{py:.2f}" font-size="{size}" text-anchor="{anchor}" font-weight="{weight}" '
                       f'font-family="{FONT}" fill="{color}">{escape(s)}</text>')
        if self.title:
            out.append(f'<text x="{left}" y="{top - 10}" font-size="13" font-weight="bold" font-family="{FONT}" '
                       f'fill="#111">{escape(self.title)}</text>')
        if self.xlabel:
            extra = 12 * (max(n.count("\n") for n in self.xcats) if self.xcats else 0)
            out.append(f'<text x="{left + w / 2}" y="{top + h + 38 + extra}" font-size="12" text-anchor="middle" '
                       f'font-family="{FONT}" fill="#111">{escape(self.xlabel)}</text>')
        if self.ylabel:
            cx, cy = left - 50, top + h / 2
            out.append(f'<text x="{cx}" y="{cy}" font-size="12" text-anchor="middle" font-family="{FONT}" '
                       f'fill="#111" transform="rotate(-90 {cx} {cy})">{escape(self.ylabel)}</text>')
        out += self._legend()
        return out

    def _legend(self) -> List[str]:
        if not self.legend_items:
            return []
        left, top, w, h = self.box
        row, pad = 16, 8
        width = 22 + max(len(lbl) for lbl, _, _ in self.legend_items) * 6.1 + 2 * pad
        height = row * len(self.legend_items) + pad
        x0 = left + w - width - 6 if "right" in self.legend_loc else left + 6
        y0 = top + 6 if "upper" in self.legend_loc else top + h - height - 6
        out = [f'<rect x="{x0:.1f}" y="{y0:.1f}" width="{width:.1f}" height="{height:.1f}" fill="white" '
               f'fill-opacity="0.92" stroke="#bbb"/>']
        for i, (label, kind, color) in enumerate(self.legend_items):
            cy = y0 + pad + row * i + 5
            sx = x0 + pad
            if kind.startswith("marker:"):
                out.append(marker_svg(sx + 7, cy, kind.split(":", 1)[1], 4.0, color, 1.0))
            elif kind.startswith("line:"):
                dash = kind.split(":", 1)[1]
                d = f' stroke-dasharray="{dash}"' if dash else ""
                out.append(f'<line x1="{sx}" y1="{cy}" x2="{sx + 14}" y2="{cy}" stroke="{color}" stroke-width="1.8"{d}/>')
            else:
                out.append(f'<rect x="{sx}" y="{cy - 5}" width="14" height="10" fill="{color}" fill-opacity="0.3" '
                           f'stroke="{color}"/>')
            out.append(f'<text x="{sx + 20}" y="{cy + 4}" font-size="10.5" font-family="{FONT}" fill="#222">'
                       f'{escape(label)}</text>')
        return out


def marker_svg(x: float, y: float, marker: str, size: float, color: str, opacity: float) -> str:
    op = f' fill-opacity="{opacity}" stroke-opacity="{opacity}"' if opacity < 1 else ""
    if marker == "o":
        return f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{size}" fill="{color}"{op}/>'
    if marker == "open":
        return f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{size}" fill="white" stroke="{color}" stroke-width="1.6"/>'
    if marker == "D":
        s = size * 1.35
        return (f'<polygon points="{x:.2f},{y - s:.2f} {x + s:.2f},{y:.2f} {x:.2f},{y + s:.2f} {x - s:.2f},{y:.2f}" '
                f'fill="{color}" stroke="#111" stroke-width="0.8"{op}/>')
    if marker == "s":
        return f'<rect x="{x - size:.2f}" y="{y - size:.2f}" width="{2 * size}" height="{2 * size}" fill="{color}"{op}/>'
    if marker == "x":
        s = size
        return (f'<path d="M{x - s:.2f} {y - s:.2f} L{x + s:.2f} {y + s:.2f} M{x - s:.2f} {y + s:.2f} L{x + s:.2f} '
                f'{y - s:.2f}" stroke="{color}" stroke-width="2"/>')
    if marker == "^":
        s = size * 1.3
        return (f'<polygon points="{x:.2f},{y - s:.2f} {x + s:.2f},{y + s * 0.8:.2f} {x - s:.2f},{y + s * 0.8:.2f}" '
                f'fill="{color}"{op}/>')
    raise ValueError(f"unknown marker {marker!r}")


def wrap_caption(text: str, width: int) -> List[str]:
    """Explicit line breaks are kept; longer lines are wrapped at word boundaries."""
    import textwrap
    return [w for line in text.split("\n") for w in (textwrap.wrap(line, width) or [""])]


class Figure:
    def __init__(self, width: float, height: float, title: str = "", caption: str = "") -> None:
        self.width, self.height, self.title, self.caption = width, height, title, caption
        self.axes: List[Axes] = []

    def add_axes(self, left: float, top: float, width: float, height: float) -> Axes:
        ax = Axes(left, top, width, height)
        self.axes.append(ax)
        return ax

    def svg(self) -> str:
        parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.width}" height="{self.height}" '
                 f'viewBox="0 0 {self.width} {self.height}">',
                 f'<rect width="{self.width}" height="{self.height}" fill="white"/>']
        if self.title:
            parts.append(f'<text x="20" y="26" font-size="15" font-weight="bold" font-family="{FONT}" fill="#111">'
                         f'{escape(self.title)}</text>')
        for ax in self.axes:
            parts += ax.render()
        lines = wrap_caption(self.caption, int((self.width - 40) / 5.6)) if self.caption else []
        for i, line in enumerate(lines):
            parts.append(f'<text x="20" y="{self.height - 14 - 14 * (len(lines) - 1 - i)}" '
                         f'font-size="10.5" font-family="{FONT}" fill="#444">{escape(line)}</text>')
        parts.append("</svg>")
        return "\n".join(parts)

    def save(self, svg_path: Path, png: bool = True, png_width: int = 1800) -> Optional[Path]:
        svg_path = Path(svg_path)
        svg_path.parent.mkdir(parents=True, exist_ok=True)
        svg_path.write_text(self.svg())
        if not png:
            return None
        return svg_to_png(svg_path, svg_path.with_suffix(".png"), png_width, self.width, self.height)


def png_tools_available() -> bool:
    return bool(shutil.which("qlmanage") and shutil.which("sips"))


def svg_to_png(svg: Path, png: Path, width_px: int, w: float, h: float) -> Optional[Path]:
    """Render with Quick Look, then crop to the figure's aspect with sips. Returns the
    PNG path, or None if the tools are missing.

    Quick Look makes square thumbnails and does not fit a wide SVG into them (it
    zooms and anchors it top-left). So the figure is first wrapped in a square SVG,
    centred vertically; the square render then fits exactly, and a centred crop
    recovers the figure."""
    if not png_tools_available():
        return None
    height_px = int(round(width_px * h / w))
    side = max(w, h)
    inner = Path(svg).read_text().split("\n", 1)[1].rsplit("</svg>", 1)[0]
    with tempfile.TemporaryDirectory() as tmp:
        square = Path(tmp) / svg.name
        square.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" width="{side}" height="{side}" '
                          f'viewBox="0 0 {side} {side}"><rect width="{side}" height="{side}" fill="white"/>'
                          f'<g transform="translate({(side - w) / 2} {(side - h) / 2})">{inner}</g></svg>')
        subprocess.run(["qlmanage", "-t", "-s", str(width_px), "-o", tmp, str(square)],
                       capture_output=True, check=True, timeout=120)
        rendered = Path(tmp) / (svg.name + ".png")
        if not rendered.exists():
            raise RuntimeError(f"qlmanage did not render {svg}")
        subprocess.run(["sips", "-c", str(height_px), str(width_px), str(rendered), "--out", str(png)],
                       capture_output=True, check=True, timeout=120)
    return png
