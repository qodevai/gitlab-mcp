"""Release resources for gitlab-mcp."""

from typing import Any

from fastmcp import Context
from gitlab_client import GitLabError, NotFoundError

from gitlab_mcp.server import gitlab_client, mcp
from gitlab_mcp.utils.errors import create_repo_not_found_error
from gitlab_mcp.utils.resolvers import resolve_project_id


@mcp.resource("gitlab://projects/{project_id}/releases/")
async def project_releases(ctx: Context, project_id: str) -> list[dict[str, Any]] | dict[str, Any]:
    """Get all releases for a project (supports project_id="current")

    Returns releases sorted by released_at in descending order (newest first).
    """
    resolved_id, _ = await resolve_project_id(ctx, gitlab_client, project_id)
    if not resolved_id:
        return create_repo_not_found_error(gitlab_client.base_url)
    return gitlab_client.get_releases(resolved_id)


@mcp.resource("gitlab://projects/{project_id}/releases/{tag_name}")
async def project_release(ctx: Context, project_id: str, tag_name: str) -> dict[str, Any]:
    """Get a specific release by tag name (supports project_id="current")"""
    resolved_id, _ = await resolve_project_id(ctx, gitlab_client, project_id)
    if not resolved_id:
        return create_repo_not_found_error(gitlab_client.base_url)

    try:
        return gitlab_client.get_release(resolved_id, tag_name)
    except NotFoundError:
        return {"error": f"Release with tag '{tag_name}' not found in project {project_id}"}
    except GitLabError as e:
        return {"error": f"Failed to fetch release '{tag_name}': {str(e)[:200]}"}
