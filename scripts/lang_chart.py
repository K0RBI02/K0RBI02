#!/usr/bin/env python3
"""Generate a pastel donut chart of the languages used in a GitHub user's repos.

Writes two SVGs (light + dark) for use with <picture> in a profile README.
Standard library only.

Env vars:
  GH_USER        GitHub username (default: K0RBI02)
  GITHUB_TOKEN   token for the API (optional, but avoids the 60 req/h limit)
  TOP_N          number of languages shown before grouping into "Other" (default: 5)
  EXCLUDE_LANGS  comma-separated languages to ignore, e.g. "Jupyter Notebook,Dockerfile"
  EXCLUDE_REPOS  comma-separated repo names to ignore
  OUT_DIR        output folder (default: assets)
  DEMO           set to 1 to render with sample data instead of calling the API
"""

import json
import math
import os
import urllib.request
from pathlib import Path

USER = os.getenv("GH_USER", "K0RBI02")
# LANG_TOKEN (personal token) also sees private repos; GITHUB_TOKEN only public ones.
PRIVATE_TOKEN = os.getenv("LANG_TOKEN", "")
TOKEN = PRIVATE_TOKEN or os.getenv("GITHUB_TOKEN", "")
TOP_N = int(os.getenv("TOP_N", "5"))
EXCLUDE_LANGS = {s.strip().lower() for s in os.getenv("EXCLUDE_LANGS", "").split(",") if s.strip()}
EXCLUDE_REPOS = {s.strip().lower() for s in os.getenv("EXCLUDE_REPOS", "").split(",") if s.strip()}
OUT_DIR = Path(os.getenv("OUT_DIR", "assets"))

# Pastel palette: known languages get a fixed colour, the rest cycle through FALLBACK.
PASTEL = {
    "HTML": "#FFB4A2",
    "CSS": "#A8C8FF",
    "JavaScript": "#FFE59E",
    "Python": "#B4E8C8",
    "TypeScript": "#C9C2F2",
    "Rust": "#F6C49B",
    "Shell": "#E6C6EE",
    "Dockerfile": "#A9E2EC",
    "Go": "#A3E0DA",
    "Java": "#F2C7B8",
}
FALLBACK = ["#F9C6D3", "#CDE8A6", "#B9D7F0", "#F3D7A6", "#D6C9F0"]
OTHER_COLOR = "#D5D8DD"

THEMES = {
    "light": {"text": "#3D444D", "muted": "#6E7781"},
    "dark": {"text": "#D1D7E0", "muted": "#9198A1"},
}


def api(url):
    req = urllib.request.Request(url, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "readme-lang-chart",
        **({"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}),
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def collect():
    totals = {}
    page = 1
    while True:
        if PRIVATE_TOKEN:
            url = f"https://api.github.com/user/repos?per_page=100&affiliation=owner&visibility=all&page={page}"
        else:
            url = f"https://api.github.com/users/{USER}/repos?per_page=100&type=owner&page={page}"
        repos = api(url)
        if not repos:
            break
        for repo in repos:
            if (repo["fork"] or repo["owner"]["login"].lower() != USER.lower()
                    or repo["name"].lower() in EXCLUDE_REPOS):
                continue
            for lang, size in api(repo["languages_url"]).items():
                if lang.lower() in EXCLUDE_LANGS:
                    continue
                totals[lang] = totals.get(lang, 0) + size
        page += 1
    return totals


def shares(totals):
    total = sum(totals.values()) or 1
    items = sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
    top, rest = items[:TOP_N], items[TOP_N:]
    result = [(lang, size / total) for lang, size in top]
    other = sum(size for _, size in rest) / total
    if other >= 0.005:
        result.append(("Other", other))
    return result


def colour_for(lang, i):
    if lang == "Other":
        return OTHER_COLOR
    return PASTEL.get(lang, FALLBACK[i % len(FALLBACK)])


def arc_path(cx, cy, r_out, r_in, a0, a1):
    """Donut segment from angle a0 to a1 (radians, 0 = top, clockwise)."""
    def pt(r, a):
        return cx + r * math.sin(a), cy - r * math.cos(a)
    large = 1 if a1 - a0 > math.pi else 0
    x0, y0 = pt(r_out, a0)
    x1, y1 = pt(r_out, a1)
    x2, y2 = pt(r_in, a1)
    x3, y3 = pt(r_in, a0)
    return (f"M{x0:.2f},{y0:.2f} A{r_out},{r_out} 0 {large} 1 {x1:.2f},{y1:.2f} "
            f"L{x2:.2f},{y2:.2f} A{r_in},{r_in} 0 {large} 0 {x3:.2f},{y3:.2f} Z")


def render(data, theme):
    t = THEMES[theme]
    W = 350
    font = "-apple-system,BlinkMacSystemFont,'Segoe UI','Noto Sans',Helvetica,Arial,sans-serif"

    # Legend: fixed 3-column grid, so rows line up regardless of label length.
    cols = 3
    labels = [f"{lang} {share * 100:.0f}%" for lang, share in data]
    # Column width = widest label in that column (rough text estimate) + dot + gap.
    col_w = [max((18 + len(l) * 7.6 for l in labels[c::cols]), default=0) + 18 for c in range(cols)]
    col_x = [(W - sum(col_w) + 18) / 2 + sum(col_w[:c]) for c in range(cols)]
    legend = []
    y = 22
    for i, (lang, share) in enumerate(data):
        c = i % cols
        if i and c == 0:
            y += 26
        x = col_x[c]
        legend.append(
            f'<circle cx="{x + 6:.1f}" cy="{y - 4.5}" r="6" fill="{colour_for(lang, i)}"/>'
            f'<text x="{x + 18:.1f}" y="{y}" fill="{t["text"]}">{lang} '
            f'<tspan fill="{t["muted"]}">{share * 100:.0f}%</tspan></text>'
        )
    y += 26

    # Donut
    cx, cy, r_out, r_in = W / 2, y + 125, 120, 66
    gap = 0.012  # radians between segments
    segs, a = [], 0.0
    for i, (lang, share) in enumerate(data):
        span = share * 2 * math.pi
        if len(data) == 1:
            segs.append(
                f'<circle cx="{cx}" cy="{cy}" r="{(r_out + r_in) / 2}" fill="none" '
                f'stroke="{colour_for(lang, i)}" stroke-width="{r_out - r_in}"/>')
        else:
            segs.append(f'<path d="{arc_path(cx, cy, r_out, r_in, a + gap / 2, a + span - gap / 2)}" '
                        f'fill="{colour_for(lang, i)}"><title>{lang} {share * 100:.1f}%</title></path>')
        a += span

    H = int(cy + r_out + 10)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" '
        f'role="img" aria-label="Most used languages">'
        f'<title>Most used languages</title>'
        f'<g font-family="{font}" font-size="13">{"".join(legend)}</g>'
        f'{"".join(segs)}</svg>\n'
    )


def main():
    if os.getenv("DEMO") == "1":
        totals = {"CSS": 380, "HTML": 340, "Python": 140, "JavaScript": 70, "Rust": 40, "Shell": 20, "TypeScript": 10}
    else:
        totals = collect()
    data = shares(totals)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for theme in THEMES:
        (OUT_DIR / f"langs-{theme}.svg").write_text(render(data, theme), encoding="utf-8")
    print(", ".join(f"{l} {s * 100:.1f}%" for l, s in data))


if __name__ == "__main__":
    main()
