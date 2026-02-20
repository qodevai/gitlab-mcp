"""CI/CD variable resources for qodev-gitlab-mcp."""

from typing import Any

from fastmcp import Context

from qodev_gitlab_mcp.server import gitlab_client, mcp
from qodev_gitlab_mcp.utils.errors import create_repo_not_found_error
from qodev_gitlab_mcp.utils.resolvers import resolve_project_id


@mcp.resource("gitlab://projects/{project_id}/variables/")
async def project_variables(ctx: Context, project_id: str) -> list[dict[str, Any]] | dict[str, Any]:
    """List all CI/CD variables for a project (metadata only, values not exposed for security)

    Supports project_id="current" for current repository.

    Returns variable metadata: key, variable_type, protected, masked, raw, environment_scope, description.
    Values are NEVER exposed for security reasons.
    """
    resolved_id, _ = await resolve_project_id(ctx, gitlab_client, project_id)
    if not resolved_id:
        return create_repo_not_found_error(gitlab_client.base_url)
    return gitlab_client.list_project_variables(resolved_id)


@mcp.resource("gitlab://projects/{project_id}/variables/{key}")
async def project_variable(ctx: Context, project_id: str, key: str) -> dict[str, Any]:
    """Get a specific CI/CD variable's metadata (value not exposed for security)

    Supports project_id="current" for current repository.

    Returns: key, variable_type, protected, masked, raw, environment_scope, description.
    Value is NEVER exposed for security reasons. Use set_project_ci_variable() to update values.
    """
    resolved_id, _ = await resolve_project_id(ctx, gitlab_client, project_id)
    if not resolved_id:
        return create_repo_not_found_error(gitlab_client.base_url)

    var = gitlab_client.get_project_variable(resolved_id, key)
    if not var:
        return {"error": f"Variable '{key}' not found in project", "key": key}

    return gitlab_client._sanitize_variable(var)
