"""Error creation helpers for gitlab-mcp."""


def create_repo_not_found_error(gitlab_base_url: str) -> dict[str, str]:
    """Create standardized error response for repository not found."""
    return {
        "error": "Not in a GitLab repository or repository not found on configured GitLab instance",
        "base_url": gitlab_base_url,
    }


def create_branch_error(branch_name: str | None = None) -> dict[str, str]:
    """Create standardized error response for branch detection issues."""
    if branch_name is None:
        return {
            "error": "Could not determine current git branch",
            "help": "Make sure you're in a git repository with a checked out branch",
        }
    return {
        "error": f"No open merge request found for branch '{branch_name}'",
        "branch": branch_name,
        "help": "This resource only shows open merge requests",
    }
