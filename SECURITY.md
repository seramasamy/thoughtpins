# Security Policy

Thought Pins stores highly sensitive user-authored content. Security reports are
handled privately and prioritized by potential impact to confidentiality,
tenant isolation, authentication, data deletion, and release integrity.

## Supported Versions

Before the first public release, only the current main development line is
supported. After version 1.0, this table must be replaced with explicit support
windows for released versions.

## Reporting A Vulnerability

Use private vulnerability reporting in the repository host's **Security** tab.
Do not open a public issue, discussion, or pull request containing exploit
details, credentials, private user content, or production identifiers.

Include:

- affected version or commit;
- affected endpoint, platform, or component;
- prerequisites and a minimal reproduction;
- expected and observed behavior;
- impact assessment;
- logs or screenshots with credentials and personal data removed.

We aim to acknowledge a complete report within three business days, provide an
initial severity assessment within seven business days, and coordinate a fix
and disclosure timeline based on impact. These are response targets, not a bug
bounty or guarantee of compensation.

## Scope Priorities

High-priority reports include cross-tenant access, authentication bypass,
account takeover, unsafe archive extraction, server-side request forgery,
secret exposure, deletion/export failures, signing or update-channel compromise,
and leakage of journal or source content through logs or analytics.

Reports based only on automated scanner output should include evidence that the
finding is reachable in the supported configuration.

## Safe Research

Use accounts and data you control. Do not access another person's content,
degrade service availability, retain sensitive data, or use social engineering.
Stop testing and report immediately if you encounter real user data.
