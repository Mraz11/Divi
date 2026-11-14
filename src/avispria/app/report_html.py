# SPDX-FileCopyrightText: 2026 Dīvi contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The report as one HTML file: no links to the internet, pictures and font inside, A4 when printed.

Open it in any browser; "Print, or save as PDF" makes the PDF. Every text from a record is escaped.
The look is Dīvi's light palette and monospace type, so the report reads as part of the program.
"""

from __future__ import annotations

import base64
import time
from html import escape
from importlib.resources import files
from pathlib import Path

from avispria.app.engines import EXPORT_FILE
from avispria.app.report_data import ReportData
from avispria.app.ui.theme import LIGHT
from avispria.core.citation import REQUEST, citation
from avispria.core.landcover import CLASSES
from avispria.core.pipeline import diagram
from avispria.core.report_text import LIMITS, findings, key_numbers, methods, num, references
from avispria.core.version import __version__

FONTS = (  # (family, file): Archivo for text, JetBrains Mono for numbers, as in the program
    ("Archivo", "archivo-latin.woff2"),
    ("Archivo", "archivo-latin-ext.woff2"),
    ("JetBrains Mono", "jetbrains-mono-latin.woff2"),
    ("JetBrains Mono", "jetbrains-mono-latin-ext.woff2"),
)


def _font_faces() -> str:
    folder = files("avispria.app.ui") / "assets" / "fonts"
    faces = []
    for family, name in FONTS:
        try:
            data = base64.b64encode((folder / name).read_bytes()).decode("ascii")
        except OSError:
            continue
        stretch = "font-stretch:62% 125%;" if family == "Archivo" else ""
        faces.append(
            f"@font-face{{font-family:'{family}';font-weight:100 900;{stretch}"
            f"src:url(data:font/woff2;base64,{data}) format('woff2')}}"
        )
    return "".join(faces)


def _style() -> str:
    p = LIGHT
    return (
        _font_faces()
        + f"""
:root{{--bg:{p.bg};--surface:{p.surface};--line:{p.border};--text:{p.text};--muted:{p.muted};
--accent:{p.primary};--accent-text:{p.primary_text};--caution:{p.caution_bg};--good:{p.good_bg}}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--text);
font:15px/1.6 Archivo,'Segoe UI',system-ui,sans-serif;font-variant-numeric:tabular-nums}}
td.value,td.num,.cite,.data{{font-family:'JetBrains Mono',ui-monospace,Consolas,monospace;
font-size:13.5px}}
main{{max-width:960px;margin:0 auto;padding:24px 16px 48px}}
header{{border:1px solid var(--line);border-radius:8px 8px 0 0;background:var(--surface);
padding:22px 24px}}
.kicker{{font-size:14px;color:var(--muted)}}
h1{{font-size:32px;font-stretch:118%;font-weight:750;letter-spacing:-.01em;line-height:1.15;
margin:4px 0 6px}}
h2{{font-size:19px;font-stretch:112%;font-weight:700;margin:0 0 12px}}
h3{{font-size:15.5px;font-weight:650;margin:16px 0 4px}}
p,li{{max-width:78ch}}
section{{background:var(--surface);border:1px solid var(--line);border-top:0;padding:20px 24px}}
section:last-of-type{{border-radius:0 0 8px 8px}}
table{{border-collapse:collapse;width:100%;font-size:13px}}
th,td{{text-align:left;vertical-align:top;padding:6px 8px;border-bottom:1px solid var(--line)}}
th{{font-size:13px;color:var(--muted);font-weight:600}}
td{{overflow-wrap:anywhere}}
td.value{{font-weight:700}}
table.numbers td:first-child{{width:30%}}
table.numbers td.value{{width:38%}}
.muted{{color:var(--muted)}}
.pipe{{display:flex;flex-wrap:wrap;margin-top:16px}}
.pipe span{{position:relative;display:flex;flex-direction:column;align-items:center;gap:4px;
padding:0 10px;font-size:12.5px;color:var(--muted)}}
.pipe span::before{{content:"";width:12px;height:12px;border-radius:50%;
border:2px solid var(--line);background:var(--surface);z-index:1}}
.pipe span::after{{content:"";position:absolute;top:7px;left:0;right:0;height:2px;
background:var(--line)}}
.pipe span:first-child::after{{left:50%}}.pipe span:last-child::after{{right:50%}}
.pipe span.done{{color:var(--text)}}
.pipe span.done::before{{background:var(--accent);border-color:var(--accent)}}
figure{{margin:0;border:1px solid var(--line);border-radius:8px;overflow:hidden}}
.maps{{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(260px,1fr))}}
figure img{{display:block;width:100%;height:auto;max-height:420px;object-fit:contain;
background:repeating-conic-gradient(#eef2f4 0 25%,#fff 0 50%) 0 0/16px 16px}}
.key{{display:inline-block;width:10px;height:10px;margin-right:4px;border:1px solid var(--line)}}
.legend{{display:flex;flex-wrap:wrap;gap:2px 12px;margin-top:4px}}
figcaption{{padding:6px 10px;font-size:12px;color:var(--muted);border-top:1px solid var(--line)}}
ul{{margin:0;padding-left:20px}}
.note{{background:var(--caution);border:1px solid var(--line);border-radius:6px;padding:10px 14px}}
.cite{{background:var(--good);border:1px solid var(--line);border-radius:6px;padding:10px 14px;
word-break:break-word}}
.print{{float:right;font:inherit;font-size:14px;font-weight:600;padding:8px 14px;
border:1px solid var(--line);border-radius:6px;background:var(--surface);cursor:pointer}}
footer{{font-size:12px;color:var(--muted);margin-top:16px}}
@page{{size:A4;margin:14mm}}
@media print{{body{{background:#fff;font-size:11.5px}}main{{padding:0;max-width:none}}
.print{{display:none}}section,figure,tr{{break-inside:avoid}}}}
"""
    )


def _rows(cells: list[list[str]], head: list[str], first_value: int = -1, cls: str = "") -> str:
    out = [
        f'<table class="{cls}"><thead><tr>',
        *(f"<th>{escape(h)}</th>" for h in head),
        "</tr></thead><tbody>",
    ]
    for row in cells:
        out.append("<tr>")
        for n, cell in enumerate(row):
            cls = ' class="value"' if n == first_value else ""
            out.append(f"<td{cls}>{escape(cell)}</td>")
        out.append("</tr>")
    out.append("</tbody></table>")
    return "".join(out)


def _section(title: str, body: str) -> str:
    return f"<section><h2>{escape(title)}</h2>{body}</section>"


def _list(items: list[str] | tuple[str, ...]) -> str:
    return "<ul>" + "".join(f"<li>{escape(i)}</li>" for i in items) + "</ul>"


def _header(data: ReportData) -> str:
    done = sum(s.done for s in data.states)
    steps = "".join(
        f'<span class="{"done" if s.done else ""}">{s.spec.number} {escape(s.spec.name)}</span>'
        for s in data.states
    )
    return (
        '<header><button class="print" onclick="window.print()">Print, or save as PDF</button>'
        '<div class="kicker">Dīvi project report</div>'
        f"<h1>{escape(data.name or 'Unnamed project')}</h1>"
        f'<div class="muted">Made {time.strftime("%Y-%m-%d %H:%M")} with Dīvi {__version__}.'
        f" {done} of {len(data.states)} steps done.</div>"
        f'<div class="pipe">{steps}</div></header>'
    )


def _results(data: ReportData) -> str:
    rows = key_numbers(data.canopy, data.surface, data.inventory)
    if not rows:
        return _section(
            "Results", '<p class="muted">Nothing has been measured yet (step 6, Measure).</p>'
        )
    return _section(
        "Results", _rows([list(r) for r in rows], ["What", "Value", "Note"], 1, "numbers")
    )


def _legend(data: ReportData) -> str:
    """The colours of the land-cover classes found in this map."""
    found = ((data.surface or {}).get("metrics") or {}).get("cover_pct") or {}
    keys = "".join(
        f'<span><span class="key" style="background:rgb{tuple(rgb)}"></span>{escape(name)}</span>'
        for name, rgb in CLASSES.values()
        if name in found
    )
    return f'<div class="legend">{keys}</div>' if keys else ""


def _pictures(data: ReportData) -> str:
    if not data.pictures:
        return ""
    body = "".join(
        f'<figure><img alt="{escape(caption)}" '
        f'src="data:image/png;base64,{base64.b64encode(png).decode("ascii")}">'
        f"<figcaption>{escape(caption)}{_legend(data) if caption == 'Land cover' else ''}"
        "</figcaption></figure>"
        for caption, png in data.pictures
    )
    return _section("Maps", f'<div class="maps">{body}</div>')


def _methods(data: ReportData) -> str:
    parts = methods(data.provenance, data.canopy, data.surface, data.inventory)
    if not parts:
        return ""
    body = "".join(
        f"<h3>{escape(h)}</h3>" + "".join(f"<p>{escape(p)}</p>" for p in ps) for h, ps in parts
    )
    return _section("Methods", body)


def _quality(data: ReportData) -> str:
    found = findings(data.canopy, data.surface, data.inventory)
    qa = (data.provenance or {}).get("capture_qa") or {}
    found += [
        f"{i.get('code', '')}: {i.get('message', '')}"
        for i in qa.get("issues") or []
        if isinstance(i, dict)
    ]
    found += [f"{name} could not be read and is left out of this report" for name in data.missing]
    if not found:
        return _section("Quality checks", '<p class="muted">No warnings were recorded.</p>')
    return _section("Quality checks", f'<div class="note">{_list(found)}</div>')


def _provenance(data: ReportData) -> str:
    rows = [
        [
            f"{s.spec.number} {s.spec.name}",
            s.label,
            s.detail,
            data.stamps.get(s.spec.key, {}).get("finished", ""),
            data.stamps.get(s.spec.key, {}).get("version", ""),
        ]
        for s in data.states
    ]
    body = f'<p class="muted">{escape(diagram())}</p>' + _rows(
        rows, ["Engine", "State", "What is there", "Finished", "Version"]
    )
    prov = data.provenance
    if prov:
        engine = prov.get("engine") or {}
        inputs, outputs = prov.get("inputs") or [], prov.get("outputs") or []
        facts = [
            f"Map engine: {engine.get('engine', '?')} {engine.get('engine_version', '')}",
            f"Options sent: {', '.join(map(str, prov.get('options_sent') or {})) or 'none'}",
            f"Processing time: {num((prov.get('task') or {}).get('processing_s'), 0)} s",
            f"{len(inputs)} input photos and {len(outputs)} outputs, each with a SHA-256 checksum "
            "in divi_provenance.json in the maps folder",
        ]
        body += "<h3>How the maps were made</h3>" + _list(facts)
    links = data.links
    where = [f"Missions: {', '.join(links.plan_files) or 'none recorded'}"]
    where += [f"Photos: {links.photo_folder or 'none recorded'}"]
    where += [f"Maps and measurements: {links.maps_folder or 'none recorded'}"]
    if links.maps_folder and (Path(links.maps_folder) / EXPORT_FILE).is_file():
        where += [f"Exported for QGIS: {Path(links.maps_folder) / 'export'} (see README.txt)"]
    return _section("Provenance", body + "<h3>Where the files are</h3>" + _list(where))


def render(data: ReportData) -> str:
    refs = references(data.provenance, data.inventory)
    tail = _section("Limits", _list(LIMITS)) + _section(
        "How to cite",
        f'<p>{escape(REQUEST)}</p><div class="cite">{escape(citation())}</div>'
        + (f"<h3>References</h3>{_list(refs)}" if refs else ""),
    )
    body = "".join(
        (
            _header(data),
            _results(data),
            _pictures(data),
            _methods(data),
            _quality(data),
            _provenance(data),
            tail,
        )
    )
    title = escape(f"{data.name or 'Unnamed project'}: Dīvi report")
    return (
        f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width,initial-scale=1">'
        f"<title>{title}</title><style>{_style()}</style></head><body><main>{body}"
        f"<footer>Dīvi {__version__}. {escape(REQUEST)}</footer></main></body></html>"
    )
