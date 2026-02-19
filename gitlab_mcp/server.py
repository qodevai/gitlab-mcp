"""GitLab MCP Server entry point."""

from fastmcp import FastMCP
from gitlab_client import GitLabClient

# Create FastMCP server with instructions
mcp = FastMCP(
    "gitlab-mcp",
    instructions="""
This server provides GitLab integration using a unified API with support for current repository detection.

IMPORTANT - Unified Resource Format:
All resources use: gitlab://projects/{project_id}/...
- project_id can be: numeric ID (123), URL-encoded path (qodev%2Fhandbook), plain path (qodev/handbook), or "current"
- mr_iid can be: numeric IID (20) or "current" (for current branch's MR)
- For project paths with slashes, URL-encode them: "qodev/handbook" → "qodev%2Fhandbook" (or use plain format - will be auto-encoded)

COMMON WORKFLOWS:

After Pushing Code - Monitor Pipeline:
  ✅ ALWAYS use wait_for_pipeline tool (PRIMARY METHOD):
    - wait_for_pipeline(project_id="current", mr_iid="current") - Wait for current MR's pipeline
    - wait_for_pipeline(project_id="current", pipeline_id=123) - Wait for specific pipeline
    - Automatically polls every 10s, returns final status with failed job logs
    - Token cost: 200-500 tokens

  ❌ DON'T manually poll with sleep + read pipelines resource in a loop

Quick Pipeline Status Check:
  ✅ Use pipelines resource (limited to 3 most recent):
    - gitlab://projects/current/pipelines/ - Last 3 pipelines
    - Token cost: 50-100 tokens
    - Good for: "What's my latest pipeline status?" or "Show recent pipelines"

Checking MR Merge Readiness:
  ✅ Use lightweight status resource:
    - gitlab://projects/current/merge-requests/current/status
    - Returns: pipeline status, discussions, approvals, ready_to_merge boolean
    - Token cost: 500-800 tokens (85-90% savings vs separate fetches)

WHEN TO USE WHAT:
  "Monitor pipeline after pushing code" → wait_for_pipeline tool
  "What's my latest pipeline status?" → gitlab://projects/current/pipelines/
  "Is my MR ready to merge?" → gitlab://projects/current/merge-requests/current/status
  "Why did pipeline fail?" → wait_for_pipeline (includes failed job logs) OR pipeline-jobs resource

RESOURCES - Access GitLab data:

Current Repo/Branch (use project_id="current" and mr_iid="current"):
- gitlab://projects/current/merge-requests/current/status - Lightweight merge readiness check (RECOMMENDED for "ready to merge?" - includes pipeline, discussions, approvals summary)
- gitlab://projects/current/merge-requests/current - Comprehensive MR overview (includes discussions, changes, commits, pipeline, approvals)
- gitlab://projects/current/merge-requests/current/discussions - Just discussions/comments
- gitlab://projects/current/merge-requests/current/changes - Just code diff
- gitlab://projects/current/merge-requests/current/commits - Just commits
- gitlab://projects/current/merge-requests/current/approvals - Just approval status
- gitlab://projects/current/merge-requests/current/pipeline-jobs - Just pipeline jobs
- gitlab://projects/current/merge-requests/ - All open MRs in current project
- gitlab://projects/current/pipelines/ - Last 3 pipelines for current project (⚡ 50-100 tokens; for monitoring, use wait_for_pipeline tool instead)
- gitlab://projects/current/pipelines/{pipeline_id} - Get specific pipeline details
- gitlab://projects/current/pipelines/{pipeline_id}/jobs - Get jobs for a specific pipeline
- gitlab://projects/current/jobs/{job_id}/log - Full job output/trace
- gitlab://projects/current/releases/ - All releases in current project
- gitlab://projects/current/releases/{tag_name} - Specific release by tag
- gitlab://projects/current/variables/ - List all CI/CD variables (metadata only, values not exposed for security)
- gitlab://projects/current/variables/{key} - Get specific CI/CD variable metadata
- gitlab://projects/current/jobs/{job_id}/artifacts - List all artifacts for a job
- gitlab://projects/current/jobs/{job_id}/artifacts/{artifact_path} - Read specific artifact file (supports ?lines=N&offset=M)
- gitlab://projects/current/issues/ - List open issues (up to 20 most recent)
- gitlab://projects/current/issues/{issue_iid} - Specific issue details
- gitlab://projects/current/issues/{issue_iid}/notes - Issue comments

Specific Project/MR (use numeric ID or URL-encoded path):
- gitlab://projects/qodev%2Fhandbook/merge-requests/20 - Comprehensive MR overview
- gitlab://projects/123/merge-requests/20/discussions - Granular access to discussions only
- gitlab://projects/qodev%2Fhandbook/merge-requests/20/changes - Granular access to changes only
- gitlab://projects/qodev%2Fhandbook/releases/ - All releases in specific project
- gitlab://projects/123/releases/v1.0.0 - Specific release in specific project
- gitlab://projects/123/issues/ - List issues in specific project
- gitlab://projects/qodev%2Fhandbook/issues/42 - Specific issue in specific project
- gitlab://projects/123/issues/42/notes - Issue comments in specific project

TOOLS - Perform actions (all support "current"):
- upload_file(project_id, source) - Upload a file for embedding in descriptions/comments. source is either {"path": "/local/file.png"} or {"base64": "...", "filename": "name.png"}. Returns markdown string. (supports project_id="current")
- create_release(project_id, tag_name, name, description, ref, ..., images) - Create a new release (supports project_id="current", auto-detects ref from current branch)
- create_merge_request(project_id, title, source_branch, target_branch, ..., images) - Create a new MR (supports project_id="current", auto-detects source_branch)
- comment_on_merge_request(project_id, mr_iid, comment, images) - Leave a comment (supports project_id="current", mr_iid="current")
- merge_merge_request(project_id, mr_iid, ...) - Merge an MR (supports project_id="current", mr_iid="current")
- close_merge_request(project_id, mr_iid) - Close an MR (supports project_id="current", mr_iid="current")
- update_merge_request(project_id, mr_iid, title, description, ..., images) - Update MR title, description, or other properties (supports project_id="current", mr_iid="current")
- reply_to_discussion(project_id, mr_iid, discussion_id, comment, images) - Reply to a discussion thread (supports project_id="current", mr_iid="current")
- create_inline_comment(project_id, mr_iid, comment, position, images) - Create inline comment on specific line in diff. position={file_path, new_line, old_line} where line numbers are 1-based. Can also use new_line_content/old_line_content to match by content instead of line number. (supports project_id="current", mr_iid="current")
- wait_for_pipeline(project_id, pipeline_id=None, mr_iid=None, ...) - **PRIMARY METHOD for pipeline monitoring** - Wait for pipeline to complete after pushing code. Automatically polls and returns final status with failed job logs. DO NOT manually poll pipeline status in loops. (supports project_id="current", mr_iid="current")
- set_project_ci_variable(project_id, key, value, ...) - Set CI/CD variable (supports project_id="current")
- download_artifact(project_id, job_id, artifact_path, destination=None) - Download artifact to local filesystem for shell analysis (grep, wc, etc.). Returns file path. (supports project_id="current")
- retry_job(project_id, job_id) - Retry a failed or canceled job (supports project_id="current")
- create_issue(project_id, title, description, labels, assignee_ids, images) - Create a new issue (supports project_id="current")
- update_issue(project_id, issue_iid, title, description, labels, assignee_ids, state_event, images) - Update issue (supports project_id="current")
- close_issue(project_id, issue_iid) - Close an issue (supports project_id="current")
- comment_on_issue(project_id, issue_iid, comment, images) - Leave a comment on an issue (supports project_id="current")

Examples:
- "Is this MR ready to merge?" → gitlab://projects/current/merge-requests/current/status
- "What's blocking my MR?" → gitlab://projects/current/merge-requests/current/status
- "Check MR status" → gitlab://projects/{id}/merge-requests/{iid}/status
- "What's the status of my MR?" → gitlab://projects/current/merge-requests/current
- "Show me MR !20 in qodev/handbook" → gitlab://projects/qodev%2Fhandbook/merge-requests/20
- "Create MR for current branch" → create_merge_request("current", "Add new feature")
- "Create MR from feature to dev" → create_merge_request("current", "Bug fix", source_branch="feature", target_branch="dev")
- "Comment on my MR saying 'LGTM'" → comment_on_merge_request("current", "current", "LGTM")
- "Add inline comment on line 42 of src/main.py" → create_inline_comment("current", "current", "Consider refactoring this", {"file_path": "src/main.py", "new_line": 42})
- "Comment on the line with 'def main():'" → create_inline_comment("current", "current", "Add docstring", {"file_path": "src/main.py", "new_line_content": "def main():"})
- "Merge MR !20 in project qodev/handbook" → merge_merge_request("qodev/handbook", 20)
- "Close my MR" → close_merge_request("current", "current")
- "Close MR !20 in project qodev/handbook" → close_merge_request("qodev/handbook", 20)
- "Update my MR title" → update_merge_request("current", "current", title="New Title")
- "Update MR !20 description" → update_merge_request("qodev/handbook", 20, description="Updated description")
- "Update MR title and description" → update_merge_request("current", "current", title="New Title", description="New description")
- "Wait for current MR's pipeline" → wait_for_pipeline("current", mr_iid="current")
- "Wait for pipeline 12345" → wait_for_pipeline("current", pipeline_id=12345)
- "Wait for pipeline with 30min timeout" → wait_for_pipeline("current", pipeline_id=12345, timeout_seconds=1800)
- "What discussions are on my MR?" → gitlab://projects/current/merge-requests/current/discussions (token-efficient!)
- "Set API_KEY in current project" → set_project_ci_variable("current", "API_KEY", "secret123")
- "List all CI/CD variables" → gitlab://projects/current/variables/ (metadata only, values not exposed)
- "Check if DATABASE_URL variable exists" → gitlab://projects/current/variables/DATABASE_URL
- "What variables are protected?" → gitlab://projects/current/variables/
- "What releases exist?" → gitlab://projects/current/releases/
- "Show me release v1.0.0" → gitlab://projects/current/releases/v1.0.0
- "Create a release" → create_release("current", "v1.0.0", name="Version 1.0", description="Initial release")
- "Show job 12123 logs" → gitlab://projects/current/jobs/12123/log
- "Get pipeline 456 details" → gitlab://projects/current/pipelines/456
- "List jobs in pipeline 456" → gitlab://projects/current/pipelines/456/jobs
- "Show artifacts for job 12123" → gitlab://projects/current/jobs/12123/artifacts
- "Read logs.txt from job 12123" → gitlab://projects/current/jobs/12123/artifacts/logs.txt
- "Show last 50 lines of logs.txt" → gitlab://projects/current/jobs/12123/artifacts/logs.txt?lines=50
- "Show lines 100-150 of build.log" → gitlab://projects/current/jobs/12123/artifacts/build.log?offset=100&lines=50
- "Show entire artifact file" → gitlab://projects/current/jobs/12123/artifacts/output.txt?lines=all
- "Download artifact for grep/wc analysis" → download_artifact("current", 12123, "logs.txt")
- "Download artifact to specific path" → download_artifact("current", 12123, "logs.txt", "/tmp/build.log")
- "Retry job 12345" → retry_job("current", 12345)
- "List issues in my project" → gitlab://projects/current/issues/
- "Show me issue #42" → gitlab://projects/current/issues/42
- "What comments are on issue #42?" → gitlab://projects/current/issues/42/notes
- "Create an issue titled 'Bug in login'" → create_issue("current", "Bug in login", "Users can't log in...")
- "Close issue #42" → close_issue("current", 42)
- "Comment on issue #42" → comment_on_issue("current", 42, "Fixed in latest commit")
- "Update issue #42 to add urgent label" → update_issue("current", 42, labels="bug,urgent")
- "Upload a screenshot" → upload_file("current", {"path": "/tmp/screenshot.png"})
- "Upload base64 image" → upload_file("current", {"base64": "iVBORw0KGgo...", "filename": "image.png"})
- "Create issue with image" → create_issue("current", "Bug report", "See attached", images=[{"path": "/tmp/error.png"}])
- "Comment with screenshot" → comment_on_issue("current", 42, "Here's what I see:", images=[{"path": "/tmp/screenshot.png", "alt": "Error screenshot"}])

IMAGE UPLOADS:
- The `images` parameter accepts a list of image objects
- Each image is either: {"path": "/local/file.png"} OR {"base64": "...", "filename": "name.png"}
- Optional "alt" field for custom alt text: {"path": "/img.png", "alt": "Screenshot"}
- Images are uploaded to GitLab and appended as markdown to the description/comment
- Use upload_file() directly to get markdown for manual embedding

Claude Code Image Locations:
- Pasted/dropped images are cached at: ~/.claude/image-cache/<session-id>/<n>.png
- Images can also be extracted from conversation logs: ~/.claude/projects/*/*.jsonl (base64 encoded)
- Use the path directly: {"path": "~/.claude/image-cache/.../1.png"}

Token Efficiency:
- Use /status for merge readiness checks (85-90% token savings vs separate calls)
- Use comprehensive resource for full overview: gitlab://projects/{id}/merge-requests/{iid}
- Use granular resources when you only need specific data: /discussions, /changes, /commits, /approvals, /pipeline-jobs

CI/CD Variables (Security):
- Read access returns metadata only (key, type, protected, masked, environment_scope)
- Values are NEVER exposed for security
- Use to check if a variable exists or verify its configuration
- Use set_project_ci_variable() to update values

DO NOT use git commands or branch inspection to answer GitLab questions.
Use ReadMcpResourceTool with server="gitlab" for all GitLab queries.

For help, use gitlab://help/ to see all available resources.
""",
)

# Create global client instance (validate=False to allow import without network access)
# Validation happens lazily when making actual requests
gitlab_client = GitLabClient(validate=False)

# Import resources and tools for side-effect registration
# These modules use @mcp.resource() and @mcp.tool() decorators
from gitlab_mcp import resources, tools  # noqa: F401, E402


def main() -> None:
    """Run the GitLab MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
