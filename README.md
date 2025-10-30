# GitLab MCP Server

A production-ready Model Context Protocol (MCP) server that provides GitLab integration for AI assistants like Claude. Exposes GitLab projects, merge requests, pipelines, discussions, and more through a standardized interface.

## Features

- **Create Releases** - Create new releases with tags, descriptions, milestones, and asset links
- **Release Management** - List all releases and view specific release details
- **Create Merge Requests** - Create new MRs directly from your current branch or any branch
- **Current Branch MR Overview** - Complete details of the MR for your current branch
- **MR Discussions** - View and track discussion threads on merge requests
- **Code Changes** - See diffs and changed files in MRs
- **Pipeline Status** - Monitor CI/CD pipeline health
- **Approval Tracking** - Check who has approved and who needs to approve
- **Comment on MRs** - Leave comments and participate in discussions
- **Merge MRs** - Merge approved MRs with customizable options
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

# Optional - Repository path override
# The server automatically detects your workspace from MCP client roots.
# Set this only if you need to override automatic detection.
# GITLAB_REPO_PATH=/path/to/your/project

# Optional - Logging level
LOG_LEVEL=INFO
```

### Workspace Detection

The server automatically detects which GitLab repository you're working on using this priority order:

1. **MCP Workspace Roots** (Automatic - Recommended)
   - When using Claude Code or Claude Desktop, the server requests workspace roots from the client
   - This is the proper MCP implementation and works automatically
   - No configuration needed!

2. **Environment Variable** (Manual Override)
   - Set `GITLAB_REPO_PATH` in `.env` to force a specific repository
   - Useful for testing or if your MCP client doesn't support roots

3. **Current Working Directory** (Fallback)
   - If neither of the above work, uses the directory where the server is running
   - Less reliable but better than nothing

**Recommendation**: Just use Claude Code or Claude Desktop - they provide workspace roots automatically!

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
- "Create a release for version 1.0.0"
- "What releases exist in my project?"
- "Show me the details of release v1.0.0"
- "Create a merge request for my current branch"
- "What's the status of my MR?"
- "Any unresolved discussions on my merge request?"
- "What files changed in the current MR?"
- "Show me the pipeline status"
- "Comment on my MR saying the changes look good"
- "Merge my current MR"

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
| `gitlab://projects/current/merge-requests/current` | Complete MR overview (recommended) |
| `gitlab://projects/current/merge-requests/current/discussions` | Discussions on current branch MR |
| `gitlab://projects/current/merge-requests/current/changes` | Code changes/diff for current MR |
| `gitlab://projects/current/merge-requests/` | Open merge requests |
| `gitlab://projects/current/pipelines/` | Recent pipelines (last 20) |
| `gitlab://projects/current/releases/` | All releases in current project |
| `gitlab://projects/current/releases/{tag_name}` | Specific release by tag name |
| `gitlab://projects/current/` | Project information |

### Global Resources

| URI | Description |
|-----|-------------|
| `gitlab://projects/` | All accessible projects |
| `gitlab://projects/{id}` | Specific project details |
| `gitlab://projects/{id}/merge-requests/` | Project merge requests |
| `gitlab://projects/{id}/merge-requests/{iid}` | Specific MR with pipeline |
| `gitlab://projects/{id}/merge-requests/{iid}/discussions` | MR discussions |
| `gitlab://projects/{id}/releases/` | All releases in specific project |
| `gitlab://projects/{id}/releases/{tag_name}` | Specific release by tag |
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

### "Not in a GitLab repository or repository not found"

**Cause**: Server cannot detect your GitLab repository

**Solution**:

1. **Check workspace detection**:
   ```bash
   # Set LOG_LEVEL=DEBUG in .env to see detection details
   # The logs will show which method is being used
   ```

2. **If using Claude Code/Desktop** (should work automatically):
   - Ensure you have a folder open in the IDE
   - Check that the folder contains a git repository with a GitLab remote
   - Verify the remote matches your `GITLAB_URL` in `.env`

3. **Manual override** (if automatic detection fails):
   ```env
   # Add to .env
   GITLAB_REPO_PATH=/full/path/to/your/gitlab/project
   ```

4. **Verify GitLab remote**:
   ```bash
   cd /path/to/your/project
   git remote -v
   # Should show a URL matching your GITLAB_URL
   ```

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
