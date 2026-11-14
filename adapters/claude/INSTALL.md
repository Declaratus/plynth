# Claude Code Adapter Install

Copy or symlink this adapter into a project that uses Claude Code project skills:

```bash
cp -R adapters/claude/.claude ./
```

Keep the CLI available with an installed package:

```bash
pipx install plynth
```

The adapter ships the board workflow: the `board-spec` skill and the `board-reviewer` subagent in `.claude/agents/`. `board-spec` reads its full rules from `skills/codex/board-spec/` in a plynth checkout. `board-reviewer` reads live boards through the GitHub MCP server's Projects and issues tools and expects that server to be registered as `github`; if yours has another name, rename the `mcp__github__*` entries in its `tools` line. Keep that list to read tools so the reviewer stays read-only. The step-to-tool map, including the web-UI-only steps, is `skills/codex/board-spec/references/tool-map.md`.
