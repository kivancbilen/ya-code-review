# ya-code-review

Semi-formal reasoning code review agent powered by Claude. Uses a 5-phase methodology — premises, execution tracing, claims, falsification, and findings — to produce evidence-backed code review findings. Inspired by (https://arxiv.org/pdf/2603.01896)

## Features

- **Multi-pass ensemble review** — 3 chunk granularities (fine/medium/coarse) with deduplication
- **Review memory** — persist learned patterns across reviews (JSON-backed)
- **Auto-severity calibration** — LLM post-pass to recalibrate finding severities
- **Test coverage analysis** — static analysis of which changed code has test coverage
- **Fault localization** — 5-phase agent-driven bug localization
- **Patch equivalence** — compare two patches for behavioral equivalence
- **MCP server** — expose all tools via Model Context Protocol

## Install

```bash
# npm (installs Python deps automatically)
npm install -g ya-code-review

# or pip
pip install -e .
```

Requires Python 3.11+ and an Anthropic API key:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

## CLI Usage

### Code Review

```bash
# Review a git diff
fb-review review HEAD~1..HEAD

# Review a GitHub PR
fb-review pr 123 --comment

# Review an Everest sandbox
fb-review sandbox 464444

# Review local Everest sandbox
fb-review ev-diff --sandbox /path/to/sandbox
```

### Test Coverage Analysis

```bash
# Standalone (no LLM calls)
fb-review coverage HEAD~1..HEAD

# Appended to any review
fb-review review HEAD~1..HEAD --coverage
fb-review sandbox 464444 --coverage
```

### Fault Localization

```bash
fb-review fault-localize "TypeError in handler when request body is empty"
fb-review fault-localize "race condition in order processing" --diff-ref HEAD~5..HEAD
```

### Patch Equivalence

```bash
# Compare two Everest sandboxes
fb-review patch-equiv --sandbox-a 464444 --sandbox-b 464460

# Compare two git refs
fb-review patch-equiv --ref-a HEAD~2..HEAD~1 --ref-b HEAD~1..HEAD

# Compare two diff files
fb-review patch-equiv --file-a patch1.diff --file-b patch2.diff
```

### Review Memory

```bash
fb-review memory list
fb-review memory add -p "Missing null check on API response" -d "Always check for null before accessing properties" -s high -c correctness -f "*.ts"
fb-review memory remove P001
fb-review memory export -o patterns.json
fb-review memory import patterns.json
```

### Options

```bash
fb-review --model claude-sonnet-4-6 review HEAD~1..HEAD    # override model
fb-review review HEAD~1..HEAD --format json                  # json output
fb-review review HEAD~1..HEAD --format markdown -v           # verbose with reasoning log
```

## MCP Server

ya-code-review exposes all tools via MCP for use with Claude Desktop, Claude Code, or any MCP client.

### Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "ya-code-review": {
      "command": "python3",
      "args": ["-m", "fb_review_agent.mcp_server"],
      "env": {
        "ANTHROPIC_API_KEY": "sk-ant-..."
      }
    }
  }
}
```

### Claude Code

Add to `.claude/settings.json`:

```json
{
  "mcpServers": {
    "ya-code-review": {
      "command": "python3",
      "args": ["-m", "fb_review_agent.mcp_server"]
    }
  }
}
```

### npm wrapper

```bash
ya-code-review mcp    # starts MCP server via stdio
```

### Available MCP Tools

| Tool | Description |
|------|-------------|
| `review_diff` | Review a git diff with semi-formal reasoning |
| `review_sandbox` | Review an Everest sandbox by ID |
| `review_ev_diff` | Review local Everest sandbox changes |
| `analyze_coverage` | Static test coverage analysis |
| `fault_localize` | 5-phase fault localization |
| `patch_equivalence` | Compare two patches for behavioral equivalence |
| `memory_list` | List known review patterns |
| `memory_add` | Add a known pattern |
| `memory_remove` | Remove a known pattern |

## How It Works

### 5-Phase Semi-Formal Reasoning

1. **Change Comprehension** — Establish premises (facts verified by reading code)
2. **Execution Path Tracing** — Build function call traces, trace data flow 2+ levels deep
3. **Divergence Analysis** — Identify claims (potential issues) referencing premises and traces
4. **Falsification** — Actively try to disprove each claim (check tests, defensive code, patterns)
5. **Findings** — Report only claims that survived falsification

### Multi-Pass Ensemble

| Pass | Chunk Size | Purpose |
|------|-----------|---------|
| Fine | 20K chars | Deep line-level bug detection |
| Medium | 50K chars | Cross-file pattern detection |
| Coarse | 200K chars | Architectural overview |

Findings are deduplicated across passes, keeping the best version of each.

### Auto-Severity Calibration

After the review, a fast LLM pass (Haiku) recalibrates finding severities based on impact scope, hot path analysis, defensive code, and test coverage indicators.

## Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `ANTHROPIC_API_KEY` | — | Anthropic API key (required) |
| `FB_REVIEW_MODEL` | `claude-opus-4-6` | Model for reviews |
| `FB_REVIEW_MAX_TURNS` | `40` | Max agent turns per chunk |
| `FB_REVIEW_CALIBRATION_ENABLED` | `true` | Enable auto-severity calibration |
| `FB_REVIEW_CALIBRATION_MODEL` | `claude-haiku-4-5-20251001` | Model for calibration |
| `FB_REVIEW_MEMORY_PATH` | `~/.fb-review/memory.json` | Path to pattern store |
| `FB_REVIEW_CHUNK_SIZE` | `30000` | Max chars per diff chunk |

## License

MIT
