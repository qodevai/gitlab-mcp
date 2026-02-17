"""Project and MR resolution helpers for gitlab-mcp."""

import logging
import os
from typing import TYPE_CHECKING, Any

from fastmcp import Context
from mcp import types

from gitlab_client import APIError, GitLabError
from gitlab_mcp.utils.git import find_git_root, get_current_branch, parse_gitlab_remote

if TYPE_CHECKING:
    from gitlab_client import GitLabClient

logger = logging.getLogger(__name__)


async def get_workspace_roots_from_client(ctx: Context) -> list[types.Root] | None:
    """Request workspace roots from MCP client.

    FastMCP 2.0 provides ctx.list_roots() method that handles all the
    complexity of requesting roots from the client.

    Args:
        ctx: FastMCP context object

    Returns:
        List of Root objects if client supports roots capability, None otherwise
    """
    try:
        # FastMCP 2.0 has built-in list_roots() method
        logger.debug("Requesting roots from MCP client via ctx.list_roots()")
        roots = await ctx.list_roots()

        if roots:
            logger.info(f"Received {len(roots)} workspace roots from MCP client")
            return roots
        else:
            logger.debug("Client returned empty roots list")
            return None

    except Exception as e:
        logger.warning(f"Failed to get roots from MCP client: {e}")
        logger.debug("This is normal if the client doesn't support roots capability")
        return None


async def detect_current_repo(ctx: Context, client: "GitLabClient") -> dict[str, Any] | None:
    """Detect current git repo from MCP roots, env var, or CWD.

    Detection priority:
    1. MCP workspace roots from client (proper MCP implementation)
    2. GITLAB_REPO_PATH environment variable (manual override)
    3. Current working directory (fallback)

    Args:
        ctx: FastMCP context object
        client: GitLab API client

    Returns:
        Dict with git_root, project_path, and project info, or None if not found
    """
    try:
        search_paths = []

        # Try to get roots from MCP client
        roots = await get_workspace_roots_from_client(ctx)
        if roots:
            for root in roots:
                root_uri = str(root.uri)
                # Extract path from file:// URI
                path = root_uri[7:] if root_uri.startswith("file://") else root_uri
                search_paths.append(path)
                logger.debug(f"Added workspace root: {path}")

        # Fallback to env var
        if not search_paths:
            repo_path = os.getenv("GITLAB_REPO_PATH")
            if repo_path:
                logger.info(f"Using GITLAB_REPO_PATH from environment: {repo_path}")
                search_paths.append(repo_path)

        # Final fallback to CWD
        if not search_paths:
            cwd = os.getcwd()
            logger.debug(f"No roots from client or env var, using CWD: {cwd}")
            search_paths.append(cwd)

        # Try each path to find a GitLab repository
        for path in search_paths:
            logger.debug(f"Searching for git repository in: {path}")

            git_root = find_git_root(path)
            if not git_root:
                logger.debug(f"No git repository found at: {path}")
                continue

            project_path = parse_gitlab_remote(git_root, client.base_url)
            if not project_path:
                logger.debug(f"Git repository found but no matching GitLab remote at: {git_root}")
                continue

            # Fetch project info from GitLab API
            try:
                project = client.get_project(project_path)
                logger.info(f"Detected GitLab project: {project.get('path_with_namespace')} from {git_root}")
                return {"git_root": git_root, "project_path": project_path, "project": project}
            except GitLabError as e:
                logger.warning(f"Failed to fetch project '{project_path}' from GitLab: {e}")
                continue
            except Exception as e:
                logger.debug(f"Error fetching project '{project_path}': {e}")
                continue

        logger.debug("No GitLab repository found in any search path")
        return None

    except Exception as e:
        logger.exception(f"Error in detect_current_repo: {e}")
        return None


def find_mr_for_branch(client: "GitLabClient", project_id: str, branch_name: str) -> dict[str, Any] | None:
    """Find the merge request for a given branch.

    Args:
        client: GitLab API client
        project_id: Project ID or path
        branch_name: Branch name to search for

    Returns:
        MR dict if found, None otherwise
    """
    try:
        logger.debug(f"Looking for MR with source branch '{branch_name}' in project {project_id}")
        # Get all open MRs
        mrs = client.get_merge_requests(project_id, state="opened")
        for mr in mrs:
            if mr.get("source_branch") == branch_name:
                logger.info(f"Found MR !{mr.get('iid')} for branch '{branch_name}'")
                return mr
        logger.debug(f"No open MR found for branch '{branch_name}'")
        return None
    except GitLabError as e:
        logger.error(f"API error while searching for MR: {e}")
        return None
    except Exception as e:
        logger.exception(f"Error finding MR for branch '{branch_name}': {e}")
        return None


async def get_current_branch_mr(
    ctx: Context, client: "GitLabClient"
) -> tuple[dict[str, Any] | None, str | None, str | None]:
    """Get MR for current branch - common logic extracted (DRY principle).

    Args:
        ctx: FastMCP context
        client: GitLab API client

    Returns:
        Tuple of (mr_dict, project_id, branch_name) or (None, None, None) on error
    """
    repo_info = await detect_current_repo(ctx, client)
    if not repo_info:
        return None, None, None

    git_root = repo_info["git_root"]
    project_id = str(repo_info["project"]["id"])

    branch_name = get_current_branch(git_root)
    if not branch_name:
        return None, None, None

    mr = find_mr_for_branch(client, project_id, branch_name)
    return mr, project_id, branch_name


async def resolve_project_id(
    ctx: Context, client: "GitLabClient", project_id: str
) -> tuple[str | None, dict[str, Any] | None]:
    """Resolve 'current' to actual project ID, pass through others.

    Args:
        ctx: FastMCP context
        client: GitLab API client
        project_id: Project ID (numeric, path, or "current")

    Returns:
        Tuple of (resolved_project_id, repo_info) or (None, None) on error
        - If project_id == "current": returns (detected_project_id, repo_info_dict)
        - Otherwise: returns (project_id, None)
    """
    if project_id == "current":
        repo_info = await detect_current_repo(ctx, client)
        if not repo_info:
            logger.warning("Could not resolve 'current' project - not in a GitLab repository")
            return None, None
        resolved_id = str(repo_info["project"]["id"])
        logger.debug(f"Resolved 'current' project to: {resolved_id}")
        return resolved_id, repo_info
    return project_id, None


async def resolve_mr_iid(ctx: Context, client: "GitLabClient", project_id: str, mr_iid: str | int) -> int | None:
    """Resolve 'current' to MR IID for current branch, parse others.

    Args:
        ctx: FastMCP context
        client: GitLab API client
        project_id: Already resolved project ID (not "current")
        mr_iid: MR IID (numeric or "current")

    Returns:
        Resolved MR IID or None on error
    """
    if str(mr_iid) == "current":
        repo_info = await detect_current_repo(ctx, client)
        if not repo_info:
            logger.warning("Could not resolve 'current' MR - not in a GitLab repository")
            return None

        branch_name = get_current_branch(repo_info["git_root"])
        if not branch_name:
            logger.warning("Could not resolve 'current' MR - unable to determine current branch")
            return None

        mr = find_mr_for_branch(client, project_id, branch_name)
        if not mr:
            logger.warning(f"Could not resolve 'current' MR - no MR found for branch '{branch_name}'")
            return None

        logger.debug(f"Resolved 'current' MR to IID: {mr['iid']} for branch '{branch_name}'")
        return mr["iid"]

    return int(mr_iid)
