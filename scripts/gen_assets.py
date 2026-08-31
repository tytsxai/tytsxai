#!/usr/bin/env python3
"""Generate every visual on the profile as a self-hosted SVG.

Design direction — "modern engineering dashboard":
Clean, polished, high-contrast SVG panels that seamlessly integrate with GitHub's
Dark and Light themes. Committed SVGs ensure zero broken image states or rate limits.

Refreshed weekly by .github/workflows/charts.yml.
Reads public GitHub data only; writes only into assets/.
"""

from __future__ import annotations

import concurrent.futures
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
TAGLINE = "Agent Workflows, RAG & Resilient Full-Stack Systems in Production"
SIGNOFF = "RELIABILITY  ·  IDEMPOTENCY  ·  OBSERVABILITY  ·  SPEED"
EMAIL = "wwtvn1937@gmail.com"

WORK_REPOS = [
    ("IDM-Activation-Script-Chinese", "Windows utility toolkit with high adoption — GBK encoding, registry rollback & safety gates"),
    ("cleanplate", "Local-first AI video watermark removal — FastAPI + ComfyUI DiffuEraser, async job queue & fallback"),
    ("PromptPanel", "Native macOS AI prompt & snippet launcher — Swift, SwiftUI, global hotkey, local-first architecture"),
    ("bazi-master", "Full-stack divination & AI reading platform — React, Express, PostgreSQL, Prisma, LLM pipeline"),
    ("bilibili-cleaner", "Safe account bulk automation — QR auth, adaptive rate limits, review gates & Dockerized"),
    ("macfriends-cli", "Systems-level Rust + ObjC++ relationship inspector, ABI-pinned, privacy-first zero-network"),
]

ASSETS = Path(__file__).resolve().parent.parent / "assets"

MONO = "ui-monospace,SFMono-Regular,SF Mono,Menlo,Consolas,Liberation Mono,monospace"
SANS = "-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif"

MONO_RATIO = 0.605


def mw(size: float, text: str) -> float:
    return len(text) * size * MONO_RATIO


THEMES = {
    "light": {
        "surface": "#ffffff", "sunken": "#f6f8fa", "card_bg": "#f9fafb", "border": "#d0d7de", "rule": "#e1e4e8",
        "ink": "#1f2328", "muted": "#57606a", "faint": "#8c959f",
        "green": "#1a7f37", "amber": "#d97706", "blue": "#0969da", "purple": "#8250df", "cyan": "#0284c7",
        "heat": ["#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"],
        "chip_fill": 0.08, "chip_stroke": 0.35,
    },
    "dark": {
        "surface": "#0d1117", "sunken": "#161b22", "card_bg": "#1c2128", "border": "#30363d", "rule": "#21262d",
        "ink": "#e6edf3", "muted": "#8b949e", "faint": "#6e7681",
        "green": "#3fb950", "amber": "#f59e0b", "blue": "#58a6ff", "purple": "#bc8cff", "cyan": "#38bdf8",
        "heat": ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"],
        "chip_fill": 0.16, "chip_stroke": 0.45,
    },
}

W = 880
PAD = 28


# ---------------------------------------------------------------- data layer

def get_token() -> str | None:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        try:
            token = os.popen("gh auth token 2>/dev/null").read().strip()
        except Exception:
            token = None
    return token or None


def api(path: str, accept: str = "application/vnd.github+json"):
    url = path if path.startswith("http") else f"https://api.github.com{path}"
    req = urllib.request.Request(url)
    req.add_header("Accept", accept)
    req.add_header("User-Agent", f"{USER}-profile-assets")
    token = get_token()
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode()
        return (json.loads(body) if body else None), resp.status


def fetch_contributions_graphql() -> tuple[int, list[int]] | None:
    token = get_token()
    if not token:
        return None
    try:
        query = """query {
          user(login: "%s") {
            contributionsCollection {
              contributionCalendar {
                totalContributions
                weeks {
                  contributionDays {
                    contributionCount
                  }
                }
              }
            }
          }
        }""" % USER
        req = urllib.request.Request(
            "https://api.github.com/graphql",
            data=json.dumps({"query": query}).encode(),
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "User-Agent": f"{USER}-profile-assets",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            cal = data["data"]["user"]["contributionsCollection"]["contributionCalendar"]
            total = cal["totalContributions"]
            weekly = [sum(d["contributionCount"] for d in w["contributionDays"]) for w in cal["weeks"]]
            return total, weekly[-52:]
    except Exception as exc:
        print(f"  ! GraphQL contribution fetch fallback: {exc}", file=sys.stderr)
        return None


def work_rows() -> list[dict]:
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


def weekly_commits_fallback(repos: list[str]) -> list[int]:
    weeks = [0] * 52
    for repo in repos:
        try:
            data, status = api(f"/repos/{USER}/{repo}/stats/commit_activity")
            if status == 200 and data:
                for i, week in enumerate(data[-52:]):
                    weeks[i] += week.get("total", 0)
        except Exception:
            continue
    return weeks


# ------------------------------------------------------------- svg plumbing

def esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def head(height: int, c: dict) -> list[str]:
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{height}" '
        f'viewBox="0 0 {W} {height}" font-family="{MONO}" role="img">',
        "<style>",
        f".kicker{{font-size:10px;letter-spacing:1.8px;font-weight:700;fill:{c['faint']}}}",
        f".label{{font-size:10px;letter-spacing:1.5px;font-weight:600;fill:{c['faint']}}}",
        f".body{{font-size:11.5px;fill:{c['muted']}}}",
        f".data{{font-size:12px;fill:{c['ink']}}}",
        ".chip{font-size:11px;font-weight:500}",
        f".name{{font-family:{SANS};font-size:42px;font-weight:800;letter-spacing:-1.2px;fill:{c['ink']}}}",
        f".num{{font-family:{SANS};font-size:28px;font-weight:800;letter-spacing:-0.6px}}",
        f".role{{font-size:12px;letter-spacing:2.2px;font-weight:700;fill:{c['blue']}}}",
        f".repo{{font-size:14px;font-weight:700;fill:{c['blue']}}}",
        f".stars{{font-family:{SANS};font-size:14px;font-weight:700;fill:{c['amber']}}}",
        "</style>",
        f'<rect x="0.5" y="0.5" width="{W - 1}" height="{height - 1}" rx="14" '
        f'fill="{c["surface"]}" stroke="{c["border"]}"/>',
    ]


def kicker(y: float, left: str, right: str, c: dict) -> list[str]:
    return [
        f'<text x="{PAD}" y="{y}" class="kicker">{esc(left)}</text>',
        f'<text x="{W - PAD}" y="{y}" class="label" text-anchor="end">{esc(right)}</text>',
        f'<line x1="0" y1="{y + 17}" x2="{W}" y2="{y + 17}" stroke="{c["rule"]}"/>',
    ]


CHIP_H = 24
CHIP_TEXT = 11


def chip_width(text: str) -> float:
    return 22 + mw(CHIP_TEXT, text) + 12


def chip(x: float, y: float, text: str, color: str, c: dict) -> str:
    return (
        f'<g><rect x="{x:.1f}" y="{y:.1f}" width="{chip_width(text):.1f}" height="{CHIP_H}" rx="6" '
        f'fill="{color}" fill-opacity="{c["chip_fill"]}" '
        f'stroke="{color}" stroke-opacity="{c["chip_stroke"]}"/>'
        f'<circle cx="{x + 11:.1f}" cy="{y + CHIP_H / 2:.1f}" r="3.2" fill="{color}"/>'
        f'<text x="{x + 20:.1f}" y="{y + CHIP_H / 2 + 4:.1f}" class="chip" fill="{c["ink"]}">{esc(text)}</text></g>'
    )


# -------------------------------------------------------------------- hero

HERO_H = 340


def cadence_tiers(weeks: list[int]):
    active = sorted(c for c in weeks if c > 0)
    if not active:
        return lambda count: 0
    cuts = [active[int(len(active) * q)] for q in (0.25, 0.55, 0.85)]

    def tier(count: int) -> int:
        if count == 0:
            return 0
        return 1 + sum(count > cut for cut in cuts)

    return tier


def render_hero(theme: str, stats: dict, weeks: list[int], lang_count: int, total_contribs: int) -> str:
    c = THEMES[theme]
    out = head(HERO_H, c)

    # Top rail
    pill_w = 196
    out.append(
        f'<rect x="{PAD}" y="12" width="{pill_w}" height="22" rx="11" fill="{c["green"]}" fill-opacity="0.12" stroke="{c["green"]}" stroke-opacity="0.3"/>'
    )
    out.append(f'<circle cx="{PAD + 12}" cy="23" r="4" fill="{c["green"]}"/>')
    out.append(f'<text x="{PAD + 22}" y="26.5" class="kicker" fill="{c["green"]}">OPEN TO OPPORTUNITIES</text>')

    out.append(
        f'<text x="{W - PAD}" y="26.5" class="label" text-anchor="end">'
        f'{USER.upper()}  ·  GMT+8  ·  UPDATED {datetime.now(timezone.utc):%Y-%m-%d}</text>'
    )
    out.append(f'<line x1="0" y1="44" x2="{W}" y2="44" stroke="{c["rule"]}"/>')

    # Identity
    out.append(f'<text x="{PAD}" y="100" class="name">{esc(NAME)}</text>')
    out.append(f'<text x="{PAD}" y="126" class="role">{esc(ROLE)}</text>')
    out.append(f'<text x="{PAD}" y="150" class="body">{esc(TAGLINE)}</text>')

    # 4 Stat Tiles
    tiles = [
        (f"{stats['repos']}", "PUBLIC REPOSITORIES", c["blue"]),
        (f"{stats['stars']:,}+", "TOTAL STARS EARNED", c["amber"]),
        (f"{lang_count}", "LANGUAGES MASTERED", c["purple"]),
        (f"{total_contribs:,}", "YEARLY CONTRIBUTIONS", c["green"]),
    ]
    tw, gap = (W - 2 * PAD - 3 * 12) / 4, 12
    ty = 172
    for i, (num, cap, fill) in enumerate(tiles):
        tx = PAD + i * (tw + gap)
        out.append(
            f'<rect x="{tx:.1f}" y="{ty}" width="{tw:.1f}" height="68" rx="10" '
            f'fill="{c["sunken"]}" stroke="{c["border"]}"/>'
        )
        out.append(f'<text x="{tx + 16:.1f}" y="{ty + 36}" class="num" fill="{fill}">{esc(num)}</text>')
        out.append(f'<text x="{tx + 17:.1f}" y="{ty + 54}" class="label">{esc(cap)}</text>')

    # Cadence Strip
    strip_y = 272
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
            f'<rect x="{x:.2f}" y="{strip_y}" width="{bw:.2f}" height="22" rx="3" fill="{c["heat"][tier]}"/>'
        )

    out.append(
        f'<text x="{PAD}" y="{strip_y + 46}" class="data" fill="{c["muted"]}">'
        f'email  <tspan fill="{c["blue"]}">{esc(EMAIL)}</tspan></text>'
    )
    out.append(
        f'<text x="{W - PAD}" y="{strip_y + 46}" class="label" text-anchor="end">'
        f'REMOTE  ·  ONSITE  ·  FULL-STACK &amp; AI DELIVERY</text>'
    )

    out.append("</svg>")
    return chr(10).join(out)


# ------------------------------------------------------------------- stack

STACK = [
    ("LANGUAGES", "#3776AB", [
        ("Python", "#3776AB"), ("TypeScript", "#3178C6"), ("JavaScript", "#F0DB4F"),
        ("Rust", "#CE422B"), ("Swift", "#F05138"), ("Java", "#ED8B00"),
        ("Bash", "#4EAA25"), ("SQL", "#4479A1"), ("Objective-C++", "#6866FB"),
    ]),
    ("AI  /  LLM", "#8250df", [
        ("Claude", "#D97757"), ("OpenAI", "#10A37F"), ("MCP", "#7C3AED"),
        ("Tool Calling", "#8250df"), ("Multi-Agent", "#8250df"), ("RAG", "#8250df"),
        ("Structured Output", "#8250df"), ("ComfyUI", "#EA580C"), ("Evals & Guardrails", "#8250df"),
    ]),
    ("BACKEND", "#009688", [
        ("FastAPI", "#009688"), ("Node.js", "#5FA04E"), ("Express", None),
        ("PostgreSQL", "#4169E1"), ("Redis", "#FF4438"), ("Prisma", "#5A67D8"),
        ("SQLAlchemy", "#D71F00"), ("Celery", "#37814A"), ("BullMQ", "#EA4335"),
    ]),
    ("FRONTEND", "#61DAFB", [
        ("React", "#61DAFB"), ("Next.js", None), ("Vite", "#646CFF"),
        ("Tailwind CSS", "#06B6D4"), ("shadcn/ui", None), ("SwiftUI", "#F05138"),
    ]),
    ("DATA  /  SEARCH", "#FF5CAA", [
        ("Meilisearch", "#FF5CAA"), ("pgvector", "#4169E1"), ("Hybrid Recall", "#0969da"),
        ("Rerank Models", "#0969da"), ("Chinese Tokenization", "#0969da"), ("SimHash Dedup", "#0969da"),
    ]),
    ("INFRA  /  OPS", "#2496ED", [
        ("Docker", "#2496ED"), ("Linux", "#FCC624"), ("Nginx", "#009639"),
        ("GitHub Actions", "#2088FF"), ("Cloudflare", "#F38020"), ("GPU Serving", "#76B900"),
    ]),
    ("PRACTICE", "#1a7f37", [
        ("Idempotent Retries", "#1a7f37"), ("Async State Machines", "#1a7f37"),
        ("Dry-run Gates", "#1a7f37"), ("Adaptive Rate Limits", "#1a7f37"),
        ("Structured Logs", "#1a7f37"), ("Human-in-the-loop", "#1a7f37"),
    ]),
]

LANE_X = 152
CHIP_GAP = 7
CHIP_ROW = 31


def _lane_rows(items):
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
    out.extend(kicker(27, "TECHNICAL RADAR  ·  SKILLS & ECOSYSTEM", "PRODUCTION-GRADE TOOLKIT", c))

    y = 60
    for label, accent, rows in lanes:
        block = len(rows) * CHIP_ROW
        out.append(
            f'<rect x="{PAD}" y="{y + 4:.1f}" width="3" height="{max(block - 10, 8):.1f}" rx="1.5" fill="{accent}"/>'
        )
        out.append(f'<text x="{PAD + 14}" y="{y + 19:.1f}" class="label">{esc(label)}</text>')
        for r, row in enumerate(rows):
            x = float(LANE_X)
            for name, color, width in row:
                out.append(chip(x, y + r * CHIP_ROW + 2, name, color or c["ink"], c))
                x += width + CHIP_GAP
        y += block + 14

    out.append("</svg>")
    return chr(10).join(out)


# ------------------------------------------------------------ selected work

WORK_ROW_H = 46


def render_work(rows: list[dict], stats: dict, theme: str) -> str:
    if not rows:
        return ""
    c = THEMES[theme]
    rows = sorted(rows, key=lambda r: r["stars"], reverse=True)
    height = 60 + len(rows) * WORK_ROW_H + 10
    out = head(height, c)
    out.extend(kicker(27, "SELECTED OPEN SOURCE  ·  PUBLIC & RUNNING",
                      f'{stats["repos"]} REPOSITORIES  ·  {stats["stars"]:,}+ STARS', c))

    y = 58
    for row in rows:
        dot = LANG_COLORS.get(row["lang"], c["faint"])
        star_text = f'{row["stars"]:,}'
        tile_w = max(64.0, 36 + len(star_text) * 9)
        tile_x = W - PAD - tile_w
        lit = row["stars"] > 0
        tone = c["amber"] if lit else c["faint"]
        out.append(
            f'<rect x="{tile_x:.1f}" y="{y + 2:.1f}" width="{tile_w:.1f}" height="30" rx="7" '
            f'fill="{tone}" fill-opacity="{c["chip_fill"] if lit else 0.06}" '
            f'stroke="{tone}" stroke-opacity="{c["chip_stroke"] if lit else 0.25}"/>'
        )
        out.append(
            f'<text x="{tile_x + tile_w / 2:.1f}" y="{y + 22:.1f}" class="stars" '
            f'text-anchor="middle" fill="{tone}">★ {esc(star_text)}</text>'
        )

        out.append(f'<circle cx="{PAD + 4}" cy="{y + 13:.1f}" r="4.5" fill="{dot}"/>')
        out.append(f'<text x="{PAD + 18}" y="{y + 18:.1f}" class="repo">{esc(row["name"])}</text>')
        lang_x = PAD + 18 + mw(14, row["name"]) + 14
        out.append(f'<text x="{lang_x:.1f}" y="{y + 18:.1f}" class="label">{esc(row["lang"].upper())}</text>')
        out.append(f'<text x="{PAD + 18}" y="{y + 35:.1f}" class="body">{esc(row["blurb"])}</text>')
        y += WORK_ROW_H

    out.append("</svg>")
    return chr(10).join(out)


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

LANG_ROWS = 6
LANG_COLS = 2


def render_langs(totals: dict, repo_count: dict, repos: int, theme: str) -> str:
    c = THEMES[theme]
    total = sum(totals.values())
    if not total:
        return ""
    ranked = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
    shown = ranked[:LANG_ROWS * LANG_COLS]

    bar_y, bar_h = 62, 18
    row_y0 = bar_y + bar_h + 42
    tail = ranked[LANG_ROWS * LANG_COLS:]
    height = int(row_y0 + LANG_ROWS * 27 + (24 if tail else 8))

    out = head(height, c)
    out.extend(kicker(27, "LANGUAGE ECOSYSTEM  ·  ALL PUBLIC REPOSITORIES",
                      f"{len(totals)} LANGUAGES  ·  {repos} REPOSITORIES", c))

    bar_w = W - 2 * PAD
    out.append(
        f'<clipPath id="bclip"><rect x="{PAD}" y="{bar_y}" width="{bar_w}" height="{bar_h}" rx="6"/></clipPath>'
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
    out.append(f'<text x="{PAD}" y="{bar_y + bar_h + 20}" class="label">BAR  =  CODE VOLUME SHARE BY BYTES</text>')
    out.append(
        f'<text x="{W - PAD}" y="{bar_y + bar_h + 20}" class="label" text-anchor="end">'
        f'METERS  =  PROJECTS UTILIZED</text>'
    )

    gutter = 44.0
    col_w = (W - 2 * PAD - gutter) / LANG_COLS
    rule_x = PAD + col_w + gutter / 2
    out.append(
        f'<line x1="{rule_x:.1f}" y1="{row_y0 - 18:.1f}" x2="{rule_x:.1f}" '
        f'y2="{row_y0 + (LANG_ROWS - 1) * 27 + 6:.1f}" stroke="{c["border"]}"/>'
    )

    name_w, meter_w = 106.0, 100.0
    for i, (name, val) in enumerate(shown):
        col, row = i // LANG_ROWS, i % LANG_ROWS
        x = PAD + col * (col_w + gutter)
        y = row_y0 + row * 27
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

        out.append(
            f'<text x="{mx + meter_w + 46:.1f}" y="{y:.1f}" class="data" text-anchor="end" '
            f'fill="{c["muted"]}">{val / total * 100:.1f}%</text>'
        )
        out.append(
            f'<text x="{mx + meter_w + 58:.1f}" y="{y:.1f}" class="body">'
            f'{reach} {"repo" if reach == 1 else "repos"}</text>'
        )

    if tail:
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
    return chr(10).join(out)


# --------------------------------------------------------------------- main

def main() -> int:
    t0 = time.time()
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

    def fetch_lang(repo_item):
        if repo_item.get("archived"):
            return None
        try:
            langs, _ = api(f"/repos/{USER}/{repo_item['name']}/languages")
            return langs
        except Exception:
            return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        lang_results = pool.map(fetch_lang, owned)
        for langs in lang_results:
            if not langs:
                continue
            for name, size in langs.items():
                totals[name] = totals.get(name, 0) + size
                repo_count[name] = repo_count.get(name, 0) + 1

    print(f"  {len(totals)} languages")

    # Contributions & Cadence
    graphql_res = fetch_contributions_graphql()
    if graphql_res:
        total_contribs, weeks = graphql_res
    else:
        weeks = weekly_commits_fallback([r["name"] for r in owned])
        total_contribs = sum(weeks)

    print(f"  {total_contribs} contributions over 52 weeks")

    work = work_rows()
    for row in work:
        print(f"  {row['name']}: {row['lang']} · {row['stars']} stars")

    written = []
    for theme in THEMES:
        suffix = "" if theme == "light" else "-dark"
        for stem, svg in (
            ("hero", render_hero(theme, stats, weeks, len(totals), total_contribs)),
            ("stack", render_stack(theme)),
            ("work", render_work(work, stats, theme)),
            ("languages", render_langs(totals, repo_count, stats["repos"], theme)),
        ):
            if not svg:
                continue
            path = ASSETS / f"{stem}{suffix}.svg"
            path.write_text(svg + chr(10), encoding="utf-8")
            written.append(path)

    for path in written:
        print(f"  wrote {path.relative_to(ASSETS.parent)} ({path.stat().st_size:,} B)")

    print(f"Done in {time.time() - t0:.2f}s")
    return 0 if written else 1


if __name__ == "__main__":
    raise SystemExit(main())
