---
name: setup
description: Use when configuring the Cognee connection, checking whether Cognee is ready or connected, or diagnosing a local or cloud Cognee instance from Codex.
---

<!-- Modified by codex-cognee-memory contributors (2026-11-02): Local readiness and summary-only lifecycle setup; preserve existing configuration. -->

# Cognee Connection And Status

For the local summary-only daily workflow, also read **daily-memory**. Preserve
existing endpoint, models, Obsidian configuration and `COGNEE_CAPTURE=false`.
This flag alone does not disable legacy session improve/watchers: the local
package replaces automatic hooks with `daily_memory.py`, without invoking the
original session-start/sync/pre-compact scripts. New plugin contents require
native `/hooks` approval. Never edit trusted hashes or bypass that review.

Use this skill when the user asks to configure Cognee, check whether Cognee is
ready or connected, switch between local and cloud mode, or diagnose a
connection problem.

## Rules

- **Server first.** Answer every question here from the plugin's own diagnostic
  and the running Cognee server over HTTP. That is the authoritative path in
  both local and cloud mode.
- **`cognee-cli` is a last resort, not an alternative.** It is reachable only on
  a machine holding a cognee **source checkout**: `scripts/cognee-cli.sh` exits
  64 ("Run this from the Cognee repository root or set COGNEE_REPO_ROOT")
  anywhere else, and in cloud mode the plugin's venv is never built at all. Never
  reach for it before the two steps below have actually failed.
- Use the plugin's managed runtime bootstrap for installation. Never run `uv sync` in the user's project. When runtime preparation is explicitly requested, keep the version pinned by `session-start.py` and install required extras only into the plugin-owned virtualenv.
- Do not print secret values from `.env`, config files, shell history, or command
  output. Report whether a key *appears configured*, never the value.
- If a command may create, delete, or overwrite durable Cognee state, say what it
  will affect before running it.
- Do not use MCP for this plugin.

## 1. Check the mode and the connection

One command answers "is Cognee ready?", "which mode am I in?", and "what is
wrong?" — it imports no cognee, makes one `/health` probe, and works from any
directory:

```bash
python3 "${CODEX_PLUGIN_ROOT}/scripts/doctor.py" --json
```

The JSON carries:

| Field | Meaning |
|-------|---------|
| `mode` | `Local` or `Cloud`, plus an annotation naming what forced the decision (e.g. `forced by COGNEE_BACKEND=local`) |
| `server_url` | The endpoint this terminal actually resolved |
| `reachable` | Whether the health probe succeeded |
| `latency_ms` | Round-trip time, or `null` when unreachable |
| `api_key_source` | Which credential the plugin is using (plugin identity, env var, cached, minted) |
| `memory_sharing` | Shared-agent-memory state |
| `circuit_breaker` | Whether recall is currently short-circuited |

Read `mode` **before** doing anything mode-specific. In particular: in `Cloud`
mode there is no local server to start and no local UI to launch — see the
**local-ui** skill, which stops on cloud by design.

Drop `--json` for a human-readable table when reporting to the user.

## 2. Probe the server directly (optional)

When you need to confirm the endpoint yourself, or the doctor's verdict looks
stale:

```bash
python3 - "${CODEX_PLUGIN_ROOT}/scripts" <<'PY'
import sys, urllib.request
sys.path.insert(0, sys.argv[1])
from _plugin_common import _local_api_url_with_source
endpoint, _ = _local_api_url_with_source()
with urllib.request.urlopen(endpoint.rstrip("/") + "/health", timeout=5) as response:
    print("HTTP", response.status)
PY
```

Resolve the endpoint from plugin configuration, including `~/.cognee/.env` and custom loopback ports. `doctor.server_url=null` in Local mode is only a display choice. If a default port is occupied, identify the listener and select a free loopback port without stopping another application. A custom local endpoint can be set with `COGNEE_BASE_URL=http://127.0.0.1:<port>`; leave a forced `COGNEE_CODEX_BACKEND=local` unset because that mode clears the configured base URL in this plugin version.

For an authenticated check of the resolved credential (cloud, or any server with
auth enabled), use the forget helper's credential resolver rather than guessing
where the key lives:

```bash
eval "$(${CODEX_PLUGIN_ROOT}/scripts/cognee-forget.sh env)" && \
curl -sS -o /dev/null -w '%{http_code}\n' \
  -H "X-Api-Key: ${COGNEE_API_KEY}" "${COGNEE_BASE_URL}/api/v1/users/me"
```

`200` means the key is accepted; `401`/`403` means it was rejected by that
server. In local mode the key is never exported to the shell, so a raw request
without this resolver will 401 misleadingly.

## Configure the connection

Durable configuration (`COGNEE_BASE_URL`, `COGNEE_API_KEY`, `LLM_API_KEY`, ...)
belongs in `~/.cognee/.env` — a one-time setup file shared with the Claude Code
plugin, loaded at session start. Guide the user to edit that file rather than
exporting in every shell; never echo its secret values. Shell exports still
override it per terminal. Changes apply on the next `codex` launch.

**Cloud or a remote server** — both values:

```bash
mkdir -p ~/.cognee
cat >> ~/.cognee/.env <<'EOF'
COGNEE_BASE_URL="https://your-instance.cognee.ai"
COGNEE_API_KEY="ck_..."
EOF
chmod 600 ~/.cognee/.env
```

**Local** (default when `COGNEE_BASE_URL` is unset) — the plugin bootstraps a
local Cognee API on `http://localhost:8011` and auto-mints `COGNEE_API_KEY`, so
Cognee 1.6.x can store and retrieve text without an LLM key using the local GLiNER extractor and fastembed. Install the matching extras and allow first-use model downloads. LLM-generated answers and some advanced operations still need an LLM. To configure an LLM when wanted:

```bash
mkdir -p ~/.cognee
cat >> ~/.cognee/.env <<'EOF'
LLM_API_KEY="sk-..."
EOF
chmod 600 ~/.cognee/.env
```

Re-pasting either block is safe — the last value of a repeated key wins.

### Which mode wins

The file may hold **both** modes' variables at once. The mode is then decided
per terminal, in this order:

1. An exported `COGNEE_BACKEND` (or the plugin-specific `COGNEE_CODEX_BACKEND`,
   which beats it) pins that terminal: `local` or `cloud`.
2. Otherwise cloud wins when `COGNEE_BASE_URL` is set anywhere.
3. Otherwise local.

A forced mode is **pinned**: `COGNEE_BACKEND=cloud` with no URL configured stays
cloud and fails visibly (`✕ (missing_cognee_base_url)`) rather than silently
falling back. `unset COGNEE_BASE_URL` is **not** a way to go local — the env file
re-injects it on the next launch; use the switch.

`COGNEE_BACKEND` may also live in `~/.cognee/.env` to make a mode the durable
default. The doctor's `mode` field always reports what the terminal actually
resolved, with the cause.

## Fallback — `cognee-cli`, local mode with a cognee checkout only

Only if steps 1 and 2 both failed, the mode is `Local`, **and** the machine has a
cognee source checkout. Route it through the wrapper so a missing checkout fails
with a clear message instead of an opaque `uv` error:

```bash
"${CODEX_PLUGIN_ROOT}/scripts/cognee-cli.sh" config list
```

Set `COGNEE_REPO_ROOT` to the checkout path if the wrapper cannot find it. Use
`config get <KEY>` only for non-secret settings.

Exit code 64 means there is no cognee checkout here — that is expected on a
normal install, and it is **not** a Cognee fault to report. Say the server is
unreachable and give the user the doctor output instead.


## Verify operational memory

Use a new synthetic acceptance dataset and a unique non-secret marker. Submit one write with `--dataset`, keep its returned pipeline id, wait for processing, and recall the marker through a fresh process against the same dataset. Check a separate control dataset to verify scope. Health/auth checks and queued writes alone do not establish working memory. Preserve existing Obsidian configuration, keep automatic raw-session capture disabled unless separately requested, and record only sanitized results.
