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
.wrap { max-width:1180px; margin:0 auto; }
h1 { font-size:1.5rem; margin:0 0 .2rem; letter-spacing:-.01em; }
.sub { color:var(--muted); margin:0 0 1.25rem; font-size:.92rem; }
.key { display:flex; gap:1.5rem; flex-wrap:wrap; align-items:center;
       margin:0 0 1.5rem; font-size:1rem; color:var(--fg); font-weight:500; }
.sw { display:inline-block; width:19px; height:19px; border-radius:4px;
      margin-right:9px; vertical-align:-4px; border:1px solid rgba(0,0,0,.12); }
.scroll { overflow-x:auto; border:1px solid var(--line); border-radius:8px; }
table { border-collapse:collapse; width:100%; min-width:660px; }
th,td { border-left:1px solid var(--line); border-right:1px solid var(--line);
        border-top:none; border-bottom:none; padding:0; height:15px;
        text-align:center; font-size:11.5px; overflow:hidden; line-height:1.1; }
td.hr, th { border-top:1px solid var(--line); }
td.cont { border-top:none; }
tr:last-child td { border-bottom:1px solid var(--line); }
th { padding:7px 4px; font-weight:600; font-size:.8rem; }
th .d { color:var(--muted); font-weight:400; font-size:.72rem; }
td.h { width:64px; white-space:nowrap; border-left:none; border-right:none; color:var(--muted); font-size:10px; padding-right:6px;
       text-align:right; border-left:none; }
td.work { background:var(--work); }
td.ex { background:var(--existing); }
td.blk { color:#fff; font-weight:600; padding:0 3px; }
section { margin-top:1.6rem; }
h2 { font-size:.74rem; text-transform:uppercase; letter-spacing:.08em;
     color:var(--muted); margin:0 0 .5rem; font-weight:600; }
ul { margin:0; padding-left:1.1rem; }
li { margin-bottom:.35rem; }
.why { color:var(--muted); }
"""


SLOT_MINUTES = 15
SLOTS_PER_HOUR = 60 // SLOT_MINUTES


def _slot(hhmm: str) -> int:
    """'17:45' -> absolute quarter-hour index within the day."""
    h, m = int(hhmm[:2]), int(hhmm[3:5])
    return h * SLOTS_PER_HOUR + m // SLOT_MINUTES


def _grid(proposal: Proposal, existing: list[Event], monday):
    """Map (day_index, slot) -> (css_class, inline_style, label, is_first_slot).

    Resolution is 15 minutes, not one hour. At hour resolution a 30-minute
    block and a 90-minute block paint identically, which makes the chart
    misrepresent the shape of the week.
    """
    cells = {}

    def paint(idx, start_slot, end_slot, cls, style, label):
        for n, slot in enumerate(range(start_slot, max(start_slot + 1, end_slot))):
            cells[(idx, slot)] = (cls, style, label, n == 0)

    for e in existing:
        idx = (e.start.date() - monday).days
        if not 0 <= idx <= 6:
            continue
        paint(idx,
              _slot(f"{e.start:%H:%M}"), _slot(f"{e.end:%H:%M}"),
              "ex", "", e.summary)

    for b in proposal.blocks:
        idx = (datetime.fromisoformat(b["day"]).date() - monday).days
        if not 0 <= idx <= 6:
            continue
        cat = b.get("category", "focus")
        colour = CATEGORY_CSS.get(cat, CATEGORY_CSS["focus"])
        paint(idx, _slot(b["start"]), _slot(b["end"]),
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
    used = [sl for (_, sl) in cells]
    if used:
        lo = max(min(HOURS) * SLOTS_PER_HOUR, min(used) - SLOTS_PER_HOUR)
        hi = min(max(HOURS) * SLOTS_PER_HOUR + SLOTS_PER_HOUR - 1,
                 max(used) + SLOTS_PER_HOUR)
    else:
        lo = min(HOURS) * SLOTS_PER_HOUR
        hi = max(HOURS) * SLOTS_PER_HOUR
    lo -= lo % SLOTS_PER_HOUR                      # start on a whole hour
    slots = list(range(lo, hi + 1))

    rows = []
    for sl in slots:
        h, on_hour = sl // SLOTS_PER_HOUR, sl % SLOTS_PER_HOUR == 0
        label_cell = (f'<td class="h hr">{hour_label(h)}</td>' if on_hour
                      else '<td class="h"></td>')
        tds = [label_cell]
        for d in range(7):
            hit = cells.get((d, sl))
            if hit:
                cls, style, label, first = hit
                st = f' style="{style}"' if style else ""
                text = label[:20] if first else ""
                edge = "" if first else " cont"
                tds.append(f'<td class="{cls}{edge}"{st} title="{label}">{text}</td>')
            elif d < 5 and blocked_start.hour <= h < blocked_end.hour:
                tds.append('<td class="work" title="Work — not visible to CalAssist"></td>')
            else:
                tds.append(f'<td class="{"hr" if on_hour else ""}"></td>')
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
<div class="scroll"><table>
<tr><th></th>{headers}</tr>
{''.join(rows)}
</table></div>
{missed}{warns}
</div></body></html>"""

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    with open(out_path, "w") as f:
        f.write(html)
    return os.path.abspath(out_path)
