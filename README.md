# Deep Loop

**v8.0.0** | Autonomous development loop for Claude Code

A deterministic, self-correcting development protocol with multi-agent BUILD phase, TDD enforcement, and senior dev mode.

## Features

- **Multi-Agent BUILD**: Fresh context per atomic task, parallel execution (up to 3)
- **TDD Enforcement**: RED → GREEN → REFACTOR for every task
- **Senior Dev Mode**: Challenge assumptions, adversarial self-review
- **External Loop**: Overnight/autonomous execution support
- **Task Sync**: Crash recovery via Claude Code task management
- **Atlas MCP Integration**: Optional context gathering

## Installation

```bash
# Install from GitHub
claude plugins install marcusgoll/deep-loop-plugin

# Or add to your Claude Code settings manually
```

### Manual Installation

1. Clone to your plugins directory:
```bash
cd ~/.claude/plugins/marketplaces/local/plugins/
git clone https://github.com/marcusgoll/deep-loop-plugin.git deep-loop
```

2. Restart Claude Code or run `/plugins refresh`

## Usage

```bash
# Start a deep loop session
/deep implement user authentication

# Quick mode for small fixes
/deep quick fix typo in README

# Check status
/deep-status

# Cancel active session
/cancel-deep
```

## Loop Phases

```
PLAN → BUILD → REVIEW → FIX → SHIP
```

1. **PLAN**: Assumptions preview, detailed plan with acceptance criteria
2. **BUILD**: Multi-agent TDD execution, atomic commits
3. **REVIEW**: Automated validation (test, lint, types, build)
4. **FIX**: Address issues found in review
5. **SHIP**: E2E verification, PR creation, merge

## Configuration

### Environment Variables

```bash
# Enable Task Sync for crash recovery
export DEEP_LOOP_TASKS_ENABLED=true
```

### state.json Options

```json
{
  "mode": "internal",      // "internal" (default) or "external"
  "buildMode": "multi-agent", // "multi-agent" (default) or "single"
  "maxParallel": 3,        // Max concurrent task agents
  "maxIterations": 10      // Safety limit
}
```

## Philosophy

> **This codebase will outlive you.**

Every shortcut becomes someone else's burden. Every hack compounds into technical debt. Fight entropy. Leave the codebase better than you found it.

## Skills Included

| Skill | Description |
|-------|-------------|
| `/deep` | Full deep loop with planning |
| `/deep-quick` | Quick mode (3 iterations, no planning) |
| `/deep-status` | Rich status display |
| `/cancel-deep` | Cancel active session |
| `/start-ralph` | PRD-driven autonomous mode |
| `/cancel-ralph` | Cancel ralph mode |

## License

MIT
