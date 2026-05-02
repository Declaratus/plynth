# Security Policy

## Token handling

plynth requires a GitHub Personal Access Token (PAT) with `repo` and `project` scopes.

**Do:**
- Pass the token via the `PLYNTH_TOKEN` environment variable.
- Use `--token` for one-off invocations where environment variables are inconvenient.
- Store tokens in a secrets management system, not in files on disk.
- Rotate tokens regularly and revoke unused ones.

**Do not:**
- Commit tokens to any repository — including instance config YAML files.
- Log tokens or include them in bug reports.
- Set tokens in shell history. To avoid this, use:
  ```bash
  read -rs PLYNTH_TOKEN && export PLYNTH_TOKEN
  ```

> **Note:** `GHES_TOKEN` is accepted for one release as a deprecated fallback
> and will be removed in v0.4.0.

Instance config files (`*.yaml`) intentionally have no `token` field.
The token is always supplied at runtime, never stored in YAML.

## Reporting a vulnerability

If you discover a security vulnerability in plynth, please report it privately
rather than opening a public GitHub issue.

**Contact:** open a [GitHub Security Advisory](https://github.com/Declaratus/plynth/security/advisories/new)
or email the maintainer directly (address on the GitHub profile).

Please include:
- A description of the vulnerability and its impact.
- Steps to reproduce or a minimal proof-of-concept.
- Any suggested mitigation.

We aim to acknowledge reports within 48 hours and to publish a fix within 14 days
for confirmed critical issues.

## Supported versions

Only the latest release receives security fixes.
Pin to a specific release tag in production and update promptly when a security
fix is published.
