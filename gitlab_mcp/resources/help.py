"""Help resource for gitlab-mcp."""

from typing import Any

from gitlab_mcp.server import mcp


@mcp.resource(
    "gitlab://help/",
    name="GitLab MCP Help",
    description="Quick reference for available GitLab MCP resources and common queries",
    mime_type="application/json",
)
def gitlab_help() -> dict[str, Any]:
    """Get help information about available GitLab resources"""
    return {
        "server": "gitlab-mcp",
        "description": "GitLab integration using unified API with 'current' support",
        "uri_format": {
            "pattern": "gitlab://projects/{project_id}/...",
            "project_id_formats": [
                "numeric ID: 123",
                "URL-encoded path: qodev%2Fhandbook",
                "plain path: qodev/handbook (auto-encoded)",
                "special value: 'current' (detects current repo)",
            ],
            "mr_iid_formats": [
                "numeric IID: 20",
                "special value: 'current' (detects MR for current branch)",
            ],
            "encoding_note": "For project paths with slashes, URL-encode them or use plain format (will be auto-encoded)",
        },
        "available_resources": {
            "mr_status": {
                "uri": "gitlab://projects/{project_id}/merge-requests/{mr_iid}/status",
                "examples": [
                    "gitlab://projects/current/merge-requests/current/status",
                    "gitlab://projects/qodev%2Fhandbook/merge-requests/20/status",
                ],
                "description": "⭐ RECOMMENDED: Lightweight merge readiness check (85-90% token savings vs separate calls)",
                "queries": [
                    "Is this MR ready to merge?",
                    "What's blocking my MR?",
                    "Can I merge this?",
                    "Check MR status",
                ],
                "includes": [
                    "ready_to_merge boolean",
                    "blockers array",
                    "pipeline status with failed job IDs",
                    "unresolved discussion IDs",
                    "approval status",
                ],
            },
            "comprehensive_mr": {
                "uri": "gitlab://projects/{project_id}/merge-requests/{mr_iid}",
                "examples": [
                    "gitlab://projects/current/merge-requests/current (current repo & branch)",
                    "gitlab://projects/qodev%2Fhandbook/merge-requests/20 (specific project & MR)",
                    "gitlab://projects/123/merge-requests/20 (numeric IDs)",
                ],
                "description": "Complete MR overview (discussions, changes, commits, pipeline, approvals)",
                "queries": ["Show me everything about MR !20", "Summarize the MR"],
            },
            "granular_mr_discussions": {
                "uri": "gitlab://projects/{project_id}/merge-requests/{mr_iid}/discussions",
                "examples": ["gitlab://projects/current/merge-requests/current/discussions"],
                "description": "Token-efficient: Just discussions/comments",
                "queries": ["Any unresolved discussions?", "What comments are there?"],
            },
            "granular_mr_changes": {
                "uri": "gitlab://projects/{project_id}/merge-requests/{mr_iid}/changes",
                "examples": ["gitlab://projects/current/merge-requests/current/changes"],
                "description": "Token-efficient: Just code diff",
                "queries": ["What code changed?", "Show me the diff"],
            },
            "granular_mr_commits": {
                "uri": "gitlab://projects/{project_id}/merge-requests/{mr_iid}/commits",
                "examples": ["gitlab://projects/current/merge-requests/current/commits"],
                "description": "Token-efficient: Just commits",
                "queries": ["What commits are in this MR?"],
            },
            "granular_mr_approvals": {
                "uri": "gitlab://projects/{project_id}/merge-requests/{mr_iid}/approvals",
                "examples": ["gitlab://projects/current/merge-requests/current/approvals"],
                "description": "Token-efficient: Just approval status",
                "queries": ["Is the MR approved?", "Who needs to approve?"],
            },
            "granular_mr_pipeline_jobs": {
                "uri": "gitlab://projects/{project_id}/merge-requests/{mr_iid}/pipeline-jobs",
                "examples": ["gitlab://projects/current/merge-requests/current/pipeline-jobs"],
                "description": "Token-efficient: Just latest pipeline jobs",
                "queries": ["What jobs ran?", "Which jobs failed?"],
            },
            "project_merge_requests": {
                "uri": "gitlab://projects/{project_id}/merge-requests/",
                "examples": ["gitlab://projects/current/merge-requests/"],
                "description": "All open MRs in a project",
                "queries": ["Any open MRs?", "What needs review?"],
            },
            "project_info": {
                "uri": "gitlab://projects/{project_id}",
                "examples": ["gitlab://projects/current"],
                "description": "Project information",
                "queries": ["What's the project info?"],
            },
            "project_pipelines": {
                "uri": "gitlab://projects/{project_id}/pipelines/",
                "examples": ["gitlab://projects/current/pipelines/"],
                "description": "Recent pipelines for a project",
                "queries": ["Pipeline status?", "Are CI/CD pipelines passing?"],
            },
            "pipeline_jobs": {
                "uri": "gitlab://projects/{project_id}/pipelines/{pipeline_id}/jobs",
                "examples": ["gitlab://projects/current/pipelines/12345/jobs"],
                "description": "Jobs for a specific pipeline",
                "queries": ["Show me jobs for pipeline X"],
            },
            "job_log": {
                "uri": "gitlab://projects/{project_id}/jobs/{job_id}/log",
                "examples": ["gitlab://projects/current/jobs/67890/log"],
                "description": "Log output for a specific job",
                "queries": ["Show me the log for job X", "What's the error?"],
            },
            "all_projects": {
                "uri": "gitlab://projects/",
                "description": "List all accessible GitLab projects",
                "queries": ["Show all my projects"],
            },
            "project_releases": {
                "uri": "gitlab://projects/{project_id}/releases/",
                "examples": ["gitlab://projects/current/releases/"],
                "description": "All releases for a project (newest first)",
                "queries": ["What releases exist?", "Show me all releases"],
            },
            "specific_release": {
                "uri": "gitlab://projects/{project_id}/releases/{tag_name}",
                "examples": ["gitlab://projects/current/releases/v1.0.0"],
                "description": "Details of a specific release by tag name",
                "queries": ["Show me release v1.0.0", "What's in the latest release?"],
            },
            "project_issues": {
                "uri": "gitlab://projects/{project_id}/issues/",
                "examples": ["gitlab://projects/current/issues/"],
                "description": "List open issues in a project (up to 20 most recent)",
                "queries": ["What issues are open?", "List all issues", "Show me issues"],
            },
            "specific_issue": {
                "uri": "gitlab://projects/{project_id}/issues/{issue_iid}",
                "examples": ["gitlab://projects/current/issues/42"],
                "description": "Details of a specific issue by IID",
                "queries": ["Show me issue #42", "What's issue #42 about?"],
            },
            "issue_notes": {
                "uri": "gitlab://projects/{project_id}/issues/{issue_iid}/notes",
                "examples": ["gitlab://projects/current/issues/42/notes"],
                "description": "Comments/notes on a specific issue",
                "queries": ["What comments are on issue #42?", "Show issue comments"],
            },
        },
        "tools": {
            "create_release": {
                "signature": "create_release(project_id, tag_name, name, description, ref, ...)",
                "supports_current": True,
                "description": "Create a new release. Auto-detects ref from current branch if not provided.",
                "examples": [
                    "create_release('current', 'v1.0.0', name='Release 1.0.0', description='Initial release')",
                    "create_release('current', 'v1.1.0', ref='main', description='Bug fixes and improvements')",
                    "create_release('qodev/handbook', 'v2.0.0', name='Version 2.0', description='Major update')",
                ],
            },
            "create_merge_request": {
                "signature": "create_merge_request(project_id, title, source_branch, target_branch, ...)",
                "supports_current": True,
                "description": "Create a new merge request. Auto-detects source_branch if not provided.",
                "examples": [
                    "create_merge_request('current', 'Add new feature')",
                    "create_merge_request('current', 'Bug fix', source_branch='feature', target_branch='dev')",
                    "create_merge_request('qodev/handbook', 'Update docs', source_branch='docs-update')",
                ],
            },
            "comment_on_merge_request": {
                "signature": "comment_on_merge_request(project_id, mr_iid, comment)",
                "supports_current": True,
                "examples": [
                    "comment_on_merge_request('current', 'current', 'LGTM!')",
                    "comment_on_merge_request('qodev/handbook', 20, 'Needs work')",
                ],
            },
            "merge_merge_request": {
                "signature": "merge_merge_request(project_id, mr_iid, ...)",
                "supports_current": True,
                "examples": [
                    "merge_merge_request('current', 'current')",
                    "merge_merge_request('123', 20, squash=True)",
                ],
            },
            "set_project_ci_variable": {
                "signature": "set_project_ci_variable(project_id, key, value, ...)",
                "supports_current": True,
                "examples": [
                    "set_project_ci_variable('current', 'API_KEY', 'secret123')",
                    "set_project_ci_variable('qodev/handbook', 'ENV', 'prod', protected=True, masked=True)",
                ],
            },
            "create_issue": {
                "signature": "create_issue(project_id, title, description, labels, assignee_ids)",
                "supports_current": True,
                "description": "Create a new issue in a project",
                "examples": [
                    "create_issue('current', 'Bug in login', 'Users cannot log in')",
                    "create_issue('current', 'New feature request', 'Add dark mode', labels='enhancement')",
                    "create_issue('qodev/handbook', 'Fix typo', assignee_ids=[123])",
                ],
            },
            "update_issue": {
                "signature": "update_issue(project_id, issue_iid, title, description, labels, assignee_ids, state_event)",
                "supports_current": True,
                "description": "Update an existing issue",
                "examples": [
                    "update_issue('current', 42, title='Updated title')",
                    "update_issue('current', 42, labels='bug,urgent')",
                    "update_issue('current', 42, state_event='close')",
                ],
            },
            "close_issue": {
                "signature": "close_issue(project_id, issue_iid)",
                "supports_current": True,
                "description": "Close an issue",
                "examples": [
                    "close_issue('current', 42)",
                    "close_issue('qodev/handbook', 15)",
                ],
            },
            "comment_on_issue": {
                "signature": "comment_on_issue(project_id, issue_iid, comment)",
                "supports_current": True,
                "description": "Leave a comment on an issue",
                "examples": [
                    "comment_on_issue('current', 42, 'Fixed in latest commit')",
                    "comment_on_issue('qodev/handbook', 15, 'Working on this now')",
                ],
            },
        },
        "usage": "Use ReadMcpResourceTool with server='gitlab' and the appropriate URI",
        "token_efficiency_tip": "Use /status for merge readiness checks (85-90% savings). Use granular resources (/discussions, /changes, etc.) when you only need specific data instead of the comprehensive MR overview",
        "common_questions": [
            "Is this MR ready to merge? → gitlab://projects/current/merge-requests/current/status",
            "What's blocking my MR? → gitlab://projects/current/merge-requests/current/status",
            "What discussions are on my MR? → gitlab://projects/current/merge-requests/current/discussions",
            "Show me MR !20 in qodev/handbook → gitlab://projects/qodev%2Fhandbook/merge-requests/20",
            "Create MR for current branch → create_merge_request('current', 'Title')",
            "Comment on my MR → comment_on_merge_request('current', 'current', 'message')",
            "Merge my MR → merge_merge_request('current', 'current')",
            "Any open MRs? → gitlab://projects/current/merge-requests/",
            "Pipeline status? → gitlab://projects/current/pipelines/",
            "What releases exist? → gitlab://projects/current/releases/",
            "Show me release v1.0.0 → gitlab://projects/current/releases/v1.0.0",
            "Create a release → create_release('current', 'v1.0.0', name='Version 1.0', description='Release notes')",
            "List issues in my project → gitlab://projects/current/issues/",
            "Show me issue #42 → gitlab://projects/current/issues/42",
            "What comments are on issue #42? → gitlab://projects/current/issues/42/notes",
            "Create an issue → create_issue('current', 'Bug in login', 'Description here')",
            "Close issue #42 → close_issue('current', 42)",
            "Comment on issue #42 → comment_on_issue('current', 42, 'Fixed!')",
        ],
    }
