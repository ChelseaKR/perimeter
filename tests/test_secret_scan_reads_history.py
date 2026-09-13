"""The `secret-scan` job must read every commit, not the commit it was handed.

Until 2026-09-13 this job was `gitleaks/gitleaks-action`, which chooses its scan range
from the triggering event rather than scanning the repository:

    push, N commits   gitleaks detect --log-opts=--no-merges --first-parent BASE^..HEAD
    push, 1 commit    gitleaks detect --log-opts=-1          <- exactly one commit
    pull_request      the pull request's own commits
    schedule
    workflow_dispatch no --log-opts at all, i.e. the whole history

`ci.yml` triggers on `push` and `pull_request` and nothing else, so the two events for
which that action reads history never fired here. Every merge into `main` is a squash
merge, which is a one-commit push, so the check named `secret-scan` read 1 of `main`'s
81 commits and reported success. A credential added in one commit and deleted in the
next was invisible to it.

`fetch-depth: 0` did not prevent that and cannot: it decides how much history
`actions/checkout` puts on disk, not how much of it the scanner is asked to read. A
checkout deep enough to scan and an invocation that declines to is precisely the state
this job was in, which is why the assertions below are about the *invocation*. The
`fetch-depth: 0` assertion is kept, and is scoped to this job, as the necessary
precondition it actually is.

`secret-scan` is one of the five contexts `.github/rulesets/main.json` would require,
and the profile is not applied (`main` carries no ruleset and no branch protection), so
this job blocks nothing today. It is still the only secret scan this repository has, and
per ADR-0004 a gate that cannot fail is worse than no gate, because it is read as one
that passed.

Measured on a throwaway clone of this repository: a random, real-shaped AWS key planted
in one commit and removed in the next left `gitleaks git . --log-opts=-1` exiting 0 and
`gitleaks git .` exiting 1, over a tree byte-identical to the baseline afterwards.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

CI = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"

# Four conformance checks elsewhere in this portfolio passed because they matched a tool
# name that appeared only inside a COMMENT. The comment above this job names both the
# action that was removed and the flag that must not return, so everything below reads
# the workflow with its comments stripped and cannot be satisfied by prose.
_COMMENT = re.compile(r"(?m)^\s*#.*$|\s+#.*$")

# A job header: exactly two spaces of indent, a name, a colon, end of line. Matched
# only inside the `jobs:` mapping, so the two-space keys under `on:` are not jobs here.
_JOB = re.compile(r"(?m)^  ([A-Za-z0-9_-]+):$")
_JOBS_KEY = re.compile(r"(?m)^jobs:$")


def ci_code() -> str:
    """`ci.yml` with comments removed, or a failure. Never an empty string."""
    if not CI.is_file():
        pytest.fail(f"{CI} is missing; the secret scan cannot be checked")
    text = _COMMENT.sub("", CI.read_text(encoding="utf-8"))
    if not text.strip():
        pytest.fail(f"{CI} holds nothing but comments")
    return text


def job(name: str) -> str:
    """The body of one job, so a `fetch-depth: 0` in another job cannot stand in for it.

    Fails rather than returning "" when the job is absent: an empty haystack satisfies
    every `not in` assertion below, which is the vacuous pass this module exists to
    prevent.
    """
    jobs_key = _JOBS_KEY.search(ci_code())
    if jobs_key is None:
        pytest.fail(f"{CI} has no top-level `jobs:` mapping")
    code = ci_code()[jobs_key.end() :]
    starts = {m.group(1): m.span() for m in _JOB.finditer(code)}
    if name not in starts:
        pytest.fail(
            f"{CI} defines no job {name!r}. Its jobs are {sorted(starts)}. "
            f"{name!r} is a required status-check context in "
            ".github/rulesets/main.json; renaming it empties that requirement."
        )
    begin = starts[name][1]
    later = [start for start, _ in starts.values() if start > begin]
    return code[begin : min(later)] if later else code[begin:]


def test_the_scanner_is_not_handed_a_range() -> None:
    assert "gitleaks git . --no-banner --redact --exit-code 1" in job("secret-scan"), (
        "the secret scan no longer runs `gitleaks git .`. Whatever replaces it must "
        "still walk every commit reachable from HEAD, on every event, rather than a "
        "range chosen from the event that triggered the run."
    )
    assert "--log-opts" not in ci_code(), (
        "`--log-opts` scopes gitleaks to a commit range. A range taken from the "
        "triggering event is how this check came to read 1 of 81 commits and pass."
    )


def test_the_event_driven_action_does_not_come_back() -> None:
    assert "gitleaks/gitleaks-action" not in ci_code(), (
        "gitleaks/gitleaks-action picks its range from the event and degrades to "
        "`--log-opts=-1` on a single-commit push, which is every squash merge here. "
        "It reads the full history only on `schedule` and `workflow_dispatch`, and "
        "this workflow fires on neither."
    )


def test_the_scan_checkout_still_fetches_the_history_it_walks() -> None:
    """Necessary, not sufficient: without it there is nothing on disk to walk.

    This says nothing about whether the scan reads that history. The assertion that
    does is `test_the_scanner_is_not_handed_a_range`.
    """
    assert re.search(r"^\s*fetch-depth:\s*0\s*$", job("secret-scan"), flags=re.M), (
        "`fetch-depth: 0` is gone from the secret-scan checkout, so `gitleaks git .` "
        "would walk only the single commit actions/checkout fetched, and would pass "
        "for the same reason the action it replaced did."
    )


def test_the_pinned_binary_is_checksum_verified() -> None:
    block = job("secret-scan")
    assert (
        "gitleaks_checksums.txt" in block and "sha256sum --check --strict" in block
    ), (
        "the gitleaks binary is fetched over the network without checking it against "
        "the checksums published with the release it is pinned to"
    )


def test_the_job_slicer_reads_one_job() -> None:
    """Positive control: every assertion above would pass on the whole file too."""
    block = job("secret-scan")
    assert "make verify" not in block, (
        "the job slicer is returning more than the secret-scan job, so a "
        "`fetch-depth: 0` belonging to `verify` would satisfy the assertion above"
    )
    assert "make verify" in job("verify"), "the job slicer returns nothing usable"
