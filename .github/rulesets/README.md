# Branch ruleset (committed, not applied)

`main.json` is the `protect-main` profile this repository owes under
CI-CD-STANDARD §5. It is committed so the intended posture is reviewable and
diffable in-tree. **It is not applied.** Applying it changes a live repository
setting, which is the owner's call, not a pull request's.

## What is true today

**No ruleset is applied on this repository.** Measured 2026-08-15 and re-read
2026-08-28, both times with the same answer:

| Question | Answer |
|---|---|
| `gh api repos/ChelseaKR/perimeter/rulesets` | `[]` |
| `gh api repos/ChelseaKR/perimeter/branches/main` | `"protected": false` |
| `gh api repos/ChelseaKR/perimeter/branches/main/protection` | 404, "Branch not protected" |

So `main` can be force-pushed, deleted, or pushed to directly with every check
red. `verify`, `secret-scan`, `sast`, `zizmor` and `codeql` run and report;
nothing blocks on them. The header of `.github/workflows/ci.yml` used to call
them merge-blocking, which was the opposite of what the server enforces.

The other half of that, worth knowing before running the command below:
`main.json` has never been applied to anything, so no live ruleset has ever
corrected it. Whatever it gets wrong, it has been getting wrong unopposed.

## Apply it in this order, or every pull request deadlocks

A required status check that never reports is a check that never turns green.
Two of the five contexts in `main.json` do not exist on `main` yet.

1. Land the workflow-SAST change, so `zizmor` and
   `codeql (actions · python · javascript)` exist on `main` and run on pull
   requests. `codeql.yml` triggers on `pull_request: branches: [main]`, so it
   reports on any PR targeting `main`.
2. Drain the five open dependabot pull requests. `strict_required_status_checks_policy`
   requires a branch to be up to date with `main` before it merges, so each one
   needs a rebase after the one before it lands. Doing this first is cheaper
   than doing it under the ruleset.
3. Check `bypass_actors` in `main.json` before you post it. It must hold
   `{ "actor_id": 5, "actor_type": "RepositoryRole", "bypass_mode": "always" }`.
   This file said `"bypass_actors": []` until 2026-08-28, and posting that
   version is how the owner gets locked out of the repository; see
   "`bypass_actors`: the repository owner, and nobody else" below. Note that
   POST adds a ruleset rather than replacing one, and rules from every
   applicable ruleset combine while bypass actors are per-ruleset, so posting
   a second time without deleting the first leaves an empty-bypass ruleset
   over `main` that blocks the owner whatever the first one allows.
4. Then apply the ruleset, owner-only:

```sh
gh api -X POST repos/ChelseaKR/perimeter/rulesets \
  --input .github/rulesets/main.json
```

5. Confirm the owner's bypass came through:
   `gh api repos/ChelseaKR/perimeter/rulesets/<id> --jq .current_user_can_bypass`
   must read `"always"`, and `--jq .bypass_actors` must hold exactly the one
   actor `main.json` names. An apply that lands every rule and loses that
   actor returns 201 like any other, and it is the lockout described below.
6. Re-export after any UI edit, so this file stays the source of truth:
   `gh api repos/ChelseaKR/perimeter/rulesets/<id>`.

## Why each rule is here

**`required_status_checks`.** CICD-13. The five contexts are the job names
GitHub reports, taken from the workflow files rather than guessed:

| Context | Workflow | Job |
|---|---|---|
| `verify` | `ci.yml` | `verify` (no `name:`, so the job id is the context) |
| `secret-scan` | `ci.yml` | `secret-scan` |
| `sast` | `ci.yml` | `sast` |
| `zizmor` | `ci.yml` | `zizmor` |
| `codeql (actions · python · javascript)` | `codeql.yml` | `analyze`, whose `name:` is the context |

`pages.yml`'s `build` and `deploy` are deliberately absent: that workflow runs
on push to `main` and `workflow_dispatch`, never on a pull request, so requiring
it would block every PR forever. That is also why the five open dependabot PRs,
which change nothing but `pages.yml`, went green against checks that never read
the file they changed. Renaming any job means updating the live ruleset first;
a required context that matches nothing is a gate that has silently gone away.

**`non_fast_forward`** (CICD-16) and **`deletion`.** The two things that are
possible today and should not be.

**`required_signatures`.** Checked before recommending it, because enabling it
with an unsigned history locks the owner out: all fourteen commits on `main`
report `verification.verified: true` from the GitHub API, across both
`ChelseaKR` and `dependabot[bot]`, so nothing is locked out by turning it on.

**`required_linear_history`** with `allowed_merge_methods: ["squash", "rebase"]`.
The repository currently also allows merge commits; linear history and a merge
commit cannot both be had, and the three merge commits already on `main` are
unaffected, since a ruleset governs new pushes rather than existing history.

**`required_approving_review_count: 0`.** GitHub does not count self-approval,
so `1` deadlocks every merge in a single-maintainer repository. This is the
CI-CD-STANDARD §5.1 solo profile, and **the rest of §5.1 is not met here**: that
section also requires a dated solo-maintainer declaration naming the owner,
reporting channel and return-to-independent-review triggers, plus a
`solo-governance` required status check that validates it. Neither exists in
this repository. Recording the gap rather than quietly taking the exemption:
raise the count to 1 the day a second maintainer exists, and until then either
write the §5.1 declaration or keep this note.

`CONTRIBUTING.md` says "Every PR requires review sign-off before merge." That is
not enforceable by one person and is not enforced by this profile either. The
PR requirement, the strict up-to-date policy, thread resolution and stale-review
dismissal are what remain of it.

**`bypass_actors`: the repository owner, and nobody else.** This file carries
exactly one bypass actor, `RepositoryRole` 5 with `bypass_mode: always`,
deliberately and permanently: an agent once applied a ruleset with no bypass
and locked the owner out of their own repository, and restoring access took a
sweep across eighteen repositories. An empty list here is not a stricter gate,
it is the lockout.

This bullet used to say the opposite. It read "`bypass_actors: []`. No
break-glass path. CICD-15 permits one designated maintainer with
`bypass_mode: pull_request`; the empty list is the stricter reading", and that
is the reasoning being reversed, not an oversight being tidied. It was not
wrong about the risk an admin bypass carries; it was wrong about which risk is
larger, and the larger one has already happened elsewhere in this portfolio.
Note also what this repository is asking the profile to enforce:
`required_signatures`, `required_linear_history`, a strict up-to-date policy
and five required contexts, two of which do not exist on `main` yet. That is a
lot of ways for a first application to wedge, on a repository that has never
had a ruleset at all, and the empty list would have removed the only way back
in that does not go through GitHub support.

`bypass_mode: always` rather than CICD-15's `pull_request`, because a bypass
that only works inside a pull request is no use when the thing that is wedged
is the pull request. One actor, and a repository role rather than a team or a
GitHub App: a second entry in this list would be a real finding, and this one
is not.
