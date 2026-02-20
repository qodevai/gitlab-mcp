"""CI/CD variable tools for qodev-gitlab-mcp."""

from typing import Any

from fastmcp import Context
from qodev_gitlab_api import APIError, GitLabError

from qodev_gitlab_mcp.server import gitlab_client, mcp
from qodev_gitlab_mcp.utils.resolvers import resolve_project_id


@mcp.tool()
async def set_project_ci_variable(
    ctx: Context,
    project_id: str,
    key: str,
    value: str,
    variable_type: str = "env_var",
    protected: bool = False,
    masked: bool = False,
    raw: bool = False,
    environment_scope: str = "*",
    description: str | None = None,
) -> dict[str, Any]:
    """Set a CI/CD variable in a specific project (upsert: creates if new, updates if exists)

    Args:
        project_id: Project ID, path, or "current" (e.g., "mygroup/myproject", "123", or "current")
        key: Variable key/name (e.g., "API_KEY", "DATABASE_URL")
        value: Variable value
        variable_type: Type of variable - "env_var" (default) or "file"
        protected: Only available in protected branches (default: False)
        masked: Hidden in job logs (default: False)
        raw: Disable variable reference expansion (default: False)
        environment_scope: Environment scope - "*" for all (default), or specific like "production", "staging"
        description: Optional description of the variable

    Returns:
        Result with success status, action taken (created/updated), and variable details

    Raises:
        Error if variable operation fails
    """
    resolved_id, _ = await resolve_project_id(ctx, gitlab_client, project_id)
    if not resolved_id:
        return {"success": False, "error": f"Could not resolve project '{project_id}'"}

    try:
        variable, action = gitlab_client.set_project_variable(
            project_id=resolved_id,
            key=key,
            value=value,
            variable_type=variable_type,
            protected=protected,
            masked=masked,
            raw=raw,
            environment_scope=environment_scope,
            description=description,
        )

        return {
            "success": True,
            "action": action,
            "message": f"Successfully {action} CI/CD variable '{key}' in project {project_id}",
            "variable": {
                "key": variable.get("key"),
                "variable_type": variable.get("variable_type"),
                "protected": variable.get("protected"),
                "masked": variable.get("masked"),
                "raw": variable.get("raw"),
                "environment_scope": variable.get("environment_scope"),
                "description": variable.get("description"),
            },
            "project_id": project_id,
        }
    except APIError as e:
        return {
            "success": False,
            "error": f"Failed to set CI/CD variable '{key}' in project {project_id}: {e}",
            "status_code": e.status_code,
            "project_id": project_id,
        }
    except GitLabError as e:
        return {
            "success": False,
            "error": f"Failed to set CI/CD variable '{key}' in project {project_id}: {e}",
            "project_id": project_id,
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Unexpected error while setting CI/CD variable '{key}' in project {project_id}: {str(e)}",
            "project_id": project_id,
        }
