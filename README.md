[![CI](https://github.com/qodevai/gitlab-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/qodevai/gitlab-mcp/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/qodev-gitlab-mcp)](https://pypi.org/project/qodev-gitlab-mcp/)

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

## Quick Start

Once configured, the MCP server gives your AI assistant access to GitLab. Example interactions:

- "Is my MR ready to merge?" -- checks pipeline, approvals, and unresolved discussions
- "Create a merge request for this branch" -- creates MR with auto-detected source branch
- "Wait for the pipeline to finish" -- monitors pipeline and reports results with failed job logs
- "Comment on MR !42 saying LGTM" -- posts a comment on the merge request

## Features

- Merge request management (create, comment, merge, close, inline comments)
- Pipeline monitoring with `wait_for_pipeline` tool
- Issue tracking (create, update, close, comment)
- Release management
- CI/CD variable management
- File uploads with image support
- Automatic "current" project/branch detection via MCP workspace roots

## Tools

The server exposes the following MCP tools:

### Merge Requests

| Tool | Description |
|------|-------------|
| `create_merge_request` | Create a new merge request |
| `update_merge_request` | Update MR title, description, labels, assignees, reviewers |
| `merge_merge_request` | Merge a merge request |
| `close_merge_request` | Close a merge request (with optional comment) |
| `comment_on_merge_request` | Leave a comment on a merge request |
| `create_inline_comment` | Add an inline comment on a specific line in a MR diff |
| `reply_to_discussion` | Reply to an existing discussion thread |
| `resolve_discussion_thread` | Resolve or unresolve a discussion thread |

### Pipelines

| Tool | Description |
|------|-------------|
| `wait_for_pipeline` | Wait for a pipeline to complete and return results |
| `download_artifact` | Download a job artifact to local filesystem |
| `retry_job` | Retry a failed CI/CD job |

### Issues

| Tool | Description |
|------|-------------|
| `create_issue` | Create a new issue |
| `update_issue` | Update an existing issue |
| `close_issue` | Close an issue |
| `comment_on_issue` | Leave a comment on an issue |

### Releases

| Tool | Description |
|------|-------------|
| `create_release` | Create a new release with tag, description, and assets |

### CI/CD Variables

| Tool | Description |
|------|-------------|
| `set_project_ci_variable` | Create or update a CI/CD variable (upsert) |

### Files

| Tool | Description |
|------|-------------|
| `upload_file` | Upload a file to GitLab for embedding in issues or MRs |

All tools support `project_id="current"` to auto-detect the project from the current working directory. Merge request tools also support `mr_iid="current"` to detect the MR for the current branch.

## Resources

The server exposes the following read-only MCP resources:

### Projects

| Resource URI | Description |
|--------------|-------------|
| `gitlab://projects/` | List all accessible projects |
| `gitlab://projects/{project_id}` | Get project details |

### Merge Requests

| Resource URI | Description |
|--------------|-------------|
| `gitlab://projects/{project_id}/merge-requests/` | List open merge requests |
| `gitlab://projects/{project_id}/merge-requests/{mr_iid}` | Full MR overview (metadata, discussions, changes, commits, pipeline, approvals) |
| `gitlab://projects/{project_id}/merge-requests/{mr_iid}/status` | Lightweight merge-readiness check |
| `gitlab://projects/{project_id}/merge-requests/{mr_iid}/discussions` | MR discussion threads |
| `gitlab://projects/{project_id}/merge-requests/{mr_iid}/changes` | MR diff/changes |
| `gitlab://projects/{project_id}/merge-requests/{mr_iid}/commits` | MR commit history |
| `gitlab://projects/{project_id}/merge-requests/{mr_iid}/approvals` | MR approval status |
| `gitlab://projects/{project_id}/merge-requests/{mr_iid}/pipeline-jobs` | Jobs from the MR's latest pipeline |

### Pipelines & Jobs

| Resource URI | Description |
|--------------|-------------|
| `gitlab://projects/{project_id}/pipelines/` | List recent pipelines |
| `gitlab://projects/{project_id}/pipelines/{pipeline_id}` | Get pipeline details |
| `gitlab://projects/{project_id}/pipelines/{pipeline_id}/jobs` | List jobs in a pipeline |
| `gitlab://projects/{project_id}/jobs/{job_id}/log` | Full job log output |
| `gitlab://projects/{project_id}/jobs/{job_id}/artifacts` | List job artifacts |
| `gitlab://projects/{project_id}/jobs/{job_id}/artifacts/{path}` | Read a specific artifact file |

### Issues

| Resource URI | Description |
|--------------|-------------|
| `gitlab://projects/{project_id}/issues/` | List open issues |
| `gitlab://projects/{project_id}/issues/{issue_iid}` | Get issue details |
| `gitlab://projects/{project_id}/issues/{issue_iid}/notes` | Get issue comments |

### Releases

| Resource URI | Description |
|--------------|-------------|
| `gitlab://projects/{project_id}/releases/` | List all releases |
| `gitlab://projects/{project_id}/releases/{tag_name}` | Get release by tag |

### CI/CD Variables

| Resource URI | Description |
|--------------|-------------|
| `gitlab://projects/{project_id}/variables/` | List CI/CD variables (metadata only, values hidden) |
| `gitlab://projects/{project_id}/variables/{key}` | Get variable metadata by key |

### Help

| Resource URI | Description |
|--------------|-------------|
| `gitlab://help` | Server capabilities and usage guide |

## License

MIT
