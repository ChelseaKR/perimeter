#!/usr/bin/env python3
"""Is the site served at chelseakr.github.io/perimeter the site this repository has?

Nothing in this repository has ever asked. `ci.yml` runs `make verify` over the working
tree, `codeql.yml` reads the source, `pages.yml` publishes -- and not one of them looks at
what a visitor actually receives. Unlike its siblings (`cairn`, `chalkline`, `plumbline`,
`disclosed`, `gauntlet`, `sprout`, `nearmiss`, `homeroom`, `id-churn-sentinel`,
`tods-validate`) this repository carries no `live-integrity.yml` either, so the published
site has no reader of any kind.

The trigger is not the problem, and this file does not change it. `pages.yml` fires on
every push to `main` with no path filter, which is correct. What is missing is anything
that notices when a firing did not land. Measured on 2026-09-13 over the 75 commits on
`main` since `pages.yml` was added on 2026-08-07: 23 of them produced no `github-pages`
deployment at all. Thirteen had their `publish-site` run **cancelled** -- the `pages`
concurrency group holds one pending run, so a second push while a publish is in flight
evicts the first -- and ten arrived inside a push whose tip was another commit and so
never got a run. Two of the 23, `4385957b9` and `edbfb9bd7` (both 2026-08-29), changed
files under `site/`: they changed the bytes a visitor receives and were never published.
Every gate was green throughout, because a cancelled run is not a failed one, and because
none of these gates was asking.

This module is the reader. It publishes nothing and holds no credential that could.

Which publishing model this assumes, and why it is not the obvious one
---------------------------------------------------------------------
`gh api repos/ChelseaKR/perimeter/pages` reports `build_type: workflow`, which invites the
comparison "deployed commit versus `main`". That comparison would be wrong here, and
loudly wrong.

`pages.yml` does not render the site. It cannot: `site/` is built from CAL FIRE's acquired
files, which are never in git and never in CI, so the workflow's own header says it has no
way to regenerate them. Its build job checks the committed bytes -- a determinism run from
fixtures, `tests/test_published_site.py` over `site/`, then `html-validate` and axe-core
over `site/` itself -- and then hands `actions/upload-pages-artifact` exactly one thing:

    - uses: actions/upload-pages-artifact@...
      with:
        path: site

So this is a **committed-tree publisher**: the repository commits the built site and the
workflow uploads that directory as-is. The visitor-visible path set is therefore not "the
renderer and its inputs" -- it is the published directory itself, `site/`, and nothing
else. Deriving it the other way round gives the same answer:

* `src/perimeter/render.py`, `artifacts.py`, `coverage.py` and the field registry produce
  `site/`, but a change to any of them alters no published byte until somebody runs
  `make site` against `data/raw/` and commits the result. `make site-check` exists
  precisely because that gap is real and only a machine holding CAL FIRE's files can close
  it. Counting a renderer commit as visitor-visible would report drift that no visitor can
  see.
* `.github/workflows/pages.yml` decides *whether* the upload happens, not *what* is in it.
  A change there that broke publishing shows up as a missing or unsuccessful deployment,
  which this module already refuses on rather than reporting as zero.
* `tests/`, `docs/`, `README.md`, `fixtures/`, the lockfiles and every dependabot bump
  change `main` constantly and change nothing a visitor receives. On this repository they
  are the overwhelming majority of commits: comparing deployed SHA against `main` head
  would have cried wolf on 21 of those 23 undeployed commits while saying nothing useful
  about the two that mattered.

The comparison implemented below is therefore the **published subtree**, by tree object
id:

    git rev-parse <deployed_sha>:site   vs   git rev-parse <head>:site

Equal tree ids mean the visitor holds exactly the bytes `main` holds, however many commits
and however many days separate the two. Unequal ids mean they do not, even if the deploy
was yesterday. This also survives the case a commit count cannot: a change to `site/` and
a revert of it leave the trees equal and the site correct, and a SHA comparison would call
that stale forever.

Why the deployment record and not the run history
-------------------------------------------------
`publish-site`'s run list is the wrong source and this repository is the proof. Thirteen of
its runs finished `cancelled`. Count a cancelled run as a publish and the site reports as
fresh every time; filter cancellations out and the newest surviving run may be days from
the commit it is credited with. A `github-pages` deployment, by contrast, exists only
because bytes were published, it names the commit they came from, and its status says
whether the publish succeeded. A deployment row on its own is only a *request* to publish,
so the newest status has to read `success` before its commit may be treated as live --
otherwise the site gets reported as fresher than it is, which is the one direction of error
this file exists to prevent.

The rule, stated once: a detector that cannot tell must refuse, never report a comfortable
zero. Every unmeasurable case below raises `StalenessUnknown` and exits non-zero.

Standard library only, and it imports nothing from `src/perimeter`, so the sentinel runs on
a bare `python3` with no dependency resolution and cannot be broken by one.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_REPO = "ChelseaKR/perimeter"

#: The environment a deployment has to belong to. A repository can carry deployments for
#: other environments; only this one is the published site.
PAGES_ENVIRONMENT = "github-pages"

#: The directory `pages.yml` hands to `actions/upload-pages-artifact`, and so the whole of
#: what a visitor receives. Held as a constant here and checked against the workflow by
#: `tests/test_deploy_staleness.py`: if the publisher's `path:` ever moves, this sentinel
#: would go on comparing a directory nobody serves and would report a reassuring zero
#: about the wrong tree.
PUBLISHED_PATH = "site"

#: How long a change to `site/` may sit unpublished before this reports. `site/` moves
#: only on a data refresh, which is a manual, occasional act, so the useful threshold is
#: generous: it exists to catch a month, not an afternoon.
DEFAULT_MAX_AGE_DAYS = 14

_SHA = re.compile(r"^[0-9a-f]{40}$")

#: Called with a deployment id, returns that deployment's statuses newest-first.
StatusesFor = Callable[[Any], Sequence[Mapping[str, Any]]]


class StalenessUnknown(Exception):
    """The comparison could not be made, so no number is reported.

    Raised in preference to returning zero anywhere the inputs do not support a
    measurement. The caller turns this into a red run: a sentinel that cannot tell is a
    broken sentinel, and it has to look broken.
    """


@dataclass(frozen=True)
class DeployRecord:
    """The published build: which commit it came from, and when it went out."""

    deployment_id: int
    sha: str
    created_at: datetime


@dataclass(frozen=True)
class Drift:
    """Where the published bytes stand against `main`."""

    deployed: DeployRecord
    head: str
    published_tree: str
    head_tree: str
    deploy_age_days: int
    commits: int
    unpublished_commits: int
    oldest_unpublished: str | None
    waiting_days: int | None
    max_age_days: int

    @property
    def serving_current_bytes(self) -> bool:
        """Does the visitor hold exactly the bytes `main` holds?

        Tree object ids, not commit ids. `pages.yml` uploads the committed `site/`
        directory as-is, so two commits with the same `site/` tree serve the same site no
        matter how far apart they are. Comparing commits instead would report drift on
        every dependabot bump and every README edit.
        """
        return self.published_tree == self.head_tree

    @property
    def overdue(self) -> bool:
        """Report only when something a visitor would receive has waited too long.

        Age alone is never the verdict. A site nobody republished for a month because
        nothing it publishes changed is correct, not stale, and a sentinel that fires on
        every finished repository is one nobody reads. The clock starts at the oldest
        unpublished commit that touched `site/`, not at the deploy: a deploy from 40 days
        ago plus a change made yesterday is one day of waiting, not forty.
        """
        if self.serving_current_bytes or self.waiting_days is None:
            return False
        return self.waiting_days > self.max_age_days


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.strip().replace("Z", "+00:00")).astimezone(UTC)


def newest_successful_deployment(
    deployments: Iterable[Mapping[str, Any]],
    statuses_for: StatusesFor,
) -> DeployRecord:
    """The most recent `github-pages` deployment that actually published.

    A deployment row is a request to publish; its statuses are what say whether bytes
    landed. A deployment whose newest status is `failure`, `error`, `in_progress` or
    `queued` never became a site, and treating its commit as the live one would report the
    site as fresher than it is.
    """
    candidates = [
        d
        for d in deployments
        if d.get("environment") in (None, PAGES_ENVIRONMENT)
        and _SHA.match(str(d.get("sha", "")))
    ]
    if not candidates:
        raise StalenessUnknown(
            "no github-pages deployment in this repository's history: there is no "
            "published build to compare main against"
        )
    candidates.sort(key=lambda d: _parse_timestamp(str(d["created_at"])), reverse=True)

    for deployment in candidates:
        states = [str(s.get("state", "")) for s in statuses_for(deployment["id"])]
        if states and states[0] == "success":
            return DeployRecord(
                deployment_id=int(deployment["id"]),
                sha=str(deployment["sha"]),
                created_at=_parse_timestamp(str(deployment["created_at"])),
            )

    raise StalenessUnknown(
        f"none of the {len(candidates)} github-pages deployment(s) reports a successful "
        "status: nothing here proves any build was ever published"
    )


def _run_git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 -- fixed argv, no shell, no untrusted input
        ["git", "-C", str(REPO_ROOT), *args],  # noqa: S607 -- git is the thing being read
        capture_output=True,
        text=True,
        check=False,
    )


def _git(*args: str) -> str:
    result = _run_git(*args)
    if result.returncode != 0:
        raise StalenessUnknown(f"git {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def _has_commit(sha: str) -> bool:
    """Whether this clone contains the commit, without raising on absence.

    `git cat-file` exits non-zero for a commit that is simply not here, which is the
    ordinary shallow-clone case and not a git failure. Routing it through `_git` would
    report it as one, and the refusal the caller raises -- the one that names the shallow
    checkout and says why a zero would be wrong -- would never be reached.
    """
    return _run_git("cat-file", "-e", f"{sha}^{{commit}}").returncode == 0


def require_comparable(deployed_sha: str, head: str) -> None:
    """Refuse unless this clone can actually place the deployed commit on `main`.

    Both failures below report no drift if they are not caught, and both are ordinary. A
    shallow checkout does not contain the deployed commit at all, so every comparison
    against it comes back empty and the site reads as current -- which is why the sentinel
    workflow checks out with `fetch-depth: 0`, and why this refuses rather than trusting
    that it did. A force-push or a rebase leaves the deployed commit off `main` entirely,
    where "what has changed since the deploy" is not a question with an answer.
    """
    if not _SHA.match(deployed_sha):
        raise StalenessUnknown(f"deployed commit {deployed_sha!r} is not a commit id")
    if not _has_commit(deployed_sha):
        raise StalenessUnknown(
            f"deployed commit {deployed_sha[:9]} is not in this clone: the checkout is "
            "shallow, and a comparison against a history that does not reach the "
            "published build would report no drift at all"
        )
    if _git("merge-base", deployed_sha, head) != _git("rev-parse", deployed_sha):
        raise StalenessUnknown(
            f"deployed commit {deployed_sha[:9]} is not an ancestor of {head[:9]}: the "
            "history has diverged and 'what has changed since the deploy' has no answer"
        )


def published_subtree(sha: str) -> str:
    """The tree object id of the directory `pages.yml` uploads, at one commit.

    This, not the commit id, is what the visitor holds. Refuses when the path is absent:
    a missing `site/` means the publisher's `path:` and this module's `PUBLISHED_PATH`
    have drifted apart, and a comparison of two things that are not the published tree is
    worth less than no comparison.
    """
    result = _run_git("rev-parse", f"{sha}:{PUBLISHED_PATH}")
    if result.returncode != 0:
        raise StalenessUnknown(
            f"{PUBLISHED_PATH}/ does not exist at {sha[:9]}: the directory pages.yml "
            "uploads and the directory this sentinel compares are not the same directory"
        )
    return result.stdout.strip()


def commits_touching_published(
    deployed_sha: str, head: str
) -> list[tuple[str, datetime]]:
    """Commits after the deployed one that changed the published directory, newest first."""
    raw = _git(
        "log", "--format=%H %cI", f"{deployed_sha}..{head}", "--", PUBLISHED_PATH
    )
    commits: list[tuple[str, datetime]] = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        sha, _, stamp = line.partition(" ")
        commits.append((sha, _parse_timestamp(stamp)))
    return commits


def measure(
    deployed: DeployRecord,
    head: str,
    now: datetime,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
) -> Drift:
    """Place the published bytes against `main`, or refuse."""
    head_sha = _git("rev-parse", head)
    require_comparable(deployed.sha, head_sha)

    published_tree = published_subtree(deployed.sha)
    head_tree = published_subtree(head_sha)
    unpublished = commits_touching_published(deployed.sha, head_sha)

    if published_tree != head_tree and not unpublished:
        raise StalenessUnknown(
            f"{PUBLISHED_PATH}/ differs between {deployed.sha[:9]} and {head_sha[:9]} but "
            "no commit between them touched it: the two readings contradict each other "
            "and neither can be reported"
        )

    oldest = unpublished[-1] if unpublished else None
    return Drift(
        deployed=deployed,
        head=head_sha,
        published_tree=published_tree,
        head_tree=head_tree,
        deploy_age_days=(now - deployed.created_at).days,
        commits=int(_git("rev-list", "--count", f"{deployed.sha}..{head_sha}") or 0),
        unpublished_commits=len(unpublished),
        oldest_unpublished=oldest[0] if oldest else None,
        waiting_days=(now - oldest[1]).days if oldest else None,
        max_age_days=max_age_days,
    )


def render(drift: Drift) -> str:
    """The report. States the measurement before its verdict, always."""
    lines = [
        f"Published build:  {drift.deployed.sha[:9]}  "
        f"({drift.deployed.created_at.date().isoformat()}, "
        f"deployment {drift.deployed.deployment_id})",
        f"main:             {drift.head[:9]}",
        f"Published bytes:  {PUBLISHED_PATH}/ tree {drift.published_tree[:9]} served, "
        f"{drift.head_tree[:9]} on main",
        f"Since the deploy: {drift.deploy_age_days} days, {drift.commits} commits, "
        f"{drift.unpublished_commits} of them touching {PUBLISHED_PATH}/",
    ]
    if drift.serving_current_bytes:
        lines.append(
            f"\nUp to date: the served {PUBLISHED_PATH}/ tree is byte-identical to "
            "main's. Distance in commits and days is not drift when the published bytes "
            "match."
        )
    elif drift.overdue:
        lines.append(
            f"\nOVERDUE: {PUBLISHED_PATH}/ has been ahead of the published bytes for "
            f"{drift.waiting_days} days (oldest unpublished change "
            f"{(drift.oldest_unpublished or '')[:9]}), past the {drift.max_age_days}-day "
            "threshold. The live site is not what this repository says it is."
        )
    else:
        lines.append(
            f"\nWaiting: {PUBLISHED_PATH}/ has been ahead of the published bytes for "
            f"{drift.waiting_days} days, within the {drift.max_age_days}-day threshold."
        )
    return "\n".join(lines)


def as_json(drift: Drift) -> dict[str, Any]:
    return {
        "deployed_sha": drift.deployed.sha,
        "deployed_at": drift.deployed.created_at.isoformat(),
        "deployment_id": drift.deployed.deployment_id,
        "head": drift.head,
        "published_path": PUBLISHED_PATH,
        "published_tree": drift.published_tree,
        "head_tree": drift.head_tree,
        "serving_current_bytes": drift.serving_current_bytes,
        "deploy_age_days": drift.deploy_age_days,
        "commits": drift.commits,
        "unpublished_commits": drift.unpublished_commits,
        "oldest_unpublished": drift.oldest_unpublished,
        "waiting_days": drift.waiting_days,
        "overdue": drift.overdue,
    }


def _gh(path: str) -> Any:
    """Read the API through `gh`, which the runner already authenticates."""
    result = subprocess.run(  # noqa: S603 -- fixed argv, no shell, no untrusted input
        ["gh", "api", path],  # noqa: S607 -- gh is the thing being read
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise StalenessUnknown(f"gh api {path} failed: {result.stderr.strip()}")
    return json.loads(result.stdout)


def _from_api(repo: str) -> tuple[Sequence[Mapping[str, Any]], StatusesFor]:
    deployments: Sequence[Mapping[str, Any]] = _gh(
        f"repos/{repo}/deployments?environment={PAGES_ENVIRONMENT}&per_page=20"
    )

    def statuses_for(deployment_id: Any) -> Sequence[Mapping[str, Any]]:
        result: Sequence[Mapping[str, Any]] = _gh(
            f"repos/{repo}/deployments/{deployment_id}/statuses?per_page=10"
        )
        return result

    return deployments, statuses_for


def _from_file(path: Path) -> tuple[Sequence[Mapping[str, Any]], StatusesFor]:
    """Read a recorded API response instead of calling it (offline use and tests)."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    statuses: Mapping[str, Sequence[Mapping[str, Any]]] = payload["statuses"]

    def statuses_for(deployment_id: Any) -> Sequence[Mapping[str, Any]]:
        return statuses.get(str(deployment_id), [])

    deployments: Sequence[Mapping[str, Any]] = payload["deployments"]
    return deployments, statuses_for


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--head", default="origin/main")
    parser.add_argument("--max-age-days", type=int, default=DEFAULT_MAX_AGE_DAYS)
    parser.add_argument(
        "--json", action="store_true", help="emit the measurement as JSON"
    )
    parser.add_argument(
        "--deployments-json",
        type=Path,
        help="read deployments from a file instead of the API (offline use and tests)",
    )
    args = parser.parse_args(argv)

    try:
        if args.deployments_json:
            deployments, statuses_for = _from_file(args.deployments_json)
        else:
            deployments, statuses_for = _from_api(args.repo)
        deployed = newest_successful_deployment(deployments, statuses_for)
        drift = measure(deployed, args.head, datetime.now(UTC), args.max_age_days)
    except StalenessUnknown as exc:
        print(f"cannot measure deploy staleness: {exc}", file=sys.stderr)
        _write_github_output(None, str(exc))
        return 2

    print(json.dumps(as_json(drift), indent=2) if args.json else render(drift))
    _write_github_output(drift, None)
    return 0


def _write_github_output(drift: Drift | None, error: str | None) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as handle:
        if drift is None:
            handle.write("measured=false\n")
            handle.write(f"error={error or 'unknown'}\n")
            return
        handle.write("measured=true\n")
        handle.write(f"overdue={str(drift.overdue).lower()}\n")
        handle.write(
            f"serving_current_bytes={str(drift.serving_current_bytes).lower()}\n"
        )
        handle.write(
            f"waiting_days={drift.waiting_days if drift.waiting_days is not None else ''}\n"
        )
        handle.write(f"commits={drift.commits}\n")
        handle.write(f"unpublished_commits={drift.unpublished_commits}\n")
        handle.write(f"deployed_sha={drift.deployed.sha}\n")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
