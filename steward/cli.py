"""Command line for steward.

    steward --root ~/projects              check every repo under a directory
    steward --root ~/projects --fast       skip running the test suites
    steward --root ~/projects --html site  also write the page
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .checks import audit_all
from .report import to_terminal, write_all

DEFAULT_CSS = """
:root{--bg:#0c0d0f;--panel:#14161a;--rule:#23262c;--ink:#e7e9ec;--ink2:#9aa2ad;
--ok:#4ade80;--warn:#fbbf24;--fail:#f87171;--mono:ui-monospace,SFMono-Regular,Menlo,monospace}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
font:400 16px/1.6 ui-sans-serif,-apple-system,"Segoe UI",Roboto,Arial,sans-serif}
.wrap{max-width:900px;margin:0 auto;padding:48px 24px 80px}
h1{font-size:2.2rem;margin:0 0 8px;letter-spacing:-.02em}
h2{font-size:1.2rem;margin:38px 0 12px}
.lede{color:var(--ink2);max-width:44em;margin:0 0 26px}
.bar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin-bottom:22px}
.pill{font-family:var(--mono);font-size:.76rem;padding:4px 10px;border-radius:999px;
border:1px solid var(--rule)}
.pill.ok{color:var(--ok);border-color:#1f3d2a;background:#0e1a13}
.pill.warn{color:var(--warn);border-color:#3d3618;background:#1a1709}
.pill.fail{color:var(--fail);border-color:#3d1f1f;background:#1a0e0e}
.when{font-family:var(--mono);font-size:.76rem;color:var(--ink2);margin-left:auto}
table{width:100%;border-collapse:collapse;font-size:.92rem}
td{border-top:1px solid var(--rule);padding:12px 10px;vertical-align:top}
tr:first-child td{border-top:none}
td.repo{font-family:var(--mono);font-size:.86rem;white-space:nowrap}
td.state{font-family:var(--mono);font-size:.76rem;white-space:nowrap}
tr.fail td.state{color:var(--fail)} tr.warn td.state{color:var(--warn)}
tr.ok td.state{color:var(--ok)}
ul{margin:0;padding-left:18px}
li{margin:.2em 0;color:var(--ink2)}
li.fail{color:#fca5a5} li.ok{color:var(--ink2)}
.d{display:block;font-family:var(--mono);font-size:.74rem;color:#6b7280;margin-top:2px}
.two{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media(max-width:700px){.two{grid-template-columns:1fr}}
.box{background:var(--panel);border:1px solid var(--rule);border-radius:10px;padding:16px 18px}
.box h3{margin:0 0 8px;font-size:.95rem}
.foot{color:#6b7280;font-size:.82rem;margin-top:38px;border-top:1px solid var(--rule);padding-top:16px}
"""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="steward",
        description="Audit repositories that a person never asked you to audit.")
    ap.add_argument("--version", action="version", version=f"steward {__version__}")
    ap.add_argument("--root", default=".", help="directory containing git repositories")
    ap.add_argument("--only", nargs="*", help="just these repository names")
    ap.add_argument("--fast", action="store_true", help="skip running test suites")
    ap.add_argument("--json", metavar="FILE", help="write the findings as JSON")
    ap.add_argument("--html", metavar="DIR", help="write report.md and index.html here")
    ap.add_argument("--strict", action="store_true", help="exit 1 on any warning too")
    args = ap.parse_args(argv)

    root = Path(args.root).expanduser().resolve()
    if not root.is_dir():
        print(f"steward: {root} is not a directory", file=sys.stderr)
        return 2

    report = audit_all(root, run_test_suite=not args.fast, only=args.only)
    if not report.checked:
        print(f"steward: no git repositories under {root}", file=sys.stderr)
        return 2

    print(to_terminal(report))

    if args.json:
        Path(args.json).write_text(json.dumps(report.to_json(), indent=2) + "\n",
                                   encoding="utf-8")
        print(f"wrote {args.json}")
    if args.html:
        for path in write_all(report, Path(args.html), css=DEFAULT_CSS):
            print(f"wrote {path}")

    if report.count("fail"):
        return 1
    if args.strict and report.count("warn"):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
