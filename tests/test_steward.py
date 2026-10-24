"""Tests for steward.

The dangerous failure here is not a crash. It is a check that says "fine" when
it means "I did not look", or one that says "broken" when it means "I do not
know how to look" -- both produce a confident report about a repository nobody
actually inspected.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from steward.checks import (FAIL, OK, WARN, audit, audit_all, check_junk,  # noqa: E402
                            check_license, check_readme, check_secrets, run_tests,
                            tracked_files)
from steward.report import to_html, to_markdown, to_terminal  # noqa: E402


def make_repo(files: dict[str, str], git: bool = True, commit: bool = True) -> Path:
    """A repository in a directory of its own, so audit_all can be pointed at
    its parent without wandering into the rest of the machine's /tmp."""
    root = Path(tempfile.mkdtemp()) / "repo"
    root.mkdir()
    for name, body in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    if git:
        subprocess.run(["git", "init", "-q"], cwd=root, check=False)
        subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=root, check=False)
        subprocess.run(["git", "config", "user.name", "t"], cwd=root, check=False)
        if commit:
            subprocess.run(["git", "add", "-A"], cwd=root, check=False)
            subprocess.run(["git", "commit", "-qm", "init"], cwd=root, check=False)
    return root


HEALTHY = {
    "README.md": "# A project\n\n" + ("This does a thing. " * 40),
    "LICENSE": "Apache License\n",
    ".github/workflows/ci.yml": "name: ci\non: push\njobs: {}\n",
    "tests/test_thing.py": (
        "import unittest\n"
        "class T(unittest.TestCase):\n"
        "    def test_it(self):\n"
        "        self.assertTrue(True)\n"
    ),
    "thing.py": "x = 1\n",
}

BROKEN_TEST = {
    "README.md": "# A project\n\n" + ("Words. " * 80),
    "LICENSE": "MIT\n",
    "tests/test_thing.py": (
        "import unittest\n"
        "class T(unittest.TestCase):\n"
        "    def test_it(self):\n"
        "        self.assertEqual(1, 2)\n"
    ),
}


class TestChecks(unittest.TestCase):

    def test_a_healthy_repository_is_quiet(self):
        repo = make_repo(HEALTHY)
        levels = {f.level for f in audit(repo, run_test_suite=False)}
        self.assertEqual(levels - {OK}, set(), [f.message for f in audit(repo, False)])

    def test_missing_readme_is_a_failure(self):
        repo = make_repo({"thing.py": "x = 1\n"})
        levels = {f.check: f.level for f in check_readme(repo, "x")}
        self.assertEqual(levels["readme"], FAIL)

    def test_a_stub_readme_is_only_a_warning(self):
        repo = make_repo({"README.md": "hi"})
        self.assertEqual(check_readme(repo, "x")[0].level, WARN)

    def test_missing_licence(self):
        repo = make_repo({"README.md": "# ok\n" + "x" * 500})
        self.assertEqual(check_license(repo, "x")[0].level, WARN)

    def test_a_committed_token_is_a_failure(self):
        """The one mistake a later commit cannot undo."""
        repo = make_repo({**HEALTHY, "notes.md": "token: github_pat_11ABCDEFG0123456789_abcdefghij"})
        finding = check_secrets(repo, "x")[0]
        self.assertEqual(finding.level, FAIL)
        self.assertIn("notes.md", finding.detail)

    def test_the_token_is_not_echoed_in_full(self):
        secret = "github_pat_11ABCDEFG0123456789_abcdefghij"
        repo = make_repo({**HEALTHY, "notes.md": secret})
        finding = check_secrets(repo, "x")[0]
        self.assertNotIn(secret, finding.detail, "the report must not leak what it found")
        self.assertNotIn(secret, to_markdown(audit_all(repo.parent, False)))

    def test_clean_files_raise_nothing(self):
        repo = make_repo(HEALTHY)
        self.assertEqual(check_secrets(repo, "x")[0].level, OK)

    def test_junk_is_caught(self):
        repo = make_repo({**HEALTHY, ".DS_Store": "junk", "thing.pyc": "x"})
        self.assertEqual(check_junk(repo, "x")[0].level, FAIL)

    def test_untracked_junk_is_left_alone(self):
        """Only what is actually committed matters; a local file is not a bug."""
        repo = make_repo(HEALTHY)
        (repo / ".DS_Store").write_text("untracked", encoding="utf-8")
        self.assertEqual(check_junk(repo, "x")[0].level, OK)

    def test_an_empty_directory_is_not_a_crash(self):
        repo = Path(tempfile.mkdtemp())
        findings = audit(repo, run_test_suite=False)
        self.assertTrue(findings)

    def test_tracked_files_falls_back_without_git(self):
        repo = make_repo({"a.py": "x"}, git=False)
        self.assertIn("a.py", tracked_files(repo))


class TestRunningTests(unittest.TestCase):

    def test_a_passing_suite_says_ok(self):
        repo = make_repo(HEALTHY)
        finding = run_tests(repo, "x")[0]
        self.assertEqual(finding.level, OK, finding.message)
        self.assertIn("Ran 1", finding.message)

    def test_a_failing_suite_says_fail(self):
        repo = make_repo(BROKEN_TEST)
        finding = run_tests(repo, "x")[0]
        self.assertEqual(finding.level, FAIL, finding.message)

    def test_no_tests_directory_is_not_a_verdict(self):
        repo = make_repo({"README.md": "x" * 500})
        self.assertEqual(run_tests(repo, "x"), [])

    def test_i_could_not_run_them_is_a_warning_not_a_failure(self):
        """If the runner is missing the repository is innocent, and saying
        otherwise would be a confident claim about code nobody ran."""
        repo = Path(tempfile.mkdtemp())
        (repo / "tests").mkdir()
        (repo / "tests" / "test_x.py").write_text(
            "import pytest\n\ndef test_a():\n    assert True\n", encoding="utf-8")
        finding = run_tests(repo, "x", timeout=30)[0]
        self.assertIn(finding.level, (OK, WARN))
        if finding.level == WARN:
            self.assertIn("could not run", finding.message)


class TestReport(unittest.TestCase):

    def setUp(self):
        self.repo = make_repo({"thing.py": "x = 1\n"})
        self.report = audit_all(self.repo.parent, run_test_suite=False)

    def test_every_repository_appears_once_in_the_terminal(self):
        text = to_terminal(self.report)
        self.assertIn("repo", text)
        self.assertEqual(text.count("repo  ["), 1)

    def test_markdown_counts_match_the_findings(self):
        markdown = to_markdown(self.report)
        self.assertIn(f"{self.report.count(OK)} ok", markdown)
        self.assertIn(f"{self.report.count(FAIL)} failures", markdown)

    def test_html_is_self_contained(self):
        """The page must survive being opened with no network at all."""
        page = to_html(self.report, css="body{color:red}")
        self.assertIn("<style>body{color:red}</style>", page)
        for needle in ("http://", "https://", "<script"):
            self.assertNotIn(needle, page, f"the page reaches outside itself: {needle}")
        self.assertIn("repo", page)

    def test_the_page_states_what_it_cannot_decide(self):
        page = to_html(self.report, css="")
        self.assertIn("Needs a person", page)
        self.assertIn("whether the code is any good", page)


class TestCli(unittest.TestCase):

    def run_cli(self, *argv):
        import io
        from contextlib import redirect_stderr, redirect_stdout

        from steward.cli import main

        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_clean_run_exits_zero(self):
        repo = make_repo(HEALTHY)
        code, out, _ = self.run_cli("--root", str(repo.parent), "--fast")
        self.assertEqual(code, 0, out)
        self.assertIn("repo", out)

    def test_a_failure_exits_one(self):
        repo = make_repo({"thing.py": "x"})
        code, _, _ = self.run_cli("--root", str(repo.parent), "--fast")
        self.assertEqual(code, 1)

    def test_json_and_html_are_written(self):
        repo = make_repo(HEALTHY)
        outdir = Path(tempfile.mkdtemp())
        code, _, _ = self.run_cli("--root", str(repo.parent), "--fast",
                                  "--json", str(outdir / "r.json"),
                                  "--html", str(outdir))
        self.assertEqual(code, 0)
        payload = json.loads((outdir / "r.json").read_text())
        self.assertEqual(payload["checked"], ["repo"])
        self.assertTrue((outdir / "index.html").exists())
        self.assertTrue((outdir / "report.md").exists())

    def test_a_missing_root_is_refused_clearly(self):
        code, _, err = self.run_cli("--root", "/nowhere/at/all")
        self.assertEqual(code, 2)
        self.assertIn("not a directory", err)

    def test_no_repositories_is_not_a_silent_success(self):
        empty = Path(tempfile.mkdtemp())
        code, _, err = self.run_cli("--root", str(empty))
        self.assertEqual(code, 2)
        self.assertIn("no git repositories", err)


if __name__ == "__main__":
    unittest.main()
