"""The evidence in `.github/rulesets/README.md` must still be true of this repository.

`tests/test_ruleset.py` holds the ruleset document itself: the owner's bypass is present
and is the only entry. This module holds the *prose around it*, which is what a person
actually follows when they decide whether to apply the profile, and which drifted badly
between 2026-08-15 and 2026-09-06:

* it said `main` carried "fourteen commits" when it carried sixty-six;
* it said "three merge commits" when there were twelve;
* it recommended `required_signatures` on the strength of a fourteen-commit reading that
  nothing had re-run.

The conclusions all survived re-measurement. The evidence for them did not, and evidence
that is not re-read is indistinguishable from evidence that is wrong.

Two things are gated here, chosen because neither can go stale on its own and neither
needs the network:

1. **The commit counts, pinned to a SHA.** Git history is immutable, so a count taken at
   a named commit is true forever. The document states the SHA it measured at; this reads
   that SHA back out of the prose and re-measures. New commits on `main` do not falsify
   it and do not jam the queue — a hand-maintained "commits on main" counter that every
   merge invalidates is a gate that stops the repository, and this is deliberately not
   that. What does fail it is somebody advancing the SHA without re-measuring, or editing
   a number without moving the SHA.

2. **The required status check contexts.** The document itself warns that "a required
   context that matches nothing is a gate that has silently gone away". Every context in
   `main.json` is derived here from the workflow files, so renaming a job breaks this test
   instead of silently emptying the profile on the day it is applied.

Fail-closed throughout, per ADR-0004: a missing document, an unparseable one, a SHA that
is not present in the checkout, or a prose sentence this module cannot find is a failure,
never a skip and never a default. A shallow clone that cannot see the pinned commit fails
here rather than passing vacuously; `.github/workflows/ci.yml` gives the `verify` job
`fetch-depth: 0` for exactly this reason, and losing that must break something.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
RULESET = ROOT / ".github" / "rulesets" / "main.json"
RULESET_DOC = ROOT / ".github" / "rulesets" / "README.md"
CI_WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"
CODEQL_WORKFLOW = ROOT / ".github" / "workflows" / "codeql.yml"

MEASURED_AT = re.compile(r"Re-measured (\d{4}-\d{2}-\d{2}) at\n`([0-9a-f]{7,40})`")
COMMIT_COUNT = re.compile(r"the tip of `main`: \*\*(\d+) commits\*\*")
MERGE_COUNT = re.compile(r"the \*\*(\d+)\*\* merge commits already on `main`")


def read_doc() -> str:
    """The ruleset prose, or a failure. Never an empty string a regex would then miss in."""
    if not RULESET_DOC.is_file():
        pytest.fail(f"{RULESET_DOC} is missing; its claims are what this module checks")
    text = RULESET_DOC.read_text(encoding="utf-8")
    if not text.strip():
        pytest.fail(f"{RULESET_DOC} is empty")
    return text


def one_match(pattern: re.Pattern[str], text: str, what: str) -> re.Match[str]:
    """Exactly one match, or a failure naming what could not be found.

    Zero matches means the sentence was reworded and this gate stopped watching it, which
    must be loud. Two means the claim is stated twice and the copies can disagree.
    """
    found = pattern.findall(text)
    if not found:
        pytest.fail(
            f"{RULESET_DOC} no longer states {what} in the form this gate reads "
            f"({pattern.pattern!r}). Re-word the gate with the prose, or the number "
            "stops being checked."
        )
    if len(found) > 1:
        pytest.fail(f"{RULESET_DOC} states {what} {len(found)} times: {found}")
    match = pattern.search(text)
    assert match is not None
    return match


def git(*args: str) -> str:
    result = subprocess.run(  # noqa: S603 -- fixed argv, no shell, no untrusted input
        ["git", "-C", str(ROOT), *args],  # noqa: S607 -- git is the thing being read
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        pytest.fail(
            f"`git {' '.join(args)}` failed in {ROOT}: {result.stderr.strip()}. "
            "If the pinned commit is missing, the checkout is shallow: "
            "`.github/workflows/ci.yml` must keep `fetch-depth: 0` on the verify job. "
            "A measurement that could not run is not a measurement that agreed."
        )
    return result.stdout.strip()


def pinned_sha() -> str:
    """The commit the document says it measured at, proven present in this checkout."""
    sha = one_match(MEASURED_AT, read_doc(), "the commit it measured at").group(2)
    kind = git("cat-file", "-t", sha)
    if kind != "commit":
        pytest.fail(f"{sha} is a {kind}, not a commit")
    return sha


def test_the_documents_commit_count_is_what_that_commit_carries() -> None:
    """Sixty-six, and it stays sixty-six because the SHA does not move on its own."""
    claimed = int(one_match(COMMIT_COUNT, read_doc(), "the commit count").group(1))
    actual = int(git("rev-list", "--count", pinned_sha()))
    assert claimed == actual, (
        f"{RULESET_DOC} claims {claimed} commits on `main` at the pinned commit; that "
        f"commit carries {actual}. Re-measure, or move the pin and re-measure."
    )


def test_the_documents_merge_commit_count_is_what_that_commit_carries() -> None:
    """The count `required_linear_history` is argued against."""
    claimed = int(one_match(MERGE_COUNT, read_doc(), "the merge commit count").group(1))
    actual = int(git("rev-list", "--count", "--merges", pinned_sha()))
    assert claimed == actual, (
        f"{RULESET_DOC} claims {claimed} merge commits on `main` at the pinned commit; "
        f"that commit carries {actual}."
    )


def test_the_measurement_date_is_not_older_than_the_pinned_commit() -> None:
    """A date earlier than the commit it claims to have read is a copied-forward date."""
    doc = read_doc()
    claimed_date = one_match(MEASURED_AT, doc, "the measurement date").group(1)
    commit_date = git("show", "-s", "--format=%cs", pinned_sha())
    assert claimed_date >= commit_date, (
        f"{RULESET_DOC} says it measured on {claimed_date} at a commit dated "
        f"{commit_date}, which cannot have happened."
    )


def workflow_job_ids(path: Path) -> set[str]:
    """Top-level job ids in a workflow, read as text rather than with a YAML parser.

    The repository's runtime has no YAML dependency and this gate is not worth adding one
    for: job ids are two-space-indented keys under `jobs:`, and the shape is stable.
    """
    if not path.is_file():
        pytest.fail(
            f"{path} is missing; the contexts this profile requires come from it"
        )
    text = path.read_text(encoding="utf-8")
    body = text.split("\njobs:\n", 1)
    if len(body) != 2:
        pytest.fail(f"{path} has no top-level `jobs:` block")
    return set(re.findall(r"^  ([A-Za-z0-9_-]+):$", body[1], re.M))


def workflow_job_names(path: Path) -> set[str]:
    """`name:` values on jobs, which are the contexts GitHub reports when present."""
    if not path.is_file():
        pytest.fail(f"{path} is missing")
    text = path.read_text(encoding="utf-8")
    return set(re.findall(r"^    name: (.+)$", text, re.M))


def required_contexts() -> list[str]:
    if not RULESET.is_file():
        pytest.fail(f"{RULESET} is missing")
    ruleset = json.loads(RULESET.read_text(encoding="utf-8"))
    for rule in ruleset.get("rules", []):
        if rule.get("type") == "required_status_checks":
            checks = rule["parameters"]["required_status_checks"]
            return [check["context"] for check in checks]
    pytest.fail(f"{RULESET} declares no required_status_checks rule")


def reportable_contexts() -> set[str]:
    """Every context the two pull-request workflows can report."""
    return (
        workflow_job_ids(CI_WORKFLOW)
        | workflow_job_names(CI_WORKFLOW)
        | workflow_job_names(CODEQL_WORKFLOW)
    )


def test_every_required_context_is_a_job_that_exists() -> None:
    """A required context matching no job is a deadlock on apply, and a silent hole before it."""
    available = reportable_contexts()
    missing = [c for c in required_contexts() if c not in available]
    assert not missing, (
        f"{RULESET} requires status checks no workflow reports: {missing}. Available: "
        f"{sorted(available)}. Applying this would deadlock every pull request; leaving "
        "it applied after a rename would quietly stop requiring the renamed job."
    )


def test_the_profile_requires_at_least_the_five_contexts_it_documents() -> None:
    """A positive control: the check above would also pass on an empty context list."""
    contexts = required_contexts()
    assert len(contexts) >= 5, (
        "the documented profile requires five contexts; this file requires "
        f"{len(contexts)}: {contexts}. A shorter list passes the matching test "
        "vacuously, which is why this one exists."
    )


@pytest.mark.parametrize(
    "context",
    [
        "verify",
        "secret-scan",
        "sast",
        "zizmor",
        "codeql (actions · python · javascript)",
    ],
)
def test_each_documented_context_is_still_required(context: str) -> None:
    """The five named in the README's table, held one by one so a drop names itself."""
    assert context in required_contexts(), (
        f"{context!r} is documented in {RULESET_DOC} as a required check and is not in "
        f"{RULESET}."
    )


def test_the_context_check_rejects_a_context_that_matches_nothing() -> None:
    """Negative control on the matcher itself, not on the committed file."""
    available = reportable_contexts()
    assert "a-job-that-does-not-exist" not in available


def test_the_document_does_not_read_local_signature_status_as_truth() -> None:
    """The trap that produced the wrong audit must stay written down.

    A local `git log --format='%G?'` reports `N` for this repository's SSH-signed commits
    when no allowed-signers file is configured. Reading that as "unsigned" is how an
    audit reported thirteen unsigned commits that do not exist. The document explains it;
    if that explanation is deleted the next reader repeats the mistake.
    """
    doc = read_doc()
    for fragment in ("%G?", "allowedSignersFile", "verification.verified"):
        assert fragment in doc, (
            f"{RULESET_DOC} no longer mentions {fragment!r}; the local-verification trap "
            "it records is how this repository's signature evidence was misread once."
        )
