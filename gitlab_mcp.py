import os
import re
import logging
from pathlib import Path
from typing import Any
import httpx
from fastmcp import FastMCP, Context
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class GitLabClient:
    def __init__(self, token: str | None = None, base_url: str | None = None, validate: bool = True):
        """Initialize GitLab API client

        Args:
            token: GitLab personal access token
            base_url: GitLab instance URL
            validate: Whether to validate configuration and test connectivity on init
        """
        self.token = token or os.getenv("GITLAB_TOKEN")
        self.base_url = (base_url or os.getenv("GITLAB_BASE_URL") or os.getenv("GITLAB_URL") or "https://gitlab.com").rstrip("/")

        # Validate configuration
        if not self.token:
            logger.error("GITLAB_TOKEN not set in environment variables")
            raise ValueError("GITLAB_TOKEN environment variable is required. Set it in your .env file or environment.")

        if not self.base_url.startswith(("http://", "https://")):
            logger.error(f"Invalid GITLAB_URL: {self.base_url}")
            raise ValueError(f"GITLAB_URL must start with http:// or https://, got: {self.base_url}")

        self.api_url = f"{self.base_url}/api/v4"
        self.client = httpx.Client(
            base_url=self.api_url,
            headers={
                "PRIVATE-TOKEN": self.token,
                "Content-Type": "application/json"
            },
            timeout=30.0
        )

        # Test connectivity on initialization if validation is enabled
        if validate:
            try:
                version_info = self.get("/version")
                logger.info(f"Connected to GitLab {version_info.get('version', 'unknown')} at {self.base_url}")
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 401:
                    logger.error("GitLab authentication failed - check your GITLAB_TOKEN")
                    raise ValueError("Invalid GITLAB_TOKEN - authentication failed") from e
                logger.error(f"GitLab API returned error: {e.response.status_code}")
                raise
            except httpx.RequestError as e:
                logger.error(f"Failed to connect to GitLab at {self.base_url}: {e}")
                raise ValueError(f"Cannot connect to GitLab at {self.base_url}. Check your GITLAB_URL.") from e
            except Exception as e:
                logger.exception(f"Unexpected error during GitLab client initialization: {e}")
                raise
        else:
            logger.info(f"GitLab client initialized for {self.base_url} (validation skipped)")

    def get(self, endpoint: str, params: dict[str, Any] | None = None) -> Any:
        """GET request to GitLab API with error handling"""
        try:
            logger.debug(f"GET {endpoint} with params={params}")
            response = self.client.get(endpoint, params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"GitLab API error for GET {endpoint}: {e.response.status_code} - {e.response.text[:200]}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Network error for GET {endpoint}: {e}")
            raise
        except Exception as e:
            logger.exception(f"Unexpected error for GET {endpoint}: {e}")
            raise

    def get_paginated(self, endpoint: str, params: dict[str, Any] | None = None,
                     per_page: int = 100, max_pages: int = 100) -> list[Any]:
        """GET request with pagination support and safety limits

        Args:
            endpoint: API endpoint to call
            params: Query parameters
            per_page: Results per page (max 100, GitLab limit)
            max_pages: Maximum number of pages to fetch (prevents infinite loops)

        Returns:
            List of results from all pages
        """
        params = params or {}
        params["per_page"] = min(per_page, 100)  # GitLab maximum is 100
        params["page"] = 1

        all_results = []
        pages_fetched = 0

        try:
            while pages_fetched < max_pages:
                logger.debug(f"GET {endpoint} page {params['page']} (per_page={params['per_page']})")
                response = self.client.get(endpoint, params=params)
                response.raise_for_status()
                results = response.json()

                if not results:
                    break

                all_results.extend(results)
                pages_fetched += 1

                # Check if there are more pages
                if "x-next-page" not in response.headers or not response.headers["x-next-page"]:
                    break

                params["page"] += 1

            if pages_fetched >= max_pages:
                logger.warning(f"Hit max_pages limit ({max_pages}) for {endpoint}. Results may be incomplete.")

            logger.debug(f"Fetched {len(all_results)} results from {pages_fetched} pages for {endpoint}")
            return all_results

        except httpx.HTTPStatusError as e:
            logger.error(f"GitLab API error during pagination of {endpoint}: {e.response.status_code}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Network error during pagination of {endpoint}: {e}")
            raise
        except Exception as e:
            logger.exception(f"Unexpected error during pagination of {endpoint}: {e}")
            raise

    def get_projects(self, owned: bool = False, membership: bool = True) -> list[dict[str, Any]]:
        """Get all projects"""
        params = {"membership": membership, "owned": owned}
        return self.get_paginated("/projects", params=params)

    def get_project(self, project_id: str) -> dict[str, Any]:
        """Get a specific project by ID or path"""
        from urllib.parse import quote
        encoded_id = quote(project_id, safe='')
        return self.get(f"/projects/{encoded_id}")

    def get_merge_requests(self, project_id: str, state: str = "opened") -> list[dict[str, Any]]:
        """Get merge requests for a project"""
        from urllib.parse import quote
        encoded_id = quote(project_id, safe='')
        params = {"state": state}
        return self.get_paginated(f"/projects/{encoded_id}/merge_requests", params=params)

    def get_merge_request(self, project_id: str, mr_iid: int) -> dict[str, Any]:
        """Get a specific merge request"""
        from urllib.parse import quote
        encoded_id = quote(project_id, safe='')
        return self.get(f"/projects/{encoded_id}/merge_requests/{mr_iid}")

    def get_pipelines(self, project_id: str, ref: str | None = None) -> list[dict[str, Any]]:
        """Get pipelines for a project"""
        from urllib.parse import quote
        encoded_id = quote(project_id, safe='')
        params = {"ref": ref} if ref else {}
        return self.get_paginated(f"/projects/{encoded_id}/pipelines", params=params)

    def get_pipeline(self, project_id: str, pipeline_id: int) -> dict[str, Any]:
        """Get a specific pipeline"""
        from urllib.parse import quote
        encoded_id = quote(project_id, safe='')
        return self.get(f"/projects/{encoded_id}/pipelines/{pipeline_id}")

    def get_mr_pipelines(self, project_id: str, mr_iid: int) -> list[dict[str, Any]]:
        """Get pipelines for a merge request"""
        from urllib.parse import quote
        encoded_id = quote(project_id, safe='')
        return self.get(f"/projects/{encoded_id}/merge_requests/{mr_iid}/pipelines")

    def get_pipeline_jobs(self, project_id: str, pipeline_id: int) -> list[dict[str, Any]]:
        """Get jobs for a specific pipeline"""
        from urllib.parse import quote
        encoded_id = quote(project_id, safe='')
        return self.get_paginated(f"/projects/{encoded_id}/pipelines/{pipeline_id}/jobs")

    def get_mr_discussions(self, project_id: str, mr_iid: int) -> list[dict[str, Any]]:
        """Get all discussions (comments/threads) for a merge request"""
        from urllib.parse import quote
        encoded_id = quote(project_id, safe='')
        return self.get_paginated(f"/projects/{encoded_id}/merge_requests/{mr_iid}/discussions")

    def get_mr_changes(self, project_id: str, mr_iid: int) -> dict[str, Any]:
        """Get the diff/changes for a merge request"""
        from urllib.parse import quote
        encoded_id = quote(project_id, safe='')
        return self.get(f"/projects/{encoded_id}/merge_requests/{mr_iid}/changes")

    def get_mr_commits(self, project_id: str, mr_iid: int) -> list[dict[str, Any]]:
        """Get commits for a merge request"""
        from urllib.parse import quote
        encoded_id = quote(project_id, safe='')
        return self.get_paginated(f"/projects/{encoded_id}/merge_requests/{mr_iid}/commits")

    def get_mr_approvals(self, project_id: str, mr_iid: int) -> dict[str, Any]:
        """Get approval status for a merge request"""
        from urllib.parse import quote
        encoded_id = quote(project_id, safe='')
        return self.get(f"/projects/{encoded_id}/merge_requests/{mr_iid}/approvals")


# Helper functions for git repository detection
def find_git_root(start_path: str) -> str | None:
    """Walk up from start_path to find .git directory"""
    current = Path(start_path).resolve()

    while current != current.parent:
        git_dir = current / ".git"
        if git_dir.exists() and git_dir.is_dir():
            return str(current)
        current = current.parent

    return None


def parse_gitlab_remote(git_root: str, base_url: str) -> str | None:
    """Parse GitLab project path from git remote URL"""
    git_config = Path(git_root) / ".git" / "config"
    if not git_config.exists():
        return None

    try:
        config_content = git_config.read_text()

        # Extract domain from base_url (e.g., gitlab.qodev.ai from https://gitlab.qodev.ai)
        domain_match = re.search(r'https?://([^/]+)', base_url)
        if not domain_match:
            return None
        domain = domain_match.group(1)

        # Look for remote URL patterns matching this GitLab instance
        # Matches both SSH and HTTPS URLs for the specific domain
        patterns = [
            rf'url = .*@{re.escape(domain)}:(.+?)\.git',  # SSH: git@gitlab.qodev.ai:group/project.git
            rf'url = https?://{re.escape(domain)}/(.+?)\.git',  # HTTPS: https://gitlab.qodev.ai/group/project.git
        ]

        for pattern in patterns:
            match = re.search(pattern, config_content)
            if match:
                return match.group(1)

        return None
    except Exception:
        return None


async def detect_current_repo(ctx: Context, gitlab_client: GitLabClient) -> dict | None:
    """Detect current git repo using Context roots and fetch project info"""
    try:
        roots = await ctx.list_roots()
        if not roots:
            return None

        # Try each root to find a git repository
        for root in roots:
            root_uri = str(root.uri) if hasattr(root, 'uri') else str(root)

            # Extract path from file:// URI or use directly
            if root_uri.startswith("file://"):
                root_path = root_uri[7:]  # Remove file://
            else:
                root_path = root_uri

            git_root = find_git_root(root_path)
            if not git_root:
                continue

            project_path = parse_gitlab_remote(git_root, gitlab_client.base_url)
            if not project_path:
                continue

            # Fetch project info from GitLab API
            try:
                project = gitlab_client.get_project(project_path)
                logger.info(f"Detected GitLab project: {project.get('path_with_namespace')}")
                return {
                    "git_root": git_root,
                    "project_path": project_path,
                    "project": project
                }
            except httpx.HTTPStatusError as e:
                logger.warning(f"Failed to fetch project '{project_path}' from GitLab: {e.response.status_code}")
                continue
            except Exception as e:
                logger.warning(f"Error fetching project '{project_path}': {e}")
                continue

        logger.debug("No GitLab repository detected in workspace roots")
        return None
    except Exception as e:
        logger.exception(f"Error in detect_current_repo: {e}")
        return None


def get_current_branch(git_root: str) -> str | None:
    """Get the current git branch name

    Args:
        git_root: Path to the git repository root

    Returns:
        Current branch name or None if unable to determine
    """
    try:
        import subprocess
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=git_root,
            capture_output=True,
            text=True,
            timeout=5
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


def find_mr_for_branch(gitlab_client: GitLabClient, project_id: str, branch_name: str) -> dict | None:
    """Find the merge request for a given branch

    Args:
        gitlab_client: GitLab API client
        project_id: Project ID or path
        branch_name: Branch name to search for

    Returns:
        MR dict if found, None otherwise
    """
    try:
        logger.debug(f"Looking for MR with source branch '{branch_name}' in project {project_id}")
        # Get all open MRs
        mrs = gitlab_client.get_merge_requests(project_id, state="opened")
        for mr in mrs:
            if mr.get("source_branch") == branch_name:
                logger.info(f"Found MR !{mr.get('iid')} for branch '{branch_name}'")
                return mr
        logger.debug(f"No open MR found for branch '{branch_name}'")
        return None
    except httpx.HTTPStatusError as e:
        logger.error(f"API error while searching for MR: {e.response.status_code}")
        return None
    except Exception as e:
        logger.exception(f"Error finding MR for branch '{branch_name}': {e}")
        return None


# Create FastMCP server
mcp = FastMCP(
    "gitlab-mcp",
    instructions="""
This server provides GitLab integration for the current repository.

ALWAYS use these resources for GitLab-related queries:
- Complete MR overview (RECOMMENDED) - use gitlab://current-project/current-branch-mr/
- Merge requests (open/closed/merged/all) - use gitlab://current-project/merge-requests/ or related URIs
- MR discussions/comments - use gitlab://current-project/current-branch-mr-discussions/
- MR changes/diff - use gitlab://current-project/current-branch-mr-changes/
- Pipeline status - use gitlab://current-project/pipelines/
- Project information - use gitlab://current-project/
- Quick overview - use gitlab://current-project/status/

Common user queries that should use this MCP:
- "What's the status of my MR?" → gitlab://current-project/current-branch-mr/ (BEST - gets everything!)
- "Show me everything about the current MR" → gitlab://current-project/current-branch-mr/
- "What code changed in my MR?" → gitlab://current-project/current-branch-mr-changes/
- "Any unresolved discussions?" → gitlab://current-project/current-branch-mr-discussions/
- "What comments are on my MR?" → gitlab://current-project/current-branch-mr-discussions/
- "Are there any open merge requests?" → gitlab://current-project/merge-requests/
- "What's the pipeline status?" → gitlab://current-project/pipelines/
- "Show me merged MRs" → gitlab://current-project/merged-merge-requests/
- "What MRs are open?" → gitlab://current-project/merge-requests/
- "What needs review?" → gitlab://current-project/merge-requests/
- "Check CI/CD status" → gitlab://current-project/pipelines/
- "What's the project status?" → gitlab://current-project/status/

DO NOT use git commands or branch inspection to answer GitLab questions.
Use ReadMcpResourceTool with server="gitlab" for all GitLab queries.

For help, use gitlab://help/ to see all available resources.
"""
)
gitlab_client = GitLabClient()


# Current project resources
@mcp.resource(
    "gitlab://current-project/",
    name="Current Repo: Project Info",
    description="""Information about the current repository's GitLab project.

Use this when users ask:
- "What's the project info?"
- "Show me project details"
- "What GitLab project is this?"
- "What's the project ID/name?"
""",
    mime_type="application/json"
)
async def current_project() -> dict:
    """Get current project information"""
    ctx = mcp.get_context()
    repo_info = await detect_current_repo(ctx, gitlab_client)

    if not repo_info:
        return {
            "error": "Not in a GitLab repository or repository not found on configured GitLab instance",
            "base_url": gitlab_client.base_url
        }

    return repo_info["project"]


@mcp.resource(
    "gitlab://current-project/merge-requests/",
    name="Current Repo: Open Merge Requests",
    description="""Open merge requests for the current repository.

Use this when users ask:
- "Are there any open merge requests?"
- "What MRs are open?"
- "Any pending merges?"
- "What needs review?"
- "Show me open MRs"
- "What merge requests need attention?"
""",
    mime_type="application/json"
)
async def current_project_merge_requests() -> dict | list:
    """Get open merge requests for current project"""
    ctx = mcp.get_context()
    repo_info = await detect_current_repo(ctx, gitlab_client)

    if not repo_info:
        return {
            "error": "Not in a GitLab repository or repository not found on configured GitLab instance"
        }

    project_id = repo_info["project"]["id"]
    return gitlab_client.get_merge_requests(str(project_id), state="opened")


@mcp.resource(
    "gitlab://current-project/all-merge-requests/",
    name="Current Repo: All Merge Requests",
    description="""All merge requests for the current repository (open, merged, and closed).

Use this when users ask:
- "Show me all MRs"
- "List all merge requests"
- "What's the complete MR history?"
- "Show me every merge request"
- "Give me all MRs regardless of status"
""",
    mime_type="application/json"
)
async def current_project_all_merge_requests() -> dict | list:
    """Get all merge requests for current project"""
    ctx = mcp.get_context()
    repo_info = await detect_current_repo(ctx, gitlab_client)

    if not repo_info:
        return {
            "error": "Not in a GitLab repository or repository not found on configured GitLab instance"
        }

    project_id = repo_info["project"]["id"]
    return gitlab_client.get_merge_requests(str(project_id), state="all")


@mcp.resource(
    "gitlab://current-project/merged-merge-requests/",
    name="Current Repo: Merged Merge Requests",
    description="""Merged merge requests for the current repository.

Use this when users ask:
- "Show me merged MRs"
- "What merge requests have been merged?"
- "List completed merges"
- "Show me merged merge requests"
- "What's been merged recently?"
""",
    mime_type="application/json"
)
async def current_project_merged_merge_requests() -> dict | list:
    """Get merged merge requests for current project"""
    ctx = mcp.get_context()
    repo_info = await detect_current_repo(ctx, gitlab_client)

    if not repo_info:
        return {
            "error": "Not in a GitLab repository or repository not found on configured GitLab instance"
        }

    project_id = repo_info["project"]["id"]
    return gitlab_client.get_merge_requests(str(project_id), state="merged")


@mcp.resource(
    "gitlab://current-project/closed-merge-requests/",
    name="Current Repo: Closed Merge Requests",
    description="""Closed (rejected/abandoned) merge requests for the current repository.

Use this when users ask:
- "Show me closed MRs"
- "What merge requests were closed?"
- "List rejected/abandoned MRs"
- "Show me MRs that weren't merged"
- "What merge requests were declined?"
""",
    mime_type="application/json"
)
async def current_project_closed_merge_requests() -> dict | list:
    """Get closed merge requests for current project"""
    ctx = mcp.get_context()
    repo_info = await detect_current_repo(ctx, gitlab_client)

    if not repo_info:
        return {
            "error": "Not in a GitLab repository or repository not found on configured GitLab instance"
        }

    project_id = repo_info["project"]["id"]
    return gitlab_client.get_merge_requests(str(project_id), state="closed")


@mcp.resource(
    "gitlab://current-project/pipelines/",
    name="Current Repo: Pipelines",
    description="""Recent pipelines for the current repository (last 20).

Use this when users ask:
- "What's the pipeline status?"
- "Are the CI/CD pipelines passing?"
- "Show me recent builds"
- "Check pipeline health"
- "What's the build status?"
- "Are there any failed pipelines?"
""",
    mime_type="application/json"
)
async def current_project_pipelines() -> dict | list:
    """Get recent pipelines for current project"""
    ctx = mcp.get_context()
    repo_info = await detect_current_repo(ctx, gitlab_client)

    if not repo_info:
        return {
            "error": "Not in a GitLab repository or repository not found on configured GitLab instance"
        }

    project_id = repo_info["project"]["id"]
    pipelines = gitlab_client.get_pipelines(str(project_id))
    return pipelines[:20]  # Return last 20 pipelines


@mcp.resource(
    "gitlab://current-project/status/",
    name="Current Repo: Quick Status",
    description="""Quick status overview of the project (open MRs count, latest pipeline status).

Use this when users ask:
- "What's the project status?"
- "Give me a quick overview"
- "What's happening in the project?"
- "Show me a summary"
- "What's the current state?"
""",
    mime_type="application/json"
)
async def current_project_status() -> dict:
    """Get quick status overview for current project"""
    ctx = mcp.get_context()
    repo_info = await detect_current_repo(ctx, gitlab_client)

    if not repo_info:
        return {
            "error": "Not in a GitLab repository or repository not found on configured GitLab instance"
        }

    project_id = str(repo_info["project"]["id"])
    project = repo_info["project"]

    # Fetch open MRs and pipelines
    open_mrs = gitlab_client.get_merge_requests(project_id, state="opened")
    pipelines = gitlab_client.get_pipelines(project_id)

    latest_pipeline = pipelines[0] if pipelines else None

    return {
        "project": {
            "id": project["id"],
            "name": project["name"],
            "path_with_namespace": project["path_with_namespace"],
            "web_url": project.get("web_url")
        },
        "open_merge_requests": {
            "count": len(open_mrs),
            "mrs": [
                {
                    "iid": mr["iid"],
                    "title": mr["title"],
                    "author": mr["author"]["name"],
                    "web_url": mr.get("web_url")
                }
                for mr in open_mrs[:5]  # Show first 5
            ]
        },
        "latest_pipeline": {
            "id": latest_pipeline["id"],
            "status": latest_pipeline["status"],
            "ref": latest_pipeline["ref"],
            "web_url": latest_pipeline.get("web_url"),
            "created_at": latest_pipeline.get("created_at")
        } if latest_pipeline else None,
        "summary": f"{len(open_mrs)} open MR(s), latest pipeline: {latest_pipeline['status'] if latest_pipeline else 'none'}"
    }


@mcp.resource(
    "gitlab://current-project/current-branch-mr-discussions/",
    name="Current Branch: MR Discussions",
    description="""Discussion threads and comments on the merge request for the current branch.

Use this when users ask:
- "Are there discussions on my MR?"
- "What comments are on the current MR?"
- "Any unresolved discussions?"
- "What feedback did I get on the MR?"
- "Show me MR comments"
- "What discussion threads are open?"
- "Are there any open discussion items?"
""",
    mime_type="application/json"
)
async def current_branch_mr_discussions() -> dict | list:
    """Get discussions for the MR associated with the current branch"""
    ctx = mcp.get_context()
    repo_info = await detect_current_repo(ctx, gitlab_client)

    if not repo_info:
        return {
            "error": "Not in a GitLab repository or repository not found on configured GitLab instance"
        }

    git_root = repo_info["git_root"]
    project_id = str(repo_info["project"]["id"])

    # Get current branch
    branch_name = get_current_branch(git_root)
    if not branch_name:
        return {
            "error": "Could not determine current git branch",
            "help": "Make sure you're in a git repository with a checked out branch"
        }

    # Find MR for this branch
    mr = find_mr_for_branch(gitlab_client, project_id, branch_name)
    if not mr:
        return {
            "error": f"No open merge request found for branch '{branch_name}'",
            "branch": branch_name,
            "help": "This resource only shows discussions for open merge requests"
        }

    # Get discussions for this MR
    discussions = gitlab_client.get_mr_discussions(project_id, mr["iid"])

    # Analyze discussions to provide summary
    total_discussions = len(discussions)
    unresolved_discussions = [d for d in discussions if not d.get("notes", [{}])[0].get("resolved", False)]

    return {
        "merge_request": {
            "iid": mr["iid"],
            "title": mr["title"],
            "source_branch": mr["source_branch"],
            "web_url": mr.get("web_url")
        },
        "summary": {
            "total_discussions": total_discussions,
            "unresolved_count": len(unresolved_discussions),
            "resolved_count": total_discussions - len(unresolved_discussions)
        },
        "discussions": discussions,
        "unresolved_discussions": unresolved_discussions
    }


@mcp.resource(
    "gitlab://current-project/current-branch-mr/",
    name="Current Branch: Complete MR Overview",
    description="""Complete overview of the MR for the current branch including discussions, changes, commits, and approvals.

Use this when users ask:
- "What's the status of my MR?"
- "Show me everything about the current MR"
- "Give me a full MR overview"
- "What's happening with my merge request?"
- "Summarize the current MR"
""",
    mime_type="application/json"
)
async def current_branch_mr_overview() -> dict:
    """Get complete overview of the MR for the current branch"""
    ctx = mcp.get_context()
    repo_info = await detect_current_repo(ctx, gitlab_client)

    if not repo_info:
        return {
            "error": "Not in a GitLab repository or repository not found on configured GitLab instance"
        }

    git_root = repo_info["git_root"]
    project_id = str(repo_info["project"]["id"])

    # Get current branch
    branch_name = get_current_branch(git_root)
    if not branch_name:
        return {
            "error": "Could not determine current git branch",
            "help": "Make sure you're in a git repository with a checked out branch"
        }

    # Find MR for this branch
    mr = find_mr_for_branch(gitlab_client, project_id, branch_name)
    if not mr:
        return {
            "error": f"No open merge request found for branch '{branch_name}'",
            "branch": branch_name,
            "help": "This resource only shows open merge requests"
        }

    mr_iid = mr["iid"]

    # Fetch all MR-related data
    try:
        discussions = gitlab_client.get_mr_discussions(project_id, mr_iid)
        changes = gitlab_client.get_mr_changes(project_id, mr_iid)
        commits = gitlab_client.get_mr_commits(project_id, mr_iid)
        pipelines = gitlab_client.get_mr_pipelines(project_id, mr_iid)

        # Try to get approvals (might fail if not available in GitLab edition)
        approvals = None
        try:
            approvals = gitlab_client.get_mr_approvals(project_id, mr_iid)
        except Exception:
            pass

        # Analyze discussions
        total_discussions = len(discussions)
        unresolved_discussions = [d for d in discussions if not d.get("notes", [{}])[0].get("resolved", False)]

        # Extract changed files list
        changed_files = [
            {
                "old_path": change.get("old_path"),
                "new_path": change.get("new_path"),
                "new_file": change.get("new_file", False),
                "renamed_file": change.get("renamed_file", False),
                "deleted_file": change.get("deleted_file", False)
            }
            for change in changes.get("changes", [])
        ]

        latest_pipeline = pipelines[0] if pipelines else None

        return {
            "merge_request": {
                "iid": mr["iid"],
                "title": mr["title"],
                "description": mr.get("description"),
                "state": mr["state"],
                "source_branch": mr["source_branch"],
                "target_branch": mr["target_branch"],
                "author": mr["author"],
                "web_url": mr.get("web_url"),
                "created_at": mr.get("created_at"),
                "updated_at": mr.get("updated_at"),
                "merge_status": mr.get("merge_status"),
                "draft": mr.get("draft", False),
                "work_in_progress": mr.get("work_in_progress", False)
            },
            "discussions_summary": {
                "total": total_discussions,
                "unresolved": len(unresolved_discussions),
                "resolved": total_discussions - len(unresolved_discussions),
                "unresolved_threads": unresolved_discussions
            },
            "changes_summary": {
                "total_files_changed": len(changed_files),
                "changed_files": changed_files
            },
            "commits_summary": {
                "total_commits": len(commits),
                "commits": [
                    {
                        "id": c.get("id"),
                        "short_id": c.get("short_id"),
                        "title": c.get("title"),
                        "message": c.get("message"),
                        "author_name": c.get("author_name"),
                        "created_at": c.get("created_at")
                    }
                    for c in commits
                ]
            },
            "pipeline_summary": {
                "latest_pipeline": {
                    "id": latest_pipeline["id"],
                    "status": latest_pipeline["status"],
                    "ref": latest_pipeline["ref"],
                    "web_url": latest_pipeline.get("web_url")
                } if latest_pipeline else None
            },
            "approvals_summary": approvals if approvals else {"note": "Approvals not available or not configured"}
        }
    except Exception as e:
        return {
            "error": f"Failed to fetch complete MR data: {str(e)}",
            "merge_request_basic": mr
        }


@mcp.resource(
    "gitlab://current-project/current-branch-mr-changes/",
    name="Current Branch: MR Changes/Diff",
    description="""Code changes and diff for the MR on the current branch.

Use this when users ask:
- "What code changed in my MR?"
- "Show me the diff"
- "What files were modified?"
- "What are the changes in the MR?"
""",
    mime_type="application/json"
)
async def current_branch_mr_changes() -> dict:
    """Get changes/diff for the MR on the current branch"""
    ctx = mcp.get_context()
    repo_info = await detect_current_repo(ctx, gitlab_client)

    if not repo_info:
        return {
            "error": "Not in a GitLab repository or repository not found on configured GitLab instance"
        }

    git_root = repo_info["git_root"]
    project_id = str(repo_info["project"]["id"])

    # Get current branch
    branch_name = get_current_branch(git_root)
    if not branch_name:
        return {
            "error": "Could not determine current git branch"
        }

    # Find MR for this branch
    mr = find_mr_for_branch(gitlab_client, project_id, branch_name)
    if not mr:
        return {
            "error": f"No open merge request found for branch '{branch_name}'",
            "branch": branch_name
        }

    # Get changes
    changes = gitlab_client.get_mr_changes(project_id, mr["iid"])
    return changes


@mcp.resource(
    "gitlab://help/",
    name="GitLab MCP Help",
    description="Quick reference for available GitLab MCP resources and common queries",
    mime_type="application/json"
)
async def gitlab_help() -> dict:
    """Get help information about available GitLab resources"""
    return {
        "server": "gitlab-mcp",
        "description": "GitLab integration for the current repository",
        "available_resources": {
            "current_branch_mr_overview": {
                "uri": "gitlab://current-project/current-branch-mr/",
                "description": "⭐ RECOMMENDED: Complete MR overview (discussions, changes, commits, approvals)",
                "queries": ["What's my MR status?", "Show me everything about the current MR", "Summarize my MR"]
            },
            "current_branch_mr_discussions": {
                "uri": "gitlab://current-project/current-branch-mr-discussions/",
                "description": "Discussions on the MR for the current branch",
                "queries": ["Any unresolved discussions?", "What comments are on my MR?", "Show MR feedback"]
            },
            "current_branch_mr_changes": {
                "uri": "gitlab://current-project/current-branch-mr-changes/",
                "description": "Code changes/diff for the current branch MR",
                "queries": ["What code changed?", "Show me the diff", "What files were modified?"]
            },
            "current_project": {
                "uri": "gitlab://current-project/",
                "description": "Project information",
                "queries": ["What's the project info?", "Show me project details"]
            },
            "status": {
                "uri": "gitlab://current-project/status/",
                "description": "Quick status overview",
                "queries": ["What's the project status?", "Give me a quick overview"]
            },
            "open_merge_requests": {
                "uri": "gitlab://current-project/merge-requests/",
                "description": "Open merge requests",
                "queries": ["Any open MRs?", "What needs review?"]
            },
            "all_merge_requests": {
                "uri": "gitlab://current-project/all-merge-requests/",
                "description": "All merge requests (open, merged, closed)",
                "queries": ["Show me all MRs", "Complete MR history"]
            },
            "merged_merge_requests": {
                "uri": "gitlab://current-project/merged-merge-requests/",
                "description": "Merged merge requests",
                "queries": ["Show me merged MRs", "What's been merged?"]
            },
            "closed_merge_requests": {
                "uri": "gitlab://current-project/closed-merge-requests/",
                "description": "Closed/rejected merge requests",
                "queries": ["Show me closed MRs", "What was declined?"]
            },
            "pipelines": {
                "uri": "gitlab://current-project/pipelines/",
                "description": "Recent pipelines (last 20)",
                "queries": ["Pipeline status?", "Are CI/CD pipelines passing?"]
            },
            "all_projects": {
                "uri": "gitlab://projects/",
                "description": "List all accessible GitLab projects",
                "queries": ["Show all my projects"]
            }
        },
        "usage": "Use ReadMcpResourceTool with server='gitlab' and the appropriate URI",
        "common_questions": [
            "What's the status of my MR? (Use current-branch-mr/)",
            "Any unresolved discussions on my MR?",
            "What code changed in my MR?",
            "Are there any open merge requests?",
            "What's the pipeline status?",
            "Show me merged MRs",
            "What needs review?",
            "Check CI/CD status",
            "What's the project status?"
        ]
    }


# Global projects resources
@mcp.resource(
    "gitlab://projects/",
    name="All Projects",
    description="List of all GitLab projects you have access to",
    mime_type="application/json"
)
async def all_projects() -> list:
    """List all projects"""
    return gitlab_client.get_projects()


@mcp.resource("gitlab://projects/{project_id}")
async def project_by_id(project_id: str) -> dict:
    """Get specific project by ID"""
    return gitlab_client.get_project(project_id)


@mcp.resource("gitlab://projects/{project_id}/merge-requests/")
async def project_merge_requests(project_id: str) -> list:
    """Get merge requests for a project"""
    return gitlab_client.get_merge_requests(project_id, state="opened")


@mcp.resource("gitlab://projects/{project_id}/merge-requests/{mr_iid}")
async def project_merge_request(project_id: str, mr_iid: str) -> dict:
    """Get specific merge request with latest pipeline and jobs"""
    mr = gitlab_client.get_merge_request(project_id, int(mr_iid))
    pipelines = gitlab_client.get_mr_pipelines(project_id, int(mr_iid))

    latest_pipeline = None
    if pipelines:
        latest_pipeline = pipelines[0]
        jobs = gitlab_client.get_pipeline_jobs(project_id, latest_pipeline['id'])
        latest_pipeline['jobs'] = jobs

    return {
        "merge_request": mr,
        "latest_pipeline": latest_pipeline
    }


@mcp.resource("gitlab://projects/{project_id}/merge-requests/{mr_iid}/discussions")
async def project_merge_request_discussions(project_id: str, mr_iid: str) -> dict:
    """Get discussions for a specific merge request"""
    discussions = gitlab_client.get_mr_discussions(project_id, int(mr_iid))

    # Analyze discussions to provide summary
    total_discussions = len(discussions)
    unresolved_discussions = [d for d in discussions if not d.get("notes", [{}])[0].get("resolved", False)]

    return {
        "summary": {
            "total_discussions": total_discussions,
            "unresolved_count": len(unresolved_discussions),
            "resolved_count": total_discussions - len(unresolved_discussions)
        },
        "discussions": discussions,
        "unresolved_discussions": unresolved_discussions
    }


@mcp.resource("gitlab://projects/{project_id}/pipelines/")
async def project_pipelines(project_id: str) -> list:
    """Get pipelines for a project"""
    return gitlab_client.get_pipelines(project_id)


@mcp.resource("gitlab://projects/{project_id}/pipelines/{pipeline_id}")
async def project_pipeline(project_id: str, pipeline_id: str) -> dict:
    """Get specific pipeline"""
    return gitlab_client.get_pipeline(project_id, int(pipeline_id))


if __name__ == "__main__":
    mcp.run()
