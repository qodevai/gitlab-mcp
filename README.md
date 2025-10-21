# GitLab MCP Server

A production-ready Model Context Protocol (MCP) server that provides GitLab integration for AI assistants like Claude. Exposes GitLab projects, merge requests, pipelines, discussions, and more through a standardized interface.

## Features

- **Current Branch MR Overview** - Complete details of the MR for your current branch
- **MR Discussions** - View and track discussion threads on merge requests
- **Code Changes** - See diffs and changed files in MRs
- **Pipeline Status** - Monitor CI/CD pipeline health
- **Approval Tracking** - Check who has approved and who needs to approve
- **Project Information** - Access project metadata and settings
- **Commit History** - View commit details for merge requests

## Installation

### Prerequisites

- Python 3.11 or higher
- [uv](https://github.com/astral-sh/uv) package manager (recommended) or pip
- GitLab Personal Access Token

### Using uv (Recommended)

```bash
# Clone the repository
git clone https://github.com/janscheffler/gitlab-mcp.git
cd gitlab-mcp

# Install dependencies
uv sync

# Configure environment
cp .env.example .env
# Edit .env with your GitLab token and URL
```

### Using pip

```bash
# Clone the repository
git clone https://github.com/janscheffler/gitlab-mcp.git
cd gitlab-mcp

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -e .

# Configure environment
cp .env.example .env
# Edit .env with your GitLab token and URL
```

## Configuration

### Environment Variables

Create a `.env` file in the project root:

```env
# Required
GITLAB_TOKEN=glpat-YOUR-TOKEN-HERE
GITLAB_URL=https://gitlab.com

# Optional
LOG_LEVEL=INFO
```

### Generating a GitLab Personal Access Token

1. Go to your GitLab instance (e.g., https://gitlab.com)
2. Navigate to: Profile → Preferences → Access Tokens
3. Click "Add new token"
4. Set a name (e.g., "MCP Server")
5. Select scopes:
   - `api` - Full API access
   - `read_api` - Read API (minimum required)
   - `read_user` - Read user information
   - `read_repository` - Read repository data
6. Set expiration date (optional)
7. Click "Create personal access token"
8. Copy the token to your `.env` file

## Usage

### With Claude Code (VSCode Extension)

Add to your Claude Code MCP configuration:

```json
{
  "mcpServers": {
    "gitlab": {
      "command": "uv",
      "args": ["run", "python", "/path/to/gitlab-mcp/gitlab_mcp.py"],
      "env": {
        "GITLAB_TOKEN": "your-token-here",
        "GITLAB_URL": "https://gitlab.com"
      }
    }
  }
}
```

Then use natural language queries:
- "What's the status of my MR?"
- "Any unresolved discussions on my merge request?"
- "What files changed in the current MR?"
- "Show me the pipeline status"

### With Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):

```json
{
  "mcpServers": {
    "gitlab": {
      "command": "uv",
      "args": ["run", "python", "/path/to/gitlab-mcp/gitlab_mcp.py"],
      "env": {
        "GITLAB_TOKEN": "your-token-here",
        "GITLAB_URL": "https://gitlab.com"
      }
    }
  }
}
```

### Testing with MCP Inspector

```bash
npx -y @modelcontextprotocol/inspector uv run python gitlab_mcp.py
```

This opens a web interface at http://localhost:5173 where you can:
1. Configure workspace roots
2. Test resources
3. View responses
4. Debug issues

## Available Resources

### Current Project Resources

| URI | Description |
|-----|-------------|
| `gitlab://current-project/current-branch-mr/` | Complete MR overview (recommended) |
| `gitlab://current-project/current-branch-mr-discussions/` | Discussions on current branch MR |
| `gitlab://current-project/current-branch-mr-changes/` | Code changes/diff for current MR |
| `gitlab://current-project/merge-requests/` | Open merge requests |
| `gitlab://current-project/pipelines/` | Recent pipelines (last 20) |
| `gitlab://current-project/status/` | Quick project status |
| `gitlab://current-project/` | Project information |

### Global Resources

| URI | Description |
|-----|-------------|
| `gitlab://projects/` | All accessible projects |
| `gitlab://projects/{id}` | Specific project details |
| `gitlab://projects/{id}/merge-requests/` | Project merge requests |
| `gitlab://projects/{id}/merge-requests/{iid}` | Specific MR with pipeline |
| `gitlab://projects/{id}/merge-requests/{iid}/discussions` | MR discussions |
| `gitlab://help/` | Resource documentation |

## Architecture

### Key Components

- **GitLabClient** - Handles all GitLab API communication
  - Automatic pagination with safety limits
  - Comprehensive error handling
  - Request logging and timing
  - Connectivity validation on startup

- **Resource Endpoints** - FastMCP resources for data access
  - Smart caching strategies
  - Structured error responses
  - Context-aware detection

- **Helper Functions** - Git and repository utilities
  - Branch detection
  - MR lookup
  - Project path parsing

### Error Handling

The server implements robust error handling:

- **Startup Validation** - Checks token and URL before starting
- **API Errors** - Logged with status codes and context
- **Network Errors** - Retry recommendations and clear messages
- **Rate Limiting** - Pagination limits prevent API abuse
- **Graceful Degradation** - Continues working if optional features fail

## Troubleshooting

### "GITLAB_TOKEN not set"

**Cause**: Environment variable not configured

**Solution**:
1. Copy `.env.example` to `.env`
2. Add your GitLab token to `.env`
3. Restart the MCP server

### "Invalid GITLAB_TOKEN - authentication failed"

**Cause**: Token is invalid or expired

**Solution**:
1. Generate a new token at https://gitlab.com/-/profile/personal_access_tokens
2. Ensure it has the required scopes (`api`, `read_api`, `read_user`, `read_repository`)
3. Update `.env` with the new token
4. Restart the MCP server

### "Cannot connect to GitLab"

**Cause**: Network issue or incorrect URL

**Solution**:
1. Check your GITLAB_URL in `.env`
2. Ensure it starts with `http://` or `https://`
3. Test connectivity: `curl https://your-gitlab.com/api/v4/version`
4. Check firewall/VPN settings

### "No open merge request found for branch"

**Cause**: No MR exists for the current branch

**Solution**:
1. Create an MR for your branch on GitLab
2. Ensure the MR is in "opened" state
3. Check you're on the correct branch: `git branch`

### Enabling Debug Logging

Set in `.env`:
```env
LOG_LEVEL=DEBUG
```

This provides detailed information about:
- API calls and responses
- Repository detection
- Branch and MR lookups
- Error details

## Security Best Practices

1. **Never commit `.env`** - Already in `.gitignore`
2. **Use token scopes carefully** - Only grant necessary permissions
3. **Rotate tokens regularly** - Set expiration dates
4. **Limit token access** - Use project-specific tokens when possible
5. **Monitor token usage** - Check GitLab audit logs periodically

## Development

### Running Tests

```bash
uv run pytest
```

### Code Style

The project follows:
- PEP 8 Python style guidelines
- Type hints for better IDE support
- Comprehensive docstrings
- Structured logging

### Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

MIT License - see [LICENSE](LICENSE) file for details

## Support

- **Issues**: https://github.com/janscheffler/gitlab-mcp/issues
- **Discussions**: https://github.com/janscheffler/gitlab-mcp/discussions
- **MCP Documentation**: https://modelcontextprotocol.io/

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for version history and changes.

## Related Projects

- [Model Context Protocol](https://modelcontextprotocol.io/) - The MCP specification
- [FastMCP](https://github.com/jlowin/fastmcp) - MCP framework for Python
- [Claude Code](https://docs.claude.com/claude-code) - VSCode extension for Claude
