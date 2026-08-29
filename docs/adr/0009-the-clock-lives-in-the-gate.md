# A retrieval goes stale, and the clock that notices lives in the gate

- Status: Accepted
- Date: 2026-08-27
- Deciders: Chelsea Kelly-Reif

## Context

Every figure these pages publish is a count of a file downloaded on one day.
`README.md` says so, the pages say the retrieval date, and `PROVENANCE.md` and
`src/perimeter/sources.py` carry the version, the byte count and the hash. All of
that is honest and none of it is the same thing as noticing.

A reader who does not check the date is served a description of a file that has
moved on. DINS carries no version string and is appended to as inspections
complete, so it is different from the acquired file the day after the acquisition
and increasingly different every season after. Nothing here raised its hand about
that, and nothing could: no code in this repository had ever asked what today is.

`DATA-GOVERNANCE-STANDARD.md` calls the answer a staleness alarm, makes it an
AUTO-GATE (DG-04), and requires the number it fires against to be stated in a
per-source data card (DG-01). The README's Data Governance row had recorded the
absence of both for twelve days: "no refresh cadence, staleness SLA or stated
tier".

The tempting implementation is the one the standard's wording suggests: flag it
in the report. That is exactly what must not happen here. `README.md` promises
that the same inputs produce byte-identical output, `tools/determinism.sh` is the
gate behind that promise, and `tests/test_artifacts_and_pages.py` asserts no wall
clock leaks into an artifact. A page that computed its own staleness would read
the clock at build time, and two builds a day apart would differ. The determinism
claim and the staleness claim would be in direct conflict, and the one that would
quietly lose is determinism, because its failure is invisible.

## Decision

The artifacts publish facts and the gate does the subtraction.

Each source carries a `tier`, a `refresh_cadence` and a `staleness_sla_days` in
`src/perimeter/sources.py`, beside the version and the hash, because that module
is the single reviewed record of provenance. Those three are policy rather than
acquisition, so a fixture build publishes them like any other build; the fields
that describe a download stay null there.

The artifacts publish the retrieval date and `staleness_sla_days` and compute
nothing from them. A consumer holding both can do the subtraction against its own
clock and get the same answer this build would, whenever it asks.

`tests/test_data_cards.py` reads `date.today()` and fails when a retrieval is
older than the SLA its card states. That is the only place in this repository
that asks what today is, and a gate is the right place for it: a gate is allowed
to give a different answer tomorrow, and an artifact is not.

The SLA is this project's declaration and the cards say so. Neither CAL FIRE nor
FRAP promises a publication schedule and neither is asked to. 400 days for the
FRAP layer is one annual release cycle plus about five weeks, so a retrieval does
not go stale on the eve of the version that would replace it. 180 days for DINS
is about one fire season.

## Consequences

This gate is built to fire, and firing is it working. The comparison is `age >
sla`, so the SLA day itself still passes and the first red day is the one after:
on the retrieval on record it fires for DINS on 2027-02-04 and for FRAP on
2027-09-12. When it does, the fix
is to re-acquire, rebuild `site/` and update `sources.py`, or to move the SLA in
the card with a reason. What it must not become is a number quietly raised to get
a green build, which is the move `CONTRIBUTING.md` already forbids for a marker
set and forbids here for the same reason.

The cost is a test whose result depends on the day it runs, in a repository whose
whole posture is that a build is reproducible. That is a real inconsistency and
it is confined on purpose: one function, one date argument, and the assertion
about the real sources is the only caller that passes `date.today()`. Everything
else about the SLA is tested against fixed dates, including both sides of the
boundary.

What this does not do is check whether the *published domains* have moved.
ADR-0003 records that a `published` basis is published as of the retrieval date
and that a publisher can revise a domain between retrievals without anything here
noticing. A staleness SLA on the file is not that check. It makes the window
bounded, which is less than the check and more than nothing.
