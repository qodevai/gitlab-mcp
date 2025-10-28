import logging
import os
import re
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from fastmcp import Context, FastMCP
from mcp import types

# Load environment variables from .env file
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
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
        self.base_url = (
            base_url or os.getenv("GITLAB_BASE_URL") or os.getenv("GITLAB_URL") or "https://gitlab.com"
        ).rstrip("/")

        self._validate_configuration()

        self.api_url = f"{self.base_url}/api/v4"
        # Type assertion: self.token is guaranteed to be str after validation
        headers: dict[str, str] = {"PRIVATE-TOKEN": str(self.token), "Content-Type": "application/json"}
        self.client = httpx.Client(
            base_url=self.api_url,
            headers=headers,
            timeout=30.0,
        )

        if validate:
            self._test_connectivity()
        else:
            logger.info(f"GitLab client initialized for {self.base_url} (validation skipped)")

    def _validate_configuration(self) -> None:
        """Validate token and URL configuration"""
        if not self.token:
            logger.error("GITLAB_TOKEN not set in environment variables")
            raise ValueError("GITLAB_TOKEN environment variable is required. Set it in your .env file or environment.")

        if not self.base_url.startswith(("http://", "https://")):
            logger.error(f"Invalid GITLAB_URL: {self.base_url}")
            raise ValueError(f"GITLAB_URL must start with http:// or https://, got: {self.base_url}")

    def _test_connectivity(self) -> None:
        """Test connectivity to GitLab instance"""
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

    @staticmethod
    def _encode_project_id(project_id: str) -> str:
        """Encode project ID for URL path (DRY principle)"""
        from urllib.parse import quote

        return quote(project_id, safe="")

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

    def get_paginated(
        self, endpoint: str, params: dict[str, Any] | None = None, per_page: int = 100, max_pages: int = 100
    ) -> list[Any]:
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
        encoded_id = self._encode_project_id(project_id)
        return self.get(f"/projects/{encoded_id}")

    def get_merge_requests(self, project_id: str, state: str = "opened") -> list[dict[str, Any]]:
        """Get merge requests for a project"""
        encoded_id = self._encode_project_id(project_id)
        params = {"state": state}
        return self.get_paginated(f"/projects/{encoded_id}/merge_requests", params=params)

    def get_merge_request(self, project_id: str, mr_iid: int) -> dict[str, Any]:
        """Get a specific merge request"""
        encoded_id = self._encode_project_id(project_id)
        return self.get(f"/projects/{encoded_id}/merge_requests/{mr_iid}")

    def get_pipelines(self, project_id: str, ref: str | None = None) -> list[dict[str, Any]]:
        """Get pipelines for a project"""
        encoded_id = self._encode_project_id(project_id)
        params = {"ref": ref} if ref else {}
        return self.get_paginated(f"/projects/{encoded_id}/pipelines", params=params)

    def get_pipeline(self, project_id: str, pipeline_id: int) -> dict[str, Any]:
        """Get a specific pipeline"""
        encoded_id = self._encode_project_id(project_id)
        return self.get(f"/projects/{encoded_id}/pipelines/{pipeline_id}")

    def get_mr_pipelines(self, project_id: str, mr_iid: int) -> list[dict[str, Any]]:
        """Get pipelines for a merge request"""
        encoded_id = self._encode_project_id(project_id)
        return self.get(f"/projects/{encoded_id}/merge_requests/{mr_iid}/pipelines")

    def get_pipeline_jobs(self, project_id: str, pipeline_id: int) -> list[dict[str, Any]]:
        """Get jobs for a specific pipeline"""
        encoded_id = self._encode_project_id(project_id)
        return self.get_paginated(f"/projects/{encoded_id}/pipelines/{pipeline_id}/jobs")

    def get_job_log(self, project_id: str, job_id: int) -> str:
        """Get logs for a specific job

        Args:
            project_id: Project ID or path
            job_id: Job ID

        Returns:
            Raw log text as string
        """
        encoded_id = self._encode_project_id(project_id)
        try:
            logger.debug(f"GET /projects/{encoded_id}/jobs/{job_id}/trace")
            response = self.client.get(f"/projects/{encoded_id}/jobs/{job_id}/trace")
            response.raise_for_status()
            # Job logs are returned as plain text, not JSON
            return response.text
        except httpx.HTTPStatusError as e:
            logger.error(f"GitLab API error for GET job {job_id} trace: {e.response.status_code}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Network error for GET job {job_id} trace: {e}")
            raise
        except Exception as e:
            logger.exception(f"Unexpected error for GET job {job_id} trace: {e}")
            raise

    def get_mr_discussions(self, project_id: str, mr_iid: int) -> list[dict[str, Any]]:
        """Get all discussions (comments/threads) for a merge request"""
        encoded_id = self._encode_project_id(project_id)
        return self.get_paginated(f"/projects/{encoded_id}/merge_requests/{mr_iid}/discussions")

    def get_mr_changes(self, project_id: str, mr_iid: int) -> dict[str, Any]:
        """Get the diff/changes for a merge request"""
        encoded_id = self._encode_project_id(project_id)
        return self.get(f"/projects/{encoded_id}/merge_requests/{mr_iid}/changes")

    def get_mr_commits(self, project_id: str, mr_iid: int) -> list[dict[str, Any]]:
        """Get commits for a merge request"""
        encoded_id = self._encode_project_id(project_id)
        return self.get_paginated(f"/projects/{encoded_id}/merge_requests/{mr_iid}/commits")

    def get_mr_approvals(self, project_id: str, mr_iid: int) -> dict[str, Any]:
        """Get approval status for a merge request"""
        encoded_id = self._encode_project_id(project_id)
        return self.get(f"/projects/{encoded_id}/merge_requests/{mr_iid}/approvals")

    def create_mr_note(self, project_id: str, mr_iid: int, body: str) -> dict[str, Any]:
        """Create a comment/note on a merge request

        Args:
            project_id: Project ID or path
            mr_iid: Merge request IID
            body: Comment text (supports Markdown)

        Returns:
            Created note data

        Raises:
            httpx.HTTPStatusError: If comment creation fails
        """
        encoded_id = self._encode_project_id(project_id)

        data = {"body": body}

        try:
            logger.info(f"Creating note on MR !{mr_iid} in project {project_id}")
            response = self.client.post(
                f"/projects/{encoded_id}/merge_requests/{mr_iid}/notes",
                json=data,
            )
            response.raise_for_status()
            logger.info(f"Successfully created note on MR !{mr_iid}")
            return response.json()
        except httpx.HTTPStatusError as e:
            error_detail = e.response.text[:500] if e.response.text else "No error details"
            logger.error(f"Failed to create note on MR !{mr_iid}: {e.response.status_code} - {error_detail}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Network error while creating note on MR !{mr_iid}: {e}")
            raise
        except Exception as e:
            logger.exception(f"Unexpected error while creating note on MR !{mr_iid}: {e}")
            raise

    def merge_mr(
        self,
        project_id: str,
        mr_iid: int,
        merge_commit_message: str | None = None,
        squash_commit_message: str | None = None,
        should_remove_source_branch: bool = True,
        merge_when_pipeline_succeeds: bool = False,
        squash: bool | None = None,
    ) -> dict[str, Any]:
        """Merge a merge request

        Args:
            project_id: Project ID or path
            mr_iid: Merge request IID
            merge_commit_message: Custom merge commit message (optional)
            squash_commit_message: Custom squash commit message (optional)
            should_remove_source_branch: Remove source branch after merge (default: True)
            merge_when_pipeline_succeeds: Merge when pipeline succeeds (default: False)
            squash: Squash commits on merge (default: None - use project/MR settings)

        Returns:
            Merged MR data

        Raises:
            httpx.HTTPStatusError: If merge fails (e.g., not mergeable, conflicts, not approved)
        """
        encoded_id = self._encode_project_id(project_id)

        data: dict[str, Any] = {
            "should_remove_source_branch": should_remove_source_branch,
            "merge_when_pipeline_succeeds": merge_when_pipeline_succeeds,
        }

        if merge_commit_message:
            data["merge_commit_message"] = merge_commit_message
        if squash_commit_message:
            data["squash_commit_message"] = squash_commit_message
        if squash is not None:
            data["squash"] = squash

        try:
            logger.info(f"Merging MR !{mr_iid} in project {project_id}")
            response = self.client.put(
                f"/projects/{encoded_id}/merge_requests/{mr_iid}/merge",
                json=data,
            )
            response.raise_for_status()
            logger.info(f"Successfully merged MR !{mr_iid}")
            return response.json()
        except httpx.HTTPStatusError as e:
            # Parse GitLab API error response for better error messages
            import json

            error_detail = e.response.text[:500] if e.response.text else "No error details"
            logger.error(f"Failed to merge MR !{mr_iid}: {e.response.status_code} - {error_detail}")

            # Try to parse the error response
            try:
                error_json = json.loads(e.response.text)
                error_message = error_json.get("message", str(e))
            except (json.JSONDecodeError, AttributeError):
                error_message = str(e)

            # Create a custom exception with additional context
            error = httpx.HTTPStatusError(
                message=f"{error_message}",
                request=e.request,
                response=e.response,
            )
            raise error
        except httpx.RequestError as e:
            logger.error(f"Network error while merging MR !{mr_iid}: {e}")
            raise
        except Exception as e:
            logger.exception(f"Unexpected error while merging MR !{mr_iid}: {e}")
            raise

    def get_project_variable(self, project_id: str, key: str) -> dict[str, Any] | None:
        """Get a specific CI/CD variable for a project

        Args:
            project_id: Project ID or path
            key: Variable key/name

        Returns:
            Variable data if exists, None if not found

        Raises:
            httpx.HTTPStatusError: If API error (except 404)
        """
        encoded_id = self._encode_project_id(project_id)

        try:
            logger.debug(f"Getting CI/CD variable '{key}' from project {project_id}")
            # URL encode the key to handle special characters
            from urllib.parse import quote

            encoded_key = quote(key, safe="")
            response = self.client.get(f"/projects/{encoded_id}/variables/{encoded_key}")
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                # Variable doesn't exist - this is expected for upsert logic
                logger.debug(f"CI/CD variable '{key}' not found in project {project_id}")
                return None
            logger.error(f"API error getting CI/CD variable '{key}': {e.response.status_code}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Network error getting CI/CD variable '{key}': {e}")
            raise
        except Exception as e:
            logger.exception(f"Unexpected error getting CI/CD variable '{key}': {e}")
            raise

    def create_project_variable(
        self,
        project_id: str,
        key: str,
        value: str,
        variable_type: str = "env_var",
        protected: bool = False,
        masked: bool = False,
        raw: bool = False,
        environment_scope: str = "*",
        description: str | None = None,
    ) -> dict[str, Any]:
        """Create a new CI/CD variable for a project

        Args:
            project_id: Project ID or path
            key: Variable key/name
            value: Variable value
            variable_type: Type of variable ("env_var" or "file")
            protected: Whether variable is only available in protected branches
            masked: Whether variable is hidden in job logs
            raw: Whether to disable variable expansion
            environment_scope: Environment scope (e.g., "*", "production", "staging")
            description: Optional description of the variable

        Returns:
            Created variable data

        Raises:
            httpx.HTTPStatusError: If variable creation fails
        """
        encoded_id = self._encode_project_id(project_id)

        data: dict[str, Any] = {
            "key": key,
            "value": value,
            "variable_type": variable_type,
            "protected": protected,
            "masked": masked,
            "raw": raw,
            "environment_scope": environment_scope,
        }

        if description is not None:
            data["description"] = description

        try:
            logger.info(f"Creating CI/CD variable '{key}' in project {project_id}")
            response = self.client.post(f"/projects/{encoded_id}/variables", json=data)
            response.raise_for_status()
            logger.info(f"Successfully created CI/CD variable '{key}'")
            return response.json()
        except httpx.HTTPStatusError as e:
            error_detail = e.response.text[:500] if e.response.text else "No error details"
            logger.error(f"Failed to create CI/CD variable '{key}': {e.response.status_code} - {error_detail}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Network error while creating CI/CD variable '{key}': {e}")
            raise
        except Exception as e:
            logger.exception(f"Unexpected error while creating CI/CD variable '{key}': {e}")
            raise

    def update_project_variable(
        self,
        project_id: str,
        key: str,
        value: str,
        variable_type: str = "env_var",
        protected: bool = False,
        masked: bool = False,
        raw: bool = False,
        environment_scope: str = "*",
        description: str | None = None,
    ) -> dict[str, Any]:
        """Update an existing CI/CD variable for a project

        Args:
            project_id: Project ID or path
            key: Variable key/name
            value: Variable value
            variable_type: Type of variable ("env_var" or "file")
            protected: Whether variable is only available in protected branches
            masked: Whether variable is hidden in job logs
            raw: Whether to disable variable expansion
            environment_scope: Environment scope (e.g., "*", "production", "staging")
            description: Optional description of the variable

        Returns:
            Updated variable data

        Raises:
            httpx.HTTPStatusError: If variable update fails
        """
        encoded_id = self._encode_project_id(project_id)

        data: dict[str, Any] = {
            "value": value,
            "variable_type": variable_type,
            "protected": protected,
            "masked": masked,
            "raw": raw,
            "environment_scope": environment_scope,
        }

        if description is not None:
            data["description"] = description

        try:
            logger.info(f"Updating CI/CD variable '{key}' in project {project_id}")
            # URL encode the key to handle special characters
            from urllib.parse import quote

            encoded_key = quote(key, safe="")
            response = self.client.put(f"/projects/{encoded_id}/variables/{encoded_key}", json=data)
            response.raise_for_status()
            logger.info(f"Successfully updated CI/CD variable '{key}'")
            return response.json()
        except httpx.HTTPStatusError as e:
            error_detail = e.response.text[:500] if e.response.text else "No error details"
            logger.error(f"Failed to update CI/CD variable '{key}': {e.response.status_code} - {error_detail}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Network error while updating CI/CD variable '{key}': {e}")
            raise
        except Exception as e:
            logger.exception(f"Unexpected error while updating CI/CD variable '{key}': {e}")
            raise

    def set_project_variable(
        self,
        project_id: str,
        key: str,
        value: str,
        variable_type: str = "env_var",
        protected: bool = False,
        masked: bool = False,
        raw: bool = False,
        environment_scope: str = "*",
        description: str | None = None,
    ) -> tuple[dict[str, Any], str]:
        """Set a CI/CD variable (upsert: update if exists, create if not)

        Args:
            project_id: Project ID or path
            key: Variable key/name
            value: Variable value
            variable_type: Type of variable ("env_var" or "file")
            protected: Whether variable is only available in protected branches
            masked: Whether variable is hidden in job logs
            raw: Whether to disable variable expansion
            environment_scope: Environment scope (e.g., "*", "production", "staging")
            description: Optional description of the variable

        Returns:
            Tuple of (variable data, action) where action is "created" or "updated"

        Raises:
            httpx.HTTPStatusError: If variable operation fails
        """
        # Check if variable exists
        existing_var = self.get_project_variable(project_id, key)

        if existing_var:
            # Variable exists - update it
            variable = self.update_project_variable(
                project_id=project_id,
                key=key,
                value=value,
                variable_type=variable_type,
                protected=protected,
                masked=masked,
                raw=raw,
                environment_scope=environment_scope,
                description=description,
            )
            return variable, "updated"
        else:
            # Variable doesn't exist - create it
            variable = self.create_project_variable(
                project_id=project_id,
                key=key,
                value=value,
                variable_type=variable_type,
                protected=protected,
                masked=masked,
                raw=raw,
                environment_scope=environment_scope,
                description=description,
            )
            return variable, "created"


# Helper functions
def create_repo_not_found_error(gitlab_base_url: str) -> dict[str, str]:
    """Create standardized error response for repository not found (DRY principle)"""
    return {
        "error": "Not in a GitLab repository or repository not found on configured GitLab instance",
        "base_url": gitlab_base_url,
    }


def create_branch_error(branch_name: str | None = None) -> dict[str, str]:
    """Create standardized error response for branch detection issues (DRY principle)"""
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
        domain_match = re.search(r"https?://([^/]+)", base_url)
        if not domain_match:
            return None
        domain = domain_match.group(1)

        # Look for remote URL patterns matching this GitLab instance
        # Matches both SSH and HTTPS URLs for the specific domain
        patterns = [
            rf"url = .*@{re.escape(domain)}:(.+?)\.git",  # SSH: git@gitlab.qodev.ai:group/project.git
            rf"url = https?://{re.escape(domain)}/(.+?)\.git",  # HTTPS: https://gitlab.qodev.ai/group/project.git
        ]

        for pattern in patterns:
            match = re.search(pattern, config_content)
            if match:
                return match.group(1)

        return None
    except Exception:
        return None


async def get_workspace_roots_from_client(ctx: Context) -> list[types.Root] | None:
    """Request workspace roots from MCP client

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


async def detect_current_repo(ctx: Context, gitlab_client: GitLabClient) -> dict[str, Any] | None:
    """Detect current git repo from MCP roots, env var, or CWD

    Detection priority:
    1. MCP workspace roots from client (proper MCP implementation)
    2. GITLAB_REPO_PATH environment variable (manual override)
    3. Current working directory (fallback)

    Args:
        ctx: FastMCP context object
        gitlab_client: GitLab API client

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

            project_path = parse_gitlab_remote(git_root, gitlab_client.base_url)
            if not project_path:
                logger.debug(f"Git repository found but no matching GitLab remote at: {git_root}")
                continue

            # Fetch project info from GitLab API
            try:
                project = gitlab_client.get_project(project_path)
                logger.info(f"Detected GitLab project: {project.get('path_with_namespace')} from {git_root}")
                return {"git_root": git_root, "project_path": project_path, "project": project}
            except httpx.HTTPStatusError as e:
                logger.warning(f"Failed to fetch project '{project_path}' from GitLab: {e.response.status_code}")
                continue
            except Exception as e:
                logger.debug(f"Error fetching project '{project_path}': {e}")
                continue

        logger.debug("No GitLab repository found in any search path")
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


def find_mr_for_branch(gitlab_client: GitLabClient, project_id: str, branch_name: str) -> dict[str, Any] | None:
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


async def get_current_branch_mr(
    ctx: Context, gitlab_client: GitLabClient
) -> tuple[dict[str, Any] | None, str | None, str | None]:
    """Get MR for current branch - common logic extracted (DRY principle)

    Args:
        ctx: FastMCP context
        gitlab_client: GitLab API client

    Returns:
        Tuple of (mr_dict, project_id, branch_name) or (None, None, None) on error
    """
    repo_info = await detect_current_repo(ctx, gitlab_client)
    if not repo_info:
        return None, None, None

    git_root = repo_info["git_root"]
    project_id = str(repo_info["project"]["id"])

    branch_name = get_current_branch(git_root)
    if not branch_name:
        return None, None, None

    mr = find_mr_for_branch(gitlab_client, project_id, branch_name)
    return mr, project_id, branch_name


async def resolve_project_id(ctx: Context, project_id: str) -> tuple[str | None, dict[str, Any] | None]:
    """Resolve 'current' to actual project ID, pass through others

    Args:
        ctx: FastMCP context
        project_id: Project ID (numeric, path, or "current")

    Returns:
        Tuple of (resolved_project_id, repo_info) or (None, None) on error
        - If project_id == "current": returns (detected_project_id, repo_info_dict)
        - Otherwise: returns (project_id, None)
    """
    if project_id == "current":
        repo_info = await detect_current_repo(ctx, gitlab_client)
        if not repo_info:
            logger.warning("Could not resolve 'current' project - not in a GitLab repository")
            return None, None
        resolved_id = str(repo_info["project"]["id"])
        logger.debug(f"Resolved 'current' project to: {resolved_id}")
        return resolved_id, repo_info
    return project_id, None


async def resolve_mr_iid(ctx: Context, project_id: str, mr_iid: str | int) -> int | None:
    """Resolve 'current' to MR IID for current branch, parse others

    Args:
        ctx: FastMCP context
        project_id: Already resolved project ID (not "current")
        mr_iid: MR IID (numeric or "current")

    Returns:
        Resolved MR IID or None on error
    """
    if str(mr_iid) == "current":
        repo_info = await detect_current_repo(ctx, gitlab_client)
        if not repo_info:
            logger.warning("Could not resolve 'current' MR - not in a GitLab repository")
            return None

        branch_name = get_current_branch(repo_info["git_root"])
        if not branch_name:
            logger.warning("Could not resolve 'current' MR - unable to determine current branch")
            return None

        mr = find_mr_for_branch(gitlab_client, project_id, branch_name)
        if not mr:
            logger.warning(f"Could not resolve 'current' MR - no MR found for branch '{branch_name}'")
            return None

        logger.debug(f"Resolved 'current' MR to IID: {mr['iid']} for branch '{branch_name}'")
        return mr["iid"]

    return int(mr_iid)


# Create FastMCP server
mcp = FastMCP(
    "gitlab-mcp",
    instructions="""
This server provides GitLab integration using a unified API with support for current repository detection.

IMPORTANT - Unified Resource Format:
All resources use: gitlab://projects/{project_id}/...
- project_id can be: numeric ID (123), URL-encoded path (qodev%2Fhandbook), plain path (qodev/handbook), or "current"
- mr_iid can be: numeric IID (20) or "current" (for current branch's MR)
- For project paths with slashes, URL-encode them: "qodev/handbook" → "qodev%2Fhandbook" (or use plain format - will be auto-encoded)

RESOURCES - Access GitLab data:

Current Repo/Branch (use project_id="current" and mr_iid="current"):
- gitlab://projects/current/merge-requests/current - Comprehensive MR overview (RECOMMENDED - includes discussions, changes, commits, pipeline, approvals)
- gitlab://projects/current/merge-requests/current/discussions - Just discussions/comments
- gitlab://projects/current/merge-requests/current/changes - Just code diff
- gitlab://projects/current/merge-requests/current/commits - Just commits
- gitlab://projects/current/merge-requests/current/approvals - Just approval status
- gitlab://projects/current/merge-requests/current/pipeline-jobs - Just pipeline jobs
- gitlab://projects/current/merge-requests/ - All open MRs in current project
- gitlab://projects/current/pipelines/ - Pipelines for current project

Specific Project/MR (use numeric ID or URL-encoded path):
- gitlab://projects/qodev%2Fhandbook/merge-requests/20 - Comprehensive MR overview
- gitlab://projects/123/merge-requests/20/discussions - Granular access to discussions only
- gitlab://projects/qodev%2Fhandbook/merge-requests/20/changes - Granular access to changes only

TOOLS - Perform actions (all support "current"):
- comment_on_merge_request(project_id, mr_iid, comment) - Leave a comment (supports project_id="current", mr_iid="current")
- merge_merge_request(project_id, mr_iid, ...) - Merge an MR (supports project_id="current", mr_iid="current")
- set_project_ci_variable(project_id, key, value, ...) - Set CI/CD variable (supports project_id="current")

Examples:
- "What's the status of my MR?" → gitlab://projects/current/merge-requests/current
- "Show me MR !20 in qodev/handbook" → gitlab://projects/qodev%2Fhandbook/merge-requests/20
- "Comment on my MR saying 'LGTM'" → comment_on_merge_request("current", "current", "LGTM")
- "Merge MR !20 in project qodev/handbook" → merge_merge_request("qodev/handbook", 20)
- "What discussions are on my MR?" → gitlab://projects/current/merge-requests/current/discussions (token-efficient!)
- "Set API_KEY in current project" → set_project_ci_variable("current", "API_KEY", "secret123")

Token Efficiency:
- Use comprehensive resource for full overview: gitlab://projects/{id}/merge-requests/{iid}
- Use granular resources when you only need specific data: /discussions, /changes, /commits, /approvals, /pipeline-jobs

DO NOT use git commands or branch inspection to answer GitLab questions.
Use ReadMcpResourceTool with server="gitlab" for all GitLab queries.

For help, use gitlab://help/ to see all available resources.
""",
)
gitlab_client = GitLabClient()


# Global project resources (support project_id="current" for current repo)
@mcp.resource(
    "gitlab://help/",
    name="GitLab MCP Help",
    description="Quick reference for available GitLab MCP resources and common queries",
    mime_type="application/json",
)
def gitlab_help() -> dict[str, Any]:
    """Get help information about available GitLab resources"""
    return {
        "server": "gitlab-mcp",
        "description": "GitLab integration using unified API with 'current' support",
        "uri_format": {
            "pattern": "gitlab://projects/{project_id}/...",
            "project_id_formats": [
                "numeric ID: 123",
                "URL-encoded path: qodev%2Fhandbook",
                "plain path: qodev/handbook (auto-encoded)",
                "special value: 'current' (detects current repo)",
            ],
            "mr_iid_formats": [
                "numeric IID: 20",
                "special value: 'current' (detects MR for current branch)",
            ],
            "encoding_note": "For project paths with slashes, URL-encode them or use plain format (will be auto-encoded)",
        },
        "available_resources": {
            "comprehensive_mr": {
                "uri": "gitlab://projects/{project_id}/merge-requests/{mr_iid}",
                "examples": [
                    "gitlab://projects/current/merge-requests/current (current repo & branch)",
                    "gitlab://projects/qodev%2Fhandbook/merge-requests/20 (specific project & MR)",
                    "gitlab://projects/123/merge-requests/20 (numeric IDs)",
                ],
                "description": "⭐ RECOMMENDED: Complete MR overview (discussions, changes, commits, pipeline, approvals)",
                "queries": ["What's my MR status?", "Show me everything about MR !20", "Summarize the MR"],
            },
            "granular_mr_discussions": {
                "uri": "gitlab://projects/{project_id}/merge-requests/{mr_iid}/discussions",
                "examples": ["gitlab://projects/current/merge-requests/current/discussions"],
                "description": "Token-efficient: Just discussions/comments",
                "queries": ["Any unresolved discussions?", "What comments are there?"],
            },
            "granular_mr_changes": {
                "uri": "gitlab://projects/{project_id}/merge-requests/{mr_iid}/changes",
                "examples": ["gitlab://projects/current/merge-requests/current/changes"],
                "description": "Token-efficient: Just code diff",
                "queries": ["What code changed?", "Show me the diff"],
            },
            "granular_mr_commits": {
                "uri": "gitlab://projects/{project_id}/merge-requests/{mr_iid}/commits",
                "examples": ["gitlab://projects/current/merge-requests/current/commits"],
                "description": "Token-efficient: Just commits",
                "queries": ["What commits are in this MR?"],
            },
            "granular_mr_approvals": {
                "uri": "gitlab://projects/{project_id}/merge-requests/{mr_iid}/approvals",
                "examples": ["gitlab://projects/current/merge-requests/current/approvals"],
                "description": "Token-efficient: Just approval status",
                "queries": ["Is the MR approved?", "Who needs to approve?"],
            },
            "granular_mr_pipeline_jobs": {
                "uri": "gitlab://projects/{project_id}/merge-requests/{mr_iid}/pipeline-jobs",
                "examples": ["gitlab://projects/current/merge-requests/current/pipeline-jobs"],
                "description": "Token-efficient: Just latest pipeline jobs",
                "queries": ["What jobs ran?", "Which jobs failed?"],
            },
            "project_merge_requests": {
                "uri": "gitlab://projects/{project_id}/merge-requests/",
                "examples": ["gitlab://projects/current/merge-requests/"],
                "description": "All open MRs in a project",
                "queries": ["Any open MRs?", "What needs review?"],
            },
            "project_info": {
                "uri": "gitlab://projects/{project_id}",
                "examples": ["gitlab://projects/current"],
                "description": "Project information",
                "queries": ["What's the project info?"],
            },
            "project_pipelines": {
                "uri": "gitlab://projects/{project_id}/pipelines/",
                "examples": ["gitlab://projects/current/pipelines/"],
                "description": "Recent pipelines for a project",
                "queries": ["Pipeline status?", "Are CI/CD pipelines passing?"],
            },
            "pipeline_jobs": {
                "uri": "gitlab://projects/{project_id}/pipelines/{pipeline_id}/jobs",
                "examples": ["gitlab://projects/current/pipelines/12345/jobs"],
                "description": "Jobs for a specific pipeline",
                "queries": ["Show me jobs for pipeline X"],
            },
            "job_log": {
                "uri": "gitlab://projects/{project_id}/jobs/{job_id}/log",
                "examples": ["gitlab://projects/current/jobs/67890/log"],
                "description": "Log output for a specific job",
                "queries": ["Show me the log for job X", "What's the error?"],
            },
            "all_projects": {
                "uri": "gitlab://projects/",
                "description": "List all accessible GitLab projects",
                "queries": ["Show all my projects"],
            },
        },
        "tools": {
            "comment_on_merge_request": {
                "signature": "comment_on_merge_request(project_id, mr_iid, comment)",
                "supports_current": True,
                "examples": [
                    "comment_on_merge_request('current', 'current', 'LGTM!')",
                    "comment_on_merge_request('qodev/handbook', 20, 'Needs work')",
                ],
            },
            "merge_merge_request": {
                "signature": "merge_merge_request(project_id, mr_iid, ...)",
                "supports_current": True,
                "examples": [
                    "merge_merge_request('current', 'current')",
                    "merge_merge_request('123', 20, squash=True)",
                ],
            },
            "set_project_ci_variable": {
                "signature": "set_project_ci_variable(project_id, key, value, ...)",
                "supports_current": True,
                "examples": [
                    "set_project_ci_variable('current', 'API_KEY', 'secret123')",
                    "set_project_ci_variable('qodev/handbook', 'ENV', 'prod', protected=True, masked=True)",
                ],
            },
        },
        "usage": "Use ReadMcpResourceTool with server='gitlab' and the appropriate URI",
        "token_efficiency_tip": "Use granular resources (/discussions, /changes, etc.) when you only need specific data instead of the comprehensive MR overview",
        "common_questions": [
            "What's the status of my MR? → gitlab://projects/current/merge-requests/current",
            "What discussions are on my MR? → gitlab://projects/current/merge-requests/current/discussions",
            "Show me MR !20 in qodev/handbook → gitlab://projects/qodev%2Fhandbook/merge-requests/20",
            "Comment on my MR → comment_on_merge_request('current', 'current', 'message')",
            "Merge my MR → merge_merge_request('current', 'current')",
            "Any open MRs? → gitlab://projects/current/merge-requests/",
            "Pipeline status? → gitlab://projects/current/pipelines/",
        ],
    }


# Global projects resources
@mcp.resource(
    "gitlab://projects/",
    name="All Projects",
    description="List of all GitLab projects you have access to",
    mime_type="application/json",
)
def all_projects() -> list[dict[str, Any]]:
    """List all projects"""
    return gitlab_client.get_projects()


@mcp.resource("gitlab://projects/{project_id}")
async def project_by_id(ctx: Context, project_id: str) -> dict[str, Any]:
    """Get specific project by ID (supports project_id="current" for current repo)"""
    resolved_id, repo_info = await resolve_project_id(ctx, project_id)
    if not resolved_id:
        return create_repo_not_found_error(gitlab_client.base_url)

    # If we already have the project info from resolution, use it
    if repo_info:
        return repo_info["project"]

    return gitlab_client.get_project(resolved_id)


@mcp.resource("gitlab://projects/{project_id}/merge-requests/")
async def project_merge_requests(ctx: Context, project_id: str) -> list[dict[str, Any]] | dict[str, Any]:
    """Get open merge requests for a project (supports project_id="current")"""
    resolved_id, _ = await resolve_project_id(ctx, project_id)
    if not resolved_id:
        return create_repo_not_found_error(gitlab_client.base_url)
    return gitlab_client.get_merge_requests(resolved_id, state="opened")


@mcp.resource("gitlab://projects/{project_id}/merge-requests/{mr_iid}")
async def project_merge_request(ctx: Context, project_id: str, mr_iid: str) -> dict[str, Any]:
    """Get comprehensive MR overview (supports project_id="current" and mr_iid="current")

    Returns complete MR information including discussions, changes, commits, pipeline, and approvals.
    For granular access to specific data, use the dedicated resources (/discussions, /changes, etc.)
    """
    resolved_project_id, _ = await resolve_project_id(ctx, project_id)
    if not resolved_project_id:
        return create_repo_not_found_error(gitlab_client.base_url)

    resolved_mr_iid = await resolve_mr_iid(ctx, resolved_project_id, mr_iid)
    if not resolved_mr_iid:
        return {"error": f"Could not resolve MR IID '{mr_iid}'"}

    try:
        mr = gitlab_client.get_merge_request(resolved_project_id, resolved_mr_iid)
        discussions = gitlab_client.get_mr_discussions(resolved_project_id, resolved_mr_iid)
        changes = gitlab_client.get_mr_changes(resolved_project_id, resolved_mr_iid)
        commits = gitlab_client.get_mr_commits(resolved_project_id, resolved_mr_iid)
        pipelines = gitlab_client.get_mr_pipelines(resolved_project_id, resolved_mr_iid)

        # Try to get approvals (might fail if not available in GitLab edition)
        try:
            approvals = gitlab_client.get_mr_approvals(resolved_project_id, resolved_mr_iid)
        except Exception:
            approvals = None

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
                "deleted_file": change.get("deleted_file", False),
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
                "work_in_progress": mr.get("work_in_progress", False),
            },
            "discussions_summary": {
                "total": total_discussions,
                "unresolved": len(unresolved_discussions),
                "resolved": total_discussions - len(unresolved_discussions),
                "unresolved_threads": unresolved_discussions,
            },
            "changes_summary": {"total_files_changed": len(changed_files), "changed_files": changed_files},
            "commits_summary": {
                "total_commits": len(commits),
                "commits": [
                    {
                        "id": c.get("id"),
                        "short_id": c.get("short_id"),
                        "title": c.get("title"),
                        "message": c.get("message"),
                        "author_name": c.get("author_name"),
                        "created_at": c.get("created_at"),
                    }
                    for c in commits
                ],
            },
            "pipeline_summary": {
                "latest_pipeline": {
                    "id": latest_pipeline["id"],
                    "status": latest_pipeline["status"],
                    "ref": latest_pipeline["ref"],
                    "web_url": latest_pipeline.get("web_url"),
                }
                if latest_pipeline
                else None
            },
            "approvals_summary": approvals if approvals else {"note": "Approvals not available or not configured"},
        }
    except Exception as e:
        return {"error": f"Failed to fetch complete MR data: {str(e)}"}


@mcp.resource("gitlab://projects/{project_id}/merge-requests/{mr_iid}/discussions")
async def project_merge_request_discussions(ctx: Context, project_id: str, mr_iid: str) -> dict[str, Any]:
    """Get discussions for a specific merge request (supports project_id="current" and mr_iid="current")"""
    resolved_project_id, _ = await resolve_project_id(ctx, project_id)
    if not resolved_project_id:
        return create_repo_not_found_error(gitlab_client.base_url)

    resolved_mr_iid = await resolve_mr_iid(ctx, resolved_project_id, mr_iid)
    if not resolved_mr_iid:
        return {"error": f"Could not resolve MR IID '{mr_iid}'"}

    discussions = gitlab_client.get_mr_discussions(resolved_project_id, resolved_mr_iid)

    total_discussions = len(discussions)
    unresolved_discussions = [d for d in discussions if not d.get("notes", [{}])[0].get("resolved", False)]

    return {
        "summary": {
            "total_discussions": total_discussions,
            "unresolved_count": len(unresolved_discussions),
            "resolved_count": total_discussions - len(unresolved_discussions),
        },
        "discussions": discussions,
        "unresolved_discussions": unresolved_discussions,
    }


@mcp.resource("gitlab://projects/{project_id}/merge-requests/{mr_iid}/changes")
async def project_merge_request_changes(ctx: Context, project_id: str, mr_iid: str) -> dict[str, Any]:
    """Get code changes/diff for a specific merge request (supports project_id="current" and mr_iid="current")"""
    resolved_project_id, _ = await resolve_project_id(ctx, project_id)
    if not resolved_project_id:
        return create_repo_not_found_error(gitlab_client.base_url)

    resolved_mr_iid = await resolve_mr_iid(ctx, resolved_project_id, mr_iid)
    if not resolved_mr_iid:
        return {"error": f"Could not resolve MR IID '{mr_iid}'"}

    return gitlab_client.get_mr_changes(resolved_project_id, resolved_mr_iid)


@mcp.resource("gitlab://projects/{project_id}/merge-requests/{mr_iid}/commits")
async def project_merge_request_commits(ctx: Context, project_id: str, mr_iid: str) -> dict[str, Any]:
    """Get commits for a specific merge request (supports project_id="current" and mr_iid="current")"""
    resolved_project_id, _ = await resolve_project_id(ctx, project_id)
    if not resolved_project_id:
        return create_repo_not_found_error(gitlab_client.base_url)

    resolved_mr_iid = await resolve_mr_iid(ctx, resolved_project_id, mr_iid)
    if not resolved_mr_iid:
        return {"error": f"Could not resolve MR IID '{mr_iid}'"}

    commits = gitlab_client.get_mr_commits(resolved_project_id, resolved_mr_iid)
    return {
        "total_commits": len(commits),
        "commits": commits,
    }


@mcp.resource("gitlab://projects/{project_id}/merge-requests/{mr_iid}/approvals")
async def project_merge_request_approvals(ctx: Context, project_id: str, mr_iid: str) -> dict[str, Any]:
    """Get approval status for a specific merge request (supports project_id="current" and mr_iid="current")"""
    resolved_project_id, _ = await resolve_project_id(ctx, project_id)
    if not resolved_project_id:
        return create_repo_not_found_error(gitlab_client.base_url)

    resolved_mr_iid = await resolve_mr_iid(ctx, resolved_project_id, mr_iid)
    if not resolved_mr_iid:
        return {"error": f"Could not resolve MR IID '{mr_iid}'"}

    try:
        return gitlab_client.get_mr_approvals(resolved_project_id, resolved_mr_iid)
    except Exception as e:
        return {"error": f"Failed to fetch approvals: {str(e)}", "note": "Approvals may not be available in this GitLab edition"}


@mcp.resource("gitlab://projects/{project_id}/merge-requests/{mr_iid}/pipeline-jobs")
async def project_merge_request_pipeline_jobs(ctx: Context, project_id: str, mr_iid: str) -> dict[str, Any]:
    """Get jobs for the latest pipeline of a merge request (supports project_id="current" and mr_iid="current")"""
    resolved_project_id, _ = await resolve_project_id(ctx, project_id)
    if not resolved_project_id:
        return create_repo_not_found_error(gitlab_client.base_url)

    resolved_mr_iid = await resolve_mr_iid(ctx, resolved_project_id, mr_iid)
    if not resolved_mr_iid:
        return {"error": f"Could not resolve MR IID '{mr_iid}'"}

    # Get pipelines for this MR
    pipelines = gitlab_client.get_mr_pipelines(resolved_project_id, resolved_mr_iid)
    if not pipelines:
        return {"error": "No pipelines found for this merge request"}

    latest_pipeline = pipelines[0]
    jobs = gitlab_client.get_pipeline_jobs(resolved_project_id, latest_pipeline["id"])

    return {
        "pipeline": {
            "id": latest_pipeline["id"],
            "status": latest_pipeline["status"],
            "ref": latest_pipeline["ref"],
            "web_url": latest_pipeline.get("web_url"),
            "created_at": latest_pipeline.get("created_at"),
        },
        "jobs": jobs,
        "summary": {
            "total_jobs": len(jobs),
            "failed_jobs": len([j for j in jobs if j.get("status") == "failed"]),
            "successful_jobs": len([j for j in jobs if j.get("status") == "success"]),
        },
    }


@mcp.resource("gitlab://projects/{project_id}/pipelines/")
async def project_pipelines(ctx: Context, project_id: str) -> list[dict[str, Any]] | dict[str, Any]:
    """Get pipelines for a project (supports project_id="current")"""
    resolved_id, _ = await resolve_project_id(ctx, project_id)
    if not resolved_id:
        return create_repo_not_found_error(gitlab_client.base_url)
    return gitlab_client.get_pipelines(resolved_id)


@mcp.resource("gitlab://projects/{project_id}/pipelines/{pipeline_id}")
async def project_pipeline(ctx: Context, project_id: str, pipeline_id: str) -> dict[str, Any]:
    """Get specific pipeline (supports project_id="current")"""
    resolved_id, _ = await resolve_project_id(ctx, project_id)
    if not resolved_id:
        return create_repo_not_found_error(gitlab_client.base_url)
    return gitlab_client.get_pipeline(resolved_id, int(pipeline_id))


@mcp.resource("gitlab://projects/{project_id}/pipelines/{pipeline_id}/jobs")
async def project_pipeline_jobs(ctx: Context, project_id: str, pipeline_id: str) -> dict[str, Any]:
    """Get jobs for a specific pipeline (supports project_id="current")"""
    resolved_id, _ = await resolve_project_id(ctx, project_id)
    if not resolved_id:
        return create_repo_not_found_error(gitlab_client.base_url)
    jobs = gitlab_client.get_pipeline_jobs(resolved_id, int(pipeline_id))
    return {
        "pipeline_id": int(pipeline_id),
        "jobs": jobs,
        "summary": {
            "total_jobs": len(jobs),
            "failed_jobs": len([j for j in jobs if j.get("status") == "failed"]),
            "successful_jobs": len([j for j in jobs if j.get("status") == "success"]),
        },
    }


@mcp.resource("gitlab://projects/{project_id}/jobs/{job_id}/log")
async def project_job_log(ctx: Context, project_id: str, job_id: str) -> str | dict[str, Any]:
    """Get log for a specific job (supports project_id="current")

    Returns the raw log text for the job.
    """
    resolved_id, _ = await resolve_project_id(ctx, project_id)
    if not resolved_id:
        return create_repo_not_found_error(gitlab_client.base_url)
    return gitlab_client.get_job_log(resolved_id, int(job_id))


# Tools
@mcp.tool()
async def comment_on_merge_request(ctx: Context, project_id: str, mr_iid: str | int, comment: str) -> dict[str, Any]:
    """Leave a comment on a specific merge request by project and MR IID

    Args:
        project_id: Project ID, path, or "current" (e.g., "mygroup/myproject", "123", or "current")
        mr_iid: Merge request IID or "current" (the !number, or "current" for current branch MR)
        comment: Comment text to post (supports Markdown formatting)

    Returns:
        Result of comment operation with created note details

    Raises:
        Error if comment creation fails
    """
    resolved_project_id, _ = await resolve_project_id(ctx, project_id)
    if not resolved_project_id:
        return {"success": False, "error": f"Could not resolve project '{project_id}'"}

    resolved_mr_iid = await resolve_mr_iid(ctx, resolved_project_id, str(mr_iid))
    if not resolved_mr_iid:
        return {"success": False, "error": f"Could not resolve MR IID '{mr_iid}'"}

    try:
        note = gitlab_client.create_mr_note(
            project_id=resolved_project_id,
            mr_iid=resolved_mr_iid,
            body=comment,
        )

        return {
            "success": True,
            "message": f"Successfully posted comment on MR !{resolved_mr_iid} in project {project_id}",
            "note": note,
            "project_id": project_id,
            "mr_iid": resolved_mr_iid,
        }
    except httpx.HTTPStatusError as e:
        error_msg = e.response.text if e.response.text else str(e)
        return {
            "success": False,
            "error": f"Failed to comment on MR !{resolved_mr_iid} in project {project_id}: {error_msg}",
            "status_code": e.response.status_code,
            "project_id": project_id,
            "mr_iid": resolved_mr_iid,
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Unexpected error while commenting on MR !{resolved_mr_iid} in project {project_id}: {str(e)}",
            "project_id": project_id,
            "mr_iid": resolved_mr_iid,
        }


@mcp.tool()
async def merge_merge_request(
    ctx: Context,
    project_id: str,
    mr_iid: str | int,
    merge_commit_message: str | None = None,
    squash_commit_message: str | None = None,
    should_remove_source_branch: bool = True,
    merge_when_pipeline_succeeds: bool = False,
    squash: bool | None = None,
) -> dict[str, Any]:
    """Merge a specific merge request by project and MR IID

    Args:
        project_id: Project ID, path, or "current" (e.g., "mygroup/myproject", "123", or "current")
        mr_iid: Merge request IID or "current" (the !number, or "current" for current branch MR)
        merge_commit_message: Custom merge commit message (optional)
        squash_commit_message: Custom squash commit message (optional, used if squashing)
        should_remove_source_branch: Remove source branch after merge (default: True)
        merge_when_pipeline_succeeds: Wait for pipeline to succeed before merging (default: False)
        squash: Squash commits on merge (None = use project/MR settings, True = squash, False = don't squash)

    Returns:
        Result of merge operation with merged MR details

    Raises:
        Error if merge fails (not mergeable, conflicts, not approved, etc.)
    """
    resolved_project_id, _ = await resolve_project_id(ctx, project_id)
    if not resolved_project_id:
        return {"success": False, "error": f"Could not resolve project '{project_id}'"}

    resolved_mr_iid = await resolve_mr_iid(ctx, resolved_project_id, str(mr_iid))
    if not resolved_mr_iid:
        return {"success": False, "error": f"Could not resolve MR IID '{mr_iid}'"}

    # Get MR details to check status
    try:
        mr = gitlab_client.get_merge_request(resolved_project_id, resolved_mr_iid)
        merge_status = mr.get("merge_status")
        detailed_merge_status = mr.get("detailed_merge_status")
        has_conflicts = mr.get("has_conflicts", False)

        # Get pipeline status
        try:
            pipelines = gitlab_client.get_mr_pipelines(resolved_project_id, resolved_mr_iid)
            latest_pipeline = pipelines[0] if pipelines else None
            pipeline_status = latest_pipeline.get("status") if latest_pipeline else None
        except Exception:
            pipeline_status = None
    except Exception:
        # If we can't get MR details, proceed with merge attempt
        mr = None
        merge_status = None
        detailed_merge_status = None
        has_conflicts = False
        pipeline_status = None

    try:
        result = gitlab_client.merge_mr(
            project_id=resolved_project_id,
            mr_iid=resolved_mr_iid,
            merge_commit_message=merge_commit_message,
            squash_commit_message=squash_commit_message,
            should_remove_source_branch=should_remove_source_branch,
            merge_when_pipeline_succeeds=merge_when_pipeline_succeeds,
            squash=squash,
        )

        return {
            "success": True,
            "message": f"Successfully merged MR !{resolved_mr_iid} in project {project_id}",
            "merged_mr": result,
            "branch_removed": should_remove_source_branch,
        }
    except httpx.HTTPStatusError as e:
        import json

        # Parse GitLab error response
        try:
            error_json = json.loads(e.response.text)
            error_message = error_json.get("message", "Unknown error")
        except (json.JSONDecodeError, AttributeError):
            error_message = e.response.text if e.response.text else str(e)

        # Build helpful error message with context
        helpful_message = f"Failed to merge MR !{resolved_mr_iid} in project {project_id}: {error_message}"
        suggestions = []

        # Add context-specific suggestions
        if e.response.status_code == 405 or e.response.status_code == 406:
            # Method Not Allowed or Not Acceptable - usually means merge is blocked
            if pipeline_status == "running":
                helpful_message = f"Cannot merge MR !{resolved_mr_iid}: Pipeline is still running (status: {pipeline_status})"
                suggestions.append(
                    "Wait for the pipeline to complete, or use merge_when_pipeline_succeeds=True to queue the merge"
                )
            elif pipeline_status == "failed":
                helpful_message = f"Cannot merge MR !{resolved_mr_iid}: Pipeline failed (status: {pipeline_status})"
                suggestions.append("Fix the pipeline failures before merging")
            elif has_conflicts:
                helpful_message = f"Cannot merge MR !{resolved_mr_iid}: MR has merge conflicts"
                suggestions.append("Resolve merge conflicts before merging")
            elif merge_status == "cannot_be_merged":
                helpful_message = f"Cannot merge MR !{resolved_mr_iid}: Merge status is 'cannot_be_merged'"
                if detailed_merge_status:
                    helpful_message += f" (detailed status: {detailed_merge_status})"
                suggestions.append("Check the MR in GitLab UI for blocking conditions (approvals, conflicts, etc.)")
            else:
                suggestions.append("Check the MR status in GitLab UI for blocking conditions")
                if merge_status:
                    suggestions.append(f"Current merge_status: {merge_status}")
                if detailed_merge_status:
                    suggestions.append(f"Detailed status: {detailed_merge_status}")

        response = {
            "success": False,
            "error": helpful_message,
            "suggestions": suggestions,
            "status_code": e.response.status_code,
            "project_id": project_id,
            "mr_iid": resolved_mr_iid,
        }

        if mr:
            response["merge_request"] = {
                "iid": mr["iid"],
                "title": mr.get("title"),
                "web_url": mr.get("web_url"),
                "merge_status": merge_status,
                "detailed_merge_status": detailed_merge_status,
                "has_conflicts": has_conflicts,
                "pipeline_status": pipeline_status,
            }

        return response
    except Exception as e:
        return {
            "success": False,
            "error": f"Unexpected error while merging MR !{resolved_mr_iid} in project {project_id}: {str(e)}",
            "project_id": project_id,
            "mr_iid": resolved_mr_iid,
        }


@mcp.tool()
async def set_project_ci_variable(
    ctx: Context,
    project_id: str,
    key: str,
    value: str,
    variable_type: str = "env_var",
    protected: bool = False,
    masked: bool = False,
    raw: bool = False,
    environment_scope: str = "*",
    description: str | None = None,
) -> dict[str, Any]:
    """Set a CI/CD variable in a specific project (upsert: creates if new, updates if exists)

    Args:
        project_id: Project ID, path, or "current" (e.g., "mygroup/myproject", "123", or "current")
        key: Variable key/name (e.g., "API_KEY", "DATABASE_URL")
        value: Variable value
        variable_type: Type of variable - "env_var" (default) or "file"
        protected: Only available in protected branches (default: False)
        masked: Hidden in job logs (default: False)
        raw: Disable variable reference expansion (default: False)
        environment_scope: Environment scope - "*" for all (default), or specific like "production", "staging"
        description: Optional description of the variable

    Returns:
        Result with success status, action taken (created/updated), and variable details

    Raises:
        Error if variable operation fails
    """
    resolved_id, _ = await resolve_project_id(ctx, project_id)
    if not resolved_id:
        return {"success": False, "error": f"Could not resolve project '{project_id}'"}

    try:
        variable, action = gitlab_client.set_project_variable(
            project_id=resolved_id,
            key=key,
            value=value,
            variable_type=variable_type,
            protected=protected,
            masked=masked,
            raw=raw,
            environment_scope=environment_scope,
            description=description,
        )

        return {
            "success": True,
            "action": action,
            "message": f"Successfully {action} CI/CD variable '{key}' in project {project_id}",
            "variable": {
                "key": variable.get("key"),
                "variable_type": variable.get("variable_type"),
                "protected": variable.get("protected"),
                "masked": variable.get("masked"),
                "raw": variable.get("raw"),
                "environment_scope": variable.get("environment_scope"),
                "description": variable.get("description"),
            },
            "project_id": project_id,
        }
    except httpx.HTTPStatusError as e:
        error_msg = e.response.text if e.response.text else str(e)
        return {
            "success": False,
            "error": f"Failed to set CI/CD variable '{key}' in project {project_id}: {error_msg}",
            "status_code": e.response.status_code,
            "project_id": project_id,
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Unexpected error while setting CI/CD variable '{key}' in project {project_id}: {str(e)}",
            "project_id": project_id,
        }


if __name__ == "__main__":
    mcp.run()
