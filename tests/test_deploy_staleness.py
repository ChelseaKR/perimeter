"""The detector that answers "is the live site the site this repository has?".

Written from both directions, because the failure it replaces was a green gate. A detector
that cannot fire is noise and gets deleted; a detector that reports a number it did not
really measure is worse than none, because the number reads as a measurement and nobody
re-derives it.

So the cases below cover the drift it must report AND every way the comparison can be
meaningless -- no deployment at all, a deployment that never succeeded, a commit this clone
does not contain, a history that has diverged, a published directory that is not there.
Each of those must end in a refusal. None of them may end in a comfortable zero.

The two sharpest cases are the ones that are specific to this repository's publishing
model. `pages.yml` uploads the committed `site/` directory as-is, so:

* `test_a_commit_that_changes_nothing_published_is_not_drift` holds the line the portfolio
  sweep got wrong once already. Comparing deployed SHA against `main` head here would
  report drift on every dependabot bump, because `site/` only moves on a data refresh.
* `test_the_compared_directory_is_the_one_the_publisher_uploads` keeps the constant honest
  against `pages.yml`. If the publisher's `path:` moves and this does not, the sentinel
  goes on comparing a directory nobody serves and reports a reassuring zero about the
  wrong tree.
"""

from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS = REPO_ROOT / "tools"
PAGES_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "pages.yml"


def _tool(name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, TOOLS / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # Registered before execution, not after: `@dataclass` resolves annotations through
    # `sys.modules[cls.__module__]`, so a module that is not there yet raises on the
    # decorator rather than on anything to do with this repository.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


staleness = _tool("deploy_staleness")

NOW = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)
SEPTEMBER = "2026-09-13T16:48:09Z"


def _deployment(**over: Any) -> dict[str, Any]:
    row = {
        "id": 6423957323,
        "sha": "c" * 40,
        "environment": "github-pages",
        "created_at": SEPTEMBER,
    }
    row.update(over)
    return row


def _succeeded(_id: Any) -> Sequence[Mapping[str, Any]]:
    return [{"state": "success"}, {"state": "in_progress"}]


def _never_succeeded(_id: Any) -> Sequence[Mapping[str, Any]]:
    return [{"state": "failure"}, {"state": "in_progress"}]


# --- what the deployment record is allowed to mean ---------------------------


def test_the_newest_successful_deployment_is_the_live_build() -> None:
    record = staleness.newest_successful_deployment([_deployment()], _succeeded)
    assert record.sha == "c" * 40
    assert record.created_at.date().isoformat() == "2026-09-13"
    assert record.deployment_id == 6423957323


def test_the_newest_deployment_wins_over_an_older_one() -> None:
    older = _deployment(id=2, sha="d" * 40, created_at="2026-08-08T06:45:01Z")
    record = staleness.newest_successful_deployment([_deployment(), older], _succeeded)
    assert record.sha == "c" * 40


def test_a_canceled_publish_creates_no_deployment_and_moves_nothing() -> None:
    """The trap this file exists for, in this repository's own numbers.

    Thirteen of `publish-site`'s runs on `main` finished `cancelled` -- the `pages`
    concurrency group holds one pending run, so a second push evicts the first. A sentinel
    built on run history would read those as publishes. They create no deployment, so the
    record still names the last commit whose bytes actually went out, and the answer stays
    that commit rather than "published an hour ago". Asserting the absence directly,
    because the bug would be a silent extra row, not an exception.
    """
    canceled_runs_create_no_deployments: list[Mapping[str, Any]] = [_deployment()]
    record = staleness.newest_successful_deployment(
        canceled_runs_create_no_deployments, _succeeded
    )
    assert record.sha == "c" * 40


def test_no_deployment_at_all_is_a_refusal_not_a_zero() -> None:
    with pytest.raises(staleness.StalenessUnknown, match="no github-pages deployment"):
        staleness.newest_successful_deployment([], _succeeded)


def test_a_deployment_that_never_succeeded_is_a_refusal() -> None:
    with pytest.raises(staleness.StalenessUnknown, match="successful status"):
        staleness.newest_successful_deployment([_deployment()], _never_succeeded)


def test_a_deployment_still_in_progress_is_not_a_publish() -> None:
    """`queued` and `in_progress` are requests, not bytes. The deploy job on this

    repository sits in the `github-pages` environment, so a row appears the moment the
    job starts; crediting its commit before the status says `success` reports the site as
    fresher than it is, which is the one direction of error that matters here.
    """

    def pending(_id: Any) -> Sequence[Mapping[str, Any]]:
        return [{"state": "in_progress"}, {"state": "queued"}, {"state": "waiting"}]

    with pytest.raises(staleness.StalenessUnknown, match="successful status"):
        staleness.newest_successful_deployment([_deployment()], pending)


def test_a_failed_newer_deployment_does_not_hide_the_successful_older_one() -> None:
    """A failed republish leaves the previous build serving; that is the live one."""
    older = _deployment(id=9, sha="e" * 40, created_at="2026-09-01T00:00:00Z")

    def statuses(deployment_id: Any) -> Sequence[Mapping[str, Any]]:
        return (
            [{"state": "failure"}]
            if deployment_id == 6423957323
            else [{"state": "success"}]
        )

    record = staleness.newest_successful_deployment([_deployment(), older], statuses)
    assert record.sha == "e" * 40


def test_a_row_without_a_commit_id_is_not_a_deployment() -> None:
    with pytest.raises(staleness.StalenessUnknown, match="no github-pages deployment"):
        staleness.newest_successful_deployment(
            [_deployment(sha="not-a-sha")], _succeeded
        )


# --- which directory is the published one ------------------------------------


def uploaded_path(text: str) -> str | None:
    """The `path:` the publisher hands to actions/upload-pages-artifact."""
    match = re.search(r"upload-pages-artifact@[^\n]*\n\s*with:\n\s*path:\s*(\S+)", text)
    return match.group(1).strip("\"'") if match else None


def test_the_compared_directory_is_the_one_the_publisher_uploads() -> None:
    """The constant and the workflow have to agree, or the measurement is of nothing.

    `pages.yml` does not render the site -- `site/` is built from CAL FIRE's files, which
    are never in git and never in CI -- so what it uploads is a committed directory,
    verbatim. That directory is the whole of what a visitor receives. If the `path:` moves
    and `PUBLISHED_PATH` does not, this module goes on diffing a tree nobody serves and
    every answer it gives is about the wrong thing.
    """
    declared = uploaded_path(PAGES_WORKFLOW.read_text(encoding="utf-8"))
    assert declared is not None, (
        f"{PAGES_WORKFLOW} no longer hands a `path:` to actions/upload-pages-artifact; "
        "this sentinel cannot know what is being published"
    )
    assert declared == staleness.PUBLISHED_PATH, (
        f"pages.yml publishes {declared!r} and deploy_staleness.py compares "
        f"{staleness.PUBLISHED_PATH!r}"
    )


def test_the_path_reader_reports_nothing_rather_than_guessing() -> None:
    """A positive control: the test above would pass vacuously on a reader that

    always returned "site". This one holds the reader to finding it in the text.
    """
    assert uploaded_path("jobs:\n  build:\n    steps:\n      - run: echo hi\n") is None


# --- the comparison against main, and every way it can be meaningless --------


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "clone"
    root.mkdir()

    def git(*args: str) -> None:
        subprocess.run(  # noqa: S603 -- fixed argv, no shell, no untrusted input
            ["git", "-C", str(root), *args],  # noqa: S607 -- git is the thing being read
            check=True,
            capture_output=True,
        )

    git("init", "-b", "main")
    git("config", "user.email", "sentinel@example.test")
    git("config", "user.name", "sentinel")
    # Local to this throwaway repository, which exists for the length of one test. The
    # portfolio's global `commit.gpgsign = true` would otherwise make every fixture commit
    # reach for a signing key that has nothing to do with what is being measured here.
    git("config", "commit.gpgsign", "false")
    return root


def _commit(
    root: Path, path: str, body: str = "x", when: datetime | None = None
) -> str:
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    stamp = (when or NOW).isoformat()
    env = {"GIT_AUTHOR_DATE": stamp, "GIT_COMMITTER_DATE": stamp}
    subprocess.run(  # noqa: S603 -- fixed argv, no shell, no untrusted input
        ["git", "-C", str(root), "add", path],  # noqa: S607 -- git is the thing being read
        check=True,
        capture_output=True,
    )
    subprocess.run(  # noqa: S603 -- fixed argv, no shell, no untrusted input
        ["git", "-C", str(root), "commit", "-m", f"touch {path}"],  # noqa: S607
        check=True,
        capture_output=True,
        env={**os.environ, **env},
    )
    return subprocess.run(  # noqa: S603 -- fixed argv, no shell, no untrusted input
        ["git", "-C", str(root), "rev-parse", "HEAD"],  # noqa: S607
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


@pytest.fixture
def clone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = _repo(tmp_path)
    monkeypatch.setattr(staleness, "REPO_ROOT", root)
    return root


def _record(sha: str, created_at: datetime) -> Any:
    return staleness.DeployRecord(deployment_id=1, sha=sha, created_at=created_at)


def test_a_commit_that_changes_nothing_published_is_not_drift(clone: Path) -> None:
    """Deployed SHA against head is the wrong comparison on this repository.

    Four commits behind and forty days old, and the visitor still holds exactly the bytes
    `main` holds, because none of those commits touched `site/`. A SHA comparison calls
    this stale; a tree comparison calls it what it is.
    """
    deployed = _commit(clone, "site/index.html", "published", NOW - timedelta(days=40))
    _commit(clone, "README.md")
    _commit(clone, "tests/test_x.py")
    _commit(clone, "src/perimeter/render.py")
    _commit(clone, "uv.lock")

    drift = staleness.measure(_record(deployed, NOW - timedelta(days=40)), "HEAD", NOW)

    assert drift.commits == 4
    assert drift.deployed.sha != drift.head
    assert drift.published_tree == drift.head_tree
    assert drift.serving_current_bytes
    assert drift.unpublished_commits == 0
    assert not drift.overdue
    assert "Up to date" in staleness.render(drift)


def test_a_change_to_the_published_directory_is_drift(clone: Path) -> None:
    deployed = _commit(clone, "site/index.html", "published", NOW - timedelta(days=40))
    _commit(clone, "README.md", "x", NOW - timedelta(days=39))
    _commit(clone, "site/index.html", "rebuilt", NOW - timedelta(days=30))
    _commit(clone, "site/data/dins-coverage.json", "{}", NOW - timedelta(days=29))

    drift = staleness.measure(_record(deployed, NOW - timedelta(days=40)), "HEAD", NOW)

    assert drift.commits == 3
    assert drift.unpublished_commits == 2
    assert not drift.serving_current_bytes
    assert drift.waiting_days == 30
    assert drift.overdue


def test_age_alone_is_not_overdue(clone: Path) -> None:
    """A site nobody has republished because nothing it publishes changed is correct,

    not stale. Reporting on the age of the deploy would make this sentinel fire on every
    repository that is simply finished, and a sentinel that always fires is one nobody
    reads.
    """
    deployed = _commit(clone, "site/index.html", "published", NOW - timedelta(days=200))
    _commit(clone, "src/perimeter/render.py")

    drift = staleness.measure(_record(deployed, NOW - timedelta(days=200)), "HEAD", NOW)

    assert drift.deploy_age_days == 200
    assert drift.commits == 1
    assert drift.unpublished_commits == 0
    assert drift.serving_current_bytes
    assert not drift.overdue


def test_the_clock_starts_at_the_change_not_at_the_deploy(clone: Path) -> None:
    """An old deploy plus a change made yesterday is one day of waiting, not two hundred.

    Measuring from the deployment date would report a fresh, unremarkable data refresh as
    six months overdue the moment it landed.
    """
    deployed = _commit(clone, "site/index.html", "published", NOW - timedelta(days=200))
    _commit(clone, "site/index.html", "rebuilt", NOW - timedelta(days=1))

    drift = staleness.measure(_record(deployed, NOW - timedelta(days=200)), "HEAD", NOW)

    assert drift.deploy_age_days == 200
    assert drift.waiting_days == 1
    assert not drift.serving_current_bytes
    assert not drift.overdue
    assert "Waiting" in staleness.render(drift)


def test_a_change_and_its_revert_leave_the_visitor_correct(clone: Path) -> None:
    """The case a commit count cannot survive.

    Two commits touched `site/` and the served tree is still the right one, because the
    second undid the first. Counting commits reports drift that nobody can see; comparing
    tree ids reports the truth.
    """
    deployed = _commit(clone, "site/index.html", "published", NOW - timedelta(days=90))
    _commit(clone, "site/index.html", "wrong", NOW - timedelta(days=89))
    _commit(clone, "site/index.html", "published", NOW - timedelta(days=88))

    drift = staleness.measure(_record(deployed, NOW - timedelta(days=90)), "HEAD", NOW)

    assert drift.unpublished_commits == 2
    assert drift.serving_current_bytes
    assert not drift.overdue


def test_nothing_since_the_deploy_is_up_to_date(clone: Path) -> None:
    deployed = _commit(clone, "site/index.html", "published", NOW - timedelta(days=1))

    drift = staleness.measure(_record(deployed, NOW - timedelta(days=1)), "HEAD", NOW)

    assert drift.commits == 0
    assert drift.unpublished_commits == 0
    assert drift.serving_current_bytes
    assert not drift.overdue


def test_a_commit_this_clone_does_not_have_is_a_refusal(clone: Path) -> None:
    """The shallow-checkout case, which is the one that reports zero silently.

    On a shallow clone the deployed commit is simply absent, every comparison against it
    comes back empty, and the site reads as current. This is why the sentinel workflow
    checks out with `fetch-depth: 0`, and why the refusal exists rather than trusting that
    it did.
    """
    _commit(clone, "site/index.html")

    with pytest.raises(staleness.StalenessUnknown, match="not in this clone"):
        staleness.measure(_record("a" * 40, NOW - timedelta(days=63)), "HEAD", NOW)


def test_a_diverged_history_is_a_refusal(clone: Path) -> None:
    _commit(clone, "site/index.html")
    subprocess.run(  # noqa: S603 -- fixed argv, no shell, no untrusted input
        ["git", "-C", str(clone), "checkout", "-b", "other"],  # noqa: S607
        check=True,
        capture_output=True,
    )
    orphan = _commit(clone, "orphan.txt")
    subprocess.run(  # noqa: S603 -- fixed argv, no shell, no untrusted input
        ["git", "-C", str(clone), "checkout", "main"],  # noqa: S607
        check=True,
        capture_output=True,
    )

    with pytest.raises(staleness.StalenessUnknown, match="not an ancestor"):
        staleness.measure(_record(orphan, NOW - timedelta(days=63)), "HEAD", NOW)


def test_a_malformed_deployed_sha_is_a_refusal(clone: Path) -> None:
    _commit(clone, "site/index.html")

    with pytest.raises(staleness.StalenessUnknown, match="not a commit id"):
        staleness.measure(_record("nope", NOW), "HEAD", NOW)


def test_a_missing_published_directory_is_a_refusal(clone: Path) -> None:
    """No `site/` means the publisher's `path:` and this comparison have parted company.

    A tree that is not there is not a tree that matches.
    """
    deployed = _commit(clone, "README.md")
    _commit(clone, "src/perimeter/render.py")

    with pytest.raises(staleness.StalenessUnknown, match="does not exist at"):
        staleness.measure(_record(deployed, NOW - timedelta(days=5)), "HEAD", NOW)


def test_two_readings_that_contradict_each_other_are_a_refusal(
    clone: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Differing trees with no commit that touched them cannot both be true.

    Reachable only if the path-limited log and the tree ids disagree, which should be
    impossible -- and is exactly the shape a silent measurement bug takes. Refusing beats
    picking whichever of the two readings is more comfortable.
    """
    deployed = _commit(clone, "site/index.html", "published", NOW - timedelta(days=5))
    _commit(clone, "site/index.html", "rebuilt", NOW - timedelta(days=4))
    monkeypatch.setattr(staleness, "commits_touching_published", lambda *_: [])

    with pytest.raises(staleness.StalenessUnknown, match="contradict"):
        staleness.measure(_record(deployed, NOW - timedelta(days=5)), "HEAD", NOW)


# --- the report, and the exit code -------------------------------------------


def test_the_report_states_the_measurement_before_its_verdict(clone: Path) -> None:
    deployed = _commit(clone, "site/index.html", "published", NOW - timedelta(days=60))
    _commit(clone, "site/index.html", "rebuilt", NOW - timedelta(days=59))
    drift = staleness.measure(_record(deployed, NOW - timedelta(days=60)), "HEAD", NOW)

    report = staleness.render(drift)

    assert deployed[:9] in report
    assert "59 days" in report
    assert "OVERDUE" in report
    assert report.index("Since the deploy") < report.index("OVERDUE")


def test_the_json_carries_every_number_the_report_states(clone: Path) -> None:
    deployed = _commit(clone, "site/index.html", "published", NOW - timedelta(days=60))
    _commit(clone, "site/data/dins-coverage.json", "{}", NOW - timedelta(days=59))
    drift = staleness.measure(_record(deployed, NOW - timedelta(days=60)), "HEAD", NOW)

    payload = staleness.as_json(drift)

    assert payload["deployed_sha"] == deployed
    assert payload["published_path"] == "site"
    assert payload["published_tree"] != payload["head_tree"]
    assert payload["serving_current_bytes"] is False
    assert payload["waiting_days"] == 59
    assert payload["unpublished_commits"] == 1
    assert payload["overdue"] is True


def test_the_cli_refuses_with_a_nonzero_exit_when_it_cannot_measure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Exit 2, not 0 with a reassuring report. The sentinel workflow turns a measurement

    into an issue and a refusal into a red run, so this exit code is the whole difference
    between "the site is fine" and "nobody can tell".
    """
    payload = tmp_path / "deployments.json"
    payload.write_text('{"deployments": [], "statuses": {}}', encoding="utf-8")

    code = staleness.main(["--deployments-json", str(payload)])

    assert code == 2
    assert "cannot measure" in capsys.readouterr().err


def test_the_cli_reports_and_exits_zero_when_it_can_measure(
    clone: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    deployed = _commit(clone, "site/index.html", "published", NOW - timedelta(days=2))
    payload = tmp_path / "deployments.json"
    payload.write_text(
        json.dumps(
            {
                "deployments": [
                    {
                        "id": 7,
                        "sha": deployed,
                        "environment": "github-pages",
                        "created_at": "2026-09-11T00:00:00Z",
                    }
                ],
                "statuses": {"7": [{"state": "success"}]},
            }
        ),
        encoding="utf-8",
    )

    code = staleness.main(
        ["--deployments-json", str(payload), "--head", "HEAD", "--json"]
    )

    assert code == 0
    assert '"serving_current_bytes": true' in capsys.readouterr().out
