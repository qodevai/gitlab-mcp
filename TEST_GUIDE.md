# Testing the GitLab MCP Server

## Overview

The GitLab MCP server provides rich integration with GitLab for your current repository. It includes:

- **Smart Instructions**: Guides AI assistants on when to use GitLab resources
- **Enhanced Descriptions**: Common query patterns for better discoverability
- **Quick Status**: Summary view of project health
- **Help Resource**: Built-in documentation

## Available Resources

### Current Project Resources

- `gitlab://current-project/` - Project information
- `gitlab://current-project/status/` - Quick status overview (NEW!)
- `gitlab://current-project/merge-requests/` - Open MRs
- `gitlab://current-project/all-merge-requests/` - All MRs
- `gitlab://current-project/merged-merge-requests/` - Merged MRs
- `gitlab://current-project/closed-merge-requests/` - Closed MRs
- `gitlab://current-project/pipelines/` - Recent pipelines

### Helper Resources

- `gitlab://help/` - Quick reference and documentation (NEW!)

### Global Resources

- `gitlab://projects/` - All accessible projects
- `gitlab://projects/{id}` - Specific project
- `gitlab://projects/{id}/merge-requests/` - Project MRs
- `gitlab://projects/{id}/pipelines/` - Project pipelines

## Option 1: Using MCP Inspector (Recommended for Testing)

The MCP Inspector allows you to test your MCP server interactively:

```bash
npx -y @modelcontextprotocol/inspector uv run python gitlab_mcp.py
```

This will:
1. Start your MCP server
2. Open a web interface at http://localhost:5173
3. Allow you to test resources and tools

### Important: Setting Workspace Roots

When testing `current-project` resources, you need to configure the workspace root in the Inspector:

1. Click on "Configure" or "Settings" in the Inspector UI
2. Add a root path pointing to your git repository, e.g.:
   ```
   file:///Users/janscheffler/dev/meinungsmonitor/app
   ```
3. Now when you call the `gitlab://current-project/` resource, it will have the correct context

### Testing Resources in the Inspector

1. In the Inspector, go to "Resources"
2. Try these resources:
   - `gitlab://help/` - See all available resources and usage examples
   - `gitlab://current-project/status/` - Get a quick project overview
   - `gitlab://current-project/` - Full project information
   - `gitlab://current-project/merge-requests/` - Open MRs

## Option 2: Using with Claude Code (Primary Use Case)

Claude Code automatically uses the opened workspace folder as the root, so no manual configuration is needed!

### Setup

1. Add the server to your Claude Code MCP config (if not already configured)

2. Open a GitLab repository in Claude Code

3. Try these natural language queries:
   - "Are there any open merge requests?"
   - "What's the pipeline status?"
   - "Show me merged MRs"
   - "What needs review?"
   - "Give me a project overview"
   - "What's the current status?"

Claude Code will automatically:
- Recognize these as GitLab queries
- Use the appropriate `gitlab://current-project/*` resource
- Parse and present the results naturally

### How It Works

The server includes **instructions** that guide Claude Code:

```
Common user queries that should use this MCP:
- "Are there any open merge requests?" → gitlab://current-project/merge-requests/
- "What's the pipeline status?" → gitlab://current-project/pipelines/
- "What's the project status?" → gitlab://current-project/status/
```

Each resource also includes **enhanced descriptions** with example queries, making it easy for Claude Code to understand when to use them.

## Option 3: Testing from Claude Desktop

1. Add the server to your Claude Desktop config at:
   - macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "gitlab": {
      "command": "uv",
      "args": ["run", "python", "/Users/janscheffler/dev/mcps/gitlab/gitlab_mcp.py"],
      "env": {
        "GITLAB_TOKEN": "your-token-here",
        "GITLAB_URL": "https://gitlab.qodev.ai"
      }
    }
  }
}
```

2. Restart Claude Desktop
3. Open a project/folder in Claude Desktop (use the folder icon or open via VSCode)
4. The workspace root will automatically be set to that folder
5. Ask Claude natural language questions like "Are there any open MRs?"

## Option 4: Direct Python Testing

Run the detection test script:

```bash
uv run python test_detection.py
```

This tests the git detection logic directly without the MCP layer.

## New Features

### Quick Status Resource

Get a project overview in one call:

```
gitlab://current-project/status/
```

Returns:
- Project info (name, ID, URL)
- Open MR count and first 5 MRs
- Latest pipeline status
- Text summary

### Help Resource

Built-in documentation:

```
gitlab://help/
```

Returns:
- All available resources with URIs
- Example queries for each resource
- Usage instructions
- Common questions

### Enhanced Descriptions

All resources now include common query patterns in their descriptions, helping Claude Code understand when to use them:

**Example:**
```
gitlab://current-project/merge-requests/

Use this when users ask:
- "Are there any open merge requests?"
- "What MRs are open?"
- "Any pending merges?"
- "What needs review?"
```

### Server Instructions

The FastMCP server now includes comprehensive instructions that guide Claude Code on:
- When to use GitLab resources vs git commands
- Which resource to use for which query
- Common query patterns

## Testing Discussion Thread Interactions

The server now supports replying to and managing discussion threads on merge requests.

### Testing with MCP Inspector

1. **Get Discussion IDs**:
   ```
   Resource: gitlab://current-project/merge-requests/{mr_iid}/discussions
   ```
   This returns all discussion threads with their IDs.

2. **Reply to a Discussion**:
   ```
   Tool: reply_to_discussion
   Parameters:
   - project_id: "current" or "mygroup/myproject" or "123"
   - mr_iid: "current" or "42"
   - discussion_id: "abc123..." (from discussions resource)
   - comment: "Thanks for the review! Fixed."
   ```

3. **Resolve a Discussion Thread**:
   ```
   Tool: resolve_discussion_thread
   Parameters:
   - project_id: "current" or "mygroup/myproject"
   - mr_iid: "current" or "42"
   - discussion_id: "abc123..."
   - resolved: true (or false to unresolve)
   ```

### Testing with Claude Code

Try these natural language queries:
- "Reply to discussion abc123 on the current MR with 'Fixed this issue'"
- "Resolve discussion abc123 on MR !42"
- "Unresolve the first discussion thread"
- "Reply to all unresolved discussions with 'Working on this'"

### Common Test Scenarios

1. **Reply to reviewer feedback**:
   - Get discussions for current branch MR
   - Reply to specific discussion thread
   - Verify reply appears in GitLab UI

2. **Resolve discussions after fixes**:
   - Reply to discussion explaining the fix
   - Resolve the discussion thread
   - Verify resolved status in GitLab UI

3. **Unresolve for further discussion**:
   - Unresolve a previously resolved thread
   - Add a new reply with questions
   - Verify thread is marked as unresolved

### Error Handling Tests

Test these error scenarios:
- Invalid discussion_id → Should return helpful error
- Non-existent MR → Should return not found error
- No permissions → Should return permission error
- Missing required parameters → Should return validation error

## Troubleshooting

### Error: "Not in a GitLab repository or repository not found"

This error occurs when:

1. **No workspace root is set** - The MCP client needs to provide workspace roots via the Context
2. **Wrong workspace root** - The root path doesn't point to a git repository
3. **Remote URL mismatch** - The git remote doesn't match your GITLAB_URL
4. **API access issue** - The token can't access the project on GitLab

### Debugging Steps

1. Check if the workspace root is being passed to the MCP server
2. Verify the git remote matches your GitLab instance:
   ```bash
   git -C ~/dev/meinungsmonitor/app remote -v
   # Should show: git@gitlab.qodev.ai:delfio/app.git
   ```
3. Verify your GitLab token can access the project:
   ```bash
   curl -H "PRIVATE-TOKEN: your-token" \
     https://gitlab.qodev.ai/api/v4/projects/delfio%2Fapp
   ```

### Understanding Context Roots

The MCP Context provides workspace roots that tell the server which directories are "active":
- In Claude Desktop: Set by the opened project folder
- In MCP Inspector: Must be manually configured
- In VSCode Extension: Set by the workspace folders

If no roots are provided, the current-project resources cannot work.
