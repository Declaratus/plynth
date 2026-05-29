# ADR: GitHub ↔ Microsoft Planner Source-of-Truth Topology & Integration Identity Model

**Status:** Proposed · **Date:** 2026-05-29 · **Path:** `docs/backends/github-planner-integration.md`
**Context:** Suite of declarative board-management CLIs (`plynth` bootstrap, `mendrik` lifecycle changesets, `eyrl` portfolio rollups) currently targeting GitHub Projects v2 + Issues. Production target backend: Planner Premium / Project Plan 3 / Project for the web (P4W).

---

## Recommendation (BLUF)

**Keep GitHub Issues + Projects v2 as the single source of truth and treat Planner as a one-way, read-oriented projection. Do not make Planner Premium/P4W an authoritative write target for the CLI suite.** There is no mature first-party or third-party GitHub↔Planner sync, and no native ADO-style work-item linking in Planner or P4W — any link must be synthesized. The decisive constraint is identity: classic Planner (Graph `/planner`) accepts app-only writes via `Tasks.ReadWrite.All`, but Planner Premium/P4W writes go exclusively through Dataverse Project Schedule APIs (PSS OperationSets), which Microsoft documents as usable only by "Users with Microsoft Project License" and explicitly not by "Application users, System users, Integration users." That makes a clean, declarative, app-only provisioner impossible on Premium.

Adopt **Topology A (GitHub source of truth → Planner projection)**:
- **Classic Planner target:** app-only push from a worker using Graph `Tasks.ReadWrite.All`. Acceptable, low-friction.
- **Premium/P4W target:** projection only, via a **licensed-service-account relay** (a named user with a Project license whose refresh token / Power Automate connection drives PSS). Scope it to leadership-visibility rollups (`eyrl`), not full bidirectional task fidelity.

Defer any bidirectional sync until a business case justifies the reconciliation cost. If the client insists on Premium task authority, budget for one licensed human identity, a token-custody mechanism, and ongoing PSS maintenance.

---

## Q1 — Native / Off-the-Shelf GitHub↔Planner Integration (re-verified 2026)

**Honest finding: nothing mature, first-party, or well-licensed exists.** Microsoft publishes no GitHub↔Planner connector. The integration surface is a patchwork of generic iPaaS templates and DIY Power Automate, all of which target **classic Planner only** and break on Premium.

| Option | Direction | Planner tier | Auth identity | Field fidelity | Latency | Maturity / license |
|---|---|---|---|---|---|---|
| **Power Automate — Planner connector + GitHub connector** | GitHub→Planner (and reverse) | **Classic only** (connector reference states verbatim: "The Planner connector currently supports basic plans only"; Premium throws `Archived entity can't be modified` / `0x80040265`) | Delegated; connection owned by a user | Title, bucket, assignee, due date, checklist (no `previewType`); comments weak | Polling/trigger (minutes) | First-party connectors, but no prebuilt template; you assemble it. GitHub connector is std; Planner connector open-source MIT |
| **Power Automate — Dataverse connector + PSS unbound actions** | GitHub→P4W | **Premium/P4W only** | **Licensed human** (connection owner must hold Project license; app users blocked) | Task subject, dates, bucket, dependencies, assignment; **no markdown body** | Polling + async PSS persist | DIY; community blueprints (Pajunen, Kabir Barker). No turnkey product |
| **Make (make.com)** | Bidirectional | Classic ("Microsoft 365 Planner") | Delegated OAuth user | Task create/bucket/comment; issue create/label/assignee | Polling | 3rd-party SaaS, paid; community-grade |
| **Appy Pie / Zapier-class** | GitHub→Planner | Classic | Delegated user | Task create from issue/PR | Polling | 3rd-party SaaS, marketing-heavy, shallow |
| **GitHub Marketplace apps** | — | — | — | — | — | **None for Planner.** (Azure Boards app exists; Planner does not) |
| **Azure Logic Apps** | Either | Classic (same Planner connector) | Delegated/managed | Same as Power Automate | Trigger/poll | Same limitations as Power Automate |
| **OnePlan / OneConnect (ISV)** | Bi-ish | **Premium** | Service account OR service principal (SP is **read-only**; "This method do not support task updates in Planner Premium") | Project/portfolio data | Polling | Commercial PPM ISV; not a GitHub bridge |

Key verifications:
- The Planner Power Automate connector documentation states verbatim that "The Planner connector currently supports basic plans only." Once a plan is converted to Premium, basic-connector writes fail with `Archived entity can't be modified` or `0x80040265`.
- The Microsoft Graph Planner API overview ("Use the Planner REST API," Graph v1.0) states verbatim: *"Premium plans and tasks aren't available on the Planner API in Microsoft Graph. Only basic plans may be accessed using this API."*
- OnePlan's own docs confirm even a service-principal connection to Planner Premium "do not support task updates."

**Conclusion:** assume build-it. No product gives you declarative, app-only, bidirectional GitHub↔Planner sync — least of all for Premium.

## Q2 — The Azure DevOps Analogy: Native GitHub Linking

**Azure Boards has it; Planner and P4W have nothing equivalent.** Azure Boards connects to GitHub via the **Azure Boards app for GitHub**, and supports `AB#<id>` mention syntax in commit messages / PR titles / descriptions (and `GH#` the other way). It auto-creates links shown in the work-item **Development** section, surfaces PR draft/review/checks status, and transitions work-item state on merge (`Fixes AB#123`). The Microsoft Learn linking documentation states verbatim that the integration "uses a 'push-and-pull' design to pull from the GitHub events every hour on the incremental changes on Commit, PR, and Issue," backed by a webhook callback to `https://dev.azure.com/{org}/_apis/work/events`.

**Neither Microsoft Planner (classic or Premium) nor Project for the web has any native GitHub linking capability at all.** There is no app, no mention syntax, no status rollup, no Development section. An ADO-style bidirectional link must be entirely **synthesized** from primitives:

- **Classic Planner:** the closest mechanism is the task **`plannerExternalReference`** (the `references` collection on task details) — a URL "attachment" with an `alias` and `type`. You can store the GitHub issue URL there. It is a dumb hyperlink: no status, no reverse link, no transition. Reverse direction (issue → task) requires writing the Planner deep link into the GitHub issue body/comment yourself.
- **Project for the web/Premium:** P4W tasks have **no external-reference/attachment collection** like classic Planner. Options are a Dataverse **hyperlink column** added to `msdyn_projecttask`, or storing the URL in the single **notes** field. Custom columns are unreliable for automation — community reports that custom columns added in the P4W UI may not surface as queryable Dataverse columns.
- **Status rollup** (the valuable part of `AB#`) does not exist anywhere. To emulate it you must run your own worker: subscribe to GitHub `projects_v2_item` / issue webhooks, map state, and push via Graph (classic) or PSS (Premium), then write the reverse pointer into GitHub. You are rebuilding the Azure Boards app from scratch, minus the GraphQL convenience of the work-item Development section.

A correct mental model: **the ADO GitHub Connection is the feature the client actually wants, and it only exists for Azure Boards.** Recommending Planner means accepting that this must be custom-built and will be lower-fidelity.

## Q3 — GitHub Issues as Source of Truth → Planner as Projection

**Feasibility: one-way GitHub→Planner is feasible and is the correct design. Bidirectional is feasible only at high and ongoing cost, and is not recommended.** The two tiers must be treated separately because of the write-auth asymmetry.

### What breaks / needs special handling

**Status / column mapping.** GitHub Projects v2 "Status" is a per-project **single-select custom field** (`ProjectV2SingleSelectField`), not a fixed enum, and its option set can only be read/changed by deleting and re-adding options (the GraphQL API cannot rename status options or add columns cleanly). Webhook `projects_v2_item` events carry the previous/current single-select value, so change detection works. Mapping target differs by tier:
- Classic Planner has **buckets** (free-form columns) + a 3-state `percentComplete` progress (Not started / In progress / Completed). You map GitHub Status → bucket and/or progress; lossy because Planner progress is tri-state.
- P4W/Premium has buckets and `msdyn_progress` (percent). Updating percent on **summary tasks** has side effects on dates — exclude summary tasks from progress writes.

**Assignee identity mapping — the hardest problem.** There is **no reliable bridge from a GitHub login to an Entra ID user.** GitHub assignees are GitHub handles; Planner/P4W assignments require an Entra object ID (GUID). You must build and maintain a mapping table. Email matching is unreliable: GitHub email can be private/noreply, and SAML/SCIM `NameID` is typically mapped to `user.mail`, not to the GitHub login. If the org runs **Entra→GitHub SCIM provisioning** or **Enterprise Managed Users (EMU)**, you can derive the mapping from the SCIM `externalId`/SAML identity — this is the only robust path, and it requires enterprise GitHub plus SCIM already in place. Absent that, expect a hand-maintained YAML map and unassigned-task fallbacks.

**Deletes / tombstoning.** GitHub issues are rarely hard-deleted (they close); Projects v2 items can be removed. Planner/P4W deletes are destructive and, in P4W, constrained (you cannot directly delete `msdyn_projectbucket`; deletion must route through PSS `msdyn_PssDeleteV1` in an OperationSet, and any user with the plan shared can delete an entire project). Design for **tombstoning, not deletion**: mark projected tasks completed/archived and keep a GitHub-id→task-id ledger so re-syncs don't duplicate.

**Comments.** Classic **Planner comments are backed by the Microsoft 365 group's Outlook group conversation** — Microsoft's own Planner concept overview confirms "Planner comments are based on Outlook group conversations" — not a first-class task field, so fidelity and threading are poor and app-only posting is awkward. P4W comments are a different Dataverse-backed mechanism. GitHub issue comments are markdown with reactions/edits. Treat comments as **non-syncable** in v1; at most, append a digest link back to the GitHub thread.

**Custom fields.** GitHub Projects v2 custom fields (text/number/date/single-select/iteration) have no clean Planner equivalent (classic Planner exposes a handful of named buckets/labels/`appliedCategories`). P4W custom fields can be added in Dataverse but, again, may not be queryable. Plan to project only a curated subset.

**Body / description — structural mismatch.** GitHub issue bodies are **markdown** (rich, arbitrarily long). Classic Planner task has a plain-text `description` plus checklist/references. **Project for the web tasks have NO rich body field at all — only a single `notes` field** (plain text). You will lose markdown rendering, images, task-lists, and code blocks. Strategy: render a plain-text/summarized digest into notes/description and **link** to the GitHub issue for the canonical body. Never treat Planner as the body of record.

### Classic vs Premium split
- **Classic:** GitHub→Planner projection is clean and **app-only** via Graph `Tasks.ReadWrite.All`. Bidirectional is technically possible (Planner change webhooks via Graph subscriptions) but adds reconciliation pain; only do it if PMs must edit in Planner.
- **Premium/P4W:** projection is possible but only through a **licensed-human relay** (Q5). Bidirectional is strongly discouraged — every write costs a PSS OperationSet round-trip under a licensed identity, with async persistence (the Project Scheduling Service "asynchronously writes the batch to Dataverse in a transaction" and marks the OperationSet Completed only on success) and documented ceilings of 200 operations per OperationSet and 10 open OperationSets per user.

## Q4 — Topologies (with classic-vs-Premium split)

| Topology | Owns create / lifecycle / rollup | Classic Planner | Premium / P4W | Failure modes | Operational cost |
|---|---|---|---|---|---|
| **A. GitHub is source of truth; mirror into Planner** | GitHub (via existing suite) owns truth; a **mirror worker** pushes to Planner. `eyrl` good fit for rollup projection | **app-only push** (Graph `Tasks.ReadWrite.All`) — clean | **licensed-identity relay** (PSS OperationSets) — projection only | Identity-map drift; bucket/status loss; markdown loss; webhook gaps | Low (classic) / Medium-High (Premium: license + token custody) | **Recommended** |
| **B. `plynth` creates board on either substrate; `mendrik` runs changesets on whichever substrate the board lives on** | `plynth` create; `mendrik` lifecycle — substrate-agnostic | feasible app-only; second backend adapter | `plynth` create via `msdyn_CreateProjectV1` + PSS; **all `mendrik` changesets need licensed human** | Two divergent backend adapters to maintain; Premium changesets can't run unattended/app-only | High — doubles backend surface; Premium breaks the declarative/unattended model | Viable only if Planner-native authoring is a hard requirement |
| **C. Planner-native: `plynth` creates plan directly; `mendrik` runs lifecycle directly against Planner** | `plynth`/`mendrik` target Planner as primary | possible app-only (Graph) | **Not viable as declarative/app-only.** Every create/update needs licensed human via PSS | Loses GitHub as dev-facing truth; Premium kills automation ergonomics; PSS async + limits | Highest on Premium; abandons GitHub-native workflow | **Not recommended** |
| **D. `eyrl` publishes portfolio/program rollups as Planner plans for leadership** | `eyrl` owns rollup generation + projection | app-only rollup plan — easy | licensed relay, but **bounded** (periodic, low-volume) writes fit relay model well | Stale rollups if relay token expires; PSS latency tolerable for daily cadence | Low-Medium; best ROI on Premium | **Recommended companion to A** |

**Recommendation:** **A + D.** GitHub remains authoritative; a mirror worker projects into Planner (app-only for classic, licensed relay for Premium); `eyrl` publishes leadership rollups. Avoid B and C on Premium — they require a licensed human in the loop for *every* lifecycle change, which is fundamentally incompatible with a declarative, unattended CLI suite.

### Tool-responsibility map (recommended A + D topology)

- **`plynth` (bootstrap):** Authoritative create remains on **GitHub** (Project v2 + Issues, app/PAT auth). For Planner projection it creates the *target* plan once: classic plan via Graph (app-only); Premium plan via `msdyn_CreateProjectV1` under the licensed relay identity. Writes the GitHub-id↔Planner-id ledger.
- **`mendrik` (lifecycle changesets):** Runs against **GitHub** as the system of record (unchanged). A **projection adapter** (not `mendrik` core) consumes GitHub webhooks/changesets and applies them downstream: classic via Graph batch; Premium by batching into PSS OperationSets (≤200 ops, ≤10 open sets/user) under the relay. Premium projection is **eventually consistent**, not transactional with GitHub.
- **`eyrl` (rollups):** Generates portfolio/program meta-boards from GitHub truth and **projects them into Planner for leadership visibility**. This is the primary sanctioned Premium write path — low-volume, scheduled, tolerant of PSS latency and the licensed-relay model.
- **Identity-map service (new shared component):** maintains GitHub-login → Entra-object-id mapping, ideally sourced from Entra↔GitHub SCIM/EMU. Shared by the projection adapter and `eyrl`.

## Q5 — The Licensed-Identity Relay for Premium/P4W (concrete comparison)

The hard constraint, from Microsoft Learn ("Use Project schedule APIs to perform operations with Scheduling entities," last updated 2026-01-31): the Project Schedule APIs "can only be used by Users with Microsoft Project License" and "can't be used by: Application users, System users, Integration users, other users that don't have the required license." An application/service-principal cannot be assigned a Project license (corroborated by CRM Chap, proMX, and MSDynamicsWorld, who note "the application user cannot be assigned a Microsoft Project license"), so app-only S2S auth is structurally impossible for Premium writes. OperationSet limits are documented verbatim: "Each OperationSet can only have up to 200 operations. Each user can only have up to 10 open OperationSets." Three relay options:

| Option | Cost | Security | Maintainability | Fit for declarative CLI suite |
|---|---|---|---|---|
| **(a) Operator-run CLI, device-code delegated auth → PSS directly** | 1 Project license for the operator | **Best secret hygiene** — no long-lived stored token; human present at run; interactive MFA | Simple; lives in same CLI codebase; but **requires a human to run it** | **Best architectural fit** for `plynth`/`eyrl` one-shot/scheduled-with-operator ops; **poor** for unattended continuous sync |
| **(b) Power Automate / Copilot Studio flow under a licensed service-account connection** | 1 Project license + Power Automate licensing for the service account | Connection stored in Power Platform (managed); service account needs Project license; MFA often must be relaxed → risk | Low-code; drifts from the CLI's declarative model; logic split across two systems | **Weakest fit** — moves logic out of the versioned CLI suite into clickops; hard to code-review |
| **(c) Hosted long-running worker holding a licensed user's refresh token** | 1 Project license for the service identity + hosting | **Highest risk** — storing a human's refresh token; needs vault, rotation, conditional-access carve-out; token revoked on password change | Most engineering; enables true unattended sync | Fits Topology A continuous projection, but custody burden is real |

**Recommended relay model:** a **dedicated licensed service-account** (a real Entra user, Project-licensed, used as a service identity — *not* an app registration) with credentials held in a secrets vault, used in one of two modes:
- For **`eyrl` rollups and `plynth` plan creation** (low-frequency, scheduled): prefer **(a)/(c) hybrid** — a hosted worker using that account's refresh token via the OAuth flow, with strict token custody (Key Vault, automated rotation, dedicated conditional-access policy, alerting on refresh failure).
- Avoid **(b)** as the primary engine; it fragments the declarative model. Use Power Automate only as a thin trigger if unavoidable.

Token-custody requirements are non-negotiable: vault storage, rotation, a break-glass for password/MFA resets that invalidate the refresh token, and monitoring. This is the single largest operational liability of targeting Premium and should be explicitly funded.

## Preview vs GA flags (date-stamped, 2026-05-29)
- **Microsoft Graph Planner API (classic):** **GA.** App-only `Tasks.ReadWrite.All` supported. *(Only basic plans.)*
- **Project Schedule APIs / PSS OperationSets (Premium/P4W writes):** Documentation URL still carries the legacy `schedule-api-preview` slug; the live page (last updated **2026-01-31**) no longer shows a preview banner and reads as a supported/production API, but **Microsoft publishes no explicit GA announcement.** Treat as **de-facto GA but formally unlabeled** — flag this to stakeholders as a stability caveat, since this surface changes frequently.
- **GitHub Projects v2 status updates via GraphQL + webhooks (`ProjectV2StatusUpdate`, `projects_v2_status_update`):** **GA** (shipped 2024).
- **Planner Premium custom fields in Dataverse:** queryability is **unreliable/undocumented** — validate per-environment before depending on it.
- **Power Automate Planner connector for Premium:** **unsupported** (basic only) — not a preview gap, a hard exclusion.

## Caveats
- "Planner Premium," "Project Plan 3," and "Project for the web" are the same Dataverse/PSS-backed engine under shifting branding; Microsoft's renames mean docs and connectors lag. Re-verify connector tier support before each release.
- The licensed-human write constraint is the crux: it makes Premium fundamentally hostile to declarative, app-only provisioning. Any plan that ignores this will fail in production with `0x80040265` / permission errors.
- Custom-field and comment fidelity are environment-dependent; do not promise round-trip fidelity.
- Identity mapping (GitHub↔Entra) is the silent project-killer; without SCIM/EMU it is a perpetual manual burden.
- Secondary sources (community blogs by Pajunen, Kabir Barker; ITtrip) corroborate first-party docs on PSS mechanics but are not authoritative for licensing — the binding statements are the Microsoft Learn schedule-API and Graph Planner pages.