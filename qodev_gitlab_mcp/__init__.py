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

__all__ = [
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
]
