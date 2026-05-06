from __future__ import annotations

import re
from datetime import date, timedelta

from plynth.models.instance import InstanceConfig
from plynth.models.plan import (
    ExecutionPlan,
    ResolvedField,
    ResolvedFieldOption,
    ResolvedIssue,
    ResolvedMilestone,
)
from plynth.models.template import KNOWN_OPTION_COLORS, TemplateDefinition

# Matches {PREFIX}-### patterns in issue bodies (cross-references).
_CROSSREF_RE = re.compile(r"\{PREFIX\}-(\d{3})")


def resolve_placeholders(
    text: str,
    values: dict[str, str],
    *,
    preserve_crossrefs: bool = False,
) -> str:
    """Replace {KEY} tokens with values from the instance config.

    When *preserve_crossrefs* is True, ``{PREFIX}-###`` patterns are left
    intact so that Phase 5 can resolve them to real issue numbers later.
    """
    if preserve_crossrefs and "PREFIX" in values:
        saved: dict[str, str] = {}

        def _save(match: re.Match[str]) -> str:
            key = f"__CROSSREF_{match.group(1)}__"
            saved[key] = match.group(0)
            return key

        text = _CROSSREF_RE.sub(_save, text)

    for key, value in values.items():
        text = text.replace(f"{{{key}}}", value)

    if preserve_crossrefs:
        for key, original in saved.items():
            text = text.replace(key, original)

    return text


def _calculate_due_date(start_date_str: str | None, offset_weeks: int) -> str | None:
    if start_date_str is None:
        return None
    start = date.fromisoformat(start_date_str)
    return (start + timedelta(weeks=offset_weeks)).isoformat()


def plan(template: TemplateDefinition, instance: InstanceConfig) -> ExecutionPlan:
    """Build a fully resolved execution plan from template + instance config.

    Pure computation — no API calls. Validates placeholder coverage, computes
    effective milestone/issue lists, resolves placeholders, trims dependency
    graph, and returns an ``ExecutionPlan`` ready for the API phases.
    """
    values = instance.values
    warnings: list[str] = []

    # ── Step 1: Validate placeholder coverage ──────────────────────
    missing = [
        key
        for key, spec in template.placeholders.items()
        if spec.required and (key not in values or not values[key])
    ]
    if missing:
        raise ValueError(f"Missing required placeholder values: {', '.join(sorted(missing))}")

    # ── Step 2: Effective milestones ───────────────────────────────
    skip_ms = set(instance.skip_milestones)
    resolved_milestones = [
        ResolvedMilestone(
            id=m.id,
            title=resolve_placeholders(m.title, values),
            description=resolve_placeholders(m.description, values),
            due_date=_calculate_due_date(instance.start_date, m.due_offset_weeks),
        )
        for m in template.milestones
        if m.id not in skip_ms
    ]

    # ── Step 3: Effective issues ───────────────────────────────────
    skipped_by_milestone = {i.template_id for i in template.issues if i.milestone_id in skip_ms}
    skipped_individually = set(instance.skip_issues)

    skipped_by_pruning: set[str] = set()
    if instance.pruning_decision and template.pruning:
        decision_field = template.pruning.decision_field
        chosen_value = instance.pruning_decision.get(decision_field)
        if chosen_value:
            for rule in template.pruning.rules:
                if rule.field_value == chosen_value:
                    skipped_by_pruning = set(rule.remove_issues)
                    break

    all_skipped = skipped_by_milestone | skipped_individually | skipped_by_pruning
    effective_issues = [i for i in template.issues if i.template_id not in all_skipped]
    valid_ids = {i.template_id for i in effective_issues}

    # ── Step 4 & 5: Resolve placeholders + trim deps ──────────────
    resolved_issues: list[ResolvedIssue] = []
    for issue in effective_issues:
        # Field precedence: template defaults → per-issue → instance overrides.
        # Last writer wins per key. Instance overrides remain top precedence so
        # operators can still patch a single instance without editing the template.
        fields: dict[str, str] = {}
        fields.update(template.defaults.fields)
        fields.update(issue.fields)
        if issue.template_id in instance.field_overrides:
            fields.update(instance.field_overrides[issue.template_id])

        # Resolve placeholders in field option values
        resolved_fields = {k: resolve_placeholders(v, values) for k, v in fields.items()}

        # Trim dependency graph
        good_bb: list[str] = []
        skip_bb: list[str] = []
        for ref in issue.blocked_by:
            if ref in valid_ids:
                good_bb.append(ref)
            else:
                skip_bb.append(ref)
                warnings.append(
                    f"Issue {issue.template_id}: blocked_by ref '{ref}' "
                    f"was skipped (milestone excluded or individually skipped)"
                )

        good_bl: list[str] = []
        skip_bl: list[str] = []
        for ref in issue.blocks:
            if ref in valid_ids:
                good_bl.append(ref)
            else:
                skip_bl.append(ref)
                warnings.append(f"Issue {issue.template_id}: blocks ref '{ref}' was skipped")

        resolved_issues.append(
            ResolvedIssue(
                template_id=issue.template_id,
                title=resolve_placeholders(issue.title, values),
                body=resolve_placeholders(issue.body, values, preserve_crossrefs=True),
                milestone_id=issue.milestone_id,
                fields=resolved_fields,
                blocked_by=good_bb,
                blocks=good_bl,
                skipped_blocked_by=skip_bb,
                skipped_blocks=skip_bl,
            )
        )

    # ── Step 6: Resolve field options ──────────────────────────────
    # Pre-flight option colors against the GHES floor. Out-of-set colors get
    # downgraded to GRAY with a warning so the run completes against any
    # supported version. Templates authored against newer GHES that adds
    # colors will degrade gracefully on the 3.19 floor.
    resolved_field_defs: list[ResolvedField] = []
    for f in template.fields:
        opts: list[ResolvedFieldOption] = []
        for opt in f.options:
            color = opt.color
            if color is not None and color not in KNOWN_OPTION_COLORS:
                warnings.append(
                    f"Field '{f.id}' option '{opt.value}': color '{color}' not in "
                    f"the supported set {sorted(KNOWN_OPTION_COLORS)}; using GRAY"
                )
                color = "GRAY"
            opts.append(
                ResolvedFieldOption(
                    value=resolve_placeholders(opt.value, values),
                    color=color or "GRAY",
                    description=resolve_placeholders(opt.description, values),
                    default=opt.default,
                )
            )
        resolved_field_defs.append(ResolvedField(id=f.id, name=f.name, type=f.type, options=opts))

    # ── Step 8: Resolve project description ({DATE}) ──────────────
    project_desc = instance.project.description.replace("{DATE}", date.today().isoformat())

    # ── Step 9: Assemble ───────────────────────────────────────────
    return ExecutionPlan(
        template_name=template.template.name,
        template_version=template.template.version,
        instance_org=instance.org,
        instance_repo=instance.repo.name,
        target=instance.target,
        project_name=instance.project.name,
        project_description=project_desc,
        status_options=list(template.status),
        fields=resolved_field_defs,
        milestones=resolved_milestones,
        issues=resolved_issues,
        views=list(template.views),
        placeholder_values=dict(values),
        skipped_milestones=sorted(all_skipped_milestones(skip_ms, template)),
        skipped_issues=sorted(all_skipped),
        warnings=warnings,
    )


def all_skipped_milestones(skip_ms: set[str], template: TemplateDefinition) -> list[str]:
    """Return milestone IDs that were actually skipped (exist in template)."""
    return [m.id for m in template.milestones if m.id in skip_ms]


# ── Dry-run formatter ─────────────────────────────────────────────


def format_dry_run(ep: ExecutionPlan) -> str:
    """Return a human-readable summary of the execution plan."""
    lines: list[str] = []
    w = lines.append

    w("=== plynth Execution Plan ===")
    w(f"Template: {ep.template_name} ({ep.template_version})")
    target_display = ep.target if ep.target else "github.com"
    w(f"Target:   {target_display} / {ep.instance_org} / {ep.instance_repo}")
    w(f"Project:  {ep.project_name}")
    w("")

    # Milestones
    w(f"Milestones ({len(ep.milestones)}):")
    for m in ep.milestones:
        due = f" (due: {m.due_date})" if m.due_date else ""
        w(f"  {m.id}: {m.title}{due}")
    w("")

    if ep.skipped_milestones:
        w(f"Skipped milestones: {', '.join(ep.skipped_milestones)}")
    if ep.skipped_issues:
        w(f"Skipped issues ({len(ep.skipped_issues)}): {', '.join(ep.skipped_issues)}")
    if ep.skipped_milestones or ep.skipped_issues:
        w("")

    # Issues
    w(f"Issues ({len(ep.issues)}):")
    for iss in ep.issues:
        # Find priority for display
        priority = iss.fields.get("priority", "")
        p_short = priority.split(" ")[0] if priority else ""
        p_tag = f" [{p_short}]" if p_short else ""
        w(f"  {iss.template_id}: {iss.title} [{iss.milestone_id}]{p_tag}")

        bb_parts: list[str] = list(iss.blocked_by)
        for ref in iss.skipped_blocked_by:
            bb_parts.append(f"~~{ref}~~ (skipped)")
        bl_parts: list[str] = list(iss.blocks)
        for ref in iss.skipped_blocks:
            bl_parts.append(f"~~{ref}~~ (skipped)")
        bb_str = ", ".join(bb_parts) if bb_parts else "(none)"
        bl_str = ", ".join(bl_parts) if bl_parts else "(none)"
        w(f"       blocked_by: {bb_str} | blocks: {bl_str}")
    w("")

    # Fields
    w(f"Fields ({len(ep.fields)}):")
    for f in ep.fields:
        n_colored = sum(1 for o in f.options if o.color != "GRAY")
        suffix = f", {n_colored} colored" if n_colored else ""
        w(f"  {f.id}: {f.name} [{f.type}] ({len(f.options)} options{suffix})")
    w("")

    # Warnings
    if ep.warnings:
        w(f"Warnings ({len(ep.warnings)}):")
        for warn in ep.warnings:
            w(f"  \u26a0 {warn}")
        w("")

    # API call estimate
    n_issues = len(ep.issues)
    n_milestones = len(ep.milestones)
    n_field_values = sum(len(i.fields) for i in ep.issues)
    n_deps = sum(len(i.blocked_by) for i in ep.issues)
    n_body_updates = n_issues
    n_add_to_project = n_issues
    total = n_milestones + n_issues + n_add_to_project + n_field_values + n_body_updates + n_deps

    w("API call estimate:")
    w(f"  Milestones:     {n_milestones} REST calls")
    w(f"  Issues:         {n_issues} GraphQL createIssue calls")
    w(f"  Add to project: {n_add_to_project} GraphQL addProjectV2ItemById calls")
    w(
        f"  Field values:   {n_field_values} GraphQL updateProjectV2ItemFieldValue calls"
        f" ({n_issues} issues \u00d7 {len(ep.fields)} fields)"
    )
    w(f"  Body updates:   {n_body_updates} GraphQL updateIssue calls (cross-ref resolution)")
    w(f"  Dependencies:   {n_deps} GraphQL addBlockedBy calls")
    w(f"  Total:          ~{total} mutating calls (~{total}s at 1s delay)")

    return "\n".join(lines)
