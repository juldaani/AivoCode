# Agent Rules

## Path Handling

**Always use relative paths from repo root** when operating on files inside the current 
repo.

Permission patterns may block absolute paths.

### Example

```bash
# ✅ mkdir -p folder/subfolder
# ❌ mkdir -p /home/user/project/folder/subfolder
```

## Executing code / tool use

- When executing long-running code (like servers, infinite loops, ...), use timeouts/kill/etc 
  to end the process. Otherwise we block.

- Use specialized file/search tools over shell; use bash for execute/builds/tests/CLI 
  (if no specialized tool available -> bash)

- Use parallel calls when independent (e.g. multiple reads/searches), sequential when dependent. 