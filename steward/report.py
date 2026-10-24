"""Turn findings into the two things anyone wants: a terminal answer and a page."""

from __future__ import annotations

from pathlib import Path

from .checks import FAIL, OK, WARN, Report

GLYPH = {OK: "ok", WARN: "warn", FAIL: "FAIL"}


def to_terminal(report: Report) -> str:
    lines = [f"steward · {len(report.checked)} repositories · {report.when}", ""]
    for repo in report.checked:
        findings = report.for_repo(repo)
        worst = FAIL if any(f.level == FAIL for f in findings) else \
            WARN if any(f.level == WARN for f in findings) else OK
        lines.append(f"{repo}  [{GLYPH[worst]}]")
        for f in findings:
            if f.level == OK:
                continue
            mark = "!" if f.level == FAIL else "~"
            lines.append(f"  {mark} {f.message}")
            if f.detail:
                lines.append(f"      {f.detail[:150]}")
        lines.append("")
    lines.append(f"{report.count(OK)} ok · {report.count(WARN)} warnings · "
                 f"{report.count(FAIL)} failures")
    return "\n".join(lines)


def to_markdown(report: Report) -> str:
    lines = [f"# steward — {report.when}", ""]
    lines.append(f"**{len(report.checked)} repositories · {report.count(OK)} ok · "
                 f"{report.count(WARN)} warnings · {report.count(FAIL)} failures**")
    lines.append("")
    lines.append("| repository | state | what is wrong |")
    lines.append("|---|---|---|")
    for repo in report.checked:
        findings = report.for_repo(repo)
        worst = FAIL if any(f.level == FAIL for f in findings) else \
            WARN if any(f.level == WARN for f in findings) else OK
        problems = [f.message for f in findings if f.level != OK]
        cell = "<br>".join(problems[:4]) if problems else "—"
        if len(problems) > 4:
            cell += f"<br>+{len(problems) - 4} more"
        lines.append(f"| `{repo}` | {GLYPH[worst]} | {cell} |")
    lines.append("")
    severe = [f for f in report.findings if f.level == FAIL]
    if severe:
        lines.append("## Failures in detail")
        lines.append("")
        for f in severe:
            lines.append(f"- **{f.repo}** — {f.message}")
            if f.detail:
                lines.append(f"  - `{f.detail[:300]}`")
        lines.append("")
    return "\n".join(lines)


def to_html(report: Report, css: str) -> str:
    rows = []
    for repo in report.checked:
        findings = report.for_repo(repo)
        worst = FAIL if any(f.level == FAIL for f in findings) else \
            WARN if any(f.level == WARN for f in findings) else OK
        problems = [f for f in findings if f.level != OK]
        items = "".join(
            f'<li class="{f.level}">{f.message}'
            + (f'<span class="d">{f.detail[:160]}</span>' if f.detail else "")
            + "</li>" for f in problems) or '<li class="ok">nothing to fix</li>'
        rows.append(f'<tr class="{worst}"><td class="repo">{repo}</td>'
                    f'<td class="state">{GLYPH[worst]}</td>'
                    f'<td><ul>{items}</ul></td></tr>')

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>steward — {len(report.checked)} repositories, checked without being asked</title>
<style>{css}</style></head>
<body><div class="wrap">
<h1>steward</h1>
<p class="lede">A program that checks every repository it is pointed at, on a schedule,
without anybody asking it to. This page is written by it, not by a person.</p>
<div class="bar">
  <span class="pill ok">{report.count(OK)} ok</span>
  <span class="pill warn">{report.count(WARN)} warnings</span>
  <span class="pill fail">{report.count(FAIL)} failures</span>
  <span class="when">{report.when}</span>
</div>
<table><tbody>{''.join(rows)}</tbody></table>
<h2>What it can and cannot decide</h2>
<div class="two">
<div class="box"><h3>Decides alone</h3><ul>
<li>whether tests still pass</li><li>whether a token is committed</li>
<li>whether a readme, licence or workflow is missing</li>
<li>whether anything is stale, oversized or junk</li></ul></div>
<div class="box"><h3>Needs a person</h3><ul>
<li>whether the code is any good</li><li>whether the product is worth building</li>
<li>anything that spends money or deploys</li>
<li>what to do about a failure it reported</li></ul></div>
</div>
<p class="foot">Checked: {', '.join(report.checked) or 'nothing'}. Every line on this page
comes from <code>steward.report</code>, and the page is rebuilt from the audit
itself — nothing here is typed.</p>
</div></body></html>
"""


def write_all(report: Report, out: Path, css: str = "") -> list[Path]:
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    written = []
    (out / "report.md").write_text(to_markdown(report), encoding="utf-8")
    written.append(out / "report.md")
    if css:
        (out / "index.html").write_text(to_html(report, css), encoding="utf-8")
        written.append(out / "index.html")
    return written
