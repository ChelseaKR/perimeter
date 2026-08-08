# Contributing

## Local gate

```sh
uv sync
make verify
```

`make verify` is the single local gate and is byte-for-byte identical to the `verify` job
in `.github/workflows/ci.yml`. If it is green locally, CI is green.

## The rule that governs changes here

This project publishes counts about other people's data. Two things follow.

**Never widen a marker set to make a build pass.** If `SentinelDriftError` fires, the
source has started using a value this project has not reviewed. The fix is to read that
value in its own field's context, decide what it means, and add it to that field's
`FieldSpec` with a note saying why. Adding it to `SUSPECTED_SENTINELS` or to an unrelated
field to clear the error turns an absence into a value, which is the one thing this
project exists not to do.

**Never publish a number that was not counted.** No estimates, no interpolation across a
gap, no rate over an empty denominator. Where a share does not exist, say so in words.

## Tone

Every page operationalizes a limitation CAL FIRE or FRAP already documents. Quote the
publisher's own sentence beside the measurement. This is not an audit and must never read
as one. Do not describe any agency's infrastructure, access controls or security posture.

## Data

Only public, openly licensed data, from the endpoints in `PROVENANCE.md`. If an endpoint
declines automated access, document a manual acquisition. Never work around bot
protection, rate limiting or any access control.

## Review

Every PR requires review sign-off before merge. PRs touching `.github/workflows/`,
`src/perimeter/schema.py` or `src/perimeter/sources.py` route to the code owner.
