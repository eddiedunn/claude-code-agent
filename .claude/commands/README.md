# Slash Commands

## Global Commands

Most slash commands live in `~/.claude/commands/` (global directory).

### API Tool Commands (in ~/.claude/commands/)

| Command | Purpose | Documentation |
|---------|---------|---------------|
| `/jenkins` | Analyze Jenkins build logs | `~/how_tos/jenkins/` |
| `/sonarqube` | Fix SonarQube issues | `~/how_tos/sonarqube/` |
| `/aap` | AAP API operations | `~/how_tos/ansible-automation-platform/` |

## Grind-Specific Commands (this repo)

### `/generate-tasks`

Generate a `tasks.yaml` file from the current conversation context.

**Usage:**
```
/generate-tasks
```

**What it does:**
1. Analyzes the current conversation
2. Identifies problems, goals, or issues discussed
3. Breaks them into actionable tasks
4. Generates a properly formatted `tasks.yaml` file

**Then run:**
```bash
uv run grind batch tasks.yaml
```

## Installation

The generate-tasks command should be copied to global:

```bash
cp .claude/commands/generate-tasks.md ~/.claude/commands/
```

## See Also

- API tool commands: `~/how_tos/.claude/commands/README.md`
- [Grind Features](../../FEATURES.md)
