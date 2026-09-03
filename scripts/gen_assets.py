#!/usr/bin/env python3
"""Render every visual on the profile as self-hosted SVG cards.

  hero.svg          name, role, focus tags, contact + four live stat tiles
  stack.svg         tech stack grid with vendored brand icons (scripts/icons/)
  project-*.svg     one card per featured repository (live stars & language)
  activity.svg      52-week contribution cadence + language share

Each card has a light and a dark variant. Only the live cards read GitHub
data; they are refreshed weekly by .github/workflows/charts.yml so the
README never embeds a number that goes stale and never depends on a
third-party card service that can rate-limit into a broken image.
"""

from __future__ import annotations

import concurrent.futures
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

USER = "qilaidev"
NAME_CJK = "绮莱"
NAME_LATIN = "qilai"
EMAIL = "wwtvn1937@gmail.com"

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
ICONS = ROOT / "scripts" / "icons"

W = 880
PAD = 28
CARD_W = 430

SANS = (
    '-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB",'
    '"Microsoft YaHei","Noto Sans CJK SC","Noto Sans SC",Helvetica,Arial,sans-serif'
)
MONO = 'ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,"Liberation Mono",monospace'

THEMES = {
    "light": {
        "paper": "#ffffff", "box": "#f6f8fa", "border": "#d0d7de", "rule": "#e6eaef",
        "ink": "#1f2328", "muted": "#57606a", "faint": "#8c959f",
        "accent": "#0969da", "amber": "#bf6a02", "green": "#1a7f37", "purple": "#8250df",
        "bars": ["#e6eaef", "#9ec5f5", "#4f9cf0", "#0969da", "#0a4a9e"],
        "chip_fill": 0.07, "chip_stroke": 0.30,
    },
    "dark": {
        "paper": "#0d1117", "box": "#161b22", "border": "#30363d", "rule": "#21262d",
        "ink": "#e6edf3", "muted": "#8b949e", "faint": "#6e7681",
        "accent": "#58a6ff", "amber": "#e3b341", "green": "#3fb950", "purple": "#bc8cff",
        "bars": ["#1c2330", "#1f4b82", "#2f6fb5", "#58a6ff", "#9ccbff"],
        "chip_fill": 0.14, "chip_stroke": 0.40,
    },
}

LANG_COLORS = {
    "Python": "#3572A5", "TypeScript": "#3178c6", "JavaScript": "#f1e05a",
    "Rust": "#dea584", "Swift": "#F05138", "Shell": "#89e051", "Go": "#00ADD8",
    "Batchfile": "#C1F12E", "HTML": "#e34c26", "CSS": "#663399", "C": "#555555",
    "C++": "#f34b7d", "Java": "#b07219", "Objective-C++": "#6866fb",
    "PowerShell": "#012456", "Dockerfile": "#384d54", "Makefile": "#427819",
    "PLpgSQL": "#336790", "Vue": "#41b883", "Kotlin": "#A97BFF", "Ruby": "#701516",
}

# (label, icon slug or None, brand colour). Near-black brands flip to ink on dark.
STACK = [
    ("LANGUAGES", [
        ("TypeScript", "typescript", "#3178C6"), ("Python", "python", "#3776AB"),
        ("JavaScript", "javascript", "#C9B300"), ("Rust", "rust", "#CE422B"),
        ("Swift", "swift", "#F05138"), ("Bash", "gnubash", "#4EAA25"),
    ]),
    ("FRONTEND", [
        ("React", "react", "#149ECA"), ("Electron", "electron", "#47848F"),
        ("Vite", "vite", "#646CFF"), ("Tailwind CSS", "tailwindcss", "#06B6D4"),
        ("shadcn/ui", "shadcnui", "#000000"), ("SwiftUI", "swift", "#F05138"),
    ]),
    ("BACKEND", [
        ("FastAPI", "fastapi", "#009688"), ("Node.js", "nodedotjs", "#5FA04E"),
        ("Express", "express", "#000000"), ("Prisma", "prisma", "#2D3748"),
        ("SQLAlchemy", "sqlalchemy", "#D71F00"), ("Pydantic", "pydantic", "#E92063"),
    ]),
    ("DATA", [
        ("PostgreSQL", "postgresql", "#4169E1"), ("Redis", "redis", "#FF4438"),
        ("SQLite", "sqlite", "#003B57"), ("pgvector / 全文检索", None, "#4169E1"),
    ]),
    ("AI · LLM", [
        ("Anthropic API", "anthropic", "#191919"), ("Claude Code", "claude", "#D97757"),
        ("OpenAI API", "openai", "#000000"), ("MCP", "modelcontextprotocol", "#000000"),
        ("Tool Calling", None, "#8250df"), ("Structured Output", None, "#8250df"),
        ("RAG", None, "#8250df"), ("Multi-Agent", None, "#8250df"),
    ]),
    ("INFRA", [
        ("Docker", "docker", "#2496ED"), ("GitHub Actions", "githubactions", "#2088FF"),
        ("Linux", "linux", "#E5A000"), ("Nginx", "nginx", "#009639"),
        ("Cloudflare", "cloudflare", "#F38020"), ("Git", "git", "#F05032"),
    ]),
    ("AUTOMATION", [
        ("Telegram Bot API", "telegram", "#26A5E4"), ("Playwright", None, "#2EAD33"),
        ("Browser Extension", None, "#0969da"), ("pytest", "pytest", "#0A9EDC"),
        ("Vitest", "vitest", "#6E9F18"),
    ]),
]

FOCUS = ["AI FDE", "AI Agent", "Multi-Agent", "RAG", "LLM Apps", "Automation", "Full-Stack"]

# (repo, one-line blurb, tags)
PROJECTS = [
    ("bazi-master", "React + Express + Prisma + PostgreSQL + Redis 全栈应用，mock / OpenAI / Anthropic 三种 LLM 解读 Provider 可切换，五种界面语言。", ["Full-Stack", "LLM Pipeline", "i18n"]),
    ("cleanplate", "本地优先的 AI 视频去水印后端：FastAPI 接单，独立 worker 异步执行，AI 主链不可用时回退到 FFmpeg。", ["FastAPI", "Async Queue", "Fallback"]),
    ("metaphysics-engine", "无状态的术数计算引擎，以 HTTP API、CLI 与 MCP 三种方式接入，OpenAPI 契约由 CI 守快照。", ["MCP", "OpenAPI", "Agent Tool"]),
    ("mac-machina", "自托管的 AI macOS 自动化平台：自然语言触发本地 Bridge 上的数十个系统工具，Agent 层可跑在 Cloudflare Worker。", ["Tool Calling", "TypeScript", "Self-Hosted"]),
    ("quant-agent-cli", "面向 AI Agent 调用的合约交易命令面：JSON Schema 输入、结构化错误码、dry-run / testnet 门禁，实盘写路径默认封死。", ["Agent CLI", "Risk-First", "Pydantic"]),
    ("bilibili-cleaner", "自托管的账号批量清理工作台：列出、筛选、人工复核、选择性删除，Web UI / API / CLI 三种入口。", ["FastAPI", "Review Gate", "Rate Limit"]),
    ("PromptPanel", "macOS 原生的提示词与片段启动器，全局快捷键唤起，纯本地存储。", ["Swift", "SwiftUI", "Local-First"]),
    ("IDM-Activation-Script-Chinese", "面向大量真实用户的 Windows 脚本套件：GBK 编码适配、注册表备份与回退。", ["Batchfile", "Windows"]),
]


# ---------------------------------------------------------------- data layer

def get_token() -> str | None:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        token = os.popen("gh auth token 2>/dev/null").read().strip()
    return token or None


def api(path: str, body: dict | None = None):
    url = path if path.startswith("http") else f"https://api.github.com{path}"
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", f"{USER}-profile-assets")
    if data:
        req.add_header("Content-Type", "application/json")
    token = get_token()
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw else None


def fetch_contributions() -> tuple[int, list[int]] | None:
    if not get_token():
        return None
    query = """query { user(login: "%s") { contributionsCollection { contributionCalendar {
      totalContributions weeks { contributionDays { contributionCount } } } } } }""" % USER
    try:
        cal = api("https://api.github.com/graphql", {"query": query})["data"]["user"]["contributionsCollection"]["contributionCalendar"]
    except Exception as exc:  # noqa: BLE001
        print(f"  ! contributions via GraphQL failed: {exc}", file=sys.stderr)
        return None
    weekly = [sum(d["contributionCount"] for d in w["contributionDays"]) for w in cal["weeks"]]
    return cal["totalContributions"], weekly[-52:]


def collect() -> dict:
    repos = api(f"/users/{USER}/repos?per_page=100&type=owner") or []
    owned = [r for r in repos if not r.get("fork")]
    by_name = {r["name"]: r for r in owned}
    stars = sum(r.get("stargazers_count", 0) for r in owned)

    totals: dict[str, int] = {}

    def fetch_lang(repo):
        if repo.get("archived"):
            return None
        try:
            return api(f"/repos/{USER}/{repo['name']}/languages")
        except Exception:  # noqa: BLE001
            return None

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        for langs in pool.map(fetch_lang, owned):
            for name, size in (langs or {}).items():
                totals[name] = totals.get(name, 0) + size

    got = fetch_contributions()
    contribs, weeks = got if got else (0, [0] * 52)

    projects = []
    for name, blurb, tags in PROJECTS:
        r = by_name.get(name)
        if not r:
            print(f"  ! project {name} not found among owned repos", file=sys.stderr)
            continue
        projects.append({"name": name, "blurb": blurb, "tags": tags,
                         "lang": r.get("language") or "—", "stars": r.get("stargazers_count", 0)})

    print(f"  {len(owned)} repos · {stars} stars · {len(totals)} languages · {contribs} contributions/52w · {len(projects)} project cards")
    return {"repos": len(owned), "stars": stars, "langs": totals, "weeks": weeks, "contribs": contribs, "projects": projects}


# ------------------------------------------------------------- svg plumbing

def esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def tw(text: str, size: float, mono: bool = False) -> float:
    """Rough advance width: CJK = 1em, ASCII = 0.6em (mono) / 0.55em (sans)."""
    ratio = 0.6 if mono else 0.55
    return sum(size if ord(ch) > 0x2E7F else size * ratio for ch in text)


def wrap(text: str, size: float, width: float, max_lines: int) -> list[str]:
    """Wrap by tokens: each CJK glyph is a token, each ASCII word (with its trailing space) is one."""
    tokens = re.findall(r"[^\x00-\x2E7F]|[\x00-\x2E7F]+?(?=\s|[^\x00-\x2E7F]|$)\s*", text)
    lines: list[str] = []
    cur = ""
    for tok in tokens:
        if cur and tw(cur + tok.rstrip(), size) > width:
            lines.append(cur.rstrip())
            cur = tok.lstrip()
        else:
            cur += tok
    if cur.strip():
        lines.append(cur.rstrip())
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip()[:-1] + "…"
    return lines


def card_open(width: int, height: int, c: dict) -> list[str]:
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img">',
        "<style>",
        f"text{{font-family:{SANS}}}",
        f".mono{{font-family:{MONO}}}",
        f".kicker{{font-family:{MONO};font-size:10.5px;letter-spacing:2px;font-weight:700;fill:{c['accent']}}}",
        f".label{{font-family:{MONO};font-size:10px;letter-spacing:1.4px;font-weight:600;fill:{c['faint']}}}",
        f".body{{font-size:12px;fill:{c['muted']}}}",
        f".ink{{font-size:12px;fill:{c['ink']}}}",
        f".name{{font-size:52px;font-weight:700;letter-spacing:-1px;fill:{c['ink']}}}",
        f".handle{{font-family:{MONO};font-size:20px;font-weight:600;fill:{c['muted']}}}",
        f".role{{font-size:15px;font-weight:600;fill:{c['ink']}}}",
        f".num{{font-size:26px;font-weight:700;letter-spacing:-0.5px}}",
        f".repo{{font-family:{MONO};font-size:14px;font-weight:700;fill:{c['accent']}}}",
        f".chip{{font-family:{MONO};font-size:11px;font-weight:500;fill:{c['ink']}}}",
        f".tag{{font-family:{MONO};font-size:9.5px;font-weight:600}}",
        "</style>",
        f'<rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="12" fill="{c["paper"]}" stroke="{c["border"]}"/>',
    ]


_icon_cache: dict[str, str] = {}


def icon_path(slug: str) -> str | None:
    if slug in _icon_cache:
        return _icon_cache[slug]
    f = ICONS / f"{slug}.svg"
    if not f.exists():
        return None
    m = re.search(r'<path[^>]*\sd="([^"]+)"', f.read_text(encoding="utf-8"))
    _icon_cache[slug] = m.group(1) if m else None
    return _icon_cache[slug]


def is_dark_colour(hex_colour: str) -> bool:
    r, g, b = (int(hex_colour[i:i + 2], 16) for i in (1, 3, 5))
    return 0.299 * r + 0.587 * g + 0.114 * b < 70


def brand(colour: str, theme: str, c: dict) -> str:
    return c["ink"] if theme == "dark" and is_dark_colour(colour) else colour


CHIP_H = 30
CHIP_FS = 11


def chip_w(label: str, with_icon: bool) -> float:
    return (34 if with_icon else 24) + tw(label, CHIP_FS, mono=True) + 12


def chip(x: float, y: float, label: str, slug: str | None, colour: str, c: dict) -> str:
    d = icon_path(slug) if slug else None
    w = chip_w(label, d is not None)
    out = [
        f'<g><rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{CHIP_H}" rx="7" fill="{c["box"]}" stroke="{c["border"]}"/>'
    ]
    if d:
        out.append(f'<g transform="translate({x + 10:.1f},{y + 7:.1f}) scale(0.6667)"><path d="{d}" fill="{colour}"/></g>')
        tx = x + 34
    else:
        out.append(f'<circle cx="{x + 12:.1f}" cy="{y + CHIP_H / 2:.1f}" r="3.2" fill="{colour}"/>')
        tx = x + 24
    out.append(f'<text x="{tx:.1f}" y="{y + CHIP_H / 2 + 4:.1f}" class="chip">{esc(label)}</text></g>')
    return "".join(out)


def tag(x: float, y: float, label: str, colour: str, c: dict) -> tuple[str, float]:
    w = tw(label, 9.5, mono=True) + 14
    s = (
        f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="18" rx="5" fill="{colour}" fill-opacity="{c["chip_fill"]}" '
        f'stroke="{colour}" stroke-opacity="{c["chip_stroke"]}"/>'
        f'<text x="{x + 7:.1f}" y="{y + 12.5:.1f}" class="tag" fill="{colour}">{esc(label)}</text>'
    )
    return s, w


# ------------------------------------------------------------------ hero

HERO_H = 252


def render_hero(theme: str, d: dict) -> str:
    c = THEMES[theme]
    out = card_open(W, HERO_H, c)
    out.append(f'<rect x="0.5" y="0.5" width="{W - 1}" height="4" rx="2" fill="{c["accent"]}"/>')

    out.append(f'<text x="{PAD}" y="86" class="name">{esc(NAME_CJK)}</text>')
    out.append(f'<text x="{PAD + 120}" y="86" class="handle">{esc(NAME_LATIN)}</text>')
    out.append(f'<text x="{PAD}" y="118" class="role">软件工程师 · AI 应用工程化落地 · 全栈系统交付</text>')
    out.append(f'<text x="{PAD}" y="140" class="body">LLM 应用 · AI Agent · 多 Agent 系统 · 智能自动化 · 从需求到上线的全流程交付</text>')

    x, y = float(PAD), 158.0
    for f in FOCUS:
        s, w = tag(x, y, f, c["accent"], c)
        out.append(s)
        x += w + 6

    out.append(f'<text x="{PAD}" y="206" class="label">GMT+8</text>')
    out.append(f'<text x="{PAD + 56}" y="206" class="ink">远程全职 · 合同制 · 技术咨询</text>')
    out.append(f'<text x="{PAD}" y="228" class="label">EMAIL</text>')
    out.append(f'<text x="{PAD + 56}" y="228" class="ink mono" fill="{c["accent"]}">{esc(EMAIL)}</text>')

    tiles = [
        (f'{d["repos"]}', "PUBLIC REPOS", c["accent"]),
        (f'{d["stars"]:,}', "STARS", c["amber"]),
        (f'{d["contribs"]:,}', "CONTRIBUTIONS", c["green"]),
        (f'{len(d["langs"])}', "LANGUAGES", c["purple"]),
    ]
    tx0, ty0, tw_, th, g = 546, 44, 150, 78, 12
    for i, (num, cap, colour) in enumerate(tiles):
        tx = tx0 + (i % 2) * (tw_ + g)
        ty = ty0 + (i // 2) * (th + g)
        out.append(f'<rect x="{tx}" y="{ty}" width="{tw_}" height="{th}" rx="10" fill="{c["box"]}" stroke="{c["border"]}"/>')
        out.append(f'<rect x="{tx + 14}" y="{ty + 16}" width="3" height="18" rx="1.5" fill="{colour}"/>')
        out.append(f'<text x="{tx + 26}" y="{ty + 34}" class="num" fill="{colour}">{esc(num)}</text>')
        out.append(f'<text x="{tx + 26}" y="{ty + 58}" class="label">{esc(cap)}</text>')

    out.append("</svg>")
    return "\n".join(out)


# ----------------------------------------------------------------- stack

LANE_X = 150
CHIP_GAP = 8
ROW_H = 38


def _lane_rows(items):
    rows, row, x = [], [], float(LANE_X)
    for label, slug, colour in items:
        w = chip_w(label, slug is not None and icon_path(slug) is not None)
        if row and x + w > W - PAD:
            rows.append(row)
            row, x = [], float(LANE_X)
        row.append((label, slug, colour, w))
        x += w + CHIP_GAP
    if row:
        rows.append(row)
    return rows


def render_stack(theme: str) -> str:
    c = THEMES[theme]
    lanes = [(label, _lane_rows(items)) for label, items in STACK]
    height = 56 + sum(len(rows) * ROW_H + 12 for _, rows in lanes)
    out = card_open(W, height, c)
    out.append(f'<text x="{PAD}" y="34" class="kicker">TECH STACK</text>')
    out.append(f'<text x="{W - PAD}" y="34" class="label" text-anchor="end">主力 · 也在用 · 不追新，追稳</text>')
    out.append(f'<line x1="{PAD}" y1="44" x2="{W - PAD}" y2="44" stroke="{c["rule"]}"/>')

    y = 56
    for label, rows in lanes:
        out.append(f'<text x="{PAD}" y="{y + 19}" class="label">{esc(label)}</text>')
        for r, row in enumerate(rows):
            x = float(LANE_X)
            for name, slug, colour, w in row:
                out.append(chip(x, y + r * ROW_H + 2, name, slug, brand(colour, theme, c), c))
                x += w + CHIP_GAP
        y += len(rows) * ROW_H + 12

    out.append("</svg>")
    return "\n".join(out)


# --------------------------------------------------------------- project

PROJ_H = 136


def render_project(theme: str, p: dict) -> str:
    c = THEMES[theme]
    out = card_open(CARD_W, PROJ_H, c)
    inner = CARD_W - 2 * 18
    out.append(f'<text x="18" y="34" class="repo">{esc(p["name"])}</text>')

    star = f'★ {p["stars"]:,}'
    if p["stars"]:
        out.append(f'<text x="{CARD_W - 18}" y="34" class="chip" font-weight="700" text-anchor="end" fill="{c["amber"]}">{esc(star)}</text>')
    lang_x = CARD_W - 18 - (tw(star, 11, mono=True) + 16 if p["stars"] else 0)
    lang = p["lang"].upper()
    out.append(f'<text x="{lang_x:.1f}" y="34" class="label" text-anchor="end">{esc(lang)}</text>')
    lang_w = tw(lang, 10, mono=True) + 1.4 * len(lang)
    out.append(f'<circle cx="{lang_x - lang_w - 9:.1f}" cy="30" r="4" fill="{LANG_COLORS.get(p["lang"], c["faint"])}"/>')

    for i, line in enumerate(wrap(p["blurb"], 12, inner, 2)):
        out.append(f'<text x="18" y="{62 + i * 19}" class="body">{esc(line)}</text>')

    x = 18.0
    for t in p["tags"]:
        s, w = tag(x, PROJ_H - 34, t, c["accent"], c)
        out.append(s)
        x += w + 6
    out.append("</svg>")
    return "\n".join(out)


# -------------------------------------------------------------- activity

ACT_H = 214


def tier_of(weeks: list[int]):
    active = sorted(v for v in weeks if v > 0)
    if not active:
        return lambda v: 0
    cuts = [active[int(len(active) * q)] for q in (0.25, 0.5, 0.8)]
    return lambda v: 0 if v == 0 else 1 + sum(v > k for k in cuts)


def render_activity(theme: str, d: dict) -> str:
    c = THEMES[theme]
    out = card_open(W, ACT_H, c)
    out.append(f'<text x="{PAD}" y="34" class="kicker">ACTIVITY</text>')
    out.append(f'<text x="{W - PAD}" y="34" class="label" text-anchor="end">公开仓库 · 不含 fork · 每周自动刷新</text>')
    out.append(f'<line x1="{PAD}" y1="44" x2="{W - PAD}" y2="44" stroke="{c["rule"]}"/>')

    lx, lw = PAD, 500
    out.append(f'<text x="{lx}" y="70" class="label">CONTRIBUTIONS · LAST 52 WEEKS</text>')
    weeks = d["weeks"] or [0] * 52
    n = len(weeks)
    base, maxh = 156, 66
    peak = max(weeks) or 1
    gapb = 3
    bwid = (lw - gapb * (n - 1)) / n
    tier = tier_of(weeks)
    out.append(f'<line x1="{lx}" y1="{base + 0.5}" x2="{lx + lw}" y2="{base + 0.5}" stroke="{c["rule"]}"/>')
    for i, v in enumerate(weeks):
        h = max(2.0, v / peak * maxh) if v else 2.0
        x = lx + i * (bwid + gapb)
        out.append(f'<rect x="{x:.2f}" y="{base - h:.2f}" width="{bwid:.2f}" height="{h:.2f}" rx="1.5" fill="{c["bars"][tier(v)]}"/>')
    out.append(f'<text x="{lx}" y="{base + 16}" class="label" font-size="9px">52 WEEKS AGO</text>')
    out.append(f'<text x="{lx + lw}" y="{base + 16}" class="label" font-size="9px" text-anchor="end">NOW</text>')
    total = f'{d["contribs"]:,}'
    out.append(f'<text x="{lx}" y="{base + 42}" class="num" fill="{c["ink"]}">{total}</text>')
    out.append(f'<text x="{lx + tw(total, 26) + 12:.1f}" y="{base + 42}" class="label">CONTRIBUTIONS</text>')

    rx, rw = 576, W - PAD - 576
    langs = sorted(d["langs"].items(), key=lambda kv: kv[1], reverse=True)
    total_b = sum(v for _, v in langs) or 1
    shown = langs[:6]
    out.append(f'<text x="{rx}" y="70" class="label">LANGUAGES · BY BYTES</text>')
    out.append(f'<text x="{rx + rw}" y="70" class="label" text-anchor="end">TOP {len(shown)} OF {len(langs)}</text>')
    bar_x, bar_w = rx + 96, rw - 96 - 48
    y = 92
    for name, v in shown:
        pct = v / total_b * 100
        colour = LANG_COLORS.get(name, c["faint"])
        out.append(f'<circle cx="{rx + 4}" cy="{y - 4}" r="3.5" fill="{colour}"/>')
        out.append(f'<text x="{rx + 13}" y="{y}" class="chip">{esc(name[:12])}</text>')
        out.append(f'<rect x="{bar_x}" y="{y - 10}" width="{bar_w}" height="8" rx="4" fill="{c["box"]}" stroke="{c["border"]}" stroke-opacity="0.7"/>')
        out.append(f'<rect x="{bar_x}" y="{y - 10}" width="{max(3.0, pct / 100 * bar_w):.1f}" height="8" rx="4" fill="{colour}"/>')
        out.append(f'<text x="{rx + rw}" y="{y}" class="body" font-size="11px" text-anchor="end">{pct:.1f}%</text>')
        y += 18
    out.append("</svg>")
    return "\n".join(out)


# ------------------------------------------------------------------ main

def main() -> int:
    t0 = time.time()
    ASSETS.mkdir(parents=True, exist_ok=True)
    for old in ASSETS.glob("*.svg"):
        old.unlink()
    data = collect()

    written = []
    for theme in THEMES:
        suffix = "" if theme == "light" else "-dark"
        outputs = [("hero", render_hero(theme, data)), ("stack", render_stack(theme)), ("activity", render_activity(theme, data))]
        outputs += [(f"project-{p['name'].lower()}", render_project(theme, p)) for p in data["projects"]]
        for stem, svg in outputs:
            path = ASSETS / f"{stem}{suffix}.svg"
            path.write_text(svg + "\n", encoding="utf-8")
            written.append(path)
    for p in written:
        print(f"  wrote {p.relative_to(ROOT)} ({p.stat().st_size:,} B)")
    print(f"Done in {time.time() - t0:.2f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
