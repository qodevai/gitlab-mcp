# qodev-gitlab-mcp

A Model Context Protocol (MCP) server for GitLab integration. Exposes projects, merge requests, pipelines, discussions, issues, releases, and more through a standardized interface for AI assistants like Claude.

## Installation

```bash
pip install qodev-gitlab-mcp
```

Or run directly with uvx:

```bash
uvx qodev-gitlab-mcp
```

## Configuration

Set the following environment variables:

```env
# Required
GITLAB_TOKEN=glpat-YOUR-TOKEN-HERE

# Optional (defaults to https://gitlab.com)
GITLAB_URL=https://gitlab.com
```

### Claude Code

Add to your MCP configuration:

```json
{
  "mcpServers": {
    "gitlab": {
      "command": "uvx",
      "args": ["qodev-gitlab-mcp"],
      "env": {
        "GITLAB_TOKEN": "your-token-here",
        "GITLAB_URL": "https://gitlab.com"
      }
    }
  }
}
```

## Features

- Merge request management (create, comment, merge, close, inline comments)
- Pipeline monitoring with `wait_for_pipeline` tool
- Issue tracking (create, update, close, comment)
- Release management
- CI/CD variable management
- File uploads with image support
- Automatic "current" project/branch detection via MCP workspace roots

## Usage

```python
from qodev_gitlab_api import GitLabClient
from qodev_gitlab_mcp.server import mcp
```

## License

MIT
