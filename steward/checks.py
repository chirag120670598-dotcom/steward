"""Health checks for a repository, run offline.

Every check answers a question with a yes or a no, and a no always names the
file it is about. Nothing here guesses, and nothing here is a suggestion engine:
if a check cannot decide, it says so instead of picking an answer.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

OK, WARN, FAIL = "ok", "warn", "fail"

# Token shapes worth catching. This check exists because the person who wrote
# this tool pasted a personal access token into a chat twice.
SECRET_PATTERNS = (
    (re.compile(r"github_pat_[A-Za-z0-9_]{20,}"), "GitHub fine-grained PAT"),
    (re.compile(r"ghp_[A-Za-z0-9]{30,}"), "GitHub classic PAT"),
    (re.compile(r"gho_[A-Za-z0-9]{30,}"), "GitHub OAuth token"),
    (re.compile(r"sk-[A-Za-z0-9]{32,}"), "OpenAI-style key"),
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AWS access key id"),
    (re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----"), "private key"),
)

# File names that should never be tracked.
JUNK = (".DS_Store", "Thumbs.db", ".env", "id_rsa", "id_ed25519")


@dataclass
class Finding:
    repo: str
    check: str
    level: str
    message: str
    detail: str = ""

    def to_json(self) -> dict:
        return {"repo": self.repo, "check": self.check, "level": self.level,
                "message": self.message, "detail": self.detail}

    def line(self) -> str:
        mark = {OK: "  ok  ", WARN: " warn ", FAIL: " FAIL "}[self.level]
        return f"[{mark}] {self.repo:<22} {self.message}"


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)
    checked: list[str] = field(default_factory=list)
    when: str = ""

    def count(self, level: str) -> int:
        return sum(1 for f in self.findings if f.level == level)

    @property
    def worst(self) -> str:
        if self.count(FAIL):
            return FAIL
        return WARN if self.count(WARN) else OK

    def for_repo(self, repo: str) -> list[Finding]:
        return [f for f in self.findings if f.repo == repo]

    def to_json(self) -> dict:
        return {"when": self.when, "checked": self.checked,
                "findings": [f.to_json() for f in self.findings],
                "ok": self.count(OK), "warn": self.count(WARN), "fail": self.count(FAIL)}


def _git(repo: Path, *args: str, timeout: int = 20) -> str:
    try:
        out = subprocess.run(["git", "-C", str(repo), *args],
                             capture_output=True, text=True, timeout=timeout)
        return out.stdout if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def tracked_files(repo: Path) -> list[str]:
    listed = _git(repo, "ls-files")
    if listed:
        return [line for line in listed.splitlines() if line.strip()]
    return [str(p.relative_to(repo)) for p in repo.rglob("*")
            if p.is_file() and ".git" not in p.parts]


def _read(path: Path, limit: int = 200_000) -> str:
    try:
        if path.stat().st_size > limit:
            return ""
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


# -- individual checks -------------------------------------------------------


def check_readme(repo: Path, name: str) -> list[Finding]:
    for candidate in ("README.md", "README.rst", "readme.md", "README"):
        path = repo / candidate
        if path.exists():
            body = _read(path)
            if len(body) < 400:
                return [Finding(name, "readme", WARN,
                                f"{candidate} is only {len(body)} characters",
                                "A front page that short tells a stranger nothing.")]
            return [Finding(name, "readme", OK, f"{candidate} present ({len(body)} chars)")]
    return [Finding(name, "readme", FAIL, "no README", "Nobody can tell what this is.")]


def check_license(repo: Path, name: str) -> list[Finding]:
    for candidate in ("LICENSE", "LICENSE.md", "LICENCE", "COPYING"):
        if (repo / candidate).exists():
            return [Finding(name, "license", OK, f"{candidate} present")]
    return [Finding(name, "license", WARN, "no licence file",
                    "Without one, nobody may legally reuse the code.")]


def check_tests(repo: Path, name: str) -> list[Finding]:
    found = []
    for pattern in ("tests/test_*.py", "test_*.py", "tests/*.py"):
        found.extend(repo.glob(pattern))
    if not found:
        return [Finding(name, "tests", WARN, "no tests found",
                        "Nothing here proves the code still works after a change.")]
    return [Finding(name, "tests", OK, f"{len(found)} test file(s)")]


RUNNERS = (
    ("unittest", ["-m", "unittest", "discover", "-s", "tests"]),
    ("pytest", ["-m", "pytest", "-q", "tests"]),
)


def _classify(label: str, out: subprocess.CompletedProcess) -> tuple[str, str]:
    """ok / fail / unusable, plus a sentence explaining which.

    "unusable" is the important one. A module written for pytest cannot be
    imported by unittest, and unittest's complaint looks exactly like a broken
    repository. Calling that a failure is a confident claim about tests nobody
    ran, so it is classified separately and never allowed to outvote a runner
    that actually executed them.
    """
    blob = ((out.stdout or "") + (out.stderr or "")).strip()
    lines = blob.splitlines()

    if "No module named" in blob and ("pytest" in blob or "unittest" in blob):
        return "unusable", f"{label} is not installed here"
    if "NO TESTS RAN" in blob.upper() or out.returncode == 5:
        return "unusable", f"{label} found no tests to run"
    if "loader._FailedTest" in blob or "ModuleNotFoundError" in blob:
        return "unusable", f"{label} could not import the test modules"

    if out.returncode == 0:
        summary = next((ln for ln in reversed(lines) if ln.startswith("Ran ")), "")
        if not summary:
            summary = next((ln for ln in reversed(lines)
                            if " passed" in ln or "passed" in ln), "tests passed")
        return "ok", f"{label}: {summary.strip()[:100]}"

    first = next((ln for ln in lines
                  if ln.startswith(("FAIL:", "ERROR:", "E   "))
                  or " failed" in ln), lines[-1] if lines else "unknown")
    return "fail", f"{label}: {first.strip()[:110]}"


def run_tests(repo: Path, name: str, timeout: int = 600) -> list[Finding]:
    """Run the suite under every runner that can run it, and report the best.

    Both runners are always tried. The first version stopped at the first
    failure, so a pytest repository reported as broken by unittest never got
    the chance to be run correctly -- and the report was wrong in the direction
    that matters, since it accused working code.
    """
    if not (repo / "tests").is_dir():
        return []

    verdicts: list[tuple[str, str, str]] = []
    for label, args in RUNNERS:
        try:
            out = subprocess.run([sys.executable, *args], cwd=str(repo),
                                 capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            verdicts.append((label, "unusable", f"{label} did not finish in {timeout}s"))
            continue
        except OSError as exc:
            verdicts.append((label, "unusable", f"{label}: {exc}"))
            continue
        verdicts.append((label, *_classify(label, out)))

    passed = [v for v in verdicts if v[1] == "ok"]
    if passed:
        note = next((f"{v[0]}: {v[2]}" for v in verdicts
                     if v[1] == "unusable"), "")
        return [Finding(name, "tests-run", OK, passed[0][2], note)]

    failed = [v for v in verdicts if v[1] == "fail"]
    if failed:
        return [Finding(name, "tests-run", FAIL, failed[0][2],
                        "; ".join(v[2] for v in verdicts if v[1] == "unusable"))]

    return [Finding(name, "tests-run", WARN,
                    "tests exist but this tool could not run them",
                    "; ".join(v[2] for v in verdicts))]


def check_ci(repo: Path, name: str) -> list[Finding]:
    workflows = list((repo / ".github" / "workflows").glob("*.yml")) + \
                list((repo / ".github" / "workflows").glob("*.yaml"))
    if not workflows:
        return [Finding(name, "ci", WARN, "no CI workflow")]
    return [Finding(name, "ci", OK, f"{len(workflows)} workflow(s)")]


def check_junk(repo: Path, name: str) -> list[Finding]:
    tracked = set(tracked_files(repo))
    bad = [f for f in tracked
           if Path(f).name in JUNK
           or "__pycache__" in f or f.endswith((".pyc", ".pyo", ".log"))]
    if bad:
        return [Finding(name, "junk", FAIL, f"{len(bad)} junk file(s) tracked",
                        ", ".join(sorted(bad)[:6]))]
    return [Finding(name, "junk", OK, "no junk tracked")]


def check_secrets(repo: Path, name: str) -> list[Finding]:
    """The check that matters most, because a leaked token is the one mistake
    that cannot be undone by committing a fix."""
    hits = []
    for rel in tracked_files(repo):
        path = repo / rel
        if not path.is_file():
            continue
        body = _read(path)
        if not body:
            continue
        for pattern, label in SECRET_PATTERNS:
            for match in pattern.finditer(body):
                fragment = match.group(0)
                hits.append(f"{rel}: {label} ({fragment[:8]}…)")
    if hits:
        return [Finding(name, "secrets", FAIL, f"{len(hits)} possible secret(s) committed",
                        "; ".join(hits[:5]))]
    return [Finding(name, "secrets", OK, "no secret-shaped strings in tracked files")]


def check_size(repo: Path, name: str, limit: int = 2_000_000) -> list[Finding]:
    big = []
    for rel in tracked_files(repo):
        path = repo / rel
        try:
            if path.is_file() and path.stat().st_size > limit:
                big.append(f"{rel} ({path.stat().st_size // 1024} KB)")
        except OSError:
            continue
    if big:
        return [Finding(name, "size", WARN, f"{len(big)} tracked file(s) over 2 MB",
                        ", ".join(big[:5]))]
    return [Finding(name, "size", OK, "nothing oversized tracked")]


def check_freshness(repo: Path, name: str, days: int = 120) -> list[Finding]:
    stamp = _git(repo, "log", "-1", "--format=%ct").strip()
    if not stamp.isdigit():
        return [Finding(name, "fresh", WARN, "no commit history")]
    last = datetime.fromtimestamp(int(stamp), tz=timezone.utc).date()
    age = (date.today() - last).days
    if age > days:
        return [Finding(name, "fresh", WARN, f"last commit {age} days ago",
                        f"on {last.isoformat()}")]
    return [Finding(name, "fresh", OK, f"last commit {age} day(s) ago")]


ALL_CHECKS = (
    check_readme, check_license, check_tests, check_ci, check_junk,
    check_secrets, check_size, check_freshness,
)


def audit(repo: Path, run_test_suite: bool = True) -> list[Finding]:
    repo = Path(repo)
    name = repo.name
    findings: list[Finding] = []
    for check in ALL_CHECKS:
        findings.extend(check(repo, name))
    if run_test_suite:
        findings.extend(run_tests(repo, name))
    return findings


def audit_all(root: Path, run_test_suite: bool = True,
              only: list[str] | None = None) -> Report:
    root = Path(root)
    report = Report(when=datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC"))

    def is_repository(path: Path) -> bool:
        # A directory the process cannot even stat -- a systemd private dir, a
        # mount owned by another user -- is not a reason to abandon an audit of
        # everything else.
        try:
            return path.is_dir() and (path / ".git").exists()
        except OSError:
            return False

    candidates = sorted(p for p in root.iterdir() if is_repository(p))
    for repo in candidates:
        if only and repo.name not in only:
            continue
        report.checked.append(repo.name)
        report.findings.extend(audit(repo, run_test_suite))
    return report
