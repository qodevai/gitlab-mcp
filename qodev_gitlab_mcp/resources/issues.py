"""Issue resources for qodev-gitlab-mcp."""

import logging
from typing import Any

from fastmcp import Context
from qodev_gitlab_api import GitLabError, NotFoundError

from qodev_gitlab_mcp.server import gitlab_client, mcp
from qodev_gitlab_mcp.utils.errors import create_repo_not_found_error
from qodev_gitlab_mcp.utils.resolvers import resolve_project_id

logger = logging.getLogger(__name__)


@mcp.resource("gitlab://projects/{project_id}/issues/")
async def project_issues(ctx: Context, project_id: str) -> list[dict[str, Any]] | dict[str, Any]:
    """List open issues in a project (supports project_id="current")

    Returns up to 20 most recently updated open issues.
    For filtering by labels/assignees/milestone, use the GitLab API parameters via tools.
    """
    resolved_id, _ = await resolve_project_id(ctx, gitlab_client, project_id)
    if not resolved_id:
        return create_repo_not_found_error(gitlab_client.base_url)

    try:
        issues = gitlab_client.get_issues(resolved_id, state="opened")
        return issues
    except Exception as e:
        logger.error(f"Error fetching issues for project {project_id}: {e}")
        return {"error": f"Failed to fetch issues: {str(e)}"}


@mcp.resource("gitlab://projects/{project_id}/issues/{issue_iid}")
async def project_issue(ctx: Context, project_id: str, issue_iid: str) -> dict[str, Any]:
    """Get a specific issue by IID (supports project_id="current")

    Returns issue details including title, description, labels, assignees, state, milestone.
    For issue comments, use the separate /notes resource for minimal token usage.
    """
    resolved_id, _ = await resolve_project_id(ctx, gitlab_client, project_id)
    if not resolved_id:
        return create_repo_not_found_error(gitlab_client.base_url)

    # Validate issue_iid is numeric
    try:
        iid = int(issue_iid)
    except ValueError:
        return {"error": f"Invalid issue IID '{issue_iid}' - must be a number"}

    try:
        issue = gitlab_client.get_issue(resolved_id, iid)
        return issue
    except NotFoundError:
        return {"error": f"Issue #{iid} not found in project"}
    except GitLabError as e:
        return {"error": f"Failed to fetch issue #{iid}: {e}"}
    except Exception as e:
        logger.error(f"Error fetching issue #{iid} for project {project_id}: {e}")
        return {"error": f"Failed to fetch issue: {str(e)}"}


@mcp.resource("gitlab://projects/{project_id}/issues/{issue_iid}/notes")
async def project_issue_notes(ctx: Context, project_id: str, issue_iid: str) -> list[dict[str, Any]] | dict[str, Any]:
    """Get comments/notes on an issue (supports project_id="current")

    Returns all comments on the issue in chronological order.
    Use this granular resource to minimize token usage when you only need comments.
    """
    resolved_id, _ = await resolve_project_id(ctx, gitlab_client, project_id)
    if not resolved_id:
        return create_repo_not_found_error(gitlab_client.base_url)

    # Validate issue_iid is numeric
    try:
        iid = int(issue_iid)
    except ValueError:
        return {"error": f"Invalid issue IID '{issue_iid}' - must be a number"}

    try:
        notes = gitlab_client.get_issue_notes(resolved_id, iid)
        return notes
    except NotFoundError:
        return {"error": f"Issue #{iid} not found in project"}
    except GitLabError as e:
        return {"error": f"Failed to fetch notes for issue #{iid}: {e}"}
    except Exception as e:
        logger.error(f"Error fetching notes for issue #{iid} in project {project_id}: {e}")
        return {"error": f"Failed to fetch notes: {str(e)}"}
