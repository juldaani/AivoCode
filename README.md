# AivoCode
Codebase Intelligence Engine for AI Agents

## Devcontainer Usage

### Prerequisites
- [DevPod](https://devpod.sh/) installed
- Docker provider configured

### Start the devcontainer
```bash
devpod up . --ide vscode --provider docker --workspace-env-file .devcontainer/devcontainer.env
```

### Connect with OpenCode (client-server mode)
SSH tunnel + OpenCode attach in one command:
```bash
devpod ssh -L 4096:localhost:4096 aivocode & sleep 5 && opencode attach http://localhost:4096
```
The `&` runs the SSH tunnel in the background (keeping port forwarding alive),
`sleep 3` waits for the tunnel to establish, then `opencode attach` connects
in the foreground.
