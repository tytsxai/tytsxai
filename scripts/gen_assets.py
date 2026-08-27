#!/usr/bin/env python3
"""Generate every visual on the profile as a self-hosted SVG.

Design direction — "engineering dossier":
Four panels that each do a different job and therefore look different.
The hero states who and how much; the stack panel shows breadth as a chip
matrix in real brand colours; the language board shows how far each language
reaches across the repository set; the work panel puts the star counts where
they can actually be seen.

Type is a two-font system: monospace carries labels, chips and data (it is
the working font of the job) while the system sans carries display numbers
and the name, so the eye has somewhere to land. Accent colours all mean
something — green is live, amber is traction, blue is information, and a
technology's chip wears its own brand colour.

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

USER = "qilaidev"
NAME = "qilai"
ROLE = "AI APPLICATION & DELIVERY ENGINEER"
TAGLINE = "Agent workflows, retrieval and automation, taken all the way into production"
SIGNOFF = "BUILD  ·  DEPLOY  ·  OPERATE  ·  HAND OVER"
EMAIL = "wwtvn1937@gmail.com"

# Repos shown in the "selected work" panel. Keep this set in sync with the
# evidence table in README.md — the two drifting apart is the failure mode
# this list exists to prevent. Order here does not matter: the panel sorts by
# star count at render time so the strongest evidence always leads. Blurbs are
# written by hand; language and stars come from the API on every run, so the
# panel can never claim a number the repo page contradicts.
WORK_REPOS = [
    ("IDM-Activation-Script-Chinese", "Windows toolkit with real users — issues, GBK encoding, registry rollback"),
    ("bazi-master", "Full-stack divination platform — React, Express, PostgreSQL, LLM readings"),
    ("cleanplate", "Local-first video watermark removal — FastAPI, ComfyUI, async job queue"),
    ("bilibili-cleaner", "Destructive automation done safely — QR login, rate limits, review gate"),
    ("PromptPanel", "Native macOS prompt launcher — Swift, SwiftUI, global hotkey, local-first"),
    ("macfriends-cli", "Systems-level Rust + ObjC++ agent, ABI-pinned, never touches the network"),
]

ASSETS = Path(__file__).resolve().parent.parent / "assets"

MONO = "ui-monospace,SFMono-Regular,SF Mono,Menlo,Consolas,Liberation Mono,monospace"
SANS = "-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"

# Monospace advance width is a fixed fraction of the font size, which is the
# whole reason the chip and column maths below works without measuring text.
MONO_RATIO = 0.605


def mw(size: float, text: str) -> float:
    return len(text) * size * MONO_RATIO


# One token set per theme. Surfaces match GitHub's own so the assets read as
# part of the page rather than as pasted-in images.
THEMES = {
    "light": {
        "surface": "#ffffff", "sunken": "#f6f8fa", "border": "#d0d7de", "rule": "#d8dee4",
        "ink": "#1f2328", "muted": "#656d76", "faint": "#8c959f",
        "green": "#1a7f37", "amber": "#9a6700", "blue": "#0969da", "purple": "#8250df",
        "heat": ["#eaeef2", "#aceebb", "#4ac26b", "#2da44e", "#116329"],
        "chip_fill": 0.10, "chip_stroke": 0.40,
    },
    "dark": {
        "surface": "#0d1117", "sunken": "#161b22", "border": "#30363d", "rule": "#21262d",
        "ink": "#e6edf3", "muted": "#8b949e", "faint": "#6e7681",
        "green": "#3fb950", "amber": "#e3b341", "blue": "#58a6ff", "purple": "#bc8cff",
        "heat": ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"],
        "chip_fill": 0.18, "chip_stroke": 0.50,
    },
}

W = 880   # every asset shares one width so the column reads as a single system
PAD = 28


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


def head(height: int, c: dict) -> list[str]:
    """Panel shell plus the shared type scale.

    Sizes sit deliberately far apart — 29px display numbers against 9.5px
    labels — because the previous revision set nearly everything at 12.5px
    and left the eye nowhere to land.
    """
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{height}" '
        f'viewBox="0 0 {W} {height}" font-family="{MONO}" role="img">',
        "<style>"
        f".kicker{{font-size:9.5px;letter-spacing:1.7px;font-weight:600;fill:{c['faint']}}}"
        f".label{{font-size:9.5px;letter-spacing:1.5px;fill:{c['faint']}}}"
        f".body{{font-size:11.5px;fill:{c['muted']}}}"
        f".data{{font-size:12px;fill:{c['ink']}}}"
        ".chip{font-size:11px}"
        f".name{{font-family:{SANS};font-size:44px;font-weight:700;letter-spacing:-1.2px;fill:{c['ink']}}}"
        f".num{{font-family:{SANS};font-size:29px;font-weight:700;letter-spacing:-0.8px}}"
        f".role{{font-size:12px;letter-spacing:2.6px;font-weight:600;fill:{c['blue']}}}"
        f".repo{{font-size:13.5px;font-weight:600;fill:{c['blue']}}}"
        f".stars{{font-family:{SANS};font-size:15px;font-weight:700;fill:{c['amber']}}}"
        "</style>",
        f'<rect x="0.5" y="0.5" width="{W - 1}" height="{height - 1}" rx="12" '
        f'fill="{c["surface"]}" stroke="{c["border"]}"/>',
    ]


def kicker(y: float, left: str, right: str, c: dict) -> list[str]:
    """Every panel opens on the same hairline rail: what this is, and one fact."""
    return [
        f'<text x="{PAD}" y="{y}" class="kicker">{esc(left)}</text>',
        f'<text x="{W - PAD}" y="{y}" class="label" text-anchor="end">{esc(right)}</text>',
        f'<line x1="0" y1="{y + 17}" x2="{W}" y2="{y + 17}" stroke="{c["rule"]}"/>',
    ]


CHIP_H = 23
CHIP_TEXT = 11


def chip_width(text: str) -> float:
    return 22 + mw(CHIP_TEXT, text) + 12


def chip(x: float, y: float, text: str, color: str, c: dict) -> str:
    """A pill in the technology's own brand colour.

    Fill and stroke are the same hue at different alphas, so one colour
    definition stays legible on either surface.
    """
    return (
        f'<g><rect x="{x:.1f}" y="{y:.1f}" width="{chip_width(text):.1f}" height="{CHIP_H}" rx="6" '
        f'fill="{color}" fill-opacity="{c["chip_fill"]}" '
        f'stroke="{color}" stroke-opacity="{c["chip_stroke"]}"/>'
        f'<circle cx="{x + 11:.1f}" cy="{y + CHIP_H / 2:.1f}" r="3.2" fill="{color}"/>'
        f'<text x="{x + 21:.1f}" y="{y + CHIP_H / 2 + 4:.1f}" class="chip" fill="{c["ink"]}">{esc(text)}</text></g>'
    )


# -------------------------------------------------------------------- hero

HERO_H = 340


def cadence_tiers(weeks: list[int]):
    """Map a week's commit count to a heat tier by quantile, not by peak.

    Scaling linearly against the peak week is what the previous revision did,
    and a single 500-commit week flattened 44 of the other 51 into one shade —
    a strip that looks like data but carries none. Quartiles of the non-zero
    weeks keep the contrast where the variation actually is.
    """
    active = sorted(c for c in weeks if c > 0)
    if not active:
        return lambda count: 0
    cuts = [active[int(len(active) * q)] for q in (0.25, 0.55, 0.85)]

    def tier(count: int) -> int:
        if count == 0:
            return 0
        return 1 + sum(count > cut for cut in cuts)

    return tier


def render_hero(theme: str, stats: dict, weeks: list[int], lang_count: int) -> str:
    c = THEMES[theme]
    out = head(HERO_H, c)

    # top rail — availability first, because it is the one line a visitor who
    # is hiring needs before anything else on the page
    out.append(f'<circle cx="{PAD + 4}" cy="23" r="4.5" fill="{c["green"]}"/>')
    out.append(f'<text x="{PAD + 16}" y="27" class="kicker" fill="{c["green"]}">OPEN TO WORK</text>')
    out.append(
        f'<text x="{W - PAD}" y="27" class="label" text-anchor="end">'
        f'{USER.upper()}  ·  GMT+8  ·  UPDATED {datetime.now(timezone.utc):%Y-%m-%d}</text>'
    )
    out.append(f'<line x1="0" y1="44" x2="{W}" y2="44" stroke="{c["rule"]}"/>')

    # identity
    out.append(f'<text x="{PAD}" y="102" class="name">{esc(NAME)}</text>')
    out.append(f'<text x="{PAD}" y="128" class="role">{esc(ROLE)}</text>')
    out.append(f'<text x="{PAD}" y="152" class="body">{esc(TAGLINE)}</text>')

    # stat tiles — these numbers used to sit inside a 12.5px text grid, which
    # is the whole reason several hundred stars read as a footnote
    tiles = [
        (f"{stats['repos']}", "PUBLIC REPOS", c["ink"]),
        (f"{stats['stars']:,}", "STARS EARNED", c["amber"]),
        (f"{lang_count}", "LANGUAGES", c["blue"]),
        (f"{sum(weeks):,}", "COMMITS · 52W", c["green"]),
    ]
    tw, gap = (W - 2 * PAD - 3 * 12) / 4, 12
    ty = 176
    for i, (num, cap, fill) in enumerate(tiles):
        tx = PAD + i * (tw + gap)
        out.append(
            f'<rect x="{tx:.1f}" y="{ty}" width="{tw:.1f}" height="66" rx="9" '
            f'fill="{c["sunken"]}" stroke="{c["border"]}"/>'
        )
        out.append(f'<text x="{tx + 16:.1f}" y="{ty + 36}" class="num" fill="{fill}">{esc(num)}</text>')
        out.append(f'<text x="{tx + 17:.1f}" y="{ty + 54}" class="label">{esc(cap)}</text>')

    # signature: 52 weeks of shipping cadence on GitHub's own heat scale
    strip_y = 274
    out.append(f'<text x="{PAD}" y="{strip_y - 8}" class="label">SHIPPING CADENCE  ·  52 WEEKS</text>')
    out.append(f'<text x="{W - PAD}" y="{strip_y - 8}" class="label" text-anchor="end">{esc(SIGNOFF)}</text>')
    n = len(weeks)
    bar_gap = 2.6
    bw = (W - 2 * PAD - bar_gap * (n - 1)) / n
    tier_of = cadence_tiers(weeks)
    for i, count in enumerate(weeks):
        tier = tier_of(count)
        x = PAD + i * (bw + bar_gap)
        out.append(
            f'<rect x="{x:.2f}" y="{strip_y}" width="{bw:.2f}" height="22" rx="2.5" fill="{c["heat"][tier]}"/>'
        )

    out.append(
        f'<text x="{PAD}" y="{strip_y + 46}" class="data" fill="{c["muted"]}">'
        f'email  <tspan fill="{c["blue"]}">{esc(EMAIL)}</tspan></text>'
    )
    out.append(
        f'<text x="{W - PAD}" y="{strip_y + 46}" class="label" text-anchor="end">'
        f'ONSITE  ·  REMOTE  ·  CLIENT SITE</text>'
    )

    out.append("</svg>")
    return "\n".join(out)


# ------------------------------------------------------------------- stack

# Each technology carries its own brand colour. `None` means "use the theme's
# ink", which is how brands that are literally black (Next.js, shadcn/ui,
# Express) stay visible on a dark surface.
STACK = [
    ("LANGUAGES", "#3776AB", [
        ("Python", "#3776AB"), ("TypeScript", "#3178C6"), ("JavaScript", "#F0DB4F"),
        ("Rust", "#CE422B"), ("Swift", "#F05138"), ("Java", "#ED8B00"),
        ("Bash", "#4EAA25"), ("SQL", "#4479A1"), ("Objective-C++", "#6866FB"),
    ]),
    ("AI  /  LLM", "#8250df", [
        ("Claude", "#D97757"), ("OpenAI", "#10A37F"), ("MCP", "#7C3AED"),
        ("Tool Calling", "#8250df"), ("Multi-Agent", "#8250df"), ("RAG", "#8250df"),
        ("Structured Output", "#8250df"), ("Evals", "#8250df"), ("Guardrails", "#8250df"),
    ]),
    ("BACKEND", "#009688", [
        ("FastAPI", "#009688"), ("Node.js", "#5FA04E"), ("Express", None),
        ("PostgreSQL", "#4169E1"), ("Redis", "#FF4438"), ("Prisma", "#5A67D8"),
        ("SQLAlchemy", "#D71F00"), ("Celery", "#37814A"), ("BullMQ", "#EA4335"),
    ]),
    ("FRONTEND", "#61DAFB", [
        ("React", "#61DAFB"), ("Next.js", None), ("Vite", "#646CFF"),
        ("Tailwind", "#06B6D4"), ("shadcn/ui", None), ("SwiftUI", "#F05138"),
    ]),
    ("DATA  /  SEARCH", "#FF5CAA", [
        ("Meilisearch", "#FF5CAA"), ("pgvector", "#4169E1"), ("Hybrid Recall", "#0969da"),
        ("Rerank", "#0969da"), ("CN Tokenisation", "#0969da"), ("SimHash Dedup", "#0969da"),
    ]),
    ("INFRA  /  OPS", "#2496ED", [
        ("Docker", "#2496ED"), ("Linux", "#FCC624"), ("Nginx", "#009639"),
        ("GitHub Actions", "#2088FF"), ("Cloudflare", "#F38020"), ("systemd", "#30A2C7"),
        ("GPU Serving", "#76B900"),
    ]),
    ("PRACTICE", "#1a7f37", [
        ("Idempotent Retries", "#1a7f37"), ("State Machines", "#1a7f37"),
        ("Dry-run Gates", "#1a7f37"), ("Rate Limits", "#1a7f37"),
        ("Structured Logs", "#1a7f37"), ("Rollback Paths", "#1a7f37"),
        ("Human Handoff", "#1a7f37"), ("Cost per Call", "#1a7f37"),
    ]),
]

LANE_X = 152          # chips start here; the lane label lives in the gutter left of it
CHIP_GAP = 7
CHIP_ROW = 30


def _lane_rows(items):
    """Greedy-wrap chips into rows that fit between LANE_X and the right pad."""
    limit = W - PAD
    rows, row, x = [], [], float(LANE_X)
    for name, color in items:
        width = chip_width(name)
        if row and x + width > limit:
            rows.append(row)
            row, x = [], float(LANE_X)
        row.append((name, color, width))
        x += width + CHIP_GAP
    if row:
        rows.append(row)
    return rows


def render_stack(theme: str) -> str:
    c = THEMES[theme]
    lanes = [(label, accent, _lane_rows(items)) for label, accent, items in STACK]
    body = sum(len(rows) * CHIP_ROW + 14 for _, _, rows in lanes)
    height = int(58 + body)

    out = head(height, c)
    out.extend(kicker(27, "STACK  ·  WHAT I ACTUALLY BUILD WITH", "SHIPPED, NOT SKIMMED", c))

    y = 60
    for label, accent, rows in lanes:
        block = len(rows) * CHIP_ROW
        # a short colour rail anchors each lane so categories can be scanned
        # without reading a single word
        out.append(
            f'<rect x="{PAD}" y="{y + 4:.1f}" width="3" height="{max(block - 12, 8):.1f}" rx="1.5" fill="{accent}"/>'
        )
        out.append(f'<text x="{PAD + 14}" y="{y + 19:.1f}" class="label">{esc(label)}</text>')
        for r, row in enumerate(rows):
            x = float(LANE_X)
            for name, color, width in row:
                out.append(chip(x, y + r * CHIP_ROW + 2, name, color or c["ink"], c))
                x += width + CHIP_GAP
        y += block + 14

    out.append("</svg>")
    return "\n".join(out)


# ------------------------------------------------------------ selected work

WORK_ROW_H = 44


def render_work(rows: list[dict], stats: dict, theme: str) -> str:
    """One card per pinned repo: language dot, name, star tile, one line of why."""
    if not rows:
        return ""
    c = THEMES[theme]
    rows = sorted(rows, key=lambda r: r["stars"], reverse=True)
    height = 60 + len(rows) * WORK_ROW_H + 8
    out = head(height, c)
    out.extend(kicker(27, "SELECTED WORK  ·  PUBLIC AND RUNNING",
                      f'{stats["repos"]} REPOS  ·  {stats["stars"]:,} STARS', c))

    y = 58
    for row in rows:
        dot = LANG_COLORS.get(row["lang"], c["faint"])
        star_text = f'{row["stars"]:,}'
        # the star count is the hardest evidence here, so it gets its own tile
        # on the right instead of an 11px number lost in the text flow
        tile_w = max(60.0, 34 + len(star_text) * 9)
        tile_x = W - PAD - tile_w
        lit = row["stars"] > 0
        tone = c["amber"] if lit else c["faint"]
        out.append(
            f'<rect x="{tile_x:.1f}" y="{y + 2:.1f}" width="{tile_w:.1f}" height="30" rx="7" '
            f'fill="{tone}" fill-opacity="{c["chip_fill"] if lit else 0.06}" '
            f'stroke="{tone}" stroke-opacity="{c["chip_stroke"] if lit else 0.25}"/>'
        )
        out.append(
            f'<text x="{tile_x + tile_w / 2:.1f}" y="{y + 23:.1f}" class="stars" '
            f'text-anchor="middle" fill="{tone}">★ {esc(star_text)}</text>'
        )

        out.append(f'<circle cx="{PAD + 4}" cy="{y + 13:.1f}" r="4.5" fill="{dot}"/>')
        out.append(f'<text x="{PAD + 18}" y="{y + 18:.1f}" class="repo">{esc(row["name"])}</text>')
        lang_x = PAD + 18 + mw(13.5, row["name"]) + 12
        out.append(f'<text x="{lang_x:.1f}" y="{y + 18:.1f}" class="label">{esc(row["lang"].upper())}</text>')
        out.append(f'<text x="{PAD + 18}" y="{y + 34:.1f}" class="body">{esc(row["blurb"])}</text>')
        y += WORK_ROW_H

    out.append("</svg>")
    return "\n".join(out)


# -------------------------------------------------------------- languages

LANG_COLORS = {
    "Python": "#3572A5", "TypeScript": "#3178c6", "JavaScript": "#f1e05a",
    "Rust": "#dea584", "Swift": "#F05138", "Shell": "#89e051", "Go": "#00ADD8",
    "Batchfile": "#C1F12E", "HTML": "#e34c26", "CSS": "#663399", "C": "#555555",
    "C++": "#f34b7d", "Java": "#b07219", "Objective-C++": "#6866fb",
    "PowerShell": "#012456", "Dockerfile": "#384d54", "Makefile": "#427819",
    "PLpgSQL": "#336790", "Go Template": "#00ADD8", "Inno Setup": "#264b99",
    "Mako": "#7e858d", "Ruby": "#701516", "Kotlin": "#A97BFF", "Vue": "#41b883",
}

LANG_ROWS = 6         # rows per column
LANG_COLS = 2


def render_langs(totals: dict, repo_count: dict, repos: int, theme: str) -> str:
    """Language board — byte share on top, reach across repositories below.

    Bytes alone told a misleading story: Python is over half the code, so a
    lone stacked bar renders as "Python developer" and buries the fact that
    Swift is an entire native app and Shell touches most of the repositories.
    Each language therefore gets a row, and that row's meter is repo reach —
    the number that actually shows breadth — with byte share kept as text.
    """
    c = THEMES[theme]
    total = sum(totals.values())
    if not total:
        return ""
    ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
    shown = ranked[:LANG_ROWS * LANG_COLS]

    bar_y, bar_h = 62, 18
    row_y0 = bar_y + bar_h + 42
    tail = ranked[LANG_ROWS * LANG_COLS:]
    height = int(row_y0 + LANG_ROWS * 26 + (24 if tail else 6))

    out = head(height, c)
    out.extend(kicker(27, "LANGUAGE BOARD  ·  ALL PUBLIC REPOS",
                      f"{len(totals)} LANGUAGES  ·  {repos} REPOS", c))

    # full-width share bar: the one place byte share is the honest metric
    bar_w = W - 2 * PAD
    out.append(
        f'<clipPath id="bclip"><rect x="{PAD}" y="{bar_y}" width="{bar_w}" height="{bar_h}" rx="5"/></clipPath>'
    )
    out.append('<g clip-path="url(#bclip)">')
    cursor = float(PAD)
    for name, val in ranked:
        seg = val / total * bar_w
        out.append(
            f'<rect x="{cursor:.2f}" y="{bar_y}" width="{max(seg, 0.8) + 0.6:.2f}" height="{bar_h}" '
            f'fill="{LANG_COLORS.get(name, c["faint"])}"/>'
        )
        cursor += seg
    out.append("</g>")
    out.append(f'<text x="{PAD}" y="{bar_y + bar_h + 20}" class="label">ABOVE  =  SHARE OF CODE BY BYTES</text>')
    out.append(
        f'<text x="{W - PAD}" y="{bar_y + bar_h + 20}" class="label" text-anchor="end">'
        f'METERS BELOW  =  REPOSITORIES IT APPEARS IN</text>'
    )

    # per-language rows in two columns, split by a hairline so the eye does not
    # read a left row and a right row as one long run-on line
    gutter = 44.0
    col_w = (W - 2 * PAD - gutter) / LANG_COLS
    rule_x = PAD + col_w + gutter / 2
    out.append(
        f'<line x1="{rule_x:.1f}" y1="{row_y0 - 18:.1f}" x2="{rule_x:.1f}" '
        f'y2="{row_y0 + (LANG_ROWS - 1) * 26 + 6:.1f}" stroke="{c["border"]}"/>'
    )

    name_w, meter_w = 106.0, 100.0
    for i, (name, val) in enumerate(shown):
        col, row = i // LANG_ROWS, i % LANG_ROWS
        x = PAD + col * (col_w + gutter)
        y = row_y0 + row * 26
        color = LANG_COLORS.get(name, c["faint"])
        reach = repo_count.get(name, 0)

        out.append(f'<circle cx="{x + 4:.1f}" cy="{y - 4:.1f}" r="4" fill="{color}"/>')
        out.append(f'<text x="{x + 15:.1f}" y="{y:.1f}" class="data">{esc(name)}</text>')

        mx = x + 15 + name_w
        out.append(
            f'<rect x="{mx:.1f}" y="{y - 11:.1f}" width="{meter_w}" height="8" rx="4" '
            f'fill="{c["sunken"]}" stroke="{c["border"]}" stroke-opacity="0.6"/>'
        )
        fill_w = max(4.0, reach / max(repos, 1) * meter_w)
        out.append(f'<rect x="{mx:.1f}" y="{y - 11:.1f}" width="{fill_w:.1f}" height="8" rx="4" fill="{color}"/>')

        # byte share sits next to the meter because it is the headline number;
        # reach trails it as the supporting one
        out.append(
            f'<text x="{mx + meter_w + 46:.1f}" y="{y:.1f}" class="data" text-anchor="end" '
            f'fill="{c["muted"]}">{val / total * 100:.1f}%</text>'
        )
        out.append(
            f'<text x="{mx + meter_w + 58:.1f}" y="{y:.1f}" class="body">'
            f'{reach} {"repo" if reach == 1 else "repos"}</text>'
        )

    if tail:
        # this runs unattended every week, so the tail has to be clipped to the
        # panel rather than trusted to stay short as more languages appear
        names, budget = [], (W - 2 * PAD) - mw(11.5, "also shipped: ")
        for name, _ in tail:
            piece = (", " if names else "") + name
            if mw(11.5, piece) > budget:
                names.append(f"+{len(tail) - len(names)} more")
                break
            names.append(piece if not names else piece)
            budget -= mw(11.5, piece)
        line = "".join(names) if names else ""
        out.append(f'<text x="{PAD}" y="{height - 14:.1f}" class="body">also shipped: {esc(line)}</text>')

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
    repo_count: dict[str, int] = {}
    for repo in owned:
        if repo.get("archived"):
            continue
        langs, _ = api(f"/repos/{USER}/{repo['name']}/languages")
        for name, size in (langs or {}).items():
            totals[name] = totals.get(name, 0) + size
            repo_count[name] = repo_count.get(name, 0) + 1
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
            ("hero", render_hero(theme, stats, weeks, len(totals))),
            ("stack", render_stack(theme)),
            ("work", render_work(work, stats, theme)),
            ("languages", render_langs(totals, repo_count, stats["repos"], theme)),
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
