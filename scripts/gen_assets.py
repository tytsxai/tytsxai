#!/usr/bin/env python3
"""Render the profile's visuals as self-hosted SVG "engineering sheets".

Three sheets, each in a light and a dark variant (six files under assets/):

  01 identity.svg   who / what / how to reach — plus a schematic of the
                    production shape most of my systems end up in
  02 process.svg    the six-stage delivery loop I own end to end
  03 activity.svg   live data: 52-week contribution cadence, language share,
                    repository and star totals (the only place numbers live)

Sheets 01 and 02 are static; sheet 03 reads public GitHub data. Refreshed
weekly by .github/workflows/charts.yml so the README never embeds a number
that goes stale, and never depends on a third-party card service that can
rate-limit into a broken image.
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
NAME_CJK = "绮莱"
NAME_LATIN = "qilai"
EMAIL = "wwtvn1937@gmail.com"

ASSETS = Path(__file__).resolve().parent.parent / "assets"
SHEETS = 3

W = 880
PAD = 32

SANS = (
    '-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB",'
    '"Microsoft YaHei","Noto Sans CJK SC","Noto Sans SC",Helvetica,Arial,sans-serif'
)
MONO = 'ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,"Liberation Mono",monospace'

THEMES = {
    "light": {
        "paper": "#ffffff", "grid": "#edf1f5", "border": "#d0d7de", "rule": "#e6eaef",
        "ink": "#1f2328", "muted": "#57606a", "faint": "#8c959f",
        "accent": "#0969da", "amber": "#bf6a02", "green": "#1a7f37", "box": "#f6f8fa",
        "bars": ["#e6eaef", "#9ec5f5", "#4f9cf0", "#0969da", "#0a4a9e"],
    },
    "dark": {
        "paper": "#0d1117", "grid": "#161d27", "border": "#30363d", "rule": "#21262d",
        "ink": "#e6edf3", "muted": "#8b949e", "faint": "#6e7681",
        "accent": "#58a6ff", "amber": "#e3b341", "green": "#3fb950", "box": "#161b22",
        "bars": ["#1c2330", "#1f4b82", "#2f6fb5", "#58a6ff", "#9ccbff"],
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


# ---------------------------------------------------------------- data layer

def get_token() -> str | None:
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        token = os.popen("gh auth token 2>/dev/null").read().strip()
    return token or None


def api(path: str):
    url = path if path.startswith("http") else f"https://api.github.com{path}"
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", f"{USER}-profile-assets")
    token = get_token()
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode()
        return json.loads(body) if body else None


def fetch_contributions() -> tuple[int, list[int]] | None:
    token = get_token()
    if not token:
        return None
    query = """query {
      user(login: "%s") {
        contributionsCollection {
          contributionCalendar {
            totalContributions
            weeks { contributionDays { contributionCount } }
          }
        }
      }
    }""" % USER
    try:
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
            cal = json.loads(resp.read().decode())["data"]["user"]["contributionsCollection"]["contributionCalendar"]
        weekly = [sum(d["contributionCount"] for d in w["contributionDays"]) for w in cal["weeks"]]
        return cal["totalContributions"], weekly[-52:]
    except Exception as exc:  # noqa: BLE001
        print(f"  ! contributions via GraphQL failed, falling back: {exc}", file=sys.stderr)
        return None


def weekly_commits_fallback(repos: list[str]) -> list[int]:
    weeks = [0] * 52
    for repo in repos:
        try:
            data = api(f"/repos/{USER}/{repo}/stats/commit_activity")
        except Exception:  # noqa: BLE001
            continue
        for i, week in enumerate((data or [])[-52:]):
            weeks[i] += week.get("total", 0)
    return weeks


def collect() -> dict:
    repos = api(f"/users/{USER}/repos?per_page=100&type=owner") or []
    owned = [r for r in repos if not r.get("fork")]
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
    if got:
        total_contribs, weeks = got
    else:
        weeks = weekly_commits_fallback([r["name"] for r in owned])
        total_contribs = sum(weeks)

    print(f"  {len(owned)} repos · {stars} stars · {len(totals)} languages · {total_contribs} contributions/52w")
    return {"repos": len(owned), "stars": stars, "langs": totals, "weeks": weeks, "contribs": total_contribs}


# ------------------------------------------------------------- svg plumbing

def esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def sheet_open(height: int, c: dict, uid: str) -> list[str]:
    """Paper, faint drafting grid, corner marks, shared styles."""
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{height}" viewBox="0 0 {W} {height}" role="img">',
        "<style>",
        f"text{{font-family:{MONO}}}",
        f".cjk{{font-family:{SANS}}}",
        f".kicker{{font-size:10.5px;letter-spacing:2px;font-weight:700;fill:{c['accent']}}}",
        f".label{{font-size:10px;letter-spacing:1.4px;font-weight:600;fill:{c['faint']}}}",
        f".mono{{font-size:12px;fill:{c['ink']}}}",
        f".muted{{font-size:11.5px;fill:{c['muted']}}}",
        f".small{{font-size:10px;fill:{c['muted']}}}",
        f".name{{font-size:58px;font-weight:700;letter-spacing:-1px;fill:{c['ink']}}}",
        f".handle{{font-size:22px;font-weight:600;fill:{c['muted']}}}",
        f".role{{font-size:15px;font-weight:600;fill:{c['ink']}}}",
        f".stage{{font-size:13px;font-weight:700;fill:{c['ink']}}}",
        f".bullet{{font-size:10.5px;fill:{c['muted']}}}",
        f".big{{font-size:26px;font-weight:700;letter-spacing:-0.5px;fill:{c['ink']}}}",
        "</style>",
        "<defs>",
        f'<pattern id="grid-{uid}" width="24" height="24" patternUnits="userSpaceOnUse">'
        f'<path d="M24 0H0V24" fill="none" stroke="{c["grid"]}" stroke-width="0.8"/></pattern>',
        f'<clipPath id="clip-{uid}"><rect x="0.5" y="0.5" width="{W - 1}" height="{height - 1}" rx="10"/></clipPath>',
        f'<marker id="arr-{uid}" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto">'
        f'<path d="M0 0L8 4L0 8z" fill="{c["accent"]}"/></marker>',
        f'<marker id="arl-{uid}" viewBox="0 0 8 8" refX="1" refY="4" markerWidth="7" markerHeight="7" orient="auto">'
        f'<path d="M8 0L0 4L8 8z" fill="{c["accent"]}"/></marker>',
        "</defs>",
        f'<rect x="0.5" y="0.5" width="{W - 1}" height="{height - 1}" rx="10" fill="{c["paper"]}" stroke="{c["border"]}"/>',
        f'<rect x="0.5" y="0.5" width="{W - 1}" height="{height - 1}" rx="10" fill="url(#grid-{uid})" clip-path="url(#clip-{uid})"/>',
        # corner registration marks
        *[
            f'<path d="{d}" fill="none" stroke="{c["faint"]}" stroke-width="1"/>'
            for d in (
                f"M{PAD - 12} {PAD - 2}v-10h10",
                f"M{W - PAD + 12} {PAD - 2}v-10h-10",
                f"M{PAD - 12} {height - PAD + 2}v10h10",
                f"M{W - PAD + 12} {height - PAD + 2}v10h-10",
            )
        ],
    ]


def title_block(height: int, c: dict, sheet: int, footer_left: str) -> list[str]:
    """Bottom-right title block like an engineering drawing, plus a left footer."""
    y = height - 38
    cells = [("SHEET", f"{sheet:02d} / {SHEETS:02d}", 90), ("REV", f"{datetime.now(timezone.utc):%Y-%m-%d}", 118), ("ID", f"github.com/{USER}", 168)]
    total = sum(w for _, _, w in cells)
    x = W - PAD - total
    out = [f'<rect x="{x}" y="{y}" width="{total}" height="26" rx="4" fill="{c["box"]}" stroke="{c["border"]}"/>']
    for i, (k, v, w) in enumerate(cells):
        if i:
            out.append(f'<line x1="{x}" y1="{y}" x2="{x}" y2="{y + 26}" stroke="{c["border"]}"/>')
        out.append(f'<text x="{x + 9}" y="{y + 11}" class="label" font-size="8.5px">{esc(k)}</text>')
        out.append(f'<text x="{x + 9}" y="{y + 22}" class="mono" font-size="10.5px">{esc(v)}</text>')
        x += w
    out.append(f'<text x="{PAD}" y="{y + 18}" class="muted cjk">{esc(footer_left)}</text>')
    return out


def kicker(y: int, text: str, c: dict) -> list[str]:
    return [
        f'<text x="{PAD}" y="{y}" class="kicker">{esc(text)}</text>',
        f'<line x1="{PAD}" y1="{y + 9}" x2="{W - PAD}" y2="{y + 9}" stroke="{c["rule"]}"/>',
    ]


def box(x: float, y: float, w: float, h: float, label: str, c: dict, cls: str = "mono", fs: str = "10.5px") -> str:
    return (
        f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="5" fill="{c["box"]}" stroke="{c["border"]}"/>'
        f'<text x="{x + w / 2:.1f}" y="{y + h / 2 + 4:.1f}" class="{cls}" font-size="{fs}" text-anchor="middle">{esc(label)}</text>'
    )


def arrow(x1: float, y1: float, x2: float, y2: float, c: dict, uid: str, dashed: bool = False) -> str:
    dash = ' stroke-dasharray="3 3"' if dashed else ""
    return (
        f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{c["accent"]}" '
        f'stroke-width="1.2"{dash} marker-end="url(#arr-{uid})"/>'
    )


# ------------------------------------------------------- sheet 01: identity

ID_H = 312


def render_identity(theme: str) -> str:
    c = THEMES[theme]
    uid = f"id-{theme}"
    out = sheet_open(ID_H, c, uid)
    out += kicker(40, "01 · IDENTITY", c)

    # Name block
    out.append(f'<text x="{PAD}" y="118" class="name cjk">{esc(NAME_CJK)}</text>')
    out.append(f'<text x="{PAD + 132}" y="118" class="handle">{esc(NAME_LATIN)}</text>')
    out.append(f'<text x="{PAD}" y="152" class="role cjk">软件工程师 · AI 应用工程化落地 · 全栈系统交付</text>')
    out.append(f'<text x="{PAD}" y="174" class="label" fill="{c["accent"]}">AI APPLICATION ENGINEERING  ·  FULL-STACK DELIVERY  ·  FDE</text>')

    rows = [
        ("TIMEZONE", "GMT+8 · 覆盖亚太时段，可配合欧美团队部分重叠时间"),
        ("OPEN TO", "远程全职 · 合同制 · 技术咨询"),
        ("LANGUAGE", "中文（母语） · 英文（工作语言）"),
        ("CONTACT", EMAIL),
    ]
    y = 208
    for k, v in rows:
        out.append(f'<text x="{PAD}" y="{y}" class="label">{esc(k)}</text>')
        cls = "mono" if k == "CONTACT" else "mono cjk"
        fill = f' fill="{c["accent"]}"' if k == "CONTACT" else ""
        out.append(f'<text x="{PAD + 96}" y="{y}" class="{cls}"{fill}>{esc(v)}</text>')
        y += 20

    # Schematic: the production shape
    sx = 500
    out.append(f'<text x="{sx}" y="66" class="label">SCHEMATIC · 生产形态</text>')
    bw, bh, gap = 56, 28, 16
    by = 96
    names = ["request", "api", "queue", "worker", "llm+tools"]
    xs = [sx + i * (bw + gap) for i in range(len(names))]
    for x, n in zip(xs, names):
        out.append(box(x, by, bw, bh, n, c))
    for i in range(len(names) - 2):
        out.append(arrow(xs[i] + bw, by + bh / 2, xs[i + 1] - 1, by + bh / 2, c, uid))
    # worker <-> llm+tools is a two-way exchange
    out.append(
        f'<line x1="{xs[3] + bw + 1}" y1="{by + bh / 2}" x2="{xs[4] - 1}" y2="{by + bh / 2}" stroke="{c["accent"]}" '
        f'stroke-width="1.2" marker-start="url(#arl-{uid})" marker-end="url(#arr-{uid})"/>'
    )
    # retry loop above: worker -> queue
    qx, wx = xs[2] + bw / 2, xs[3] + bw / 2
    out.append(
        f'<path d="M{wx} {by}v-12H{qx}v11" fill="none" stroke="{c["accent"]}" stroke-width="1.2" '
        f'stroke-dasharray="3 3" marker-end="url(#arr-{uid})"/>'
    )
    out.append(f'<text x="{(qx + wx) / 2:.1f}" y="78" class="small" text-anchor="middle">retry · idempotent</text>')
    # state store below worker/queue
    stx, stw = xs[2], (xs[3] + bw) - xs[2]
    out.append(box(stx, by + 60, stw, 26, "state · postgres / redis", c))
    out.append(arrow(wx, by + bh, wx, by + 59, c, uid))
    out.append(arrow(qx, by + bh, qx, by + 59, c, uid, dashed=True))
    # observability rail
    out.append(f'<line x1="{sx}" y1="{by + 104}" x2="{xs[4] + bw}" y2="{by + 104}" stroke="{c["green"]}" stroke-width="1.2" stroke-dasharray="2 4"/>')
    out.append(f'<text x="{sx}" y="{by + 118}" class="small">structured logs · metrics · alerts · human takeover</text>')

    out += title_block(ID_H, c, 1, "不追新，追稳 · 让 AI 在生产环境中存活")
    out.append("</svg>")
    return "\n".join(out)


# -------------------------------------------------------- sheet 02: process

STAGES = [
    ("需求分析", ["边界与验收标准", "数据与合规约束", "风险与可行性"]),
    ("架构设计", ["状态模型与状态机", "幂等与重试策略", "降级与兜底路径"]),
    ("开发实现", ["TypeScript · Python", "API 契约与测试", "结构化日志"]),
    ("AI 能力集成", ["工具调用 · 结构化输出", "RAG · 上下文管理", "多 Agent 编排"]),
    ("部署上线", ["Docker · CI/CD", "可观测与告警", "灰度与回滚"]),
    ("持续迭代", ["线上排障", "评估与提示词迭代", "成本与效果复盘"]),
]

PR_H = 246


def render_process(theme: str) -> str:
    c = THEMES[theme]
    uid = f"pr-{theme}"
    out = sheet_open(PR_H, c, uid)
    out += kicker(40, "02 · DELIVERY PROCESS · 全流程交付", c)

    n = len(STAGES)
    gap = 14
    bw = (W - 2 * PAD - gap * (n - 1)) / n
    by, bh = 64, 44
    for i, (title, bullets) in enumerate(STAGES):
        x = PAD + i * (bw + gap)
        out.append(f'<rect x="{x:.1f}" y="{by}" width="{bw:.1f}" height="{bh}" rx="6" fill="{c["box"]}" stroke="{c["border"]}"/>')
        out.append(f'<rect x="{x:.1f}" y="{by}" width="3" height="{bh}" rx="1.5" fill="{c["accent"]}"/>')
        out.append(f'<text x="{x + 12:.1f}" y="{by + 17}" class="label">S{i + 1}</text>')
        out.append(f'<text x="{x + 12:.1f}" y="{by + 35}" class="stage cjk">{esc(title)}</text>')
        for j, b in enumerate(bullets):
            out.append(f'<text x="{x + 12:.1f}" y="{by + bh + 22 + j * 18}" class="bullet cjk">{esc(b)}</text>')
        if i < n - 1:
            cx = x + bw + gap / 2
            out.append(f'<path d="M{cx - 3:.1f} {by + bh / 2 - 5}l5 5l-5 5" fill="none" stroke="{c["accent"]}" stroke-width="1.4"/>')

    # feedback loop: S6 back to S1
    ly = by + bh + 22 + 3 * 18 + 2
    x0, x1 = PAD + bw / 2, PAD + (n - 1) * (bw + gap) + bw / 2
    out.append(
        f'<path d="M{x1:.1f} {ly - 10}v10H{x0:.1f}v-9" fill="none" stroke="{c["accent"]}" stroke-width="1.2" '
        f'stroke-dasharray="3 3" marker-end="url(#arr-{uid})"/>'
    )
    out.append(f'<text x="{(x0 + x1) / 2:.1f}" y="{ly + 14}" class="small cjk" text-anchor="middle">线上反馈回到需求与架构 · 迭代闭环</text>')

    out += title_block(PR_H, c, 2, "从需求分析到持续迭代，独立完成全流程交付")
    out.append("</svg>")
    return "\n".join(out)


# ------------------------------------------------------- sheet 03: activity

AC_H = 250


def tier_of(weeks: list[int]):
    active = sorted(v for v in weeks if v > 0)
    if not active:
        return lambda v: 0
    cuts = [active[int(len(active) * q)] for q in (0.25, 0.5, 0.8)]
    return lambda v: 0 if v == 0 else 1 + sum(v > k for k in cuts)


def render_activity(theme: str, d: dict) -> str:
    c = THEMES[theme]
    uid = f"ac-{theme}"
    out = sheet_open(AC_H, c, uid)
    out += kicker(40, "03 · ACTIVITY · 每周自动刷新", c)

    # --- left: 52-week contribution bars
    lx, lw = PAD, 500
    out.append(f'<text x="{lx}" y="70" class="label">CONTRIBUTIONS · LAST 52 WEEKS</text>')
    out.append(f'<text x="{lx + lw}" y="70" class="label" text-anchor="end">WEEKLY</text>')
    weeks = d["weeks"] or [0] * 52
    n = len(weeks)
    top, base, maxh = 84, 150, 64
    peak = max(weeks) or 1
    gapb = 3
    bwid = (lw - gapb * (n - 1)) / n
    tier = tier_of(weeks)
    out.append(f'<line x1="{lx}" y1="{base + 0.5}" x2="{lx + lw}" y2="{base + 0.5}" stroke="{c["rule"]}"/>')
    for i, v in enumerate(weeks):
        h = max(2.0, v / peak * maxh) if v else 2.0
        x = lx + i * (bwid + gapb)
        out.append(f'<rect x="{x:.2f}" y="{base - h:.2f}" width="{bwid:.2f}" height="{h:.2f}" rx="1.5" fill="{c["bars"][tier(v)]}"/>')
    out.append(f'<text x="{lx}" y="{base + 16}" class="small">52 WEEKS AGO</text>')
    out.append(f'<text x="{lx + lw}" y="{base + 16}" class="small" text-anchor="end">NOW</text>')
    out.append(f'<text x="{lx}" y="{base + 46}" class="big">{d["contribs"]:,}</text>')
    out.append(f'<text x="{lx + 12 + len(f"{d["contribs"]:,}") * 16}" y="{base + 46}" class="label">CONTRIBUTIONS · 52 WEEKS</text>')

    # --- right: language share
    rx, rw = 580, W - PAD - 580
    out.append(f'<text x="{rx}" y="70" class="label">LANGUAGES · BY BYTES</text>')
    langs = sorted(d["langs"].items(), key=lambda kv: kv[1], reverse=True)
    total = sum(v for _, v in langs) or 1
    shown = langs[:6]
    out.append(f'<text x="{rx + rw}" y="70" class="label" text-anchor="end">TOP {len(shown)} OF {len(langs)}</text>')
    bar_x, bar_w = rx + 92, rw - 92 - 46
    y = 90
    for name, v in shown:
        pct = v / total * 100
        color = LANG_COLORS.get(name, c["faint"])
        out.append(f'<circle cx="{rx + 4}" cy="{y - 4}" r="3.5" fill="{color}"/>')
        out.append(f'<text x="{rx + 13}" y="{y}" class="mono" font-size="11px">{esc(name[:12])}</text>')
        out.append(f'<rect x="{bar_x}" y="{y - 10}" width="{bar_w}" height="8" rx="4" fill="{c["box"]}" stroke="{c["border"]}" stroke-opacity="0.7"/>')
        out.append(f'<rect x="{bar_x}" y="{y - 10}" width="{max(3.0, pct / 100 * bar_w):.1f}" height="8" rx="4" fill="{color}"/>')
        out.append(f'<text x="{rx + rw}" y="{y}" class="muted" font-size="11px" text-anchor="end">{pct:.1f}%</text>')
        y += 17

    stats = f'REPOS {d["repos"]}   ·   STARS {d["stars"]:,}   ·   LANGUAGES {len(langs)}'
    out.append(f'<text x="{rx + rw}" y="{base + 46}" class="label" text-anchor="end">{esc(stats)}</text>')

    out += title_block(AC_H, c, 3, "数据来自公开仓库 · 不含私有与 fork")
    out.append("</svg>")
    return "\n".join(out)


# --------------------------------------------------------------------- main

def main() -> int:
    t0 = time.time()
    ASSETS.mkdir(parents=True, exist_ok=True)
    data = collect()

    written = []
    for theme in THEMES:
        suffix = "" if theme == "light" else "-dark"
        for stem, svg in (
            ("identity", render_identity(theme)),
            ("process", render_process(theme)),
            ("activity", render_activity(theme, data)),
        ):
            path = ASSETS / f"{stem}{suffix}.svg"
            path.write_text(svg + "\n", encoding="utf-8")
            written.append(path)
    for p in written:
        print(f"  wrote {p.relative_to(ASSETS.parent)} ({p.stat().st_size:,} B)")
    print(f"Done in {time.time() - t0:.2f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
