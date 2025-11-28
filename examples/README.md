# Grind Loop Examples

## example-tasks.yaml

Single file showing task definitions from simple to complex:
- Basic task (just essentials)
- Standard task (with hooks)
- Complex task (with custom prompts)

**Usage**:
```bash
uv run grind.py batch examples/example-tasks.yaml
```

**Or copy and modify**:
```bash
cp examples/example-tasks.yaml my-tasks.yaml
# Edit my-tasks.yaml
uv run grind.py batch my-tasks.yaml
```

## Generating Your Own

Instead of manually creating task files, use the `/generate-tasks` slash command:

1. Start a conversation with Claude Code
2. Discuss your problems, goals, or issues
3. Type `/generate-tasks`
4. Claude will analyze context and generate a task file

Example conversation:
```
User: I have 47 failing tests and ruff is complaining about 200 issues
User: /generate-tasks

Claude: I'll generate a tasks.yaml file based on our discussion...
[Generates optimized task file with proper model selection]
```

## Tips

- Start with simple tasks
- Add hooks as needed
- Use haiku for simple tasks (cheap, fast)
- Use sonnet for most work (balanced)
- Use opus for complex tasks (powerful, expensive)
