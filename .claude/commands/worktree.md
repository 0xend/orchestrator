# /worktree

Manage git worktrees for parallel implementation threads.

## Create

```bash
./scripts/worktree create <plan-name-or-path> <branch-name>
```

## List

```bash
./scripts/worktree list
```

## Remove

```bash
./scripts/worktree remove <name-or-path>
```

## Notes

- Port offsets are tracked in `~/.orchestrator-worktree-ports`.
- Startup metadata is read from `repos.yaml` and mirrored into `.worktree.startup.env`.
- Use `--no-setup` to skip dependency installation.
