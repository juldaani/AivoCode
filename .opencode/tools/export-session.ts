import path from "path"
import { tool } from "@opencode-ai/plugin"
import { $ } from "bun"

export default tool({
  description: "Export current session to JSON file",
  args: {
    outputPath: tool.schema.string().describe("Path to save session JSON"),
  },
  async execute(args, context) {
    const { sessionID, worktree } = context
    const baseDir = worktree ?? process.cwd()
    const outputPath = path.isAbsolute(args.outputPath)
      ? args.outputPath
      : path.join(baseDir, args.outputPath)

    const exportResult = await $`opencode export ${sessionID}`.text()
    await Bun.write(outputPath, exportResult)

    return `Exported session ${sessionID} to ${outputPath}`
  },
})
