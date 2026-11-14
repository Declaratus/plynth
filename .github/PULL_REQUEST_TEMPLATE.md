## Summary

<!-- What does this PR do and why? Link to the issue it resolves if applicable.
     Fixes #<issue> -->

## Changes

<!-- Bullet list of what changed. -->

-

## Testing

<!-- How was this tested? Check all that apply. -->

- [ ] New unit tests added (`tests/`)
- [ ] Existing tests pass (`pytest -q`)
- [ ] Tested manually against a live instance (describe below)
- [ ] No testable behaviour change (docs, config, refactor)

<!-- If manually tested, describe what you tested: -->

## Checklist

- [ ] `ruff check .` passes
- [ ] `ruff format --check .` passes
- [ ] `mypy plynth` passes
- [ ] PR title is a Conventional Commit (`feat:`, `fix:`, `docs:`, ...); for `feat`, `fix`, `perf`, `revert` and `deps` it becomes the changelog entry
- [ ] No `--token` flag with a literal value committed in any YAML, shell script, or workflow file
- [ ] No `PLYNTH_TOKEN` value committed (only references such as `${{ secrets.PLYNTH_TOKEN }}` are OK)
