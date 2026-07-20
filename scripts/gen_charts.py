#!/usr/bin/env python3
"""Generate self-hosted profile charts (star history + language mix).

Why self-hosted: third-party card services (star-history.com,
github-readme-stats) share one pool of GitHub tokens and return 503 /
"rate-limited" for hours at a time, which renders as a broken image on the
profile. These SVGs are committed to the repo, so they always render.

Refreshed weekly by .github/workflows/charts.yml.
Only reads public data from the GitHub API; writes only into assets/.
"""

from __future__ import annotations

import json
import math
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

USER = "tytsxai"

# Repos shown in the star-history chart, in legend order.
STAR_REPOS = [
    "IDM-Activation-Script-Chinese",
    "bazi-master",
    "PromptPanel",
    "bilibili-cleaner",
    "macfriends-cli",
    "anyreality-resi-stack",
]

SERIES_COLORS = [
    "#e3b341",  # amber
    "#3fb950",  # green
    "#58a6ff",  # blue
    "#bc8cff",  # purple
    "#f778ba",  # pink
    "#39c5cf",  # cyan
]

ASSETS = Path(__file__).resolve().parent.parent / "assets"

# Palette per theme: (axis/label, grid, subtle text)
THEMES = {
    "light": {"fg": "#57606a", "grid": "#d8dee4", "muted": "#6e7781"},
    "dark": {"fg": "#8b949e", "grid": "#30363d", "muted": "#7d8590"},
}


def api(path: str, accept: str = "application/vnd.github+json") -> tuple[object, dict]:
    url = path if path.startswith("http") else f"https://api.github.com{path}"
    req = urllib.request.Request(url)
    req.add_header("Accept", accept)
    req.add_header("User-Agent", f"{USER}-profile-charts")
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            return json.loads(resp.read().decode()), dict(resp.headers)
    except urllib.error.HTTPError as exc:  # surfaced by the caller
        raise RuntimeError(f"{url} -> HTTP {exc.code}: {exc.read()[:200]!r}") from exc


def stargazer_dates(repo: str) -> list[datetime]:
    """All starred_at timestamps for a repo, oldest first."""
    dates: list[datetime] = []
    page = 1
    while True:
        data, _ = api(
            f"/repos/{USER}/{repo}/stargazers?per_page=100&page={page}",
            accept="application/vnd.github.star+json",
        )
        if not data:
            break
        for item in data:
            stamp = item.get("starred_at")
            if stamp:
                dates.append(datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc))
        if len(data) < 100:
            break
        page += 1
        if page > 60:  # 6k stars guard; the API caps out around here anyway
            break
    dates.sort()
    return dates


def esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# --------------------------------------------------------------------------
# star history
# --------------------------------------------------------------------------

W, H = 880, 400
PAD_L, PAD_R, PAD_T, PAD_B = 58, 22, 74, 42


def log_y(value: int, top: int) -> float:
    """Log scale so a 1k-star repo and a 4-star repo share one readable chart."""
    lo, hi = 0.0, math.log10(top)
    frac = (math.log10(max(value, 1)) - lo) / (hi - lo)
    return H - PAD_B - frac * (H - PAD_T - PAD_B)


def render_stars(series: list[tuple[str, list[datetime]]], theme: str) -> str:
    c = THEMES[theme]
    active = [(name, dates) for name, dates in series if dates]
    if not active:
        return ""

    all_dates = [d for _, dates in active for d in dates]
    t0, t1 = min(all_dates), max(all_dates)
    span = max((t1 - t0).total_seconds(), 1.0)
    peak = max(len(dates) for _, dates in active)
    top = 10 ** math.ceil(math.log10(max(peak, 10)))

    def x_of(dt: datetime) -> float:
        return PAD_L + (dt - t0).total_seconds() / span * (W - PAD_L - PAD_R)

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif">',
        "<style>text{font-size:11px}.lg{font-size:12px}.ti{font-size:13px;font-weight:600}</style>",
    ]

    # y grid (decades)
    decade = 1
    while decade <= top:
        y = log_y(decade, top)
        out.append(
            f'<line x1="{PAD_L}" y1="{y:.1f}" x2="{W - PAD_R}" y2="{y:.1f}" stroke="{c["grid"]}" stroke-width="1"/>'
        )
        out.append(
            f'<text x="{PAD_L - 8}" y="{y + 4:.1f}" fill="{c["muted"]}" text-anchor="end">{decade:,}</text>'
        )
        decade *= 10

    # x ticks: 5 evenly spaced points across the observed range
    steps = 4
    ticks = [t0 + timedelta(seconds=span * i / steps) for i in range(steps + 1)]
    for tick in ticks:
        x = x_of(tick)
        out.append(
            f'<line x1="{x:.1f}" y1="{PAD_T}" x2="{x:.1f}" y2="{H - PAD_B}" stroke="{c["grid"]}" stroke-width="1" stroke-dasharray="3 4"/>'
        )
        out.append(
            f'<text x="{x:.1f}" y="{H - PAD_B + 18}" fill="{c["muted"]}" text-anchor="middle">{tick.strftime("%Y-%m-%d")}</text>'
        )

    # series
    for idx, (name, dates) in enumerate(active):
        color = SERIES_COLORS[idx % len(SERIES_COLORS)]
        pts = [f"{x_of(dates[0]):.1f},{log_y(1, top):.1f}"]
        step = max(1, len(dates) // 400)  # keep the path small on big repos
        for i in range(0, len(dates), step):
            pts.append(f"{x_of(dates[i]):.1f},{log_y(i + 1, top):.1f}")
        pts.append(f"{x_of(dates[-1]):.1f},{log_y(len(dates), top):.1f}")
        out.append(
            f'<polyline fill="none" stroke="{color}" stroke-width="2.2" stroke-linejoin="round" '
            f'stroke-linecap="round" points="{" ".join(pts)}"/>'
        )
        out.append(
            f'<circle cx="{x_of(dates[-1]):.1f}" cy="{log_y(len(dates), top):.1f}" r="3.4" fill="{color}"/>'
        )

    # title + legend
    out.append(f'<text x="{PAD_L}" y="20" class="ti" fill="{c["fg"]}">Star history</text>')
    out.append(
        f'<text x="{W - PAD_R}" y="20" text-anchor="end" fill="{c["muted"]}">'
        f'log scale · updated {datetime.now(timezone.utc):%Y-%m-%d}</text>'
    )
    lx, ly = PAD_L, 38
    for idx, (name, dates) in enumerate(active):
        color = SERIES_COLORS[idx % len(SERIES_COLORS)]
        label = f"{name} ({len(dates)})"
        width = 16 + len(label) * 6.4
        if lx + width > W - PAD_R:
            lx, ly = PAD_L, ly + 17
        out.append(f'<rect x="{lx}" y="{ly - 7}" width="9" height="9" rx="2" fill="{color}"/>')
        out.append(f'<text x="{lx + 14}" y="{ly + 1}" class="lg" fill="{c["fg"]}">{esc(label)}</text>')
        lx += width + 12

    out.append("</svg>")
    return "\n".join(out)


# --------------------------------------------------------------------------
# language mix
# --------------------------------------------------------------------------

LW, LH = 880, 118
LANG_COLORS = {
    "Python": "#3572A5", "TypeScript": "#3178c6", "JavaScript": "#f1e05a",
    "Rust": "#dea584", "Swift": "#F05138", "Shell": "#89e051", "Go": "#00ADD8",
    "Batchfile": "#C1F12E", "HTML": "#e34c26", "CSS": "#563d7c", "C": "#555555",
    "C++": "#f34b7d", "Java": "#b07219", "Ruby": "#701516", "Objective-C++": "#6866fb",
    "PowerShell": "#012456", "Dockerfile": "#384d54", "Makefile": "#427819",
}


def render_langs(totals: dict[str, int], theme: str) -> str:
    c = THEMES[theme]
    total = sum(totals.values())
    if not total:
        return ""
    ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
    top = ranked[:8]
    other = sum(v for _, v in ranked[8:])
    if other:
        top.append(("Other", other))

    bar_x, bar_y, bar_w, bar_h = 0, 30, LW, 14
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{LW}" height="{LH}" viewBox="0 0 {LW} {LH}" '
        f'font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif">',
        "<style>text{font-size:11.5px}.ti{font-size:13px;font-weight:600}</style>",
        f'<text x="0" y="16" class="ti" fill="{c["fg"]}">Language mix across public repos</text>',
        f'<text x="{LW}" y="16" text-anchor="end" fill="{c["muted"]}">by bytes of code</text>',
        f'<clipPath id="r"><rect x="{bar_x}" y="{bar_y}" width="{bar_w}" height="{bar_h}" rx="7"/></clipPath>',
        '<g clip-path="url(#r)">',
    ]
    cursor = float(bar_x)
    for name, value in top:
        seg = value / total * bar_w
        color = LANG_COLORS.get(name, "#8b949e")
        out.append(f'<rect x="{cursor:.2f}" y="{bar_y}" width="{seg + 0.5:.2f}" height="{bar_h}" fill="{color}"/>')
        cursor += seg
    out.append("</g>")

    lx, ly = 0, 68
    for name, value in top:
        pct = value / total * 100
        color = LANG_COLORS.get(name, "#8b949e")
        label = f"{name} {pct:.1f}%"
        width = 16 + len(label) * 6.3
        if lx + width > LW:
            lx, ly = 0, ly + 20
        out.append(f'<circle cx="{lx + 5}" cy="{ly - 4}" r="5" fill="{color}"/>')
        out.append(f'<text x="{lx + 15}" y="{ly}" fill="{c["fg"]}">{esc(label)}</text>')
        lx += width + 10

    out.append("</svg>")
    return "\n".join(out)


# --------------------------------------------------------------------------

def main() -> int:
    ASSETS.mkdir(parents=True, exist_ok=True)

    series: list[tuple[str, list[datetime]]] = []
    for repo in STAR_REPOS:
        try:
            dates = stargazer_dates(repo)
        except RuntimeError as exc:
            print(f"  ! {repo}: {exc}", file=sys.stderr)
            continue
        print(f"  {repo}: {len(dates)} stars")
        series.append((repo, dates))

    repos, _ = api(f"/users/{USER}/repos?per_page=100&type=owner")
    totals: dict[str, int] = {}
    for repo in repos:
        if repo.get("fork") or repo.get("archived"):
            continue
        langs, _ = api(f"/repos/{USER}/{repo['name']}/languages")
        for name, size in langs.items():
            totals[name] = totals.get(name, 0) + size
    print(f"  languages: {len(totals)} across {len(repos)} repos")

    written = []
    for theme in THEMES:
        suffix = "" if theme == "light" else "-dark"
        star_svg = render_stars(series, theme)
        if star_svg:
            path = ASSETS / f"star-history{suffix}.svg"
            path.write_text(star_svg + "\n", encoding="utf-8")
            written.append(path)
        lang_svg = render_langs(totals, theme)
        if lang_svg:
            path = ASSETS / f"languages{suffix}.svg"
            path.write_text(lang_svg + "\n", encoding="utf-8")
            written.append(path)

    for path in written:
        print(f"  wrote {path.relative_to(ASSETS.parent)} ({path.stat().st_size:,} bytes)")
    return 0 if written else 1


if __name__ == "__main__":
    raise SystemExit(main())
