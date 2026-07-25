# Security Policy

## Supported versions

| Version | Supported |
| :--- | :--- |
| 0.1.x | Yes |

## Reporting a vulnerability

Please **do not open a public issue** for security problems.

Report privately to **founder@urdugen.com**, or use GitHub's
[private vulnerability reporting](https://github.com/HaiderHanif/agentgate/security/advisories/new).

Include:

- A description of the issue and its impact
- Steps to reproduce, ideally with a minimal example
- Any suggested remediation

You can expect an acknowledgement within 72 hours and a status update within 7 days.

## Handling traces safely

Golden traces record real tool arguments and results, which may contain personal or
sensitive data. Before committing a trace:

- Redact customer identifiers, tokens, and credentials
- Prefer synthetic fixtures over production captures
- Treat `traces/` as reviewed source code, not as throwaway output

agentgate never transmits traces anywhere. Everything runs locally and in your CI.
