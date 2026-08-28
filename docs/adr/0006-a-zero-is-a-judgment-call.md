# A recorded zero is a judgment call, and is audited as one

- Status: Accepted
- Date: 2026-08-27
- Deciders: Chelsea Kelly-Reif

## Context

ADR-0001 decided that a recorded zero is a value: an inspector writing `0` in
`NOOFCARSONPROPERTY` counted no cars, and folding that into the blanks would
erase the count. That is right, and it was applied to every numeric field at
once, as a property of the number rather than of the field.

`YEARBUILT` shows what that costs. 12,148 of the 132,522 DINS records hold the
literal `0`, and every one was counted toward the field's 77.0% recorded share.
No structure standing in a California wildfire was built in year 0. The value is
not a year, and reading it as one published an absence as a value, which is the
single thing this project exists not to do.

The audit did not catch it, and could not have. `docs/MARKERS.md` covers every
field that *declares* a vocabulary, and `tests/test_schema.py` enforces that.
`YEARBUILT` declared nothing: no markers, no codes, no domain. A field deciding
that its zeros are measurements makes that decision by declaring nothing at all,
so it sat outside the audit by construction, and the gate that reads the audit
was green the whole time over a set that excluded exactly the field that needed
reviewing.

The same shape covers five other numeric fields. Three of them turn out to be
inspector counts where a zero is the measurement. Two are contested and are left
as values with the reason recorded. One is not a value at all. Only reading the
distributions separated them.

## Decision

A zero in a numeric field is a judgment call about that field, not a property of
the number, and it is audited like every other judgment call here.

`docs/MARKERS.md` section 7 covers every numeric field that publishes a
`recorded_zero_values` count above zero: what the zeros are, what the file shows,
whether a marker is declared, and where a declaration was considered and refused.
`tests/test_schema.py` fails when a numeric field publishes recorded zeros and
that document does not cover it.

`YEARBUILT` declares `0` as an unknown marker on `Basis.INFERRED`. The field
moves from 102,091 recorded values (77.0%) to 89,943 (67.9%), and the 12,148 are
published as recorded-as-unknown. `NUMBEROFUNITPERSTRUCTURE` and
`ASSESSEDIMPROVEDVALUE` are not declared, because each has a reading in which the
zero is real and the file does not settle it. Refusing to declare is a decision
and is written up as one, in the same place, with the counts that would change if
a later reader decided differently.

## Consequences

A numeric field is no longer free. Adding one now means reading its zeros before
the build goes green, which is the same cost ADR-0003 imposed on markers and for
the same reason.

The gate this adds is deliberately weak in one direction: it checks that the
audit *covers* a field, not that what the audit says is right. `docs/MARKERS.md`
can be wrong about `NUMBEROFUNITPERSTRUCTURE` and nothing will fail. What the
gate removes is the case where nobody looked, which is the case that produced
this record.

It is also weak in the other direction, and this is worth stating: a field whose
zeros are declared as markers stops publishing recorded zeros, so the zero gate
stops applying to it. `YEARBUILT` now publishes `recorded_zero_values: 0`, and
what keeps it in the audit is the existing rule that a declared vocabulary needs
a write-up. The two gates cover each other and neither covers the field alone.

The observation that should supersede this record is a numeric field whose zeros
are genuinely mixed: some rows a count, some rows a placeholder, separable only
by another column. Nothing in `cells.py` can express that today. Both states
would have to be reachable for one field, and the three-state model in ADR-0001
would be what has to give.
