# steward

**A program that checks every repository it is pointed at, on a schedule, without anybody asking it to.**

No login, no dashboard, no "connect your account". It wakes up, looks, writes down what it found, and goes back to sleep. [The page](https://chirag120670598-dotcom.github.io/steward/) is written by it.

```
13 repositories · 103 checks · 0 failures · 1 warning
naam  [warn]
  ~ no CI workflow
```

---

## Why this exists

The fantasy is an AI that does everything by itself and needs no person at all.

That is not achievable, and the reason is structural rather than a matter of effort: **the intelligence is not in the code, it is in the weights** — and weights come from compute, data and teams that train models for a living. Any amount of Python written on a laptop produces a harness around somebody else's intelligence, not a new one. Anyone selling you the other thing is selling a search engine with a good voice.

What *is* achievable, today, is narrower and genuinely useful: **a program that does one whole job with nobody in the loop.** Not thinking. Checking.

That is steward. It is the honest version of "needs no human", and it runs unattended every day.

---

## What it decides alone

| Check | What it answers |
|---|---|
| `tests-run` | Do the tests still pass? It runs them. |
| `secrets` | Is a token or private key committed? |
| `readme` | Is there a front page, and does it say anything? |
| `license` | May anyone legally reuse this code? |
| `ci` | Is there a workflow at all? |
| `junk` | Is `__pycache__`, `.DS_Store` or a `.pyc` committed? |
| `size` | Is anything over 2 MB tracked? |
| `fresh` | Has it been touched in four months? |

## What needs a person, and always will

- Whether the code is any good.
- Whether the product is worth building.
- Anything that spends money, deploys, or deletes.
- What to do about a failure it reported.

The page it writes says this itself, in a box, on the front. A tool that lists its own ignorance is worth more than one that only lists yours.

---

## The two mistakes it refuses to make

Both were found by pointing it at real repositories and reading the output.

**1. "I could not run the tests" is not "the tests fail".** The first version ran `unittest` only. A repository that used `pytest` came back as `tests fail: NO TESTS RAN` — which is a confident claim about code nobody ran. Now it tries both runners, and if neither works it says *that*, as a warning, because the ignorance is the tool's and not the repository's.

**2. A report must not repeat the secret it found.** The token check shows the file and the first eight characters, never the whole string. A security report that leaks the thing it warned you about is a second leak.

**3. It cannot tell a fixture from a credential, so it does not pretend to.** Every secret scanner hits this: the test data and the real key are the same characters. Instead of a hidden allowlist in a config file, a line can carry a marker:

```python
FAKE_PAT = "github_pat_11ABC..."  # steward:allow-secret (not a credential)
```

The suppression lives in the diff, where a reviewer sees it, and it applies to that line only. This exact problem is how steward failed its own audit the first time it ran in CI — it accused its own tests of leaking a key.

---

## Use it

```bash
python3 -m steward --root ~/projects                 # every git repo under a directory
python3 -m steward --root ~/projects --fast          # skip running the test suites
python3 -m steward --root ~/projects --html site     # also write report.md and index.html
python3 -m steward --root . --strict                 # exit 1 on warnings too, for CI
```

Exit codes: `0` clean, `1` something failed, `2` the tool could not do its job.

No dependencies. Python 3.9 or newer. It shells out to `git` and to your test runner and nothing else — there is no network code in the package at all, which is a test that fails the build if it ever changes.

---

## Honest limits

- **It checks form, not substance.** A repository can pass every check here and still be full of wrong answers. Green means "nothing structural is broken", not "this works".
- **The secret patterns are a net, not a guarantee.** It catches GitHub tokens, OpenAI-style keys, AWS key ids and private key headers. A password written in a config file will sail straight past it.
- **Only Python test suites are run.** A JavaScript or Rust repository gets `tests exist` and no verdict, because guessing a runner and trusting its output would be worse than admitting the gap.
- **It reads the working tree, not history.** A token deleted in a later commit is still in the git history and still needs rotating — steward will not see it.
- **`git ls-files` is the source of truth** for what counts as committed. In a directory that is not a repository it falls back to walking the filesystem, which is a different question with a different answer.
- **It runs daily on GitHub Actions and writes a commit.** That is real autonomy, and it is bounded: the thing that writes the commit is a script with a `for` loop in it. Calling that an agent would be the same dishonesty as calling a spreadsheet an accountant.

---

## What this is in the longer argument

`connect4` has 17,121 repositories on GitHub. `sprout` made one of them improve itself and stopped honestly at its ceiling. steward is the other half of the same point: **the thing that genuinely needs no human is not the thing that thinks — it is the thing that checks.**

That is not the Ultron story. It is the one that works.

Apache-2.0.
