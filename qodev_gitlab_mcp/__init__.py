"""GitLab MCP Server - Model Context Protocol server for GitLab integration.

This package provides a FastMCP server for GitLab operations including:
- Merge request management
- Pipeline monitoring
- Issue tracking
- Release management
- CI/CD variable management
- File uploads
"""

from qodev_gitlab_api import (
    APIError,
    AuthenticationError,
    ConfigurationError,
    DiffPosition,
    FileFromBase64,
    FileFromPath,
    FileSource,
    GitLabClient,
    GitLabError,
    NotFoundError,
)

from qodev_gitlab_mcp.models import (
    ImageFromBase64,
    ImageFromPath,
    ImageInput,
)
from qodev_gitlab_mcp.server import gitlab_client, main, mcp
from qodev_gitlab_mcp.utils.discussions import filter_actionable_discussions, is_user_discussion
from qodev_gitlab_mcp.utils.git import get_current_branch, parse_gitlab_remote
from qodev_gitlab_mcp.utils.images import process_images as _process_images_internal


def process_images(project_id: str, images: list[ImageInput] | None) -> str:
    """Process image list and return markdown to append.

    Uploads each image to GitLab and returns markdown image tags.
    This helper is used by tools that support the `images` parameter.

    This is a backward-compatible wrapper that uses the global gitlab_client.

    Args:
        project_id: Resolved project ID (must already be resolved, not "current")
        images: List of ImageInput (either ImageFromPath or ImageFromBase64)

    Returns:
        Markdown string with all uploaded images prefixed with newlines,
        or empty string if no images provided.
    """
    return _process_images_internal(gitlab_client, project_id, images)


__all__ = [
    # Server
    "mcp",
    "gitlab_client",
    "main",
    # Client
    "GitLabClient",
    # Exceptions
    "GitLabError",
    "APIError",
    "AuthenticationError",
    "NotFoundError",
    "ConfigurationError",
    # Models (from gitlab-client library)
    "FileFromPath",
    "FileFromBase64",
    "FileSource",
    "DiffPosition",
    # Models (MCP-specific)
    "ImageFromPath",
    "ImageFromBase64",
    "ImageInput",
    # Utils (for backward compatibility)
    "is_user_discussion",
    "filter_actionable_discussions",
    "process_images",
    "get_current_branch",
    "parse_gitlab_remote",
]
