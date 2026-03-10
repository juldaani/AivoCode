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
