"""Tools registration for qodev-gitlab-mcp.

This module imports all tool modules for side-effect registration with FastMCP.
"""

from qodev_gitlab_mcp.tools import files, issues, merge_requests, pipelines, releases, variables

__all__ = [
    "merge_requests",
    "pipelines",
    "issues",
    "releases",
    "variables",
    "files",
]
