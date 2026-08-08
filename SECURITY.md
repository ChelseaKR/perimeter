# Security Policy

## Supported versions

| Version | Supported |
|---------|-----------|
| latest `main` | yes |
| tagged releases < latest | best-effort, see CHANGELOG |

## Reporting a vulnerability

Please use GitHub's [private vulnerability reporting](https://github.com/ChelseaKR/perimeter/security/advisories/new)
for this repo. Do not open a public issue for a security report.

**Response SLA:** acknowledgment within 72 hours.

## Scope

This project has no server, no user accounts and no runtime. It reads two public files and
writes static output. Scan configuration (SAST, SCA, secret scan) lives in
`.github/workflows/ci.yml`.

This project has no relationship to any California state agency's systems. It reads two
published open-data files and writes static output.
