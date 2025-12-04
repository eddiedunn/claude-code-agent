# Installation

## Requirements

- Python 3.11 or higher
- [uv](https://docs.astral.sh/uv/) package manager
- Claude Code CLI installed

## Install uv

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

## Clone Repository

```bash
git clone https://github.com/eddiedunn/claude-code-agent
cd claude-code-agent
```

## Install Dependencies

```bash
uv sync
```

This will:
- Create a virtual environment
- Install all dependencies
- Set up the grind package

## Verify Installation

```bash
# Check CLI works
uv run grind.py --help

# Check package imports
uv run python -c "from grind import grind; print('Success!')"
```

## Development Installation

If you want to contribute:

```bash
# Install with dev dependencies
uv sync --all-extras

# Install pre-commit hooks
uv run pre-commit install
```

## Troubleshooting

### Python Version

Ensure you're using Python 3.11+:

```bash
python --version
```

If not, install via:
- [pyenv](https://github.com/pyenv/pyenv) (recommended)
- [Official Python](https://www.python.org/downloads/)

### uv Not Found

Add to your PATH:

```bash
export PATH="$HOME/.cargo/bin:$PATH"
```

### Import Errors

If you see `ModuleNotFoundError`, ensure you're using `uv run`:

```bash
# ❌ Wrong
python grind.py

# ✅ Correct
uv run grind.py
```

## Next Steps

- [Quick Start Guide](quickstart.md) - Run your first task
- [Features](../guide/features.md) - Learn all capabilities
