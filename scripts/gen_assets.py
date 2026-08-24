#!/usr/bin/env python3
"""Generate every visual on the profile as a self-hosted SVG.

Design direction — "status board":
Delivery engineering is judged on whether it still runs after handover.
So the profile is dressed as an ops console: monospace data rows, hairline
rules, status dots, and a real 52-week shipping-cadence strip. Every accent
colour carries meaning (green = live, amber = traction, blue = information)
rather than decoration.

Practical reason it is self-hosted: star-history.com and github-readme-stats
share one pool of GitHub tokens and serve 503 for hours at a time, and
shields.io dynamic badges render as "invalid" when their upstream hiccups.
Committed SVGs cannot break.

Refreshed weekly by .github/workflows/charts.yml.
Reads public GitHub data only; writes only into assets/.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

USER = "tytsxai"
NAME = "qilai"
ROLE = "AI APPLICATION & DELIVERY ENGINEER"
SIGNOFF = "BUILD  ·  DEPLOY  ·  OPERATE  ·  HAND OVER"
# Email is the only contact channel published anywhere on this profile.
EMAIL = "wwtvn1937@gmail.com"

# Repos shown in the "selected work" panel, in display order. Keep this in
# sync with the pinned repositories on the profile. The blurb is written by
# hand; language and star count are read from the API on every run, so the
# panel can never drift away from what a visitor sees on the repo page.
WORK_REPOS = [
    ("IDM-Activation-Script-Chinese", "Chinese GBK toolkit · registry backup, no patching"),
    ("bazi-master", "Divination platform — BaZi, Tarot, I Ching, AI reading"),
    ("cleanplate", "Local-first video watermark removal — FastAPI + ComfyUI"),
    ("bilibili-cleaner", "Bulk cleanup for Bilibili accounts — QR login, web UI"),
    ("PromptPanel", "Native macOS prompt launcher with a global hotkey"),
    ("virtual-chem-lab", "Gamified virtual chemistry lab for teaching and drills"),
]

ASSETS = Path(__file__).resolve().parent.parent / "assets"

MONO = "ui-monospace,SFMono-Regular,SF Mono,Menlo,Consolas,Liberation Mono,monospace"

# One token set per theme. `surface` matches GitHub's own panel colour so the
# assets read as part of the page rather than as pasted-in images.
THEMES = {
    "light": {
        "surface": "#f6f8fa", "border": "#d0d7de", "rule": "#d8dee4",
        "ink": "#1f2328", "muted": "#656d76", "faint": "#8c959f",
        "green": "#1a7f37", "amber": "#9a6700", "blue": "#0969da", "purple": "#8250df",
        "heat": ["#eaeef2", "#aceebb", "#4ac26b", "#2da44e", "#116329"],
    },
    "dark": {
        "surface": "#161b22", "border": "#30363d", "rule": "#30363d",
        "ink": "#e6edf3", "muted": "#8b949e", "faint": "#7d8590",
        "green": "#3fb950", "amber": "#e3b341", "blue": "#58a6ff", "purple": "#bc8cff",
        "heat": ["#21262d", "#0e4429", "#006d32", "#26a641", "#39d353"],
    },
}

W = 880  # every asset shares one width so the column reads as a single system


# ---------------------------------------------------------------- data layer

def api(path: str, accept: str = "application/vnd.github+json"):
    url = path if path.startswith("http") else f"https://api.github.com{path}"
    req = urllib.request.Request(url)
    req.add_header("Accept", accept)
    req.add_header("User-Agent", f"{USER}-profile-assets")
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=45) as resp:
        body = resp.read().decode()
        return (json.loads(body) if body else None), resp.status


def work_rows() -> list[dict]:
    """Live language + star count for every repo in WORK_REPOS.

    A repo that has been renamed, archived away or made private is skipped
    rather than fabricated, so the panel shrinks instead of lying.
    """
    rows: list[dict] = []
    for name, blurb in WORK_REPOS:
        try:
            repo, _ = api(f"/repos/{USER}/{name}")
        except (urllib.error.HTTPError, urllib.error.URLError) as exc:
            print(f"  ! {name}: {exc}", file=sys.stderr)
            continue
        rows.append(
            {
                "name": name,
                "blurb": blurb,
                "lang": repo.get("language") or "—",
                "stars": repo.get("stargazers_count", 0),
            }
        )
    return rows


def weekly_commits(repos: list[str]) -> list[int]:
    """Commits per week for the last 52 weeks, summed over every repo.

    GitHub computes these stats lazily and answers 202 while the cache warms,
    so each repo gets a couple of retries before it is skipped.
    """
    weeks = [0] * 52
    for repo in repos:
        for attempt in range(3):
            try:
                data, status = api(f"/repos/{USER}/{repo}/stats/commit_activity")
            except urllib.error.HTTPError as exc:
                if exc.code in (403, 404):
                    break
                raise
            if status == 202 or data is None:
                time.sleep(2 + attempt * 2)
                continue
            for i, week in enumerate(data[-52:]):
                weeks[i] += week.get("total", 0)
            break
    return weeks


# ------------------------------------------------------------- svg plumbing

def esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def head(height: int, c: dict, panel: bool = True) -> list[str]:
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{height}" '
        f'viewBox="0 0 {W} {height}" font-family="{MONO}">',
        "<style>"
        f".lbl{{font-size:10.5px;letter-spacing:1.4px;fill:{c['faint']}}}"
        ".val{font-size:12.5px}"
        ".nm{font-size:38px;font-weight:600;letter-spacing:-0.5px}"
        ".rl{font-size:13px;letter-spacing:3.2px;font-weight:500}"
        ".ax{font-size:10.5px}.lg{font-size:11px}"
        ".st{font-size:12.5px;letter-spacing:1.6px;font-weight:600}"
        "</style>",
    ]
    if panel:
        out.append(
            f'<rect x="0.5" y="0.5" width="{W - 1}" height="{height - 1}" rx="10" '
            f'fill="{c["surface"]}" stroke="{c["border"]}"/>'
        )
    return out


def label(x: float, y: float, text: str, c: dict) -> str:
    return f'<text x="{x}" y="{y}" class="lbl">{esc(text)}</text>'


def value(x: float, y: float, text: str, c: dict, fill: str | None = None) -> str:
    return f'<text x="{x}" y="{y}" class="val" fill="{fill or c["ink"]}">{esc(text)}</text>'


# -------------------------------------------------------------------- hero

HERO_H = 338
PAD = 28


def render_hero(theme: str, stats: dict, weeks: list[int]) -> str:
    c = THEMES[theme]
    out = head(HERO_H, c)

    # header hairline: who / when
    out.append(label(PAD, 27, f"{USER.upper()}  ·  CHINA GMT+8", c))
    out.append(
        f'<text x="{W - PAD}" y="27" class="lbl" text-anchor="end">'
        f'UPDATED {datetime.now(timezone.utc):%Y-%m-%d}</text>'
    )
    out.append(f'<line x1="0" y1="44" x2="{W}" y2="44" stroke="{c["rule"]}"/>')

    # identity
    out.append(
        f'<text x="{PAD}" y="98" class="nm" fill="{c["ink"]}">{esc(NAME)}</text>'
    )
    out.append(
        f'<text x="{PAD}" y="126" class="rl" fill="{c["blue"]}">{esc(ROLE)}</text>'
    )

    # data grid — two columns, four rows. Right-hand values stay under ~44
    # characters or they run past the panel edge.
    rows = [
        ("FOCUS", "agent workflows · RAG · automation", None),
        ("EXPERIENCE", "4 yrs engineering · AI in prod since 2023", None),
        ("DELIVERY", "1-2 week MVP · build → deploy → operate", None),
        ("DEPTH", "state machines · idempotency · rollback", None),
    ]
    right = [
        ("BASED", "China · GMT+8", None),
        ("WORK MODE", "onsite · remote · client site", None),
        ("AVAILABLE", "immediately · no notice period", c["green"]),
        ("PUBLIC WORK", f"{stats['repos']} own repos · {stats['stars']:,} stars", c["amber"]),
    ]
    ry = 158
    for (l1, v1, f1), (l2, v2, f2) in zip(rows, right):
        out.append(label(PAD, ry, l1, c))
        out.append(value(PAD + 96, ry, v1, c, f1))
        out.append(label(468, ry, l2, c))
        out.append(value(468 + 96, ry, v2, c, f2))
        ry += 22

    # signature: 52 weeks of shipping cadence, GitHub's own heat scale
    strip_y = 258
    out.append(label(PAD, strip_y - 8, "SHIPPING CADENCE  ·  52 WEEKS", c))
    peak = max(weeks) or 1
    n = len(weeks)
    gap = 2.6
    bw = (W - 2 * PAD - gap * (n - 1)) / n
    for i, count in enumerate(weeks):
        if count == 0:
            tier = 0
        else:
            tier = min(4, 1 + int(count / peak * 3.999))
        x = PAD + i * (bw + gap)
        out.append(
            f'<rect x="{x:.2f}" y="{strip_y}" width="{bw:.2f}" height="24" rx="2.5" fill="{c["heat"][tier]}"/>'
        )
    out.append(
        f'<text x="{W - PAD}" y="{strip_y - 8}" class="lbl" text-anchor="end">'
        f'{sum(weeks):,} COMMITS</text>'
    )

    # status line
    sy = 316
    out.append(f'<circle cx="{PAD + 4}" cy="{sy - 4}" r="4.5" fill="{c["green"]}"/>')
    out.append(
        f'<text x="{PAD + 16}" y="{sy}" class="st" fill="{c["green"]}">OPEN TO WORK</text>'
    )
    out.append(
        f'<text x="{PAD + 148}" y="{sy}" class="val" fill="{c["muted"]}">{esc(SIGNOFF)}</text>'
    )
    out.append(
        f'<text x="{W - PAD}" y="{sy}" class="val" text-anchor="end" fill="{c["muted"]}">'
        f'email  <tspan fill="{c["blue"]}">{esc(EMAIL)}</tspan></text>'
    )

    out.append("</svg>")
    return "\n".join(out)


# ------------------------------------------------------------------- stack

STACK = [
    ("LANGUAGES", "TypeScript · Python · Swift · Rust · Bash", "ink"),
    ("AI / LLM", "LLM APIs · tool calling · agent workflows · JSON Schema · MCP · RAG", "purple"),
    ("BACKEND", "Node.js · FastAPI · Express · PostgreSQL · Redis · BullMQ", "ink"),
    ("FRONTEND", "React · Next.js · Vite · Tailwind · SwiftUI", "ink"),
    ("RETRIEVAL", "Meilisearch · pgvector · hybrid recall · rerank · SimHash dedup", "blue"),
    ("INFRA", "Docker · Linux · Nginx · GitHub Actions · GPU model serving (ComfyUI/SD)", "ink"),
    ("PRACTICE", "idempotent retries · human handoff · structured logs · cost per call", "green"),
]


def render_stack(theme: str) -> str:
    c = THEMES[theme]
    height = 60 + len(STACK) * 26
    out = head(height, c)
    out.append(label(PAD, 27, "STACK  ·  WHAT I ACTUALLY BUILD WITH", c))
    out.append(f'<line x1="0" y1="44" x2="{W}" y2="44" stroke="{c["rule"]}"/>')
    y = 70
    for name, items, tone in STACK:
        out.append(label(PAD, y, name, c))
        out.append(value(PAD + 104, y, items, c, c[tone] if tone != "ink" else None))
        y += 26
    out.append("</svg>")
    return "\n".join(out)


# ------------------------------------------------------------ selected work

WORK_ROW_H = 30


def render_work(rows: list[dict], stats: dict, theme: str) -> str:
    """One row per pinned repo: language dot, name, language, stars, blurb."""
    if not rows:
        return ""
    c = THEMES[theme]
    height = 74 + len(rows) * WORK_ROW_H
    out = head(height, c)
    out.append(label(PAD, 27, "SELECTED WORK  ·  PINNED REPOSITORIES", c))
    out.append(
        f'<text x="{W - PAD}" y="27" class="lbl" text-anchor="end">'
        f'{stats["repos"]} PUBLIC REPOS  ·  {stats["stars"]:,} STARS</text>'
    )
    out.append(f'<line x1="0" y1="44" x2="{W}" y2="44" stroke="{c["rule"]}"/>')

    y = 72
    for row in rows:
        dot = LANG_COLORS.get(row["lang"], c["faint"])
        out.append(f'<circle cx="{PAD + 4}" cy="{y - 4}" r="4" fill="{dot}"/>')
        out.append(value(PAD + 16, y, row["name"], c, c["blue"]))
        out.append(
            f'<text x="{PAD + 330}" y="{y}" class="lg" text-anchor="end" fill="{c["amber"]}">'
            f'{row["stars"]} \u2605</text>'
        )
        out.append(
            f'<text x="{PAD + 352}" y="{y}" class="lg" fill="{c["muted"]}">{esc(row["blurb"])}</text>'
        )
        y += WORK_ROW_H

    out.append("</svg>")
    return "\n".join(out)


# -------------------------------------------------------------- languages

LANG_H = 128
LANG_COLORS = {
    "Python": "#3572A5", "TypeScript": "#3178c6", "JavaScript": "#f1e05a",
    "Rust": "#dea584", "Swift": "#F05138", "Shell": "#89e051", "Go": "#00ADD8",
    "Batchfile": "#C1F12E", "HTML": "#e34c26", "CSS": "#563d7c", "C": "#555555",
    "C++": "#f34b7d", "Java": "#b07219", "Objective-C++": "#6866fb",
    "PowerShell": "#012456", "Dockerfile": "#384d54", "Makefile": "#427819",
}


def render_langs(totals: dict[str, int], theme: str) -> str:
    c = THEMES[theme]
    total = sum(totals.values())
    if not total:
        return ""
    ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
    top, rest = ranked[:8], sum(v for _, v in ranked[8:])
    if rest:
        top.append(("Other", rest))

    out = head(LANG_H, c)
    out.append(label(PAD, 27, "LANGUAGE MIX  ·  ALL PUBLIC REPOS", c))
    out.append(f'<text x="{W - PAD}" y="27" class="lbl" text-anchor="end">BY BYTES OF CODE</text>')
    out.append(f'<line x1="0" y1="44" x2="{W}" y2="44" stroke="{c["rule"]}"/>')

    bar_y, bar_h, bar_w = 62, 12, W - 2 * PAD
    out.append(f'<clipPath id="clip"><rect x="{PAD}" y="{bar_y}" width="{bar_w}" height="{bar_h}" rx="6"/></clipPath>')
    out.append('<g clip-path="url(#clip)">')
    cursor = float(PAD)
    for name, val in top:
        seg = val / total * bar_w
        out.append(
            f'<rect x="{cursor:.2f}" y="{bar_y}" width="{seg + 0.6:.2f}" height="{bar_h}" '
            f'fill="{LANG_COLORS.get(name, c["faint"])}"/>'
        )
        cursor += seg
    out.append("</g>")

    lx, ly = PAD, 100
    for name, val in top:
        text = f"{name} {val / total * 100:.1f}%"
        width = 14 + len(text) * 6.7
        if lx + width > W - PAD:
            lx, ly = PAD, ly + 19
        out.append(f'<circle cx="{lx + 4}" cy="{ly - 4}" r="4" fill="{LANG_COLORS.get(name, c["faint"])}"/>')
        out.append(f'<text x="{lx + 13}" y="{ly}" class="lg" fill="{c["muted"]}">{esc(text)}</text>')
        lx += width + 10

    out.append("</svg>")
    return "\n".join(out)


# --------------------------------------------------------------------- main

def main() -> int:
    ASSETS.mkdir(parents=True, exist_ok=True)

    repos, _ = api(f"/users/{USER}/repos?per_page=100&type=owner")
    owned = [r for r in repos if not r.get("fork")]
    stats = {
        "repos": len(owned),
        "stars": sum(r.get("stargazers_count", 0) for r in owned),
    }
    print(f"  {stats['repos']} repos · {stats['stars']} stars")

    totals: dict[str, int] = {}
    for repo in owned:
        if repo.get("archived"):
            continue
        langs, _ = api(f"/repos/{USER}/{repo['name']}/languages")
        for name, size in (langs or {}).items():
            totals[name] = totals.get(name, 0) + size
    print(f"  {len(totals)} languages")

    weeks = weekly_commits([r["name"] for r in owned])
    print(f"  {sum(weeks)} commits over 52 weeks")

    work = work_rows()
    for row in work:
        print(f"  {row['name']}: {row['lang']} · {row['stars']} stars")

    written = []
    for theme in THEMES:
        suffix = "" if theme == "light" else "-dark"
        for stem, svg in (
            ("hero", render_hero(theme, stats, weeks)),
            ("stack", render_stack(theme)),
            ("work", render_work(work, stats, theme)),
            ("languages", render_langs(totals, theme)),
        ):
            if not svg:
                continue
            path = ASSETS / f"{stem}{suffix}.svg"
            path.write_text(svg + "\n", encoding="utf-8")
            written.append(path)

    for path in written:
        print(f"  wrote {path.relative_to(ASSETS.parent)} ({path.stat().st_size:,} B)")
    return 0 if written else 1


if __name__ == "__main__":
    raise SystemExit(main())
