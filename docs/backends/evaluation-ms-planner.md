# Backend Evaluation: Microsoft Planner as a plynth Backend

*Status: Evaluation — date 2026-05-28. Microsoft Graph endpoints, permissions, and limits change frequently; re-verify against learn.microsoft.com before implementation.*

> **Strategic context.** The intended production target for Microsoft 365 deployments is **Planner and Project Plan 3** (Planner Premium / Project for the web). This evaluation covers **classic Planner** (`/planner` Graph API) as a lower-cost **v1 stepping stone** to exercise the integration end-to-end; the Plan 3 / Premium backend (Dataverse + Project Schedule APIs) is the strategic goal and is the subject of a separate follow-up evaluation. See §7 for why Premium is not v1, and what a Premium backend additionally requires.

## Executive summary (verdict)

**Classic Planner (the `/planner` Graph API) is viable as a v1 plynth backend, but only as a deliberately degraded one — and three of plynth's eight primitives cannot be expressed natively.** Issues→tasks, the project container→plan, and stable IDs all map cleanly and are GA on Graph v1.0. But Planner has **no milestone object**, only **fixed boolean category labels** (no typed single-select/iteration/number/date custom fields), and **no task-dependency support whatsoever**. Dependencies and rich custom fields exist only in **Planner Premium / Project for the web**, which is **not on the Planner Graph API at all** — it lives in Dataverse behind the Project Schedule APIs (a completely different, partly-preview surface).

Two hard operational realities shape the implementation: every create lives under a **Microsoft 365 Group** (or a beta "roster" container), and **every PATCH/DELETE requires an ETag round-trip** (read-then-write), so Planner is chattier than GitHub. Application (app-only) permissions for Planner now exist (`Tasks.ReadWrite.All`), unblocking a CLI service principal — a relatively recent change (surfaced ~2023).

**Recommendation:** ship classic Planner as a capability-reduced backend with a `backend_capabilities` opt-out for milestones, typed fields, and dependencies. Do **not** target Project for the web for v1 — the Dataverse/Schedule-API surface roughly doubles the work. Implementation size: **comparable-to-larger** than the GitHub backend, driven by ETag choreography and Group prerequisites, not by primitive count.

---

## 1. API surface and auth

### Which surface this section covers
There are two distinct surfaces and they must not be conflated:

- **Classic Planner** = the `https://graph.microsoft.com/{v1.0|beta}/planner/*` endpoints (`plannerPlan`, `plannerBucket`, `plannerTask`, `plannerTaskDetails`, `plannerPlanDetails`). This is what people mean by "the Planner Graph API."
- **Planner Premium / Project for the web** = the same UX brand, but data stored in **Dataverse**, accessed via the **Dataverse Web API** and the **Project Schedule APIs** (`msdyn_*` tables, `msdyn_PssCreateV1`, etc.). **Premium plans and tasks are explicitly NOT available on the `/planner` Graph endpoints.** Microsoft's v1.0 docs (`planner-overview`): *"Premium plans and tasks aren't available on the Planner API in Microsoft Graph. Only basic plans may be accessed using this API."*

### Endpoints (classic Planner) and GA status

| Object | Endpoint | v1.0 GA? |
|---|---|---|
| Plans | `POST/GET /planner/plans`, `GET /groups/{id}/planner/plans` | GA v1.0 |
| Plan details (labels) | `GET/PATCH /planner/plans/{id}/details` | GA v1.0 |
| Buckets | `POST/GET /planner/buckets`, `GET /planner/plans/{id}/buckets` | GA v1.0 |
| Tasks | `POST/GET/PATCH/DELETE /planner/tasks`, `GET /planner/plans/{id}/tasks`, `GET /planner/buckets/{id}/tasks` | GA v1.0 |
| Task details (description, checklist, references) | `GET/PATCH /planner/tasks/{id}/details` | GA v1.0 |
| Assignments | property on `plannerTask` (`assignments` open type) | GA v1.0 |

**Beta-only features (flag):** **roster containers** (plans without a Microsoft 365 Group), **archive/unarchive**, **move plan to container**, **business scenarios**, **delta query** for Planner, and the task `notes`/HTML-rich-description (`microsoft.graph.itemBody`) field are beta. The `plannerTask` container types `plannerTask`, `teamsChannel`, and `roster` are documented on the **beta** overview. Everything plynth's core needs (plans, buckets, tasks, task details, plan details, assignments, labels) is **GA on v1.0**.

### Delegated vs application permissions

- **Delegated:** `Tasks.ReadWrite` (and historically `Group.ReadWrite.All`). The signed-in account must be a **member of the owning Group** to act on its plans.
- **Application (app-only):** `Tasks.ReadWrite.All` — this is the **only** Planner permission needed to create plans, buckets, tasks, and details app-only. `Tasks.Read.All` for read. Application permissions were a relatively recent addition; many older "app permissions not supported" posts (pre-2023) are now outdated. As Tony Redmond (Practical365) put it, after years of absence *"the Tasks.Read.All and Tasks.ReadWrite.All application permissions for the Planner Graph API turned up."*

**Critical for a CLI:** App-only plan/task creation **works** via client-credentials with `Tasks.ReadWrite.All`, into a **pre-existing** Microsoft 365 Group. The v1.0 "Create plannerPlan" reference lists Application = `Tasks.ReadWrite.All`. The doc note *"If the container is a Microsoft 365 group, the user who creates the plan must be a member of the group that contains the plan"* applies to the **delegated** flow (there is no user in app-only). Sean McAvinue (Practical365, 2023, "Automating Microsoft Planner Plan Creation with PowerShell"): *"Surprisingly, provisioning a Plan with application permissions only requires one permission: Tasks.ReadWrite.All."*

**Scope caveat:** there is **no `Sites.Selected` equivalent** for Planner. Microsoft Support (Microsoft Q&A, 2024): *"the application permissions Tasks.ReadWrite.All are global and allow access to all planners, not limited to individual planners. If you need access limited to individual planners, use delegated permissions."* App-only Planner access is **tenant-wide** — a meaningful security blast-radius for a CLI tool.

**Group creation:** if plynth must create the owning Group too, that needs the separate `Group.ReadWrite.All` **application** permission (`POST /groups`). Note `Group.ReadWrite.All` is **not** sufficient to create the plan itself — `Tasks.ReadWrite.All` is required. (PnP PowerShell issue #401 documents the classic mistake: a service principal granted only `Group.ReadWrite.All` got a 401 on plan creation; the fix is `Tasks.ReadWrite.All`.)

### Tenant / licensing requirements
- **Entra ID tenant + Microsoft 365** required. Classic Planner is included in most M365/Office 365 enterprise SKUs (E3/E5) with **no extra license**.
- **Personal Microsoft accounts are not supported** for Planner Graph.
- **Planner Premium** (the Project-for-the-web engine) requires a paid SKU: **Planner Plan 1**, or **Planner and Project Plan 3 / Plan 5**. Per Microsoft's Support FAQ, *"As of September 18, 2024, Project Plan 3 and Project Plan 5 have been renamed Planner and Project Plan 3 and Planner and Project Plan 5, respectively"* (and Project Plan 1 → Planner Plan 1 in April 2024). Premium data is in **Dataverse**; the **Project Schedule APIs require an appropriate Microsoft Project license**. The ecosystem is mid-transition: "Planner and Project Plan 5" moves to End of Sale on May 1, 2026, and Project Online retires September 30, 2026.

---

## 2. Capability mapping to plynth primitives

Verdicts: **native** / **workaround** / **not possible**. "Classic" = `/planner` Graph API (v1.0). "Premium" = Project for the web / Planner Premium via Dataverse.

| # | plynth primitive | Closest classic-Planner construct | Classic verdict | Premium (P4W) verdict |
|---|---|---|---|---|
| 1 | Issues/tasks (title, body, labels) | `plannerTask` (title) + `plannerTaskDetails.description` (body) + `appliedCategories` (labels) | **native** (body needs a 2nd call — see §3) | native (`msdyn_projecttask`) |
| 2 | Milestones (grouping + due date) | **No milestone object.** Closest = `bucket` (grouping, no date) OR task `dueDateTime` (date, not a group) | **workaround / not possible** as a true milestone | **native** — P4W has real milestone tasks + a Timeline |
| 3 | Project container | `plannerPlan`, **owned by a Microsoft 365 Group** (or beta roster) | **native (with Group prerequisite)** | native (`msdyn_project`) |
| 4 | Fields with options (single-select/iteration/number/date/text) | 25 boolean **category labels** per plan; fixed `priority` (0/1/3/5/9); fixed `percentComplete` (0/50/100); `dueDateTime`/`startDateTime` | **workaround (labels≈single-select only) / not possible** for iteration/number/text | **native** — P4W custom fields (but stored as a binary blob in Dataverse, hard to query) |
| 5 | Default field values (e.g. `Backlog` status) | No status field; `percentComplete` defaults to 0 (notStarted); no per-plan default mechanism | **workaround** (plynth sets values explicitly) | workaround |
| 6 | Placeholder/templating in body | `plannerTaskDetails.description` accepts the resolved string | **native** | native |
| 7 | Cross-issue dependencies | **None. Classic Planner has no task-dependency concept.** | **not possible** | **native** (Finish-to-Start via Project Schedule API) |
| 8 | Stable IDs | Plan/bucket/task/details IDs are durable, opaque, 28-char, queryable | **native** | native (GUIDs) |

### Notes on the hard cases

**Milestones (#2).** Planner genuinely has no milestone object. Options: (a) model each milestone as a **bucket** (gives grouping, loses the due date); (b) model it as a **task with a due date** (gives the date, loses "things belong to it"); (c) emulate "issue assigned to milestone" by putting the issue in the milestone's bucket and copying the milestone date onto each task's `dueDateTime`. None is a faithful mapping. Real milestones require Premium/P4W (which adds milestone tasks plus a Timeline/Gantt view).

**Fields (#4).** Planner's only general-purpose categorization is **`appliedCategories`** — `category1`…`category25`, each a **boolean**, with human-readable names defined once per plan in `plannerPlanDetails.categoryDescriptions`. This is at best a **multi-select of up to 25 fixed tags**, not a typed field system. A plynth single-select with N options ≤ 25 can be emulated by reserving N labels and setting one true. **There is no native iteration/sprint, number, or free-text custom field** in classic Planner. (`priority` and `percentComplete` are fixed-domain enums, not user-defined fields.) The 25-label cap is a **hard product limit**; per Microsoft Q&A, *"Microsoft Planner currently supports a maximum of 25 labels per plan. This is a fixed product limit and there is no documented way to increase it."* Documented footgun: **renaming a label changes it on every existing task in the plan**, because the name lives at plan level.

**Dependencies (#7).** Confirmed and citable: Microsoft Q&A — *"These endpoints are limited to 'classic' Planner plans and tasks and do not expose properties for advanced features like task dependencies, resource assignments, or custom fields."* Dependencies exist only in P4W, created via `msdyn_PssCreateV1` against a `msdyn_projecttaskdependency` row inside an **OperationSet** — a Dataverse-only path, and **only Finish-to-Start** is supported today (P4W documents up to 20 links per task / up to 2,000 successor links per project).

---

## 3. Required-workflow / orchestration constraints

### Rate limits and throttling
- Microsoft Graph does **not publish specific Planner service limits** — the throttling-limits doc literally states *"Service limits for Planner aren't available."* Planner is therefore governed by general Graph throttling: a **token-bucket** model returning **429 Too Many Requests** with a **`Retry-After`** header when exceeded.
- A correction worth internalizing: the often-quoted *"~10,000 requests per 10 minutes"* figure is the **Outlook** service limit (10,000 requests/10 min **plus a 4-concurrent-request cap**), **not** a Planner figure. Planner has no published numeric ceiling, so design for 429s rather than to a number. Writes are throttled more aggressively than reads.
- **Expected pattern for a 20–200-task run:** plynth will be fine on volume (200 tasks × ~3 calls each ≈ 600 calls), but should implement **`Retry-After`-respecting backoff with exponential fallback** when the header is absent. Do **not** auto-retry blindly — retries accrue against the quota and extend the throttle window.
- **Plan-count/size limits (classic, per Microsoft Learn "Microsoft Planner limits"):** **400 plans** owned by a group/user; **9,000 tasks** (incomplete + complete) per plan; **200 buckets** per plan; a task can be assigned to **a maximum of 11 people**; **1,500 tasks created per user**. (The older "250 active tasks per person per plan" limit has been removed.) These are irrelevant for typical plynth runs but worth a guard, especially the **11-assignee-per-task** cap.

### Batching
- Graph **`$batch` works for Planner endpoints** (Microsoft's own batch examples include `/me/planner/tasks`) but is capped at **20 sub-requests per batch**. Per Microsoft Learn: *"JSON batch requests are currently limited to 20 individual requests… Requests in a batch are evaluated individually against the applicable throttling limits and if any request exceeds the limits, it fails with a status of 429"* (while the batch envelope itself returns 200). You can order interdependent sub-requests with `dependsOn`, and up to four such batch requests can run concurrently against the same backend.
- **Gotcha:** batching does **not** relieve the ETag problem. A task body (`/details`) PATCH needs the details object's **own** ETag, which you only get by **GET-ing the freshly-created task's details first** — so the natural flow is create-task → GET details → PATCH details, a data dependency that `$batch` `dependsOn` only partially helps with (you can't feed one sub-response's ETag into a later sub-request in the same batch).

### ETag / If-Match semantics (the defining constraint)
Planner uses **aggressive optimistic concurrency**. From Microsoft's overview: *"All Planner API POST, PATCH, and DELETE requests require the If-Match header to be specified with the last known etag value."* In practice:
- **Every PATCH and DELETE requires a fresh `If-Match` ETag.** Omit it → **400**. Stale ETag → **409 Conflict** or **412 Precondition Failed**.
- The mandatory **read-then-write** pattern plynth must implement: `GET task/details` → extract `@odata.etag` → `PATCH` with `If-Match: <etag>` → on 409/412, re-GET and retry.
- The ETag comes back **weak** (`W/"..."`); SDKs/clients sometimes need to handle the `W/` prefix. plynth's client layer must store and refresh ETags per object.

### Eventual consistency
- A newly created `plannerTask` returns its ID and is **generally immediately addressable** for the follow-up `/details` PATCH and assignment PATCH — the standard create-then-patch-details flow is the documented norm.
- **But:** when you create a Group first (for the container), there is a **propagation delay** (minutes) before the group is usable as a plan container and before newly-added members can be assigned. Practitioners report needing to wait after group membership changes before Planner calls succeed. plynth should **create/verify the Group, then poll/backoff** before creating the plan.

---

## 4. Identity and assignment

- **Who can be assigned:** historically, assignees had to be **members of the owning Microsoft 365 Group**. The newer Planner experience can **add non-members as members when you assign them**, but the safe, deterministic assumption for a CLI is: **the assignee must be a Group member**, else expect failures or surprising side effects. Roster-contained (beta) plans gate on the roster member list instead.
- **User identity format:** assignments use the **Entra user object ID (GUID)**, not UPN or email. The `assignments` property is an **open type** keyed by the user's object ID, with a `plannerAssignment` value carrying `@odata.type` and a required `orderHint`:
  ```json
  "assignments": {
    "<user-object-id>": { "@odata.type": "#microsoft.graph.plannerAssignment", "orderHint": " !" }
  }
  ```
  This dynamic-key shape is a known source of SDK/client friction.
- **Resolving users:** plynth must resolve a human-friendly handle → object ID. Email/UPN → object ID is a single `GET /users/{userPrincipalName}` call (no extra permission beyond a directory read).
- **Template implication:** plynth's GitHub templates use GitHub handles. For Planner, the equivalent placeholder is a **UPN/email** that plynth resolves to an object ID at run time (Phase 1/2), then injects into the `assignments` open-type map. A `backend_capabilities`/identity-mapping section in the template is the clean way to keep templates backend-portable.

---

## 5. Idempotence and reruns

- **Template-node → backend-ID mapping is fully supported.** Plan, bucket, task, and details IDs are **durable, opaque, queryable** strings (28-char, case-sensitive) — exactly what `plynth/models/state.py` needs. plynth can store `{template_node: planner_id}` and re-fetch by ID on rerun.
- **Non-idempotent operations needing defensive logic:**
  - **Task creation is not idempotent** — POSTing the same task twice creates **two tasks**. plynth must check its state file / query existing tasks before creating, keyed by stored ID (there is no client-supplied idempotency key).
  - **All updates need a current ETag** — a rerun must **re-GET** to refresh ETags before patching, or it will 409/412.
  - **Label setup** (`categoryDescriptions`, a plan-level PATCH) must precede any task that references labels.
- **Soft vs hard delete (interrupted-run recovery):**
  - **Deleting a task is a HARD delete — there is no recycle bin and no recovery.** Microsoft Support ("Delete a task or plan"): *"There is no way to recover a deleted task. If you accidentally delete a task, you'll need to recreate it from scratch."* plynth's rollback/cleanup logic must be conservative: a half-finished run that deletes tasks **cannot undo** that.
  - **Deleting a plan directly is also unrecoverable** (no Planner recycle bin).
  - **The one safety net is at the Group level:** if the owning **Microsoft 365 Group** is deleted, it (and its plans/tasks) enters a **30-day soft-delete** and can be restored via `Restore-AzureADMSDeletedDirectoryObject` / the admin center (restore takes minutes to ~24h). Individual tasks/buckets deleted within a live plan are **not** recoverable.
  - **Practical guidance:** plynth's Planner backend should **prefer create/update over delete**, and never destructively "reset" a plan on rerun. If a run is interrupted mid-creation, the safe recovery is to **resume from the state file**, not to tear down.

---

## 6. Dealbreakers and "must accept"s

Capabilities plynth supports on GitHub that **cannot be expressed against classic Planner** without schema/behavior changes:

| GitHub capability | Classic Planner reality | Proposed resolution |
|---|---|---|
| **Cross-issue dependencies (blockers)** | **Not possible** in classic Planner at all | **(a) Drop + (c) declare.** Degrade gracefully; surface dependencies only as text in the task description ("Blocked by: X"). Add `backend_capabilities: {dependencies: false}`. For real dependencies, **(b) push to P4W/Premium**. |
| **Milestones as first-class objects with due dates that issues attach to** | No milestone object | **(c) declare + workaround.** Map milestone→bucket (grouping) and copy its date to each task's `dueDateTime`. Or **(b)** P4W for true milestones + Timeline. |
| **Typed custom fields: iteration/sprint, number, free text** | Only 25 boolean labels + fixed priority/percentComplete | **(a) drop / (c) declare.** Support single-select via labels (≤25 options); declare `fields: {iteration:false, number:false, text:false}`. **(b)** P4W for custom fields (but blob-stored, low queryability). |
| **Default field value = `Backlog` status (Phase 4)** | No status field; only `percentComplete` enum | **(a) degrade.** Map status→a reserved label or to percentComplete buckets (0/50/100); document that arbitrary default statuses aren't representable. |
| **Single API call per object** | ETag read-then-write + separate details call doubles round-trips | **Must accept.** Architectural; not a template change. Affects performance, not schema. |
| **Backend with no Group prerequisite** | Every plan needs a Microsoft 365 Group (or beta roster) | **Must accept / (c) declare.** Require a `group_id` (or opt into beta rosters) in the Planner backend config. |
| **Assign by handle/email directly** | Assign by Entra object ID; assignee must be Group member; max 11 assignees/task | **Must accept.** plynth resolves UPN→objectID and ensures Group membership at run time. |

**Recommended schema change:** add a **`backend_capabilities`** block to templates (option (c)) so a single template can declare which features are required vs optional, and the Planner backend can **fail fast** ("this template needs dependencies; Planner can't provide them") or **degrade** per a per-feature policy. This is cleaner than silently dropping features or maintaining backend-specific template forks.

---

## 7. Recommendation

### Is classic Planner viable as a v1 backend?
**Yes — only with these changes:** (1) add a `backend_capabilities` declaration so templates opt out of dependencies, milestones-as-objects, and typed fields on Planner; (2) implement the **ETag read-then-write** wrapper in the client layer; (3) require a **Microsoft 365 Group** (config-supplied `group_id`, or opt into beta rosters) as the plan container; (4) implement **UPN→object-ID** resolution and Group-membership checks for assignments; (5) make the backend **non-destructive on rerun** (no task deletes) because deletes are unrecoverable.

It is a **good fit for the "structured task board" subset** of plynth templates and a **poor fit for templates whose value is in dependencies, sprints, or typed fields.**

### Smallest plynth template that materializes cleanly against classic Planner

> **Illustrative / proposed shape — does not parse against today's `plynth/models/template.py`.** This sketch shows a *future* template (with the proposed `backend_capabilities` block, buckets, and assignees) to convey the mapping; the current schema uses `template:` / `milestones:` / `issues:` with `template_id` / `milestone_id`. Treat as pseudocode.

```yaml
# template.yaml — Planner-clean: tasks + buckets + label-as-single-select + due dates
backend_capabilities:
  dependencies: false        # classic Planner cannot express these
  milestones: bucket         # milestones modeled as buckets (+ due date on tasks)
  fields:
    single_select: label     # up to 25 options, emulated via appliedCategories
    iteration: false
    number: false
    text: false

project:
  container: { type: group, group_id: "${PLANNER_GROUP_ID}" }   # M365 Group required
  title: "Release ${release.version}"

buckets:                       # buckets stand in for milestones/phases
  - id: backlog
    name: "Backlog"
  - id: m1
    name: "Milestone 1 — Alpha"

fields:
  - id: area
    type: single_select       # → reserved category labels (categoryDescriptions)
    options: [api, ui, docs]   # ≤ 25

issues:
  - id: setup
    title: "Set up CI for ${repo.name}"
    body: "Resolved placeholder text goes in plannerTaskDetails.description"
    bucket: backlog            # = grouping
    due: "2026-06-15"          # → task dueDateTime
    labels: [area:api]         # → appliedCategories category1=true
    assignees: ["dev@contoso.com"]   # → resolved to Entra object ID (≤11/task)
```

Materialization order (maps onto plynth's `plynth/engine/phases.py`): validate/resolve → (ensure Group) → create plan → PATCH plan details (label names) → create buckets → create tasks → GET each task's details + PATCH description/labels (ETag) → set assignments. **No dependency phase.**

### If no — is Project for the web / Planner Premium the right target instead?
**Not for v1.** P4W/Premium gives you the missing primitives (real milestones, typed custom fields, Finish-to-Start dependencies, Timeline), but the eval changes drastically and **worsens** on integration cost:
- **Different API entirely:** Dataverse Web API + **Project Schedule APIs** (`msdyn_CreateProjectV1`, `msdyn_PssCreateV1`, OperationSets), **not** Graph `/planner`. plynth's Graph client doesn't transfer.
- **Async transactional model:** writes go through the **Project Scheduling Service (PSS)**, persisted to Dataverse **asynchronously** — you create an OperationSet, execute it, then **poll `msdyn_status` for Completed (192350003)**. Limits: max **10 open OperationSets/user**, **200 operations/OperationSet**, and parts are **preview**.
- **Licensing:** requires a paid **Project license** to even call the Schedule APIs; data sits in Dataverse with environment/capacity considerations.
- **Custom fields** are reportedly stored as a **binary blob** in `msdyn_project`/`msdyn_projecttask`, making them hard to set/read programmatically.

Recommendation: keep P4W as a **future "premium" backend** behind the same `backend_capabilities` mechanism, justified only if users specifically need dependencies + typed fields.

### Estimated implementation size vs the existing GitHub backend
**Comparable-to-larger** for classic Planner (`graphql_client`/`rest_client`/`phases` equivalents):
- **Larger because:** mandatory **ETag read-then-write** on every update (no GitHub analog); **two-step task creation** (task then details); **Group prerequisite + propagation waits**; **UPN→objectID + membership** resolution; open-type JSON shapes (`assignments`, `appliedCategories`) with `@odata.type`/dynamic-key quirks; non-idempotent creates needing state-guarded dedupe; throttling/`Retry-After` backoff.
- **Smaller because:** **fewer primitives to wire** (no dependency phase; fields reduce to labels), all on a **single REST/Graph surface** (no GraphQL+REST split like GitHub), and Microsoft's SDKs/snippets are plentiful.
- **Net:** the *primitive* surface is smaller, but the *protocol* surface (ETags, async group creation, two-step writes, tenant-wide auth) makes it **at least as much code** as the GitHub backend, likely **~1.2–1.5×**. P4W/Premium would be **roughly double** the GitHub backend due to the Dataverse/OperationSet/polling model.

---

## Where Planner sits relative to other candidates
Compared to plynth's existing GitHub backends, classic Planner is a **lower-fidelity target**: it nails issues, a project container, and stable IDs, but cannot express dependencies or typed fields and has no milestone object, while imposing an ETag-heavy, Group-anchored, tenant-wide-auth protocol. It is the right backend for organizations that live in Microsoft 365 and want plynth to populate a **task board**, not a dependency-aware project plan. Teams needing the full plynth feature set on Microsoft infrastructure should wait for (or sponsor) a Project-for-the-web/Premium backend, accepting roughly double the integration cost.