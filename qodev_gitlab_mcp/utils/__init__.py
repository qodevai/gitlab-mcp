"""Utility functions for qodev-gitlab-mcp."""

from qodev_gitlab_mcp.utils.decorators import (
    MAX_ERROR_DETAIL_LENGTH,
    handle_gitlab_errors,
    resolve_project_or_error,
)
from qodev_gitlab_mcp.utils.discussions import filter_actionable_discussions, is_user_discussion
from qodev_gitlab_mcp.utils.errors import create_branch_error, create_repo_not_found_error
from qodev_gitlab_mcp.utils.git import find_git_root, get_current_branch, parse_gitlab_remote
from qodev_gitlab_mcp.utils.images import process_images
from qodev_gitlab_mcp.utils.resolvers import (
    detect_current_repo,
    find_mr_for_branch,
    get_current_branch_mr,
    get_workspace_roots_from_client,
    resolve_mr_iid,
    resolve_project_id,
)

__all__ = [
    # decorators
    "handle_gitlab_errors",
    "resolve_project_or_error",
    "MAX_ERROR_DETAIL_LENGTH",
    # errors
    "create_repo_not_found_error",
    "create_branch_error",
    # discussions
    "is_user_discussion",
    "filter_actionable_discussions",
    # images
    "process_images",
    # git
    "find_git_root",
    "parse_gitlab_remote",
    "get_current_branch",
    # resolvers
    "get_workspace_roots_from_client",
    "detect_current_repo",
    "find_mr_for_branch",
    "get_current_branch_mr",
    "resolve_project_id",
    "resolve_mr_iid",
]
