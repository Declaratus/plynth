# Evaluation: Microsoft "Planner and Project Plan 3" (Project for the web / Planner Premium) as a plynth backend

*Status: Evaluation — date 2026-05-28. Microsoft Dataverse / Project Schedule API endpoints, permissions, and limits change frequently; re-verify against learn.microsoft.com before implementation.*

> **Strategic note.** Planner & Project Plan 3 (this surface) is the **intended production target** for Microsoft 365 deployments. This evaluation finds it currently **not buildable** under plynth's headless app-only model — see the verdict. The classic-Planner evaluation (`evaluation-ms-planner.md`) covers the lower-fidelity surface that *is* buildable today.

## Verdict (≤200 words)

**P4W/Plan 3 can technically express 7 of plynth's 8 primitives, but it is NOT a viable production backend for plynth as currently architected — because of one hard blocker: the Project Schedule APIs (the only supported way to create projects, tasks, and dependencies) explicitly cannot be called by application users / service principals.** Microsoft Learn states: *"Only Users with Microsoft Project License can use the Project Schedule APIs. The following users can't use these APIs: Application users; System users; Integration users."* This restriction is still live as of the 2026‑01‑31 doc revision. A headless CLI authenticating app‑only into Dataverse therefore cannot create tasks, dependencies, or assignments at all. The only workarounds — delegated/ROPC auth as a licensed human, or a Power Automate relay — are operationally ugly for a CLI.

Secondary problems compound this: writes are async (a 200‑task plan realistically takes minutes), UI‑created custom fields are stored as an opaque binary blob and are NOT API‑queryable, and access is environment‑wide (no per‑project scoping). Recommendation: do not build this now. Re‑evaluate only if Microsoft lifts the application‑user restriction. Effort if unblocked: ~2–3× the classic‑Planner backend.

---

## 1. API surface & authentication

**The product.** "Planner and Project Plan 3" was renamed from "Project Plan 3" in September 2024. Its premium plans are Project for the web (P4W) projects stored in Microsoft Dataverse and driven by the Project Scheduling Service (PSS), a multitenant Azure service. Data is not reachable through the Microsoft Graph `/planner` endpoints — Graph explicitly only supports basic plans. The supported programmatic surface is the Dataverse Web API (OData v4) plus the **Project Schedule APIs**, a set of unbound Dataverse custom actions ([Project schedule APIs](https://learn.microsoft.com/en-us/dynamics365/project-operations/project-management/schedule-api-preview)).

**Two write paths, only one supported.** Scheduling tables (`msdyn_project`, `msdyn_projecttask`, `msdyn_projecttaskdependency`, `msdyn_resourceassignment`, `msdyn_projectbucket`, `msdyn_projectteam`) cannot be written directly via the ordinary Dataverse `Create`/`Update` table operations. Attempting a direct update returns `0x80040265`: *"You cannot directly do 'Update' operation to 'msdyn_projecttask'. Try editing it through the Resource editing UI via Project."* The supported path is the Schedule APIs:

- **`msdyn_CreateProjectV1`** — creates a project + default bucket immediately (no OperationSet needed). GA.
- **`msdyn_CreateTeamMemberV1`** — creates a team member immediately. GA.
- **`msdyn_CreateOperationSetV1`** — opens an OperationSet (unit-of-work). GA.
- **`msdyn_PssCreateV1` / `msdyn_PssCreateV2`** — create scheduling entities inside an OperationSet. V2 supports multiple entities per call. GA.
- **`msdyn_PssUpdateV1` / `V2`**, **`msdyn_PssDeleteV1` / `V2`** — update/delete inside an OperationSet. GA.
- **`msdyn_ExecuteOperationSetV1`** (and a newer `ExecuteOperationSetV3` referenced in the performance docs) — commits the batch; PSS then asynchronously persists to Dataverse. GA.
- **`msdyn_AbandonOperationSetV1`** — discards an open OperationSet.

**GA vs preview.** The Schedule APIs reached general availability in Project Operations in 2021 (release 4.9.0.188). The doc page retains the legacy `schedule-api-preview` URL slug but is no longer labeled "preview" in body content (last updated 2026‑01‑31). The V2/V3 action variants and several entity additions (Project Goal, Project Label, bucket create/delete added in "Update Release 16") arrived later; treat the newest action versions as the recommended GA surface. **⚠️ Preview/recency flag:** the **Dataverse Recycle Bin / "restore deleted records"** feature used for recovery (Section 4) reached **GA in April 2026** per the 2026 Release Wave 1 plan — very recent.

**Authentication — the decisive blocker.** App-only (service principal) authentication into Dataverse is the normal pattern: register an Entra ID app, create a Dataverse **Application User** in the target environment, and assign it a security role ([Dataverse security roles](https://learn.microsoft.com/en-us/power-platform/admin/database-security)). Crucially, in Dataverse, *security roles* — not Entra API permission scopes — grant data access (the only relevant Dynamics scope is the `user_impersonation` delegated scope, which is irrelevant for app-only client‑credentials auth). So far, standard.

**However:** the Project Schedule APIs are explicitly restricted. The Microsoft Learn doc states verbatim: *"Only Users with Microsoft Project License can use the Project Schedule APIs. The following users can't use these APIs: Application users; System users; Integration users; Other users that don't have the required license."* This language is **still present in the live doc as of the 2026‑01‑31 revision** — it has not been lifted, and a 2024/2025/2026 search of release notes found no relaxation. Because a CLI authenticating app-only is, by definition, an Application User, **it cannot call `msdyn_CreateProjectV1`, `msdyn_PssCreateV1`, or `msdyn_ExecuteOperationSetV1` at all.** This is not a permissions-tuning problem; it is a categorical product restriction. A service principal can *read* scheduling tables via the Dataverse Web API, but cannot *write* via the only supported write API.

The implication: plynth's app-only model does not work. The only ways around it are (a) authenticate as a licensed human user via delegated/interactive or ROPC flows (carrying a Project Plan 1/3/5 license), which defeats the "headless CLI with a service principal" design; or (b) have the CLI write to a queue and let a Power Automate cloud flow — running under a licensed user connection — perform the Schedule API calls. Both are heavy.

**Scoping model.** Dataverse security is environment-wide and role-based, scoped to business units, not to individual projects. There is no native per-project access scoping for an application identity short of building owning-team/row-level sharing logic yourself. A principal with the relevant role over `msdyn_project` can see/act on all projects in that environment. So "give the CLI access to just one project" is not a built-in capability.

## 2. Capability map of the 8 plynth primitives

| # | plynth primitive | P4W/Plan 3 mapping | Status |
|---|---|---|---|
| 1 | Issues/tasks: title + body + labels | `msdyn_projecttask` (`msdyn_subject` = title). **No rich "body"/description field** equivalent to a GitHub issue body — P4W tasks have notes/checklists, not a markdown body. Labels via `msdyn_projectlabel` + `msdyn_projecttasktolabel` (labels are created on first project open; only renamable via API). | **Partial** |
| 2 | Milestones (grouping + due date) | A milestone is a **zero-duration task** (`msdyn_duration = 0`) on `msdyn_projecttask` — not a separate object and not a queryable boolean exposed in the P4W UI. Grouping is via summary tasks (`msdyn_outlinelevel` / `msdyn_parenttask`) or buckets (`msdyn_projectbucket`). | **Partial** |
| 3 | Project container | `msdyn_project` — first-class. Created via `msdyn_CreateProjectV1`. | **Full** (write blocked for app users) |
| 4 | Typed fields with options (single-select, iteration, number, date, text) | Two distinct mechanisms — see below. **UI-created custom fields are stored as a binary blob** and are not queryable. Enterprise-grade typed columns must be added to the Dataverse table as real columns. Iteration ≈ `msdyn_projectsprint` (sprints). | **Partial** |
| 5 | Default field values | Dataverse column-level default values exist for real custom columns; not for P4W UI custom fields. Achievable but set at schema-definition time, not per-run. | **Partial** |
| 6 | Placeholder text in bodies | No task "body" field to hold placeholder text (see #1). Could be jammed into a checklist/notes, but not a clean fit. | **Unsupported / awkward** |
| 7 | Cross-issue dependencies | `msdyn_projecttaskdependency` (predecessor/successor lookups). Native, Finish-to-Start via the standard model; advanced types (SS/FF/SF) exist for Plan 3/5 in the UI. Limits below. | **Full** (Finish-to-Start), with limits |
| 8 | Stable IDs for idempotent reruns | GUIDs are client-suppliable. The ID property on create is optional; if you supply it, PSS uses it (or throws if unusable), else it generates one. So you *can* assign stable GUIDs — but idempotence is complicated by async persistence (Section 4). | **Partial** |

### 2a. Milestones (detail)
P4W has **no dedicated "is milestone" boolean exposed to API writers**. A milestone is simply a task with `msdyn_duration = 0` (confirmed via Microsoft Tech Community/MVP guidance and the migration-lessons blog noting *"This is a milestone task (i.e. duration = 0)"*). The broader Common Data Model schema for the PSA/Project Operations `ProjectTask` entity does define an `isMilestone`/`msdyn_ismilestone` boolean described as "Show whether this task is a milestone," but in P4W the milestone state is driven by zero duration, not a user-set checkbox. plynth's "milestone with a due date" maps to a zero-duration task with a scheduled date — workable, but you lose the semantic distinction and grouping affordance that GitHub milestones provide. Migration gotcha: sending both start and finish *plus* duration on a zero-duration milestone task causes date recalculation; Microsoft's guidance is to send only one date plus duration.

### 2b. Typed custom fields (the "binary blob" claim — verified)
**The claim is TRUE for UI-created custom fields.** The official Project for the web FAQ states: *"Local custom fields are stored in a binary format within Project tables in Dataverse. These fields aren't available for reporting."* A Microsoft Q&A moderator response specific to Planner Premium adds that this data "is stored as a binary blob directly within the related Dataverse tables, such as `msdyn_project` and `msdyn_projecttask`… they are not exposed as individual, queryable columns." So custom fields created through the P4W/Planner UI are **opaque and not API-readable/writable as typed columns** — a fatal limitation for plynth's typed-field primitive if you rely on the UI mechanism.

**The escape hatch:** you can add *real* Dataverse columns (choice/optionset, integer, decimal, datetime, string) to the `msdyn_projecttask` / `msdyn_project` tables yourself via solution/schema customization. These ARE typed, queryable, settable and readable via the Schedule APIs ("Both out-of-box fields and custom fields are supported" per the performance doc; the sample code shows `task["new_custom1"]`, `task["new_age"]`, `task["new_amount"]`, `task["new_isready"] = new OptionSetValue(...)`). But these are environment-level schema changes (the "Maximum total custom fields for a project: 10" limit applies to the P4W-managed kind), not per-plan declarative fields, so plynth would have to manage Dataverse schema as a deployment step — far heavier than GitHub Project fields.

### 2c. Dependencies and documented limits (verified)
Per Microsoft Learn "Project for the web limits and boundaries":
- **20 links per task** — confirmed: "Maximum links (successor + predecessor): 20."
- **2000 dependencies per project** — confirmed: "Maximum total links (successor only) for a project: 2000."
- Other ceilings: **Maximum total tasks for a project: 3000**, **10 hierarchy levels**, **Maximum total resources for a project: 300**, **Maximum total custom fields for a project: 10**, **Maximum total goals for a project: 10**, dates 1/1/2000–12/31/2149.
- `msdyn_projecttaskdependency` supports **create and delete only — no update**: per the schedule-api-preview supported-operations table, *"Project task dependency records aren't updated. Instead, you can delete an old record and create a new record."*

## 3. Orchestration model (async PSS flow)

The flow for any task/dependency creation:
1. `msdyn_CreateProjectV1` → returns `ProjectId` immediately (also creates default bucket "Bucket 1").
2. `msdyn_CreateOperationSetV1(ProjectId, description)` → returns `OperationSetId`.
3. N × `msdyn_PssCreateV1`/`V2` (tasks, then dependencies, then assignments) added to the set. The response gives back the GUID even before execution.
4. `msdyn_ExecuteOperationSetV1(OperationSetId)` → PSS validates synchronously, then **asynchronously persists** to Dataverse.
5. Poll `msdyn_status` on the OperationSet until **Completed (192350003)**; Open = 192350000; a Failed state rolls back the whole batch.

**Documented limits** (verbatim from the schedule-api-preview Limitations section):
- *"Each user can only have up to 10 open OperationSets."* Exceeding it blocks further sets. An out-of-the-box "Project Service Core – Abandon Open Operation Sets" flow abandons open sets after 60 minutes.
- *"Each OperationSet can only have up to 200 operations."*
- **Dataverse service protection limits** (separate, per-user, 5-minute sliding window, per [Dataverse service protection API limits](https://learn.microsoft.com/en-us/power-apps/developer/data-platform/api-limits)): ~6,000 requests, ~20 min combined execution time, ~52 concurrent; 429 + Retry-After on breach. A `$batch` can hold up to 1,000 operations but each still counts as a request.

**Throughput reality (Microsoft's own benchmark doc, "Project schedule API performance").** Microsoft measured these by running operations on "a UR58 Project Operations Core distributed across North America, EMEA, and APAC," where *"Schedule API Duration"* = time taken by `ExecuteOperationSetV3` and *"Total Duration"* = "Schedule API duration + Project Save Service time + time taken to sync to Dataverse." The synchronous accept is fast (~1.5–4 s) but **Total Duration** is what matters:
- Single task create: required-fields ≈ **7.86 s**, all-fields ≈ **12.63 s**.
- Bulk create 100 tasks (one OperationSet): ≈ **15.96 s** (required) to **47.55 s** (all fields).
- Bulk create 100 dependencies: ≈ **41.29 s** (required) to **83.41 s** (all fields).
- Bulk update 100 tasks (all fields): ≈ **155.52 s**.

**A realistic 20→200-task plynth run:** tasks must be chunked into OperationSets of ≤200, and you'd typically split tasks / dependencies / assignments into separate sets (and order them — tasks must exist before their dependencies/parents). A 200-task plan with ~200 dependencies is roughly 2–3 OperationSets, each executing and persisting in tens of seconds, plus polling latency. Plan on **single-digit minutes end-to-end** for a 200-task plan, not seconds. There's also a known read-after-write lag: a task created via the API may not be returned by an immediate query for a few seconds. Microsoft's best practices: group operations, set only minimum required fields (foreign keys/rollups hurt performance), use the latest API versions.

## 4. Idempotence / reruns under async PSS

- **Stable, queryable IDs:** Yes — you may supply the GUID on create (`msdyn_projecttaskid`, etc.); PSS honors it or throws if unusable. After persistence completes, records are queryable by that GUID via the Dataverse Web API. This is the basis for idempotent reruns: keep a state file mapping plynth logical IDs → Dataverse GUIDs, and on rerun check existence before re-creating.
- **What is NOT idempotent / recoverable:** `msdyn_CreateProjectV1` and `msdyn_CreateTeamMemberV1` execute **immediately and outside any OperationSet**, so a crash after creating the project but before the task OperationSet executes leaves an orphan project (and an orphan default bucket). OperationSets are transactional (all-or-nothing on persist), so a *failed* set rolls back cleanly — but an *interrupted* client (process killed mid-poll) can leave the set Open/processing, counting against the 10-open limit until the 60-minute auto-abandon flow or an explicit `msdyn_AbandonOperationSetV1`. Project task dependencies cannot be updated, only delete+recreate — so "fixing" a dependency is not idempotent in place.
- **Delete/restore semantics:** Deletes go through `msdyn_PssDeleteV1`. Dataverse uses a soft-delete → hard-delete model **only if the Recycle Bin / "Keep deleted Dataverse records" feature is enabled** (configurable retention 1–30 days; restorable via UI or the `Restore` SDK message with `DataSource="bin"`). By default this is OFF — deleted rows are permanently gone and unrecoverable. Even when on, records deleted via cascade don't appear in the deleted-records view, and the feature only reached **GA in April 2026** (recent; flag). For plynth, treat deletes as destructive and never rely on restore.

## 5. Licensing mechanics

- **What Plan 3 grants for API access:** A "Planner and Project Plan 3" license entitles a *human user* to use P4W/Planner Premium and is what satisfies the "Users with Microsoft Project License" requirement for the Schedule APIs. **The calling identity that invokes the Schedule APIs must be a licensed human user, not the service principal.** The application user itself cannot satisfy this requirement (application users are categorically blocked regardless of license). So: the *human* needs Plan 1/3/5; the app-only principal is simply not allowed.
- **Environment & capacity:** P4W requires a Dataverse environment. First use auto-provisions the **default environment**; one Project license deploys to default, **five+** licenses are needed to deploy to dedicated Production/Sandbox environments (recommended for production — the default environment grants Environment Maker to everyone and can't be backed up/restored). Project data consumes Dataverse database capacity; custom tables/columns and audit logs consume additional capacity (audit log ~$10/GB/month).
- **Retirement dates (assessed):**
  - **Project Online retires September 30, 2026**; per Microsoft's "Microsoft Project Online is retiring" blog: *"October 1, 2025: End of sale for new customers for Project Online-only SKUs. September 30, 2026: Official retirement date… Starting April 1, 2026, current customers will no longer be able to create new tenants in Project Online."* This is a *separate, legacy, SharePoint-based product*. **It does NOT affect Project Plan 3 / Project for the web** — P4W is the *successor*, and Plan 3/5 licenses carry forward to Planner Premium.
  - **Planner and Project Plan 5 End of Sale May 1, 2026** — per Microsoft message-center notice MC1253809: *"End of Sale (Worldwide): Planner and Project Plan 5 will move to End of Sale on May 1, 2026… Planner and Project Plan 3 is the recommended supported SKU for customers who need desktop project management capabilities."*
  - **Net:** none of these retirements kill the P4W/Plan 3 + Dataverse + Schedule API stack plynth would target. Microsoft is consolidating *toward* it (Project for the web was retired as a standalone brand in August 2025 and absorbed into Planner Premium, same Dataverse backend). The platform is durable; the blocker in Section 1 is the problem, not platform longevity.

## 6. Relationship to the classic-Planner backend & plynth's contract

The prior classic-Planner backend design has three reusable structural pieces — and the reuse story is **mixed**:

- **`backend_capabilities` descriptor — fully reusable as a pattern, different values.** P4W's capability vector is almost the inverse of classic Planner: classic Planner *lacked* milestones, typed fields, and dependencies (the reasons it was a degraded v1); P4W *has* native dependencies, real (zero-duration) milestones, and real typed columns (if you manage schema). So the descriptor mechanism carries over directly, but every flag flips. This is the strongest argument that P4W is a genuinely *different* backend, not a variant of classic Planner.
- **State file for stable IDs — reusable concept, more important here.** Both backends need a logical-ID → remote-ID map for idempotent reruns. For P4W it's load-bearing because of async persistence and the non-idempotent immediate creates (project/team member). The file format carries over; the reconciliation logic must be more defensive (poll-for-completion, existence checks, orphan handling).
- **Client class — largely throwaway.** Classic Planner talks to Graph `/planner` with simple REST + ETags for optimistic concurrency. P4W talks to Dataverse OData *plus* the unbound Schedule API custom actions with the OperationSet lifecycle, GUID pre-assignment, async status polling, and a completely different auth story (and the app-user blocker). Almost none of the HTTP/transport/auth code survives.

**Is there a clean shared abstraction?** Only at the level of plynth's existing 8-primitive `Backend` interface. Below that, classic Planner and P4W are **two genuinely separate backends** sharing an interface and a state-file convention, not a common implementation. There is no meaningful shared client layer. Architecturally: keep the primitive interface and the state-file module as the seam; implement P4W as a fully independent backend. Do not try to subclass or share the Graph client.

## 7. Recommendation

**Do not build the P4W/Plan 3 backend now.** The application-user restriction on the Schedule APIs is a categorical blocker for a service-principal CLI: the only supported write path refuses app-only callers, and direct Dataverse table writes to scheduling entities are blocked by a platform plugin. plynth's core operating model (headless, app-only, idempotent reruns) is incompatible with this constraint today.

**Staged plan and the thresholds that change it:**
1. **Now:** Stop. Document P4W as "blocked on app-only auth." Keep classic Planner / GitHub as the shipping backends.
2. **Trigger to revisit (the single benchmark that matters):** Microsoft removes "Application users / System users / Integration users" from the Schedule API restriction list (watch the `schedule-api-preview` doc and Project release notes). If that happens, P4W becomes viable.
3. **If you must ship before then,** the least-bad bridge is a **Power Automate relay**: plynth writes a declarative plan to a Dataverse staging table (app-only is fine for ordinary tables), and a cloud flow running under a *licensed human* connection drains the queue via the Schedule APIs. This adds a stateful, licensed, human-tied component — acceptable only if a human Plan 3 license and a flow are tolerable in the deployment. Interactive/ROPC auth as a licensed user is the other option but breaks the headless model.
4. **Schema prerequisite for typed fields:** whichever path, ship a Dataverse solution that adds real typed columns to `msdyn_projecttask`/`msdyn_project` (don't use UI custom fields — they're binary blobs). This is a deploy-time step plynth must own.

**Effort sizing.** Relative to the existing GitHub Projects v2 backend (baseline 1×): the classic-Planner backend was simpler than GitHub in capability but similar in transport effort (~0.8–1×). The P4W backend, *if unblocked*, is **~2–3×** the classic-Planner backend: you add the OperationSet lifecycle, async status polling with read-after-write handling, GUID pre-assignment, orphan/abandon recovery, Dataverse schema management for typed fields, and a much more involved auth/licensing setup. If you must build the Power Automate relay bridge, add another large increment for the flow, the staging table, and the two-system reconciliation — pushing it well beyond 3×.

### Smallest plynth template YAML that materializes cleanly against Plan 3

> **Illustrative / proposed shape — does not parse against today's `plynth/models/template.py`.** Keys like `backend`, `environment`, `project`, `tasks`, and `dependencies` are a proposed future Dataverse-backend schema, not the current `template:` / `milestones:` / `issues:` model. Treat as pseudocode.

This sketch assumes (a) the app-user blocker is resolved or a licensed relay is in place, and (b) a Dataverse solution has pre-added the real typed column `cr123_risk` (choice) to `msdyn_projecttask`.

```yaml
# template.yaml — minimal P4W/Plan 3-compatible plan
backend: ms-planner-premium      # P4W / Dataverse / Schedule APIs
environment: https://org.crm.dynamics.com   # Dataverse environment URL (env-wide scope)

project:                          # -> msdyn_project (msdyn_CreateProjectV1)
  name: "Launch Plan"             # -> msdyn_subject
  schedule_mode: fixed_duration   # -> msdyn_schedulemode

fields:                           # typed custom fields = REAL Dataverse columns, not UI fields
  - logical_name: cr123_risk      # must already exist on msdyn_projecttask
    type: single_select           # Dataverse choice / OptionSet
    options: [Low, Medium, High]
    default: Low                  # column-level default

tasks:                            # -> msdyn_projecttask via msdyn_PssCreateV1 in an OperationSet
  - id: design                    # plynth logical id -> stable msdyn_projecttaskid GUID (state file)
    title: "Design"               # -> msdyn_subject
    duration_days: 5              # -> msdyn_duration (non-zero => normal task)
    fields:
      cr123_risk: Medium          # typed value: OptionSetValue

  - id: design_complete           # MILESTONE = zero-duration task
    title: "Design complete"
    duration_days: 0              # -> msdyn_duration = 0  (P4W milestone convention)
    depends_on: [design]          # cross-task dependency, Finish-to-Start

dependencies:                     # -> msdyn_projecttaskdependency (create-only; FS)
  - predecessor: design
    successor: design_complete
    type: finish_to_start         # -> msdyn_linktype
```

Notes baked into the sketch: there is **no `body:` field** because `msdyn_projecttask` has no GitHub-issue-style body (primitive #1/#6 limitation); the milestone is a zero-duration task (#2); the typed field references a pre-provisioned real Dataverse column, never a UI custom field (#4/#5); the dependency is Finish-to-Start, within the 20-per-task / 2000-per-project limits (#7); and `id` values map to client-assigned stable GUIDs persisted in plynth's state file (#8).

---

## Closing comparison: P4W/Plan 3 vs. the classic-Planner option

Classic Planner was rejected as a degraded v1 backend because it structurally cannot express milestones, typed custom fields, or dependencies. P4W/Plan 3 *solves all three of those modeling gaps* — it has native dependencies, zero-duration milestones, and (with schema work) real typed columns. On pure data-model fidelity, P4W is clearly the superior target and is the closest Microsoft product to plynth's GitHub-Projects feature set. **But it trades a capability problem for an access-and-operability problem that is worse for a CLI:** the only supported write API bans service principals, writes are async and slow (minutes for a 200-task plan), UI custom fields are unusable binary blobs, access is environment-wide with no per-project scoping, and deletes are destructive by default. Classic Planner is *buildable today* with app-only auth and synchronous, fast writes but *can't model the domain*; P4W *can model the domain* but *isn't buildable today* under plynth's auth model. Neither is a good production backend right now — and between them, P4W should be revisited (not adopted) the moment Microsoft lifts the application-user restriction.