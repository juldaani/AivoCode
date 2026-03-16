import path from "path"
import { tool } from "@opencode-ai/plugin"
import { $ } from "bun"

/**
 * Export and filter a session to JSON file.
 *
 * This function is shared between export-session tool and git-commit tool
 * to ensure identical session export behavior.
 *
 * @param sessionID - The session ID to export
 * @param outputPath - Path where filtered JSON should be saved
 * @param options - Options for export behavior
 * @returns The path to the exported file
 */
export async function exportAndFilterSession(
  sessionID: string,
  outputPath: string,
  options?: { deleteRaw?: boolean }
): Promise<string> {
  const rawPath = `${outputPath}.raw.json`

  await $`sh -c ${`opencode export ${sessionID} > ${rawPath}`}`

  const rawJson = JSON.parse(await Bun.file(rawPath).text())
  const filtered = filterSession(rawJson)
  await Bun.write(outputPath, JSON.stringify(filtered, null, 2))

  if (options?.deleteRaw !== false) {
    await Bun.file(rawPath).unlink()
  }

  return outputPath
}

// --- Shared types and filtering logic ---

export type ToolInput = Record<string, unknown> | string | number | boolean | null

export type FilteredMessage = {
  /** Message role, e.g. user/assistant/system */
  role?: string

  /**
   * Lightweight metadata about the message.
   *
   * We intentionally keep only a small set of fields that are useful
   * for later analysis:
   * - agent type (architect/coder/tester/...)
   * - model identifier (modelID only)
   * - time_created (timestamp when the message was created)
   * - finish reason (e.g. "tool-calls", "stop")
   * - working directory / root path
   */
  meta?: {
    agent?: string
    model?: string
    time_created?: number
    finish?: string
    path?: { cwd?: string; root?: string }
  }

  /** Human-visible text content (merged text parts). */
  content?: string

  /**
   * Model reasoning trace, merged into a single string from all
   * `type: "reasoning"` parts.
   */
  reasoning?: string

  /** Normalized tool calls for this message. */
  tools_used?: Array<{
    tool?: string
    input?: ToolInput
    output?: string
    status?: string
    sessionId?: string
  }>
}

// Tools whose output should be completely skipped in the filtered
// session export (typically because the payload is very large or
// not useful for later inspection). For these, we still keep the
// *input* so the content can be re-fetched later if needed.
const SKIP_OUTPUT_TOOLS = ["webfetch", "codesearch", "read", "grep", "skill"]

// Tools for which we want to preserve the *full* output without
// truncation, because this output is critical for understanding
// what was changed in the workspace.
//
// In particular, write/edit/apply_patch are used to modify files,
// and the patch/content information is essential when reviewing
// past sessions and reconstructing changes.
const NO_TRUNCATE_OUTPUT_TOOLS = ["write", "edit", "apply_patch"]

// Default truncation limits for tool output. Inputs are never
// truncated by this filter.
const DEFAULT_OUTPUT_MAX_CHARS = 5000
const OUTPUT_MAX_CHARS: Record<string, number> = {
  bash: 2000,
}

/**
 * Filter raw session export to extract relevant information.
 * Keeps: sessionID, message roles, text content, tool calls with truncated output.
 */
export function filterSession(raw: unknown): {
  sessionID?: string
  info?: Record<string, unknown>
  messages: FilteredMessage[]
} {
  if (!raw || typeof raw !== "object") {
    return { messages: [] }
  }

  const rawRecord = raw as Record<string, unknown>
  const rawMessages = Array.isArray(rawRecord.messages)
    ? rawRecord.messages
    : Array.isArray(raw)
      ? raw
      : []

  const firstMessage = rawMessages.length > 0 ? rawMessages[0] : undefined
  const firstInfo =
    firstMessage && typeof firstMessage === "object"
      ? (firstMessage as Record<string, unknown>).info
      : undefined
  const firstSessionID =
    firstInfo && typeof firstInfo === "object"
      ? (firstInfo as Record<string, unknown>).sessionID
      : undefined

  const sessionID =
    (rawRecord.sessionID as string | undefined) ??
    (rawRecord.id as string | undefined) ??
    (typeof firstSessionID === "string" ? firstSessionID : undefined)

  const messages = rawMessages
    .map((message) => filterMessage(message))
    .filter((message) => message.content || (message.tools_used ?? []).length > 0)

  // Preserve a compact top-level session info block when present so
  // that callers can see high-level metadata (title, project, summary
  // of changes, etc.), without embedding large per-message diffs.
  const rawInfo =
    typeof rawRecord.info === "object" && rawRecord.info !== null
      ? (rawRecord.info as Record<string, unknown>)
      : undefined

  let info: Record<string, unknown> | undefined
  if (rawInfo) {
    info = {}

    // Basic identifiers / labels
    if (typeof rawInfo.id === "string") info.id = rawInfo.id
    if (typeof rawInfo.slug === "string") info.slug = rawInfo.slug
    if (typeof rawInfo.projectID === "string") info.projectID = rawInfo.projectID
    if (typeof rawInfo.directory === "string") info.directory = rawInfo.directory
    if (typeof rawInfo.title === "string") info.title = rawInfo.title
    if (typeof rawInfo.version === "string") info.version = rawInfo.version

    // Aggregate summary (additions/deletions/files) is useful; keep as-is.
    if (rawInfo.summary && typeof rawInfo.summary === "object") {
      info.summary = rawInfo.summary
    }

    // Collapse time block into a single created timestamp.
    const time = rawInfo.time as Record<string, unknown> | undefined
    if (time && typeof time.created === "number") {
      info.time_created = time.created
    }

    if (Object.keys(info).length === 0) {
      info = undefined
    }
  }

  return { sessionID, info, messages }
}

function filterMessage(message: unknown): FilteredMessage {
  if (!message || typeof message !== "object") {
    return {}
  }

  const messageRecord = message as Record<string, unknown>
  const info = (messageRecord.info ?? {}) as Record<string, unknown>
  const role = info.role as string | undefined
  const parts = Array.isArray(messageRecord.parts) ? messageRecord.parts : []

  const content = parts
    .filter((part) => {
      if (!part || typeof part !== "object") {
        return false
      }
      return (part as Record<string, unknown>).type === "text"
    })
    .map((part) => (part as Record<string, unknown>).text)
    .filter((text) => typeof text === "string")
    .join("\n")
    .trim()

  // Merge all reasoning parts into a single reasoning string. This
  // preserves reasoning while avoiding thousands of micro-parts when
  // models stream character-by-character.
  const reasoningText = parts
    .filter((part) => {
      if (!part || typeof part !== "object") {
        return false
      }
      return (part as Record<string, unknown>).type === "reasoning"
    })
    .map((part) => (part as Record<string, unknown>).text)
    .filter((text) => typeof text === "string")
    .join("\n")
    .trim()

  const tools_used = parts
    .filter((part) => isToolPart(part))
    .map((part) => normalizeToolPart(part))
    .filter((toolPart) => toolPart.tool || toolPart.input)

  // Build lightweight meta block from info.
  const meta: FilteredMessage["meta"] = {}

  const agent = info.agent as string | undefined
  const modelID = (info.modelID ?? (info.model as Record<string, unknown> | undefined)?.modelID) as
    | string
    | undefined
  const time = (info.time ?? {}) as Record<string, unknown>
  const finish = info.finish as string | undefined
  const pathInfo = (info.path ?? {}) as Record<string, unknown>

  if (agent) meta.agent = agent
  if (modelID) meta.model = modelID
  if (typeof time.created === "number") {
    meta.time_created = time.created
  }
  if (finish) meta.finish = finish
  if (pathInfo && (pathInfo.cwd || pathInfo.root)) {
    meta.path = {
      cwd: typeof pathInfo.cwd === "string" ? pathInfo.cwd : undefined,
      root: typeof pathInfo.root === "string" ? pathInfo.root : undefined,
    }
  }

  return {
    role,
    meta: Object.keys(meta).length > 0 ? meta : undefined,
    content: content.length > 0 ? content : undefined,
    reasoning: reasoningText.length > 0 ? reasoningText : undefined,
    tools_used: tools_used.length > 0 ? tools_used : undefined,
  }
}

function isToolPart(part: unknown): part is Record<string, unknown> {
  if (!part || typeof part !== "object") {
    return false
  }

  const partRecord = part as Record<string, unknown>
  return (
    partRecord.type === "tool" ||
    partRecord.type === "tool_call" ||
    partRecord.type === "tool-call"
  )
}

function normalizeToolPart(part: Record<string, unknown>): {
  tool?: string
  input?: ToolInput
  output?: string
  status?: string
  sessionId?: string
} {
  const tool = (part.tool ?? part.name) as string | undefined
  const state = (part.state ?? {}) as Record<string, unknown>
  const input = (state.input ?? part.input ?? part.args) as ToolInput
  let output: string | undefined
  if (tool && !SKIP_OUTPUT_TOOLS.includes(tool)) {
    const rawOutput = typeof state.output === "string" ? state.output : undefined
    if (rawOutput) {
      if (NO_TRUNCATE_OUTPUT_TOOLS.includes(tool)) {
        // Preserve full output for write/edit/apply_patch so we can
        // later inspect exactly what content or patches were applied.
        output = rawOutput
      } else {
        const maxChars = OUTPUT_MAX_CHARS[tool] ?? DEFAULT_OUTPUT_MAX_CHARS
        output =
          rawOutput.length > maxChars
            ? `${rawOutput.slice(0, maxChars)}... (truncated)`
            : rawOutput
      }
    }
  }
  const status = typeof state.status === "string" ? state.status : undefined
  const metadata = (state.metadata ?? {}) as Record<string, unknown>
  const sessionId = typeof metadata.sessionId === "string" ? metadata.sessionId : undefined
  return { tool, input, output, status, sessionId }
}

// --- Tool definition ---

export default tool({
  description: "Export current session to filtered JSON file",
  args: {
    outputPath: tool.schema.string().describe("Path to save session JSON"),
    deleteRaw: tool.schema
      .boolean()
      .default(true)
      .describe("Delete raw export file after filtering"),
  },
  async execute(args, context) {
    const { sessionID, worktree } = context
    const baseDir = worktree ?? process.cwd()
    const outputPath = path.isAbsolute(args.outputPath)
      ? args.outputPath
      : path.join(baseDir, args.outputPath)

    await exportAndFilterSession(sessionID, outputPath, { deleteRaw: args.deleteRaw })

    return `Exported session ${sessionID} to ${outputPath}`
  },
})
