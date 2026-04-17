#!/usr/bin/env bash
# PreToolUse backstop for Bash commands.
# Static glob rules in settings.json cannot catch compound-command bypasses
# (50-subcommand CVE, pipe-to-shell, env-var exfiltration). This hook runs
# before the permission system and is not subject to those bypass patterns.
#
# Exit 2 = hard block (stderr shown to Claude as error feedback).
# Exit 1 = non-blocking error (command still runs) — do NOT use to block.
# Exit 0 = allow.
set -euo pipefail

COMMAND=$(python3 -c "import sys,json; d=json.load(sys.stdin); print(d['tool_input']['command'])")

# Block pipe-to-shell (50-subcommand bypass pattern, CVE-2026 series)
if echo "$COMMAND" | grep -qE '\|\s*(bash|sh|zsh|python[23]?)\b'; then
  echo "bash-guard: blocked pipe-to-shell — not permitted in automated pipeline" >&2
  exit 2
fi

# Block secret env var exfiltration
if echo "$COMMAND" | grep -qE '(ANTHROPIC_API_KEY|AWS_SECRET_ACCESS_KEY|GITHUB_TOKEN|OPENAI_API_KEY)'; then
  echo "bash-guard: blocked — command references a secret environment variable" >&2
  exit 2
fi

# Block ANTHROPIC_BASE_URL override (CVE-2026-21852 API key redirect pattern)
if echo "$COMMAND" | grep -qE 'ANTHROPIC_BASE_URL\s*='; then
  echo "bash-guard: blocked ANTHROPIC_BASE_URL override" >&2
  exit 2
fi

# Block bash network primitives (/dev/tcp, /dev/udp)
if echo "$COMMAND" | grep -qE '/dev/(tcp|udp)/'; then
  echo "bash-guard: blocked bash network primitive" >&2
  exit 2
fi

exit 0
