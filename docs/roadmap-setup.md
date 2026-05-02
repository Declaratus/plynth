# Roadmap setup (one-time, manual)

This document records the `gh` commands a maintainer runs once to seed
labels, milestones, and the v0.4.0 backlog issues. The README and
CONTRIBUTING already point at the resulting filtered URLs; running these
commands populates them.

These steps cannot be automated in a PR — labels and milestones are repo
state, not files. Run them after [pr/9-roadmap](#) merges.

```bash
# Labels — type:* and area:*, plus the discovery labels.
gh label create type:feature      --color 1f883d --description "New feature"
gh label create type:bug          --color d73a4a --description "Bug"
gh label create type:docs         --color 0075ca --description "Documentation"
gh label create type:chore        --color cfd3d7 --description "Tooling/refactor, no behavior change"
gh label create area:engine       --color 5319e7 --description "engine/ module"
gh label create area:cli          --color 5319e7 --description "cli.py"
gh label create area:docs         --color 5319e7 --description "docs/, README"
gh label create good-first-issue  --color 7057ff
gh label create help-wanted       --color 008672

# Milestones
gh api -X POST repos/Declaratus/plynth/milestones -f title=v0.3.0 \
  -f description="github.com support, PyPI release, roadmap"
gh api -X POST repos/Declaratus/plynth/milestones -f title=v0.4.0
gh api -X POST repos/Declaratus/plynth/milestones -f title=Backlog

# Seed v0.4.0 backlog issues
gh issue create \
  --title "JSON dry-run output (--dry-run --format json)" \
  --label "type:feature,area:cli,area:engine" \
  --milestone v0.4.0 \
  --body "Emit the ExecutionPlan as JSON when --dry-run --format json is passed, so plans can pipe into other tools."

gh issue create \
  --title "Repo creation when repo.create: true" \
  --label "type:feature,area:engine" \
  --milestone v0.4.0 \
  --body "When the instance config sets repo.create: true, call POST /orgs/{org}/repos before Phase 1 instead of failing on 'repository not found'."

gh issue create \
  --title "Configurable default Status field options" \
  --label "type:feature,area:engine" \
  --milestone v0.4.0 \
  --body "Allow the instance config (or template) to override which Status options are created and which is the default for new items."

gh issue create \
  --title "GHES version detection (GET /api/v3/meta)" \
  --label "type:feature,area:engine" \
  --milestone v0.4.0 \
  --body "Preflight GET {target}/api/v3/meta on GHES targets to detect the installed version. Warn or refuse on mismatched feature support (e.g. createProjectV2View landed in 3.20+)."
```
