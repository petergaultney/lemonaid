// lemonaid's OpenClaw plugin. Each hook hands its event to `lemonaid openclaw hook <event>`
// as JSON on stdin, as Claude Code and Codex run `lemonaid hooks`; lemonaid decides what it
// means. `lemonaid openclaw plugin install` writes lemonaid.json beside this file.

import { spawn } from "node:child_process";
import { readdirSync, readFileSync } from "node:fs";
import { basename, dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const TIMEOUT_MS = 5000;
const RENEW_MS = 60000; // a running turn's record is renewed this often, so it never goes stale

export function settingsFrom(dir) {
  return JSON.parse(readFileSync(join(dir, "lemonaid.json"), "utf8"));
}

// Runs one event; resolves to its exit code and stderr, never rejects.
export function runner(settings, spawnProcess = spawn) {
  return (event, payload) =>
    new Promise((resolve) => {
      let child;
      try {
        child = spawnProcess(
          settings.python,
          ["-m", "lemonaid", "openclaw", "hook", event, "--plugin-version", settings.version],
          { env: { ...process.env, ...settings.env }, stdio: ["pipe", "ignore", "pipe"] },
        );
      } catch (error) {
        resolve({ code: -1, stderr: String(error) });
        return;
      }
      let stderr = "";
      const timer = setTimeout(() => child.kill("SIGKILL"), TIMEOUT_MS);
      child.stderr.on("data", (chunk) => (stderr += chunk));
      child.on("error", (error) => {
        clearTimeout(timer);
        resolve({ code: -1, stderr: String(error) });
      });
      child.on("close", (code) => {
        clearTimeout(timer);
        resolve({ code: code ?? -1, stderr });
      });
      child.stdin.on("error", () => {});
      child.stdin.end(JSON.stringify(payload));
    });
}

// Whether a tool call can change a doc the session's waiters watch, or push: only those are
// worth starting lemonaid for, before a tool that waits on it. Its own hooks do the same.
export function worthRecording(ownEdits, sessionKey, params) {
  const text = JSON.stringify(params ?? {});
  if (/\bgit\b[\s\S]*\bpush\b/.test(text)) {
    return true;
  }
  const dir = join(ownEdits, `openclaw-${sessionKey}`);
  let names;
  try {
    names = readdirSync(dir).filter((name) => name.endsWith(".doc"));
  } catch {
    return false;
  }
  return names.some((name) => {
    try {
      const doc = basename(readFileSync(join(dir, name), "utf8").trim());
      return doc !== "" && text.includes(doc);
    } catch {
      return false;
    }
  });
}

// The text of the last assistant message among a turn's messages.
export function finalText(messages) {
  for (let i = (messages ?? []).length - 1; i >= 0; i -= 1) {
    const message = messages[i];
    if (message?.role !== "assistant") {
      continue;
    }
    const content = message.content;
    if (typeof content === "string") {
      return content;
    }
    return (Array.isArray(content) ? content : [])
      .filter((block) => block?.type === "text" && typeof block.text === "string")
      .map((block) => block.text)
      .join("\n");
  }
  return "";
}

export function register(api, settings, run = runner(settings), now = Date.now) {
  const renewed = new Map(); // session key: when its turn was last recorded as running, in ms
  const warn = (event, result) => {
    if (result.code !== 0 && result.code !== 2) {
      api.logger?.warn?.(`lemonaid openclaw hook ${event} exited ${result.code}: ${result.stderr}`);
    }
  };
  const fire = (event, payload) => run(event, payload).then((result) => warn(event, result));
  const running = (sessionKey, runId) => {
    renewed.set(sessionKey, now());
    return fire("turn", { session_key: sessionKey, run: runId ?? "", at: now() / 1000 });
  };
  const tool = (hookEventName, event, ctx, extra = {}) => ({
    session_key: ctx.sessionKey,
    hook_event_name: hookEventName,
    tool_use_id: event.toolCallId ?? ctx.toolCallId ?? "",
    tool_input: event.params ?? {},
    ...extra,
  });

  api.on("llm_input", async (event, ctx) => {
    if (ctx?.sessionKey) {
      await running(ctx.sessionKey, event.runId ?? ctx.runId);
    }
  });
  api.on("before_tool_call", async (event, ctx) => {
    if (!ctx?.sessionKey || !worthRecording(settings.ownEdits, ctx.sessionKey, event.params)) {
      return undefined;
    }
    const result = await run("tool", tool("PreToolUse", event, ctx));
    warn("tool", result);
    return result.code === 2 ? { block: true, blockReason: result.stderr.trim() } : undefined;
  });
  api.on("after_tool_call", async (event, ctx) => {
    if (!ctx?.sessionKey) {
      return;
    }
    const waits = [];
    if (now() - (renewed.get(ctx.sessionKey) ?? 0) >= RENEW_MS) {
      waits.push(running(ctx.sessionKey, event.runId ?? ctx.runId));
    }
    if (worthRecording(settings.ownEdits, ctx.sessionKey, event.params)) {
      waits.push(fire("tool", tool("PostToolUse", event, ctx, { tool_response: event.result })));
    }
    await Promise.all(waits);
  });
  api.on("agent_end", async (event, ctx) => {
    if (!ctx?.sessionKey) {
      return;
    }
    renewed.delete(ctx.sessionKey);
    await fire("turn-end", {
      session_key: ctx.sessionKey,
      run: event.runId ?? ctx.runId ?? "",
      at: now() / 1000,
      said: event.success ? finalText(event.messages) : "",
      failed: !event.success,
      error: event.error ?? "",
    });
  });
  api.on("gateway_start", async () => {
    await fire("gateway-start", { at: now() / 1000 });
  });
}

export default {
  id: "lemonaid",
  name: "lemonaid",
  description: "Tells lemonaid when a session's turns run and end, and what its tool calls change.",
  register(api) {
    register(api, settingsFrom(dirname(fileURLToPath(import.meta.url))));
  },
};
