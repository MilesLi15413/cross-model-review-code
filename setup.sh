#!/usr/bin/env bash
# Setup script: install dependencies and clone LiveCodeBench

set -e

echo "=== Cross-Model Review Artifact Setup ==="

PYTHON_BIN=""
for candidate in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "${candidate}" >/dev/null 2>&1; then
    if "${candidate}" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)'; then
      PYTHON_BIN="${candidate}"
      break
    fi
  fi
done

if [ -z "${PYTHON_BIN}" ]; then
  echo "Python 3.10+ is required to run the benchmark harness."
  echo "Install a newer interpreter, then rerun ./setup.sh."
  exit 1
fi

PYTHON_VERSION="$(${PYTHON_BIN} -c 'import sys; print(".".join(map(str, sys.version_info[:3])))')"
echo "Using ${PYTHON_BIN}: ${PYTHON_VERSION}"

# Python deps
"${PYTHON_BIN}" -m pip install -r requirements.txt

# Clone LiveCodeBench
if [ ! -d "external/livecodebench" ]; then
  echo "Cloning LiveCodeBench..."
  git clone https://github.com/LiveCodeBench/LiveCodeBench external/livecodebench
  "${PYTHON_BIN}" -m pip install -e external/livecodebench
else
  echo "external/livecodebench already exists, skipping."
fi

# Verify CLIs
echo ""
echo "Verifying CLIs..."
if command -v claude &>/dev/null; then
  echo "  [ok] claude CLI found: $(claude --version 2>/dev/null || echo 'version unknown')"
else
  echo "  [missing] claude CLI not found. Install Claude Code: https://claude.ai/code"
fi

if command -v codex &>/dev/null; then
  echo "  [ok] codex CLI found: $(codex --version 2>/dev/null || echo 'version unknown')"
else
  echo "  [missing] codex CLI not found. Install Codex CLI: https://github.com/openai/codex"
fi

echo ""
echo "Test model access:"
echo "  claude --model claude-opus-4-7 --print --output-format json --no-session-persistence 'Reply exactly with OK'"
echo "  codex exec --model gpt-5.5 --skip-git-repo-check --json 'Reply exactly with OK'"
echo ""
echo "Use ${PYTHON_BIN} for benchmark commands unless your shell's python3 already points to 3.10+."
echo ""
echo "Setup complete."
