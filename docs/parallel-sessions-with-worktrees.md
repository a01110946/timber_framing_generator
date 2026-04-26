# Parallel Claude Code Sessions with Git Worktrees

## The Problem

You want to work on multiple features simultaneously, each with its own Claude Code session and its own branch. But all sessions share the same directory, so they all see the same branch.

## The Solution: Git Worktrees

Git worktrees let you check out multiple branches into **separate directories** while sharing the same Git history and remotes. Each Claude Code session runs in its own directory, on its own branch, with zero interference.

```
timber_framing_generator/          <-- main repo (e.g., on 'main')
../tfg-mep-routing/                <-- worktree on 'feature/mep-routing'
../tfg-sheathing-fix/              <-- worktree on 'fix/sheathing-overlap'
../tfg-cfs-bridging/               <-- worktree on 'feature/cfs-bridging'
```

Each directory is a full working copy. You can open a terminal in each, run `claude`, and they're completely independent.

## Quick Reference

### Create a worktree

```bash
# New branch from current HEAD
git worktree add ../tfg-my-feature -b feature/my-feature

# New branch from main
git worktree add ../tfg-my-feature -b feature/my-feature main

# Existing branch
git worktree add ../tfg-my-feature feature/my-feature
```

**Naming convention**: Use `tfg-` prefix (timber framing generator) so worktree directories are easy to identify.

### Set up the worktree environment

```bash
cd ../tfg-my-feature
uv pip install -e .
```

### Start a Claude Code session in the worktree

```bash
cd ../tfg-my-feature
claude
```

Use `/rename` inside the session to label it (e.g., "MEP Routing", "Sheathing Fix").

### List all worktrees

```bash
git worktree list
```

### Remove a worktree (after merging)

```bash
# From any worktree or the main repo
git worktree remove ../tfg-my-feature

# If there are untracked files, force remove
git worktree remove --force ../tfg-my-feature
```

### Prune stale worktree references

```bash
git worktree prune
```

## Full Workflow Example

```bash
# 1. You're in the main repo, on 'main'
cd ~/Documents/GitHub/timber_framing_generator

# 2. Create worktrees for two features
git worktree add ../tfg-mep-routing -b feature/mep-routing main
git worktree add ../tfg-sheathing-fix -b fix/sheathing-overlap main

# 3. Set up environments
cd ../tfg-mep-routing && uv pip install -e .
cd ../tfg-sheathing-fix && uv pip install -e .

# 4. Open Terminal 1
cd ../tfg-mep-routing
claude
# Inside session: /rename MEP Routing

# 5. Open Terminal 2
cd ../tfg-sheathing-fix
claude
# Inside session: /rename Sheathing Fix

# 6. Work independently in each session...

# 7. When done, merge and clean up
cd ~/Documents/GitHub/timber_framing_generator
git worktree remove ../tfg-mep-routing
git worktree remove ../tfg-sheathing-fix
```

## Session Management Tips

### Resuming sessions

When you restart Claude Code in a worktree directory, the session picker shows previous sessions. Useful shortcuts:

| Key | Action |
|-----|--------|
| Up/Down | Navigate sessions |
| `B` | Filter to current branch |
| `Enter` | Resume selected session |
| `R` | Rename session |
| `/` | Search sessions |
| `P` | Preview session content |

### Context management

- `/compact` -- Compress context when it gets large
- `/clear` -- Reset context for unrelated tasks within a session

### What's shared vs isolated

| Shared across all worktrees | Isolated per worktree |
|---|---|
| Git history and remotes | Working files |
| `~/.claude/CLAUDE.md` (global instructions) | Branch and HEAD |
| `~/.claude/projects/*/memory/` (session memory) | Installed packages (if using venvs) |
| | Claude Code conversation context |

Note: The project `CLAUDE.md` is checked into the repo, so each worktree gets its own copy. Edits in one worktree won't appear in others until merged.

## Common Gotchas

### Can't check out the same branch in two worktrees

Git prevents this by design. If you need the same branch in two places, create a new branch from it:

```bash
git worktree add ../tfg-experiment -b feature/experiment feature/original
```

### Forgetting to install dependencies

Each worktree is a fresh directory. Always run `uv pip install -e .` after creating one.

### Stale worktrees after deleting directories

If you delete a worktree directory manually (instead of `git worktree remove`), run:

```bash
git worktree prune
```

### Branch cleanup after merge

After merging and removing the worktree, delete the branch:

```bash
git branch -d feature/my-feature        # safe delete (must be merged)
git branch -D feature/my-feature        # force delete
```
