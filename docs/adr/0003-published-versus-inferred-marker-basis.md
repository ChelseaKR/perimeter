# Every declared marker carries whether it is published or inferred

- Status: Accepted
- Date: 2026-08-15 (back-filled; the decision landed with `docs/MARKERS.md`)
- Deciders: Chelsea Kelly-Reif

## Context

Twenty-seven of the fifty-four measured fields declare a marker, a code or a
finding of absence. Those declarations are not all the same kind of claim.

Twelve of them are in the layer's own coded-value domain, or in FRAP's metadata
document, or in CAL FIRE's DINS database dictionary. Reading `Unknown` as
unknown in a field whose published domain lists `Unknown` is not a judgment
call.

Fifteen are not. The field is free text, or the value is one the published
domain does not carry, and this project read it off the acquired file. The
all-zeros local incident number is the clearest case: it appears on 12,469
perimeter records across many units and decades, FRAP publishes no domain for
`INC_NUM` at all, and reading it as a placeholder rests on the field's published
definition plus the distribution of the file. Reading it as a number instead
would report 12,230 records as sharing an incident key rather than 376.

Counting the two kinds identically is right, because both are the best available
reading. Presenting them identically is not, because a reader should lean harder
on one than the other.

## Decision

Every `FieldSpec` that declares a vocabulary carries a `basis`.
`Basis.PUBLISHED` requires that *every* declared value appears in a published
domain or definition; one undocumented value out of several makes the whole field
`Basis.INFERRED`. The basis travels with the measurement: it is in `schema.py`,
in the JSON artifacts as `marker_basis`, and on the pages beside each field's
marker list.

`docs/MARKERS.md` is the audit behind it, per field: the declared values, the
evidence, the URL it can be checked against, the effect on the published figures,
and a confidence. Where a call has a counterfactual worth counting, the
counterfactual is counted rather than described, and published in the artifact
under `marker_counterfactuals`.

The tests enforce the whole chain, so a marker cannot be declared without a
basis, and a basis cannot claim `published` without the evidence.

## Consequences

A reader can tell which numbers rest on somebody else's documentation and which
rest on this project's reading, and can go check the second kind. Publishing the
counterfactual means the cost of a judgment call is a number rather than an
assurance.

The cost is that adding a marker is slow: it needs the field read in its own
context, a written note, a URL and a confidence. That slowness is deliberate.
`CONTRIBUTING.md` states the rule it protects, which is that a marker set is
never widened to make a build pass.

The pressure this record does not resolve is `published` becoming stale. A basis
is `published` as of the retrieval date, and a publisher can revise a domain
between retrievals without anything here noticing. Re-checking the cited URLs is
a manual step at acquisition time, and nothing gates it.
