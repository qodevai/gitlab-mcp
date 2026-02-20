"""Resources registration for qodev-gitlab-mcp.

This module imports all resource modules for side-effect registration with FastMCP.
"""

from qodev_gitlab_mcp.resources import help as help_resource
from qodev_gitlab_mcp.resources import issues, merge_requests, pipelines, releases, variables

__all__ = [
    "help_resource",
    "merge_requests",
    "pipelines",
    "issues",
    "releases",
    "variables",
]
