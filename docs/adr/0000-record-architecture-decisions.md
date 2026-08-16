# Record architecture decisions

- Status: Accepted
- Date: 2026-08-15
- Deciders: Chelsea Kelly-Reif

## Context

`docs/adr/` has existed in this repository since the scaffold and has been empty
the whole time, while the decisions that shape every published number were
written up as prose in `README.md`, `CONTRIBUTING.md` and `docs/MARKERS.md`. The
reasoning is not missing; it is unfiled. An empty ADR directory beside that much
recorded argument reads as a project that has not thought about its
architecture, which is the opposite of what happened here.

DOC-04 of the portfolio documentation standard requires `docs/adr/` with a
`0000` meta-record and MADR-format entries.

## Decision

Decisions live in `docs/adr/NNNN-kebab-title.md`, numbered sequentially from this
record, in MADR format: Status, Date, Deciders, Context, Decision, Consequences.
The log is append-only. A superseded record keeps its text and gains a Status of
Superseded naming the record that replaced it; it is never rewritten in place.

The first records after this one are back-filled from prose that already existed.
They cite where the reasoning was written rather than restating it, because the
prose is written for a reader of the pages and the ADR is written for a
maintainer, and both are worth keeping.

A decision earns a record when reversing it would change what the pages publish,
what the build refuses, or what a reader is entitled to trust. Choosing a library
or a directory name does not.

## Consequences

New reasoning has one place to go, and the back-filled records make the existing
reasoning findable by somebody who does not already know which README paragraph
to read. `README.md` and `docs/MARKERS.md` stay the reader-facing explanation;
the ADR log is the maintainer-facing history, and the two are expected to agree.
