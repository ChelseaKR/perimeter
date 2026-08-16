# A gate is not adopted until it has been seen to fail

- Status: Accepted
- Date: 2026-08-15
- Deciders: Chelsea Kelly-Reif

## Context

On 2026-08-15 four checks in this repository were found to be incapable of
reporting the thing they were named for. None of them was written carelessly;
each was a reasonable-looking line that did not do what its name said.

- The determinism check ran `find build/site-offline -type f | sort | xargs
  shasum -a 256`. A workflow `run:` block uses `bash -e` without `pipefail`, so a
  pipeline reports its last command's status: `find` on a missing directory exits
  1 and the step stayed green. With no files to hash, both sides also came out
  identical, so an empty build passed the determinism check.
- `make sync` ran `uv sync --frozen` as the lockfile-drift gate. Measured against
  a `pyproject.toml` the lockfile does not satisfy: `uv lock --check` exits 1,
  `uv sync --locked` exits 1, `uv sync --frozen` exits 0. Every target after it
  runs `uv run`, which rewrites `uv.lock`, so the gate would have gone green and
  then repaired the state it was checking.
- The coverage floor was 90% with `src/perimeter/acquire.py` omitted. Omitted, the
  figure was 100%; included, it was 88%. The excluded module was the only one that
  touches the network and the only one carrying this project's promises about how
  it treats somebody else's server.
- `verify`, `secret-scan` and `sast` were described in `ci.yml` as merge-blocking.
  `main` had no ruleset and no branch protection, so none of them blocked
  anything. Separately, none of the three reads `.github/workflows/`, so five open
  pull requests changing nothing but `pages.yml` carried three green ticks from
  checks that never opened the file.

The common shape is not a bug in any one line. It is that each gate was adopted
on the strength of reading it, and reading a gate tells you what it does when it
passes.

## Decision

A check is not adopted here until there is evidence it fails on the input it
exists to catch. Three forms of evidence count, in descending order of strength:

1. **A test that runs the gate against failing input.**
   `tests/test_determinism_gate.py` runs `tools/determinism.sh` against thirteen
   cases: changed bytes, an extra file, the same bytes at a different path, an
   empty tree, a missing tree, a file where a directory should be, wrong arity.
   This is the preferred form and the reason the determinism check is a script
   rather than four lines inlined in a workflow.
2. **A recorded measurement in the commit that adopts it.** Exit codes observed
   against a deliberately broken input, quoted in the commit message with the
   command that produced them. Used where the gate is a third-party tool: zizmor
   exits 12 with findings and 0 without; `uv lock --check` exits 1 on drift.
3. **A named reason the first two were not possible**, in the commit, plus the
   first real run treated as the verification. Used once, for CodeQL, which needs
   a bundle download to execute.

Corollaries that fall out of the four cases above:

- A shell gate that pipes runs under `set -euo pipefail`, or it is not a gate.
- A gate that can find nothing to examine fails rather than passing. No files, no
  SARIF, no scanner installed: all of those are failures, not clean runs.
- A coverage exclusion is a claim that the code is untestable, not that it is
  inconvenient to test. If the reason is "it touches the network", the network
  call is what gets substituted, not the module that gets excluded.
- A gate's documentation states what the gate enforces on the server, not what
  the author intends. `ci.yml`'s header names the live protection state, and
  `.github/rulesets/main.json` carries the profile that would change it.

## Consequences

Adding a check costs more than it did. Writing `tests/test_determinism_gate.py`
took longer than writing `tools/determinism.sh`, and that is the correct ratio
for a repository whose entire claim is that its measurements are trustworthy: a
project that publishes counts about somebody else's data cannot also be a project
whose own checks are decorative.

Two known gaps remain, recorded rather than closed. The CodeQL job has never
been executed; its first pull-request run is its verification. And the required
status checks in `.github/rulesets/main.json` cannot block anything until the
ruleset is applied, which is a live repository setting and not a decision a pull
request can make.
