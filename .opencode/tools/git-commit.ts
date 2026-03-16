import path from "path"
import { tool } from "@opencode-ai/plugin"
import { $ } from "bun"
import { exportAndFilterSession } from "./export-session"

/**
 * Git commit tool with session tracking.
 *
 * Creates a git commit with:
 * - Automatic Session-ID trailer for tracking
 * - Session export file (aivocode/sessions/<id>/<id>.json) auto-staged
 * - Custom author (opencode/<agent>) for filtering commits
 * - Optional custom trailers (e.g., Spec: feature-name)
 */
export default tool({
  description: `Create a git commit with session export and tracking.

Automatically includes:
- Session-ID trailer (always added)
- Session export file (aivocode/sessions/<id>/<id>.json) auto-staged
- Author: opencode/<agent> <noreply@opencode.ai>

Optional trailers:
- Spec: ONLY include when session reads/generates spec docs under specs/<feature-name>/.
  Format: "Spec: <feature-name>" (e.g., "Spec: lsp-client")
  Validation: specs/<feature-name>/ directory must exist and contain files

Args:
- message: Commit description (what and why)
- files: Files to commit (required, session export auto-added)
- trailers: Additional custom trailers (optional)`,

  args: {
    message: tool.schema.string().describe("Commit message description"),
    files: tool.schema
      .array(tool.schema.string())
      .describe("Files to stage and commit (required)"),
    trailers: tool.schema
      .record(tool.schema.string(), tool.schema.string())
      .optional()
      .describe("Custom trailers (e.g., { Spec: 'lsp-client' })"),
  },

  async execute(args, context) {
    const { sessionID, agent, worktree } = context
    const baseDir = worktree ?? process.cwd()

    // Validate required args
    if (!args.files || args.files.length === 0) {
      throw new Error("files array is required and cannot be empty")
    }

    // Validate Spec trailer if provided (case-insensitive: Spec/spec)
    const specValue =
      args.trailers?.Spec ??
      (args.trailers as Record<string, string> | undefined)?.spec
    if (specValue) {
      const specDir = path.join(baseDir, "specs", specValue)
      
      // Check directory exists using Bun.file().stat()
      try {
        const dirStat = await Bun.file(specDir).stat()
        if (!dirStat.isDirectory()) {
          throw new Error(`specs/${specValue} exists but is not a directory`)
        }
      } catch (error) {
        throw new Error(
          `specs/${specValue}/ directory does not exist. ` +
          `Cannot use spec: "${specValue}" trailer.`
        )
      }
      
      // Check directory is not empty using shell
      try {
        const files = await $`ls -A ${specDir}`.text()
        if (!files.trim()) {
          throw new Error(
            `specs/${specValue}/ directory exists but is empty. ` +
            `Add spec files before committing with spec trailer.`
          )
        }
      } catch (error) {
        if (error instanceof Error && error.message.includes("is empty")) {
          throw error
        }
        throw new Error(
          `Could not verify files in specs/${specValue}/ directory. ` +
          `Ensure directory contains spec files.`
        )
      }
    }

    // 1. Create session directory
    const sessionDir = path.join(baseDir, "aivocode/sessions", sessionID)
    await $`mkdir -p ${sessionDir}`

    // 2. Export session using shared logic from export-session.ts
    //
    // IMPORTANT: We first export to a temporary file. Only after all
    // Spec validations pass do we promote it to the canonical
    // aivocode/sessions/<id>/<id>.json path. This avoids leaving
    // partially-updated exports behind when validation fails.
    const exportPath = path.join(sessionDir, `${sessionID}.json`)
    const tmpExportPath = path.join(sessionDir, `${sessionID}.tmp.json`)

    await exportAndFilterSession(sessionID, tmpExportPath)

    // 2b. If a Spec trailer is present, ensure this session actually
    // touched specs/<specValue>/ via read/write/edit/apply_patch tools.
    if (specValue) {
      let rawSession: {
        sessionID?: string
        messages?: Array<{
          tools_used?: Array<{
            tool?: string
            input?: unknown
            output?: unknown
          }>
        }>
      }

      try {
        rawSession = JSON.parse(await Bun.file(tmpExportPath).text())
      } catch (error) {
        // Best-effort cleanup of temp export file on parse failure.
        await Bun.file(tmpExportPath).unlink().catch(() => {})
        throw error
      }

      if (!sessionTouchedSpec(rawSession, specValue, worktree)) {
        // Cleanup temp export and fail without touching any existing
        // canonical export file.
        await Bun.file(tmpExportPath).unlink().catch(() => {})
        throw new Error(
          `Spec trailer "Spec: ${specValue}" used but this session never ` +
            `touched specs/${specValue}/ via read/write/edit/apply_patch tools. ` +
            `Only include Spec when the session reads or generates docs there.`,
        )
      }
    }

    // 2c. Promote temporary export to canonical path. If there was an
    // existing export file for this session, it will be atomically
    // replaced with the latest filtered snapshot.
    try {
      const tmpContents = await Bun.file(tmpExportPath).text()
      await Bun.write(exportPath, tmpContents)
      await Bun.file(tmpExportPath).unlink().catch(() => {})
    } catch (error) {
      // If promotion fails, attempt to remove the temp file and
      // surface the error. We intentionally do NOT delete an existing
      // exportPath here to avoid losing previous session history.
      await Bun.file(tmpExportPath).unlink().catch(() => {})
      throw error
    }

    // 3. Build trailer arguments (Session-ID always included)
    const trailerEntries: [string, string][] = [["Session-ID", sessionID]]
    if (args.trailers) {
      trailerEntries.push(...Object.entries(args.trailers))
    }
    const trailerArgs = trailerEntries
      .map(([k, v]) => `--trailer '${k}: ${v}'`)
      .join(" ")

    // 4. Build file list and stage all files (including session export)
    const allFiles = [...args.files, exportPath]
    const quotedFiles = allFiles.map((f) => `"${f}"`).join(" ")

    // 5. Execute git add and commit
    try {
      await $`sh -c ${`git add ${quotedFiles}`}`

      const commitCmd = `git commit --author="opencode/${agent} <noreply@opencode.ai>" --message "${args.message}" ${trailerArgs}`
      const result = await $`sh -c ${commitCmd}`.text()

      return `Committed successfully: ${result.trim()}\nSession-ID: ${sessionID}`
    } catch (error) {
      // Check if nothing to commit
      const statusResult = await $`git status --short`.text()
      if (!statusResult.trim()) {
        throw new Error("nothing to commit (working tree clean)")
      }
      throw error
    }
  },
})

// --- Spec usage detection helpers ---

function stringTouchesSpec(
  value: string,
  specValue: string,
  worktree?: string,
): boolean {
  const relative = `specs/${specValue}/`
  if (value.includes(relative)) {
    return true
  }

  if (worktree) {
    const absolute = path.join(worktree, "specs", specValue) + "/"
    if (value.includes(absolute)) {
      return true
    }
  }

  return false
}

function sessionTouchedSpec(
  session: {
    messages?: Array<{
      tools_used?: Array<{
        tool?: string
        input?: unknown
        output?: unknown
      }>
    }>
  },
  specValue: string,
  worktree?: string,
): boolean {
  const messages = session.messages ?? []

  return messages.some((msg) => {
    const tools = msg.tools_used ?? []
    return tools.some((t) => {
      if (!t.tool) return false

      // read/write/edit: check input.filePath (or input string) for spec path
      if (t.tool === "read" || t.tool === "write" || t.tool === "edit") {
        const input = t.input as unknown
        let filePath: unknown

        if (typeof input === "string") {
          filePath = input
        } else if (input && typeof input === "object") {
          filePath = (input as Record<string, unknown>).filePath
        }

        if (typeof filePath === "string") {
          return stringTouchesSpec(filePath, specValue, worktree)
        }
        return false
      }

      // apply_patch: check textual output for specs/<feature>/ paths
      if (t.tool === "apply_patch") {
        const out = t.output
        if (typeof out === "string") {
          return stringTouchesSpec(out, specValue, worktree)
        }
        return false
      }

      return false
    })
  })
}
