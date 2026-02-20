"""Decorators for qodev-gitlab-mcp tools."""

import functools
from collections.abc import Callable
from typing import Any, TypeVar

from fastmcp import Context
from qodev_gitlab_api import APIError, GitLabError

# Maximum length for error details in responses
MAX_ERROR_DETAIL_LENGTH = 500

F = TypeVar("F", bound=Callable[..., Any])


def handle_gitlab_errors(operation: str) -> Callable[[F], F]:
    """Decorator to handle common GitLab API errors in tool functions.

    Args:
        operation: Description of the operation for error messages (e.g., "create MR", "close issue")

    Returns:
        Decorated function that catches GitLab errors and returns standardized error responses
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> dict[str, Any]:
            try:
                return await func(*args, **kwargs)
            except APIError as e:
                return {
                    "success": False,
                    "error": f"Failed to {operation}: {e}",
                    "status_code": e.status_code,
                }
            except GitLabError as e:
                return {
                    "success": False,
                    "error": f"Failed to {operation}: {e}",
                }
            except Exception as e:
                return {
                    "success": False,
                    "error": f"Unexpected error while trying to {operation}: {str(e)}",
                }

        return wrapper  # type: ignore[return-value]

    return decorator


async def resolve_project_or_error(
    ctx: Context,
    client: Any,
    project_id: str,
    resolve_func: Callable[..., Any],
) -> tuple[str | None, dict[str, Any] | None]:
    """Resolve project ID or return an error response.

    Args:
        ctx: FastMCP context
        client: GitLab client instance
        project_id: Project ID, path, or "current"
        resolve_func: The resolve_project_id function to use

    Returns:
        Tuple of (resolved_id, error_response). If resolution succeeds,
        error_response is None. If it fails, resolved_id is None.
    """
    resolved_id, _ = await resolve_func(ctx, client, project_id)
    if not resolved_id:
        return None, {"success": False, "error": f"Could not resolve project '{project_id}'"}
    return resolved_id, None
