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


def hour_label(h: int) -> str:
    """24-hour int -> '7 AM' / '12 PM' / '5 PM'."""
    suffix = "AM" if h < 12 else "PM"
    twelve = h % 12 or 12
    return f"{twelve} {suffix}"

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
.wrap { max-width:1440px; margin:0 auto; }
.cols { display:flex; gap:1.75rem; align-items:flex-start; }
.chart { flex:1 1 auto; min-width:0; }
.side { flex:0 0 290px; }
.side section:first-child { margin-top:0; }
@media (max-width:940px) { .cols { flex-direction:column; }
                           .side { flex:1 1 auto; width:100%; } }
h1 { font-size:1.5rem; margin:0 0 .2rem; letter-spacing:-.01em; }
.sub { color:var(--muted); margin:0 0 1.25rem; font-size:.92rem; }
.key { display:flex; gap:1.5rem; flex-wrap:wrap; align-items:center;
       margin:0 0 1.5rem; font-size:1rem; color:var(--fg); font-weight:500; }
.sw { display:inline-block; width:19px; height:19px; border-radius:4px;
      margin-right:9px; vertical-align:-4px; border:1px solid rgba(0,0,0,.12); }
.scroll { overflow-x:auto; border:1px solid var(--line); border-radius:8px; }
table { border-collapse:collapse; width:100%; min-width:660px; }
th,td { border-left:1px solid var(--line); border-right:1px solid var(--line);
        border-top:1px solid var(--line); border-bottom:none; padding:0;
        height:46px; text-align:center; font-size:12px; line-height:1.15;
        position:relative; }
tr:last-child td { border-bottom:1px solid var(--line); }
/* Flush to the cell edges and painted OVER the hour rule, so consecutive
   blocks read as one continuous run instead of being separated by seams. */
.seg { position:absolute; left:0; right:0; border-radius:0; overflow:hidden;
       display:flex; align-items:center; justify-content:center; padding:0 3px;
       color:#fff; font-weight:600; line-height:1.18; text-align:center;
       white-space:normal; overflow-wrap:anywhere; hyphens:auto;
       margin-top:-1px; padding-bottom:1px; z-index:1;
       border-top:1px solid var(--bg); }
/* A single event spanning several hours must read as ONE block, so its
   continuation slices carry no divider. Only the START of a block does,
   which is what separates two different events sitting back to back. */
.seg.cont { border-top:none; }
.seg.ex { background:var(--existing); color:var(--fg); font-weight:500; }
th { padding:7px 4px; font-weight:600; font-size:.8rem; }
th .d { color:var(--muted); font-weight:400; font-size:.72rem; }
td.h { width:64px; white-space:nowrap; border-left:none; border-right:none; color:var(--muted); font-size:10px; padding-right:6px;
       text-align:right; border-left:none; }
td.work { background:var(--work); }


section { margin-top:1.6rem; }
h2 { font-size:.74rem; text-transform:uppercase; letter-spacing:.08em;
     color:var(--muted); margin:0 0 .5rem; font-weight:600; }
ul { margin:0; padding-left:1.1rem; }
li { margin-bottom:.35rem; }
.why { color:var(--muted); }
"""


ROW_PX = 46          # height of one hour row
COL_PX = 128         # approximate width of one day column


def _minutes(hhmm: str) -> int:
    return int(hhmm[:2]) * 60 + int(hhmm[3:5])


def _fit_font(text: str, minutes: int) -> float:
    """Largest font size at which `text` wraps into the block's real area.

    Labels are not truncated — the type shrinks until the whole title fits,
    so a 30-minute "Travel to Pickleball" stays readable and complete.
    """
    height = max(9.0, minutes / 60 * ROW_PX - 3)
    width = COL_PX - 6
    for size in (12.5, 12, 11, 10, 9.5, 9, 8.5, 8, 7.5, 7, 6.5, 6):
        per_line = max(1, int(width / (size * 0.53)))
        lines = -(-len(text) // per_line)               # ceil division
        if lines * size * 1.18 <= height:
            return size
    return 6


def _grid(proposal: Proposal, existing: list[Event], monday):
    """Map (day_index, hour) -> list of segments inside that hour.

    One row per hour, but each block is painted as a proportional slice of the
    cell it sits in. A 3:30-4:00 block fills the bottom half of the 3 PM cell
    rather than the whole thing — at hour granularity a 30-minute block and a
    2-hour block looked identical.
    """
    cells: dict = {}

    def paint(idx, start_min, end_min, cls, style, label):
        # Collect the slices first so the label can go in the TALLEST one and
        # be sized against that slice's real height. Sizing against the whole
        # block's duration overflowed short leading slices — a 7:30-8:30 event
        # has only 30 minutes of room in its first cell, not 60.
        pieces = []
        for h in range(start_min // 60, ((end_min - 1) // 60) + 1):
            hour_start, hour_end = h * 60, h * 60 + 60
            top = max(start_min, hour_start) - hour_start
            bottom = min(end_min, hour_end) - hour_start
            if bottom > top:
                pieces.append((h, top, bottom))
        if not pieces:
            return

        tallest = max(range(len(pieces)), key=lambda i: pieces[i][2] - pieces[i][1])
        for i, (h, top, bottom) in enumerate(pieces):
            span = bottom - top
            cells.setdefault((idx, h), []).append(
                (top / 60 * 100, span / 60 * 100,
                 cls + ("" if i == 0 else " cont"), style,
                 label if i == tallest else "", label, span)
            )

    for e in existing:
        idx = (e.start.date() - monday).days
        if 0 <= idx <= 6:
            paint(idx, _minutes(f"{e.start:%H:%M}"), _minutes(f"{e.end:%H:%M}"),
                  "ex", "", e.summary)

    for b in proposal.blocks:
        idx = (datetime.fromisoformat(b["day"]).date() - monday).days
        if 0 <= idx <= 6:
            cat = b.get("category", "focus")
            colour = CATEGORY_CSS.get(cat, CATEGORY_CSS["focus"])
            paint(idx, _minutes(b["start"]), _minutes(b["end"]),
                  f"blk cat-{cat}", f"background:{colour}", b["title"])

    return cells


def render(proposal: Proposal, existing: list[Event],
           out_path: str = "outputs/week-preview.html") -> str:
    days = [datetime.fromisoformat(b["day"]).date() for b in proposal.blocks]
    days += [e.start.date() for e in existing]
    anchor = min(days) if days else datetime.now(config.TIMEZONE).date()
    monday = anchor - timedelta(days=anchor.weekday())

    cells = _grid(proposal, existing, monday)
    blocked_start, blocked_end = config.WEEKDAY_BLOCKED

    # Zoom: render only the hours that carry something, padded by one either
    # side, rather than a fixed 7 AM-10 PM wall that is mostly empty.
    used_hours = [h for (_, h) in cells]
    if used_hours:
        lo = max(min(HOURS), min(used_hours) - 1)
        hi = min(max(HOURS), max(used_hours) + 1)
    else:
        lo, hi = min(HOURS), max(HOURS)
    hours = list(range(lo, hi + 1))

    rows = []
    for h in hours:
        tds = [f'<td class="h">{hour_label(h)}</td>']
        for d in range(7):
            segs = cells.get((d, h))
            work = d < 5 and blocked_start.hour <= h < blocked_end.hour
            base = ' class="work" title="Work — not visible to CalAssist"' if work else ""
            if segs:
                inner = "".join(
                    f'<div class="seg {cls}" style="top:{top:.4f}%;'
                    f'height:{ht:.4f}%;font-size:{_fit_font(text, dur):.1f}px;{style}" '
                    f'title="{full}">{text}</div>'
                    for top, ht, cls, style, text, full, dur in segs
                )
                tds.append(f"<td{base}>{inner}</td>")
            else:
                tds.append(f"<td{base}></td>")
        rows.append(f"<tr>{''.join(tds)}</tr>")

    headers = "".join(
        f"<th>{n}<br><span class='d'>{(monday + timedelta(days=i)):%m/%d}</span></th>"
        for i, n in enumerate(DAYS)
    )

    used = sorted({b.get("category", "focus") for b in proposal.blocks})
    key = "".join(
        f'<span><i class="sw" style="background:{CATEGORY_CSS.get(c, "#888")}"></i>'
        f'{c.title()}</span>'
        for c in used
    )
    key += ('<span><i class="sw" style="background:var(--work)"></i>'
            'Work — Not Visible To CalAssist</span>')

    def section(title, items):
        return f"<section><h2>{title}</h2><ul>{''.join(items)}</ul></section>" if items else ""

    missed = section("Did Not Fit", [
        f"<li><strong>{n['item']}</strong> <span class='why'>&mdash; {n['why']}</span></li>"
        for n in proposal.not_scheduled])
    warns = section("Notes", [f"<li>{w}</li>" for w in proposal.warnings])

    title = f"{config.OWNER_NAME}'s Week of {monday:%b}-{monday.day}-{monday.year}"
    tzname = datetime.now(config.TIMEZONE).strftime("%Z")

    mins = sum(
        (int(b["end"][:2]) * 60 + int(b["end"][3:]))
        - (int(b["start"][:2]) * 60 + int(b["start"][3:]))
        for b in proposal.blocks
    )

    html = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title><style>{CSS}</style></head>
<body><div class="wrap">
<h1>{title}</h1>
<p class="sub">{len(proposal.blocks)} Proposed Blocks &middot; {mins // 60}h {mins % 60}m
   &middot; All Times {tzname}</p>
<div class="key">{key}</div>
<div class="cols">
  <div class="chart"><div class="scroll"><table>
  <tr><th></th>{headers}</tr>
  {''.join(rows)}
  </table></div></div>
  <aside class="side">{missed}{warns}</aside>
</div>
</div></body></html>"""

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w") as f:
        f.write(html)
    return os.path.abspath(out_path)
