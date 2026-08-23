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
        position:relative; overflow:visible; }
tr:last-child td { border-bottom:1px solid var(--line); }
/* An event that crosses this hour boundary owns it — no rule through a
   single continuous block. */
td.nb { border-top-color:transparent; }
/* Flush to the cell edges and painted OVER the hour rule, so consecutive
   blocks read as one continuous run instead of being separated by seams. */
.seg { position:absolute; left:0; right:0; border-radius:0; overflow:hidden;
       display:flex; align-items:center; justify-content:center; padding:0 3px;
       color:#fff; font-weight:600; line-height:1.18; text-align:center;
       white-space:normal; overflow-wrap:anywhere; hyphens:auto;
       z-index:2; box-shadow:0 0 0 1px var(--bg); }
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
    """Map (day_index, hour) -> blocks that START in that hour.

    One element per block, not one per hour cell. A block spanning 90 minutes
    is a single div 150% of a row tall, so there is no seam and no cell border
    running through the middle of one event — and its label can be sized
    against the block's real height rather than a single slice of it.
    """
    cells: dict = {}
    # Cells a block passes THROUGH, after the hour it starts in. The hour rule
    # is suppressed on these so a single event is never crossed by a line.
    crossed: set = set()

    def place(idx, start_min, end_min, cls, style, label):
        h = start_min // 60
        top = (start_min - h * 60) / 60 * 100
        height = (end_min - start_min) / 60 * 100
        cells.setdefault((idx, h), []).append(
            (top, height, cls, style, label, end_min - start_min)
        )
        # end_min - 1 so a block ending exactly on the hour does not claim the
        # next row, which belongs to whatever starts there.
        for hh in range(h + 1, ((end_min - 1) // 60) + 1):
            crossed.add((idx, hh))

    for e in existing:
        idx = (e.start.date() - monday).days
        if 0 <= idx <= 6:
            place(idx, _minutes(f"{e.start:%H:%M}"), _minutes(f"{e.end:%H:%M}"),
                  "ex", "", e.summary)

    for b in proposal.blocks:
        idx = (datetime.fromisoformat(b["day"]).date() - monday).days
        if 0 <= idx <= 6:
            cat = b.get("category", "focus")
            colour = CATEGORY_CSS.get(cat, CATEGORY_CSS["focus"])
            place(idx, _minutes(b["start"]), _minutes(b["end"]),
                  f"blk cat-{cat}", f"background:{colour}", b["title"])

    return cells, crossed


def render(proposal: Proposal, existing: list[Event],
           out_path: str = "outputs/week-preview.html") -> str:
    days = [datetime.fromisoformat(b["day"]).date() for b in proposal.blocks]
    days += [e.start.date() for e in existing]
    anchor = min(days) if days else datetime.now(config.TIMEZONE).date()
    monday = anchor - timedelta(days=anchor.weekday())

    cells, crossed = _grid(proposal, existing, monday)
    blocked_start, blocked_end = config.WEEKDAY_BLOCKED

    # Zoom: render only the hours that carry something, padded by one either
    # side, rather than a fixed 7 AM-10 PM wall that is mostly empty.
    used_hours = [h for (_, h) in cells]
    used_hours += [h + int((top + ht) // 100)
                   for (_, h), segs in cells.items() for top, ht, *_ in segs]
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
            klass = " ".join(filter(None, [
                "work" if work else "",
                "nb" if (d, h) in crossed else "",
            ]))
            title = ' title="Work — not visible to CalAssist"' if work else ""
            base = f' class="{klass}"{title}' if klass else title
            if segs:
                inner = "".join(
                    f'<div class="seg {cls}" style="top:{top:.4f}%;'
                    f'height:{ht:.4f}%;font-size:{_fit_font(text, dur):.1f}px;{style}" '
                    f'title="{text}">{text}</div>'
                    for top, ht, cls, style, text, dur in segs
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
