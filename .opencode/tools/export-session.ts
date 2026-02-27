import path from "path"
import { tool } from "@opencode-ai/plugin"
import { $ } from "bun"

export default tool({
  description: "Export current session to filtered JSON file",
  args: {
    outputPath: tool.schema.string().describe("Path to save session JSON"),
  },
  async execute(args, context) {
    const { sessionID, worktree } = context
    const baseDir = worktree ?? process.cwd()
    const outputPath = path.isAbsolute(args.outputPath)
      ? args.outputPath
      : path.join(baseDir, args.outputPath)
    const rawPath = `${outputPath}.raw.json`

    await $`sh -c ${`opencode export ${sessionID} > ${rawPath}`}`

    const rawJson = JSON.parse(await Bun.file(rawPath).text())
    const filtered = filterSession(rawJson)
    await Bun.write(outputPath, JSON.stringify(filtered, null, 2))

    return `Exported session ${sessionID} to ${outputPath}`
  },
})

type ToolInput = Record<string, unknown> | string | number | boolean | null

const SKIP_OUTPUT_TOOLS = ["webfetch"]
const DEFAULT_OUTPUT_MAX_CHARS = 10000
const OUTPUT_MAX_CHARS: Record<string, number> = {
  bash: 1000,
  grep: 4000,
}

type FilteredMessage = {
  role?: string
  content?: string
  tools_used?: Array<{
    tool?: string
    input?: ToolInput
    output?: string
    status?: string
    sessionId?: string
  }>
}

function filterSession(raw: unknown): { sessionID?: string; messages: FilteredMessage[] } {
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

  return { sessionID, messages }
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

  const tools_used = parts
    .filter((part) => isToolPart(part))
    .map((part) => normalizeToolPart(part))
    .filter((toolPart) => toolPart.tool || toolPart.input)

  return {
    role,
    content: content.length > 0 ? content : undefined,
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
      const maxChars = OUTPUT_MAX_CHARS[tool] ?? DEFAULT_OUTPUT_MAX_CHARS
      output =
        rawOutput.length > maxChars
          ? `${rawOutput.slice(0, maxChars)}... (truncated)`
          : rawOutput
    }
  }
  const status = typeof state.status === "string" ? state.status : undefined
  const metadata = (state.metadata ?? {}) as Record<string, unknown>
  const sessionId = typeof metadata.sessionId === "string" ? metadata.sessionId : undefined
  return { tool, input, output, status, sessionId }
}
