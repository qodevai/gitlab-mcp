"""Git repository detection helpers for gitlab-mcp."""

import logging
import re
import subprocess

logger = logging.getLogger(__name__)


def find_git_root(start_path: str) -> str | None:
    """Find git repository root using git command (works with worktrees automatically).

    Args:
        start_path: Starting directory path

    Returns:
        Path to git repository root, or None if not in a git repository
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=start_path,
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode == 0:
            git_root = result.stdout.strip()
            logger.debug(f"Found git repository at {git_root}")
            return git_root

        logger.debug(f"Not a git repository: {start_path}")
        return None

    except subprocess.TimeoutExpired:
        logger.error(f"Git command timed out at {start_path}")
        return None
    except FileNotFoundError:
        logger.error("Git command not found - is git installed?")
        return None
    except Exception as e:
        logger.debug(f"Error finding git root: {e}")
        return None


def parse_gitlab_remote(git_root: str, base_url: str) -> str | None:
    """Parse GitLab project path from git remote using git command (works with worktrees).

    Args:
        git_root: Path to git repository root
        base_url: Base URL of the GitLab instance

    Returns:
        Project path (e.g., "group/project"), or None if not found
    """
    try:
        # Use git command to get remote URL - works with worktrees automatically!
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=git_root,
            capture_output=True,
            text=True,
            timeout=5,
        )

        if result.returncode != 0:
            logger.debug(f"No git remote 'origin' found at {git_root}")
            return None

        remote_url = result.stdout.strip()
        logger.debug(f"Found remote URL: {remote_url}")

        # Extract domain from base_url (e.g., gitlab.qodev.ai from https://gitlab.qodev.ai)
        domain_match = re.search(r"https?://([^/]+)", base_url)
        if not domain_match:
            return None
        domain = domain_match.group(1)

        # Parse project path from remote URL
        # SSH: git@gitlab.qodev.ai:group/project.git
        # HTTPS: https://gitlab.qodev.ai/group/project.git
        patterns = [
            rf"@{re.escape(domain)}:(.+?)\.git$",  # SSH
            rf"https?://{re.escape(domain)}/(.+?)\.git$",  # HTTPS
        ]

        for pattern in patterns:
            match = re.search(pattern, remote_url)
            if match:
                project_path = match.group(1)
                logger.debug(f"Parsed project path: {project_path}")
                return project_path

        logger.debug(f"Remote URL does not match GitLab instance {domain}")
        return None

    except subprocess.TimeoutExpired:
        logger.error(f"Git command timed out while getting remote URL at {git_root}")
        return None
    except FileNotFoundError:
        logger.error("Git command not found - is git installed?")
        return None
    except Exception as e:
        logger.debug(f"Error parsing git remote: {e}")
        return None


def get_current_branch(git_root: str) -> str | None:
    """Get the current git branch name.

    Args:
        git_root: Path to the git repository root

    Returns:
        Current branch name or None if unable to determine
    """
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=git_root, capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            branch_name = result.stdout.strip()
            logger.debug(f"Current branch: {branch_name}")
            return branch_name
        else:
            logger.warning(f"Failed to get current branch: {result.stderr}")
            return None
    except subprocess.TimeoutExpired:
        logger.error("Git command timed out while getting current branch")
        return None
    except FileNotFoundError:
        logger.error("Git command not found - is git installed?")
        return None
    except Exception as e:
        logger.exception(f"Unexpected error getting current branch: {e}")
        return None
