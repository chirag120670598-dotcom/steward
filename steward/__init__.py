"""steward — a repository caretaker that runs without being asked.

It checks the things a check can decide: do the tests still pass, is a token
committed, is there a licence, has anything rotted. It does not decide what the
code should do or whether the project is worth building, and it says so on the
page it writes.
"""

from .checks import FAIL, OK, WARN, Finding, Report, audit, audit_all
from .report import to_html, to_markdown, to_terminal

__version__ = "1.0.0"

__all__ = ["audit", "audit_all", "Finding", "Report", "OK", "WARN", "FAIL",
           "to_markdown", "to_terminal", "to_html", "__version__"]
