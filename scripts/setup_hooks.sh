#!/usr/bin/env bash
# Install git pre-push hook for AI log submission (POSIX / Git Bash).
# Run once after cloning: bash scripts/setup_hooks.sh
set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Support git worktrees by querying git for the hooks directory
GIT_HOOK_DIR="$(git -C "$REPO_ROOT" rev-parse --git-path hooks 2>/dev/null || true)"
if [ -n "$GIT_HOOK_DIR" ]; then
    if [[ "$GIT_HOOK_DIR" = /* ]]; then
        HOOK_DIR="$GIT_HOOK_DIR"
    else
        HOOK_DIR="$REPO_ROOT/$GIT_HOOK_DIR"
    fi
else
    HOOK_DIR="$REPO_ROOT/.git/hooks"
fi
HOOK_FILE="$HOOK_DIR/pre-push"

if [ ! -d "$HOOK_DIR" ] && [ ! -e "$REPO_ROOT/.git" ]; then
    echo "[ai-log] Error: No .git or hooks directory found at $REPO_ROOT"
    exit 1
fi

mkdir -p "$HOOK_DIR"

cat > "$HOOK_FILE" <<'EOF'
#!/usr/bin/env bash
# Pre-push: sweep recent Antigravity / Gemini prompts, then submit AI logs.
# Uses the cross-platform Python launcher so it works whether the user
# has python3, python, or only the `py` launcher (Windows).
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
bash "$REPO_ROOT/scripts/_pyrun.sh" "$REPO_ROOT/scripts/log_antigravity.py" --auto || true
bash "$REPO_ROOT/scripts/_pyrun.sh" "$REPO_ROOT/scripts/submit_log.py" || true
exit 0  # Never block push, even if either step fails
EOF

chmod +x "$HOOK_FILE"
chmod +x "$REPO_ROOT/scripts/_pyrun.sh" 2>/dev/null || true
echo "[ai-log] Git pre-push hook installed at $HOOK_FILE."

mkdir -p "$REPO_ROOT/.ai-log"
touch "$REPO_ROOT/.ai-log/.gitkeep"

echo "[ai-log] Setup complete. Configure AI_LOG_SERVER in your .env file."
