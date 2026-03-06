#!/usr/bin/env node

/**
 * ya-code-review CLI wrapper.
 *
 * Usage:
 *   ya-code-review mcp          — Start the MCP server (stdio transport)
 *   ya-code-review <command>    — Forward to the Python fb-review CLI
 */

import { spawn } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const projectRoot = join(__dirname, "..");

const args = process.argv.slice(2);

if (args[0] === "mcp") {
  // Start the MCP server via Python
  const child = spawn("python3", ["-m", "fb_review_agent.mcp_server"], {
    cwd: projectRoot,
    stdio: "inherit",
    env: { ...process.env },
  });
  child.on("error", (err) => {
    if (err.code === "ENOENT") {
      // Fallback to python
      const fallback = spawn("python", ["-m", "fb_review_agent.mcp_server"], {
        cwd: projectRoot,
        stdio: "inherit",
        env: { ...process.env },
      });
      fallback.on("error", () => {
        console.error("Error: Python not found. Install Python 3.11+ and run: pip install -e .");
        process.exit(1);
      });
      fallback.on("exit", (code) => process.exit(code ?? 0));
    } else {
      console.error(`Error: ${err.message}`);
      process.exit(1);
    }
  });
  child.on("exit", (code) => process.exit(code ?? 0));
} else {
  // Forward to fb-review CLI
  const child = spawn("fb-review", args, {
    cwd: process.cwd(),
    stdio: "inherit",
    env: { ...process.env },
  });
  child.on("error", (err) => {
    if (err.code === "ENOENT") {
      console.error("Error: fb-review not found. Run: pip install -e " + projectRoot);
      process.exit(1);
    }
    console.error(`Error: ${err.message}`);
    process.exit(1);
  });
  child.on("exit", (code) => process.exit(code ?? 0));
}
