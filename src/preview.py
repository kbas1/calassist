"""Render the proposed week as a diff, not a snapshot.

The value is seeing what CalAssist wants to ADD against what is already
there — a mirror of your calendar would be pointless. Category colours match
what will land on Google Calendar, so the preview reads the same as the result.
"""
import os
from datetime import datetime, timedelta

import config
from src.calendar_read import Event
from src.tools import Proposal

HOURS = list(range(7, 23))
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# Approximations of Google Calendar's palette, so the preview matches the result.
CATEGORY_CSS = {
    "focus": "#4a63d4", "social": "#e0736b", "workout": "#3f9a5c",
    "errand": "#d4a92f", "travel": "#7d7d84",
}

CSS = """
:root { --bg:#fbfaf8; --fg:#1a1a1a; --line:#e2ded8; --muted:#8a857e;
        --existing:#cfc9c0; --work:#f1efeb; }
@media (prefers-color-scheme: dark) { :root {
  --bg:#15151a; --fg:#e9e7e4; --line:#2c2c33; --muted:#8f8a84;
  --existing:#413e39; --work:#1c1c21; } }
* { box-sizing:border-box; }
body { background:var(--bg); color:var(--fg); margin:0; padding:2rem 1.5rem;
       font:15px/1.55 ui-sans-serif,system-ui,-apple-system,sans-serif; }
.wrap { max-width:980px; margin:0 auto; }
h1 { font-size:1.5rem; margin:0 0 .2rem; letter-spacing:-.01em; }
.sub { color:var(--muted); margin:0 0 1.25rem; font-size:.92rem; }
.key { display:flex; gap:1.1rem; flex-wrap:wrap; align-items:center;
       margin:0 0 1.25rem; font-size:.82rem; color:var(--muted); }
.sw { display:inline-block; width:13px; height:13px; border-radius:3px;
      margin-right:5px; vertical-align:-2px; border:1px solid rgba(0,0,0,.12); }
.scroll { overflow-x:auto; border:1px solid var(--line); border-radius:8px; }
table { border-collapse:collapse; width:100%; min-width:660px; }
th,td { border:1px solid var(--line); padding:0; height:24px; text-align:center;
        font-size:11px; overflow:hidden; }
th { padding:7px 4px; font-weight:600; font-size:.8rem; }
th .d { color:var(--muted); font-weight:400; font-size:.72rem; }
td.h { width:52px; color:var(--muted); font-size:10px; padding-right:6px;
       text-align:right; border-left:none; }
td.work { background:var(--work); }
td.ex { background:var(--existing); }
td.blk { color:#fff; font-weight:600; }
section { margin-top:1.6rem; }
h2 { font-size:.74rem; text-transform:uppercase; letter-spacing:.08em;
     color:var(--muted); margin:0 0 .5rem; font-weight:600; }
ul { margin:0; padding-left:1.1rem; }
li { margin-bottom:.35rem; }
.why { color:var(--muted); }
"""


def _grid(proposal: Proposal, existing: list[Event], monday):
    """Map (day_index, hour) -> (css_class, inline_style, label)."""
    cells = {}
    for e in existing:
        idx = (e.start.date() - monday).days
        if not 0 <= idx <= 6:
            continue
        for h in range(e.start.hour, max(e.start.hour + 1, e.end.hour)):
            cells[(idx, h)] = ("ex", "", e.summary)
    for b in proposal.blocks:
        idx = (datetime.fromisoformat(b["day"]).date() - monday).days
        if not 0 <= idx <= 6:
            continue
        cat = b.get("category", "focus")
        colour = CATEGORY_CSS.get(cat, CATEGORY_CSS["focus"])
        sh, eh = int(b["start"][:2]), int(b["end"][:2])
        for h in range(sh, max(sh + 1, eh)):
            cells[(idx, h)] = (f"blk cat-{cat}", f"background:{colour}", b["title"])
    return cells


def render(proposal: Proposal, existing: list[Event],
           out_path: str = "outputs/week-preview.html") -> str:
    days = [datetime.fromisoformat(b["day"]).date() for b in proposal.blocks]
    days += [e.start.date() for e in existing]
    anchor = min(days) if days else datetime.now(config.TIMEZONE).date()
    monday = anchor - timedelta(days=anchor.weekday())

    cells = _grid(proposal, existing, monday)
    blocked_start, blocked_end = config.WEEKDAY_BLOCKED

    rows = []
    for h in HOURS:
        tds = [f'<td class="h">{h:02d}</td>']
        for d in range(7):
            hit = cells.get((d, h))
            if hit:
                cls, style, label = hit
                st = f' style="{style}"' if style else ""
                tds.append(f'<td class="{cls}"{st} title="{label}">{label[:13]}</td>')
            elif d < 5 and blocked_start.hour <= h < blocked_end.hour:
                tds.append('<td class="work" title="Work — not visible to CalAssist"></td>')
            else:
                tds.append("<td></td>")
        rows.append(f"<tr>{''.join(tds)}</tr>")

    headers = "".join(
        f"<th>{n}<br><span class='d'>{(monday + timedelta(days=i)):%m/%d}</span></th>"
        for i, n in enumerate(DAYS)
    )

    used = sorted({b.get("category", "focus") for b in proposal.blocks})
    key = "".join(
        f'<span><i class="sw" style="background:{CATEGORY_CSS.get(c, "#888")}"></i>{c}</span>'
        for c in used
    )
    key += ('<span><i class="sw" style="background:var(--existing)"></i>'
            'already on your calendar</span>'
            '<span><i class="sw" style="background:var(--work)"></i>'
            'work — not visible to CalAssist</span>')

    def section(title, items):
        return f"<section><h2>{title}</h2><ul>{''.join(items)}</ul></section>" if items else ""

    skipped = section("Already on your calendar — skipped", [
        f"<li><strong>{s['item']}</strong> <span class='why'>&rarr; matched "
        f"&ldquo;{s['matched']}&rdquo;</span></li>"
        for s in proposal.skipped_already_scheduled])
    missed = section("Did not fit", [
        f"<li><strong>{n['item']}</strong> <span class='why'>&mdash; {n['why']}</span></li>"
        for n in proposal.not_scheduled])
    warns = section("Watch out", [f"<li>{w}</li>" for w in proposal.warnings])

    mins = sum(
        (int(b["end"][:2]) * 60 + int(b["end"][3:]))
        - (int(b["start"][:2]) * 60 + int(b["start"][3:]))
        for b in proposal.blocks
    )

    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Week of {monday:%b %-d}</title><style>{CSS}</style></head>
<body><div class="wrap">
<h1>Week of {monday:%B %-d}</h1>
<p class="sub">{len(proposal.blocks)} proposed blocks &middot; {mins // 60}h {mins % 60}m</p>
<div class="key">{key}</div>
<div class="scroll"><table>
<tr><th></th>{headers}</tr>
{''.join(rows)}
</table></div>
{skipped}{missed}{warns}
</div></body></html>"""

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w") as f:
        f.write(html)
    return os.path.abspath(out_path)
