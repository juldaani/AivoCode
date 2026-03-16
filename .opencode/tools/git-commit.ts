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
 * - Optional custom trailers (e.g., spec: feature-name)
 */
export default tool({
  description: `Create a git commit with session export and tracking.

Automatically includes:
- Session-ID trailer (always added)
- Session export file (aivocode/sessions/<id>/<id>.json) auto-staged
- Author: opencode/<agent> <noreply@opencode.ai>

Optional trailers:
- spec: Include when session reads/generates spec docs.
  Format: "spec: <feature-name>" (e.g., "spec: lsp-client")
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
      .describe("Custom trailers (e.g., { spec: 'lsp-client' })"),
  },

  async execute(args, context) {
    const { sessionID, agent, worktree } = context
    const baseDir = worktree ?? process.cwd()

    // Validate required args
    if (!args.files || args.files.length === 0) {
      throw new Error("files array is required and cannot be empty")
    }

    // Validate spec trailer if provided
    if (args.trailers?.spec) {
      const specValue = args.trailers.spec
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
    const exportPath = path.join(sessionDir, `${sessionID}.json`)
    await exportAndFilterSession(sessionID, exportPath)

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
