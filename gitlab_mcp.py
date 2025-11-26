import asyncio
import logging
import os
import re
import time
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

    def get_pipelines(
        self,
        project_id: str,
        ref: str | None = None,
        per_page: int = 3,
        max_pages: int = 1,
    ) -> list[dict[str, Any]]:
        """Get pipelines for a project.

        Args:
            project_id: Project ID or path
            ref: Optional branch/tag to filter by
            per_page: Number of pipelines per page (default: 3)
            max_pages: Maximum number of pages to fetch (default: 1)

        Returns:
            List of pipeline objects (default: 3 most recent)
        """
        encoded_id = self._encode_project_id(project_id)
        params = {"ref": ref} if ref else {}
        return self.get_paginated(f"/projects/{encoded_id}/pipelines", params=params, per_page=per_page, max_pages=max_pages)

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

    def get_job(self, project_id: str, job_id: int) -> dict[str, Any]:
        """Get job details including artifact metadata

        Args:
            project_id: Project ID or path
            job_id: Job ID

        Returns:
            Job details dictionary including artifacts array

        Raises:
            httpx.HTTPStatusError: If job not found or access denied
        """
        encoded_id = self._encode_project_id(project_id)
        try:
            logger.debug(f"GET /projects/{encoded_id}/jobs/{job_id}")
            response = self.client.get(f"/projects/{encoded_id}/jobs/{job_id}")
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"GitLab API error for GET job {job_id}: {e.response.status_code}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Network error for GET job {job_id}: {e}")
            raise
        except Exception as e:
            logger.exception(f"Unexpected error for GET job {job_id}: {e}")
            raise

    def get_job_artifact(self, project_id: str, job_id: int, artifact_path: str) -> bytes:
        """Download a specific artifact file from a job

        Args:
            project_id: Project ID or path
            job_id: Job ID
            artifact_path: Path to the artifact file within the job's artifact archive

        Returns:
            Raw bytes of the artifact file

        Raises:
            httpx.HTTPStatusError: If artifact not found or access denied
        """
        encoded_id = self._encode_project_id(project_id)
        try:
            logger.debug(f"GET /projects/{encoded_id}/jobs/{job_id}/artifacts/{artifact_path}")
            response = self.client.get(f"/projects/{encoded_id}/jobs/{job_id}/artifacts/{artifact_path}")
            response.raise_for_status()
            # Return raw bytes for artifact content
            return response.content
        except httpx.HTTPStatusError as e:
            logger.error(
                f"GitLab API error for GET job {job_id} artifact {artifact_path}: {e.response.status_code}"
            )
            raise
        except httpx.RequestError as e:
            logger.error(f"Network error for GET job {job_id} artifact {artifact_path}: {e}")
            raise
        except Exception as e:
            logger.exception(f"Unexpected error for GET job {job_id} artifact {artifact_path}: {e}")
            raise

    def enrich_jobs_with_failure_logs(self, project_id: str, jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Enrich failed jobs with last 10 lines of their logs

        Args:
            project_id: Project ID or path
            jobs: List of job objects

        Returns:
            Jobs list with failure_log_tail added to failed jobs
        """
        enriched_jobs = []
        for job in jobs:
            job_copy = job.copy()
            if job.get("status") == "failed":
                try:
                    full_log = self.get_job_log(project_id, job["id"])
                    log_lines = full_log.split("\n")
                    # Get last 10 non-empty lines
                    last_lines = [line for line in log_lines if line.strip()][-10:]
                    job_copy["failure_log_tail"] = "\n".join(last_lines)
                    job_copy["log_note"] = f"Showing last 10 lines. Full log: gitlab://projects/{project_id}/jobs/{job['id']}/log"
                except Exception as e:
                    logger.warning(f"Failed to fetch log for job {job['id']}: {e}")
                    job_copy["log_note"] = f"Failed to fetch log. Full log: gitlab://projects/{project_id}/jobs/{job['id']}/log"
            enriched_jobs.append(job_copy)
        return enriched_jobs

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

    def get_releases(self, project_id: str, order_by: str = "released_at", sort: str = "desc") -> list[dict[str, Any]]:
        """Get all releases for a project

        Args:
            project_id: Project ID or path
            order_by: Order by "released_at" or "created_at" (default: "released_at")
            sort: Sort direction "asc" or "desc" (default: "desc")

        Returns:
            List of releases

        Raises:
            httpx.HTTPStatusError: If API request fails
        """
        encoded_id = self._encode_project_id(project_id)
        params = {"order_by": order_by, "sort": sort}
        return self.get_paginated(f"/projects/{encoded_id}/releases", params=params)

    def get_release(self, project_id: str, tag_name: str) -> dict[str, Any]:
        """Get a specific release by tag name

        Args:
            project_id: Project ID or path
            tag_name: Tag name of the release

        Returns:
            Release data

        Raises:
            httpx.HTTPStatusError: If release not found or API request fails
        """
        encoded_id = self._encode_project_id(project_id)
        # Tag name needs to be URL encoded
        from urllib.parse import quote

        encoded_tag = quote(tag_name, safe="")
        return self.get(f"/projects/{encoded_id}/releases/{encoded_tag}")

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

    def reply_to_discussion(
        self, project_id: str, mr_iid: int, discussion_id: str, body: str
    ) -> dict[str, Any]:
        """Reply to an existing discussion thread on a merge request

        Args:
            project_id: Project ID or path
            mr_iid: Merge request IID
            discussion_id: Discussion thread ID
            body: Reply text (supports Markdown)

        Returns:
            Created note data

        Raises:
            httpx.HTTPStatusError: If reply creation fails
        """
        encoded_id = self._encode_project_id(project_id)

        data = {"body": body}

        try:
            logger.info(f"Replying to discussion {discussion_id} on MR !{mr_iid} in project {project_id}")
            response = self.client.post(
                f"/projects/{encoded_id}/merge_requests/{mr_iid}/discussions/{discussion_id}/notes",
                json=data,
            )
            response.raise_for_status()
            logger.info(f"Successfully replied to discussion {discussion_id} on MR !{mr_iid}")
            return response.json()
        except httpx.HTTPStatusError as e:
            error_detail = e.response.text[:500] if e.response.text else "No error details"
            logger.error(
                f"Failed to reply to discussion {discussion_id} on MR !{mr_iid}: {e.response.status_code} - {error_detail}"
            )
            raise
        except httpx.RequestError as e:
            logger.error(f"Network error while replying to discussion {discussion_id} on MR !{mr_iid}: {e}")
            raise
        except Exception as e:
            logger.exception(f"Unexpected error while replying to discussion {discussion_id} on MR !{mr_iid}: {e}")
            raise

    def resolve_discussion(
        self, project_id: str, mr_iid: int, discussion_id: str, resolved: bool
    ) -> dict[str, Any]:
        """Resolve or unresolve a discussion thread on a merge request

        Args:
            project_id: Project ID or path
            mr_iid: Merge request IID
            discussion_id: Discussion thread ID
            resolved: True to resolve, False to unresolve

        Returns:
            Updated discussion data

        Raises:
            httpx.HTTPStatusError: If resolve/unresolve fails
        """
        encoded_id = self._encode_project_id(project_id)

        data = {"resolved": resolved}

        try:
            action = "Resolving" if resolved else "Unresolving"
            logger.info(f"{action} discussion {discussion_id} on MR !{mr_iid} in project {project_id}")
            response = self.client.put(
                f"/projects/{encoded_id}/merge_requests/{mr_iid}/discussions/{discussion_id}",
                json=data,
            )
            response.raise_for_status()
            action_past = "resolved" if resolved else "unresolved"
            logger.info(f"Successfully {action_past} discussion {discussion_id} on MR !{mr_iid}")
            return response.json()
        except httpx.HTTPStatusError as e:
            error_detail = e.response.text[:500] if e.response.text else "No error details"
            logger.error(
                f"Failed to resolve discussion {discussion_id} on MR !{mr_iid}: {e.response.status_code} - {error_detail}"
            )
            raise
        except httpx.RequestError as e:
            logger.error(f"Network error while resolving discussion {discussion_id} on MR !{mr_iid}: {e}")
            raise
        except Exception as e:
            logger.exception(f"Unexpected error while resolving discussion {discussion_id} on MR !{mr_iid}: {e}")
            raise

    def create_merge_request(
        self,
        project_id: str,
        source_branch: str,
        target_branch: str,
        title: str,
        description: str | None = None,
        assignee_ids: list[int] | None = None,
        reviewer_ids: list[int] | None = None,
        labels: str | None = None,
        remove_source_branch: bool = True,
        squash: bool | None = None,
        allow_collaboration: bool = False,
    ) -> dict[str, Any]:
        """Create a new merge request

        Args:
            project_id: Project ID or path
            source_branch: Source branch name
            target_branch: Target branch name
            title: MR title
            description: MR description/body (optional, supports Markdown)
            assignee_ids: List of user IDs to assign (optional)
            reviewer_ids: List of user IDs to review (optional)
            labels: Comma-separated label names (optional)
            remove_source_branch: Remove source branch after merge (default: True)
            squash: Squash commits on merge (default: None - use project settings)
            allow_collaboration: Allow commits from members with merge access (default: False)

        Returns:
            Created MR data

        Raises:
            httpx.HTTPStatusError: If MR creation fails
        """
        encoded_id = self._encode_project_id(project_id)

        data: dict[str, Any] = {
            "source_branch": source_branch,
            "target_branch": target_branch,
            "title": title,
            "remove_source_branch": remove_source_branch,
            "allow_collaboration": allow_collaboration,
        }

        if description is not None:
            data["description"] = description
        if assignee_ids is not None:
            data["assignee_ids"] = assignee_ids
        if reviewer_ids is not None:
            data["reviewer_ids"] = reviewer_ids
        if labels is not None:
            data["labels"] = labels
        if squash is not None:
            data["squash"] = squash

        try:
            logger.info(f"Creating MR from {source_branch} to {target_branch} in project {project_id}")
            response = self.client.post(
                f"/projects/{encoded_id}/merge_requests",
                json=data,
            )
            response.raise_for_status()
            logger.info(f"Successfully created MR !{response.json().get('iid')} in project {project_id}")
            return response.json()
        except httpx.HTTPStatusError as e:
            error_detail = e.response.text[:500] if e.response.text else "No error details"
            logger.error(f"Failed to create MR in project {project_id}: {e.response.status_code} - {error_detail}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Network error while creating MR in project {project_id}: {e}")
            raise
        except Exception as e:
            logger.exception(f"Unexpected error while creating MR in project {project_id}: {e}")
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

    def close_mr(self, project_id: str, mr_iid: int) -> dict[str, Any]:
        """Close a merge request

        Args:
            project_id: Project ID or path
            mr_iid: Merge request IID

        Returns:
            Closed MR data

        Raises:
            httpx.HTTPStatusError: If close operation fails
        """
        encoded_id = self._encode_project_id(project_id)

        data: dict[str, Any] = {"state_event": "close"}

        try:
            logger.info(f"Closing MR !{mr_iid} in project {project_id}")
            response = self.client.put(
                f"/projects/{encoded_id}/merge_requests/{mr_iid}",
                json=data,
            )
            response.raise_for_status()
            logger.info(f"Successfully closed MR !{mr_iid}")
            return response.json()
        except httpx.HTTPStatusError as e:
            error_detail = e.response.text[:500] if e.response.text else "No error details"
            logger.error(
                f"Failed to close MR !{mr_iid}: {e.response.status_code} - {error_detail}"
            )
            raise
        except httpx.RequestError as e:
            logger.error(f"Network error while closing MR !{mr_iid}: {e}")
            raise
        except Exception as e:
            logger.exception(f"Unexpected error while closing MR !{mr_iid}: {e}")
            raise

    def update_mr(
        self,
        project_id: str,
        mr_iid: int,
        title: str | None = None,
        description: str | None = None,
        target_branch: str | None = None,
        state_event: str | None = None,
        assignee_ids: list[int] | None = None,
        reviewer_ids: list[int] | None = None,
        labels: str | None = None,
    ) -> dict[str, Any]:
        """Update a merge request

        Args:
            project_id: Project ID or path
            mr_iid: Merge request IID
            title: New title (optional)
            description: New description (optional)
            target_branch: New target branch (optional)
            state_event: State change event - "open", "close", "reopen" (optional)
            assignee_ids: List of assignee IDs (optional)
            reviewer_ids: List of reviewer IDs (optional)
            labels: Comma-separated labels (optional)

        Returns:
            Updated MR data

        Raises:
            httpx.HTTPStatusError: If update fails
        """
        encoded_id = self._encode_project_id(project_id)

        data: dict[str, Any] = {}

        if title is not None:
            data["title"] = title
        if description is not None:
            data["description"] = description
        if target_branch is not None:
            data["target_branch"] = target_branch
        if state_event is not None:
            data["state_event"] = state_event
        if assignee_ids is not None:
            data["assignee_ids"] = assignee_ids
        if reviewer_ids is not None:
            data["reviewer_ids"] = reviewer_ids
        if labels is not None:
            data["labels"] = labels

        try:
            logger.info(f"Updating MR !{mr_iid} in project {project_id} with {len(data)} field(s)")
            response = self.client.put(
                f"/projects/{encoded_id}/merge_requests/{mr_iid}",
                json=data,
            )
            response.raise_for_status()
            logger.info(f"Successfully updated MR !{mr_iid}")
            return response.json()
        except httpx.HTTPStatusError as e:
            error_detail = e.response.text[:500] if e.response.text else "No error details"
            logger.error(
                f"Failed to update MR !{mr_iid}: {e.response.status_code} - {error_detail}"
            )
            raise
        except httpx.RequestError as e:
            logger.error(f"Network error while updating MR !{mr_iid}: {e}")
            raise
        except Exception as e:
            logger.exception(f"Unexpected error while updating MR !{mr_iid}: {e}")
            raise

    def wait_for_pipeline(
        self,
        project_id: str,
        pipeline_id: int,
        timeout_seconds: int = 3600,
        check_interval: int = 10,
        include_failed_logs: bool = True,
    ) -> dict[str, Any]:
        """Wait for a pipeline to complete (success or failure)

        Args:
            project_id: Project ID or path
            pipeline_id: Pipeline ID to wait for
            timeout_seconds: Maximum time to wait in seconds (default: 3600/1 hour)
            check_interval: How often to check status in seconds (default: 10)
            include_failed_logs: Include last 10 lines of failed job logs (default: True)

        Returns:
            Dict with status, duration, job summary, and optionally failed job logs

        Raises:
            httpx.HTTPStatusError: If API calls fail
        """
        encoded_id = self._encode_project_id(project_id)
        start_time = time.time()
        checks = 0

        logger.info(
            f"Waiting for pipeline {pipeline_id} in project {project_id} "
            f"(timeout: {timeout_seconds}s, interval: {check_interval}s)"
        )

        final_status = None
        pipeline = None

        try:
            while True:
                checks += 1
                elapsed = time.time() - start_time

                # Get current pipeline status
                pipeline = self.get_pipeline(project_id, pipeline_id)
                status = pipeline.get("status")

                logger.debug(
                    f"Check #{checks}: Pipeline {pipeline_id} status = {status} "
                    f"(elapsed: {elapsed:.1f}s)"
                )

                # Check if pipeline has completed
                if status in ["success", "failed", "canceled", "skipped"]:
                    final_status = status
                    logger.info(
                        f"Pipeline {pipeline_id} completed with status '{status}' "
                        f"after {elapsed:.1f}s ({checks} checks)"
                    )
                    break

                # Check timeout
                if elapsed > timeout_seconds:
                    final_status = "timeout"
                    logger.warning(
                        f"Pipeline {pipeline_id} timed out after {elapsed:.1f}s "
                        f"(status was '{status}')"
                    )
                    break

                # Wait before next check
                time.sleep(check_interval)

        except httpx.HTTPStatusError as e:
            error_detail = e.response.text[:500] if e.response.text else "No error details"
            logger.error(
                f"Failed to check pipeline {pipeline_id}: {e.response.status_code} - {error_detail}"
            )
            raise
        except Exception as e:
            logger.exception(f"Unexpected error while waiting for pipeline {pipeline_id}: {e}")
            raise

        # Build response
        total_duration = time.time() - start_time
        result: dict[str, Any] = {
            "final_status": final_status,
            "pipeline_id": pipeline_id,
            "pipeline_url": pipeline.get("web_url") if pipeline else None,
            "total_duration": round(total_duration, 2),
            "checks_performed": checks,
        }

        # Get job summary if pipeline completed
        if pipeline and final_status != "timeout":
            try:
                jobs = self.get_pipeline_jobs(project_id, pipeline_id)
                job_summary = {
                    "total": len(jobs),
                    "success": len([j for j in jobs if j.get("status") == "success"]),
                    "failed": len([j for j in jobs if j.get("status") == "failed"]),
                }
                result["job_summary"] = job_summary

                # Include failed job logs if requested
                if include_failed_logs and final_status == "failed":
                    failed_jobs = [j for j in jobs if j.get("status") == "failed"]
                    failed_job_details = []

                    for job in failed_jobs[:5]:  # Limit to first 5 failed jobs
                        job_detail = {
                            "id": job.get("id"),
                            "name": job.get("name"),
                            "status": job.get("status"),
                            "web_url": job.get("web_url"),
                        }

                        # Try to fetch last 10 lines of log
                        try:
                            log = self.get_job_log(project_id, job["id"])
                            lines = log.strip().split("\n")
                            job_detail["last_log_lines"] = "\n".join(lines[-10:])
                        except Exception as log_error:
                            logger.warning(
                                f"Could not fetch log for job {job['id']}: {log_error}"
                            )
                            job_detail["last_log_lines"] = "(log unavailable)"

                        failed_job_details.append(job_detail)

                    result["failed_jobs"] = failed_job_details

            except Exception as job_error:
                logger.warning(f"Could not fetch job details: {job_error}")

        return result

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

    def _sanitize_variable(self, var: dict[str, Any]) -> dict[str, Any]:
        """Remove sensitive value field from variable data.

        Args:
            var: Variable data from GitLab API

        Returns:
            Variable metadata without the value field (for security)
        """
        return {
            "key": var.get("key"),
            "variable_type": var.get("variable_type"),
            "protected": var.get("protected"),
            "masked": var.get("masked"),
            "raw": var.get("raw"),
            "environment_scope": var.get("environment_scope"),
            "description": var.get("description"),
        }

    def list_project_variables(
        self,
        project_id: str,
        per_page: int = 100,
        max_pages: int = 100,
    ) -> list[dict[str, Any]]:
        """List all CI/CD variables for a project (values not included for security).

        Args:
            project_id: Project ID or path
            per_page: Results per page (default: 100)
            max_pages: Max pages to fetch (default: 100)

        Returns:
            List of variable metadata (without values)
        """
        encoded_id = self._encode_project_id(project_id)
        logger.debug(f"Listing CI/CD variables for project {project_id}")
        variables = self.get_paginated(
            f"/projects/{encoded_id}/variables",
            per_page=per_page,
            max_pages=max_pages,
        )
        # Sanitize: remove value field for security
        return [self._sanitize_variable(var) for var in variables]

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

    def create_release(
        self,
        project_id: str,
        tag_name: str,
        name: str | None = None,
        description: str | None = None,
        ref: str | None = None,
        milestones: list[str] | None = None,
        released_at: str | None = None,
        assets_links: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """Create a new release

        Args:
            project_id: Project ID or path
            tag_name: Tag name for the release (required)
            name: Release title (optional, defaults to tag_name)
            description: Release description/notes (optional, supports Markdown)
            ref: Commit SHA, branch, or existing tag (required only if tag_name doesn't exist yet)
            milestones: List of milestone titles to associate (optional)
            released_at: ISO 8601 datetime for release (optional, defaults to current time)
            assets_links: List of asset link dicts with 'name', 'url', and optional 'direct_asset_path' (optional)

        Returns:
            Created release data

        Raises:
            httpx.HTTPStatusError: If release creation fails
        """
        encoded_id = self._encode_project_id(project_id)

        data: dict[str, Any] = {"tag_name": tag_name}

        if name is not None:
            data["name"] = name
        if description is not None:
            data["description"] = description
        if ref is not None:
            data["ref"] = ref
        if milestones is not None:
            data["milestones"] = milestones
        if released_at is not None:
            data["released_at"] = released_at
        if assets_links is not None:
            data["assets"] = {"links": assets_links}

        try:
            logger.info(f"Creating release '{tag_name}' in project {project_id}")
            response = self.client.post(
                f"/projects/{encoded_id}/releases",
                json=data,
            )
            response.raise_for_status()
            logger.info(f"Successfully created release '{tag_name}' in project {project_id}")
            return response.json()
        except httpx.HTTPStatusError as e:
            error_detail = e.response.text[:500] if e.response.text else "No error details"
            logger.error(f"Failed to create release '{tag_name}' in project {project_id}: {e.response.status_code} - {error_detail}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Network error while creating release '{tag_name}' in project {project_id}: {e}")
            raise
        except Exception as e:
            logger.exception(f"Unexpected error while creating release '{tag_name}' in project {project_id}: {e}")
            raise

    def update_release(
        self,
        project_id: str,
        tag_name: str,
        name: str | None = None,
        description: str | None = None,
        milestones: list[str] | None = None,
        released_at: str | None = None,
    ) -> dict[str, Any]:
        """Update an existing release

        Args:
            project_id: Project ID or path
            tag_name: Tag name of the release to update
            name: New release title (optional)
            description: New release description/notes (optional, supports Markdown)
            milestones: New list of milestone titles (optional)
            released_at: New release datetime in ISO 8601 format (optional)

        Returns:
            Updated release data

        Raises:
            httpx.HTTPStatusError: If release update fails
        """
        encoded_id = self._encode_project_id(project_id)

        # Tag name needs to be URL encoded
        from urllib.parse import quote

        encoded_tag = quote(tag_name, safe="")

        data: dict[str, Any] = {}

        if name is not None:
            data["name"] = name
        if description is not None:
            data["description"] = description
        if milestones is not None:
            data["milestones"] = milestones
        if released_at is not None:
            data["released_at"] = released_at

        try:
            logger.info(f"Updating release '{tag_name}' in project {project_id}")
            response = self.client.put(
                f"/projects/{encoded_id}/releases/{encoded_tag}",
                json=data,
            )
            response.raise_for_status()
            logger.info(f"Successfully updated release '{tag_name}' in project {project_id}")
            return response.json()
        except httpx.HTTPStatusError as e:
            error_detail = e.response.text[:500] if e.response.text else "No error details"
            logger.error(f"Failed to update release '{tag_name}' in project {project_id}: {e.response.status_code} - {error_detail}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Network error while updating release '{tag_name}' in project {project_id}: {e}")
            raise
        except Exception as e:
            logger.exception(f"Unexpected error while updating release '{tag_name}' in project {project_id}: {e}")
            raise

    def delete_release(self, project_id: str, tag_name: str) -> None:
        """Delete a release (note: does not delete the associated tag)

        Args:
            project_id: Project ID or path
            tag_name: Tag name of the release to delete

        Raises:
            httpx.HTTPStatusError: If release deletion fails
        """
        encoded_id = self._encode_project_id(project_id)

        # Tag name needs to be URL encoded
        from urllib.parse import quote

        encoded_tag = quote(tag_name, safe="")

        try:
            logger.info(f"Deleting release '{tag_name}' in project {project_id}")
            response = self.client.delete(f"/projects/{encoded_id}/releases/{encoded_tag}")
            response.raise_for_status()
            logger.info(f"Successfully deleted release '{tag_name}' in project {project_id} (tag preserved)")
        except httpx.HTTPStatusError as e:
            error_detail = e.response.text[:500] if e.response.text else "No error details"
            logger.error(f"Failed to delete release '{tag_name}' in project {project_id}: {e.response.status_code} - {error_detail}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Network error while deleting release '{tag_name}' in project {project_id}: {e}")
            raise
        except Exception as e:
            logger.exception(f"Unexpected error while deleting release '{tag_name}' in project {project_id}: {e}")
            raise


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

COMMON WORKFLOWS:

After Pushing Code - Monitor Pipeline:
  ✅ ALWAYS use wait_for_pipeline tool (PRIMARY METHOD):
    - wait_for_pipeline(project_id="current", mr_iid="current") - Wait for current MR's pipeline
    - wait_for_pipeline(project_id="current", pipeline_id=123) - Wait for specific pipeline
    - Automatically polls every 10s, returns final status with failed job logs
    - Token cost: 200-500 tokens

  ❌ DON'T manually poll with sleep + read pipelines resource in a loop

Quick Pipeline Status Check:
  ✅ Use pipelines resource (limited to 3 most recent):
    - gitlab://projects/current/pipelines/ - Last 3 pipelines
    - Token cost: 50-100 tokens
    - Good for: "What's my latest pipeline status?" or "Show recent pipelines"

Checking MR Merge Readiness:
  ✅ Use lightweight status resource:
    - gitlab://projects/current/merge-requests/current/status
    - Returns: pipeline status, discussions, approvals, ready_to_merge boolean
    - Token cost: 500-800 tokens (85-90% savings vs separate fetches)

WHEN TO USE WHAT:
  "Monitor pipeline after pushing code" → wait_for_pipeline tool
  "What's my latest pipeline status?" → gitlab://projects/current/pipelines/
  "Is my MR ready to merge?" → gitlab://projects/current/merge-requests/current/status
  "Why did pipeline fail?" → wait_for_pipeline (includes failed job logs) OR pipeline-jobs resource

RESOURCES - Access GitLab data:

Current Repo/Branch (use project_id="current" and mr_iid="current"):
- gitlab://projects/current/merge-requests/current/status - Lightweight merge readiness check (RECOMMENDED for "ready to merge?" - includes pipeline, discussions, approvals summary)
- gitlab://projects/current/merge-requests/current - Comprehensive MR overview (includes discussions, changes, commits, pipeline, approvals)
- gitlab://projects/current/merge-requests/current/discussions - Just discussions/comments
- gitlab://projects/current/merge-requests/current/changes - Just code diff
- gitlab://projects/current/merge-requests/current/commits - Just commits
- gitlab://projects/current/merge-requests/current/approvals - Just approval status
- gitlab://projects/current/merge-requests/current/pipeline-jobs - Just pipeline jobs
- gitlab://projects/current/merge-requests/ - All open MRs in current project
- gitlab://projects/current/pipelines/ - Last 3 pipelines for current project (⚡ 50-100 tokens; for monitoring, use wait_for_pipeline tool instead)
- gitlab://projects/current/pipelines/{pipeline_id} - Get specific pipeline details
- gitlab://projects/current/pipelines/{pipeline_id}/jobs - Get jobs for a specific pipeline
- gitlab://projects/current/jobs/{job_id}/log - Full job output/trace
- gitlab://projects/current/releases/ - All releases in current project
- gitlab://projects/current/releases/{tag_name} - Specific release by tag
- gitlab://projects/current/variables/ - List all CI/CD variables (metadata only, values not exposed for security)
- gitlab://projects/current/variables/{key} - Get specific CI/CD variable metadata
- gitlab://projects/current/jobs/{job_id}/artifacts - List all artifacts for a job
- gitlab://projects/current/jobs/{job_id}/artifacts/{artifact_path} - Read specific artifact file (supports ?lines=N&offset=M)

Specific Project/MR (use numeric ID or URL-encoded path):
- gitlab://projects/qodev%2Fhandbook/merge-requests/20 - Comprehensive MR overview
- gitlab://projects/123/merge-requests/20/discussions - Granular access to discussions only
- gitlab://projects/qodev%2Fhandbook/merge-requests/20/changes - Granular access to changes only
- gitlab://projects/qodev%2Fhandbook/releases/ - All releases in specific project
- gitlab://projects/123/releases/v1.0.0 - Specific release in specific project

TOOLS - Perform actions (all support "current"):
- create_release(project_id, tag_name, name, description, ref, ...) - Create a new release (supports project_id="current", auto-detects ref from current branch)
- create_merge_request(project_id, title, source_branch, target_branch, ...) - Create a new MR (supports project_id="current", auto-detects source_branch)
- comment_on_merge_request(project_id, mr_iid, comment) - Leave a comment (supports project_id="current", mr_iid="current")
- merge_merge_request(project_id, mr_iid, ...) - Merge an MR (supports project_id="current", mr_iid="current")
- close_merge_request(project_id, mr_iid) - Close an MR (supports project_id="current", mr_iid="current")
- update_merge_request(project_id, mr_iid, title, description, ...) - Update MR title, description, or other properties (supports project_id="current", mr_iid="current")
- wait_for_pipeline(project_id, pipeline_id=None, mr_iid=None, ...) - **PRIMARY METHOD for pipeline monitoring** - Wait for pipeline to complete after pushing code. Automatically polls and returns final status with failed job logs. DO NOT manually poll pipeline status in loops. (supports project_id="current", mr_iid="current")
- set_project_ci_variable(project_id, key, value, ...) - Set CI/CD variable (supports project_id="current")

Examples:
- "Is this MR ready to merge?" → gitlab://projects/current/merge-requests/current/status
- "What's blocking my MR?" → gitlab://projects/current/merge-requests/current/status
- "Check MR status" → gitlab://projects/{id}/merge-requests/{iid}/status
- "What's the status of my MR?" → gitlab://projects/current/merge-requests/current
- "Show me MR !20 in qodev/handbook" → gitlab://projects/qodev%2Fhandbook/merge-requests/20
- "Create MR for current branch" → create_merge_request("current", "Add new feature")
- "Create MR from feature to dev" → create_merge_request("current", "Bug fix", source_branch="feature", target_branch="dev")
- "Comment on my MR saying 'LGTM'" → comment_on_merge_request("current", "current", "LGTM")
- "Merge MR !20 in project qodev/handbook" → merge_merge_request("qodev/handbook", 20)
- "Close my MR" → close_merge_request("current", "current")
- "Close MR !20 in project qodev/handbook" → close_merge_request("qodev/handbook", 20)
- "Update my MR title" → update_merge_request("current", "current", title="New Title")
- "Update MR !20 description" → update_merge_request("qodev/handbook", 20, description="Updated description")
- "Update MR title and description" → update_merge_request("current", "current", title="New Title", description="New description")
- "Wait for current MR's pipeline" → wait_for_pipeline("current", mr_iid="current")
- "Wait for pipeline 12345" → wait_for_pipeline("current", pipeline_id=12345)
- "Wait for pipeline with 30min timeout" → wait_for_pipeline("current", pipeline_id=12345, timeout_seconds=1800)
- "What discussions are on my MR?" → gitlab://projects/current/merge-requests/current/discussions (token-efficient!)
- "Set API_KEY in current project" → set_project_ci_variable("current", "API_KEY", "secret123")
- "List all CI/CD variables" → gitlab://projects/current/variables/ (metadata only, values not exposed)
- "Check if DATABASE_URL variable exists" → gitlab://projects/current/variables/DATABASE_URL
- "What variables are protected?" → gitlab://projects/current/variables/
- "What releases exist?" → gitlab://projects/current/releases/
- "Show me release v1.0.0" → gitlab://projects/current/releases/v1.0.0
- "Create a release" → create_release("current", "v1.0.0", name="Version 1.0", description="Initial release")
- "Show job 12123 logs" → gitlab://projects/current/jobs/12123/log
- "Get pipeline 456 details" → gitlab://projects/current/pipelines/456
- "List jobs in pipeline 456" → gitlab://projects/current/pipelines/456/jobs
- "Show artifacts for job 12123" → gitlab://projects/current/jobs/12123/artifacts
- "Read logs.txt from job 12123" → gitlab://projects/current/jobs/12123/artifacts/logs.txt
- "Show last 50 lines of logs.txt" → gitlab://projects/current/jobs/12123/artifacts/logs.txt?lines=50
- "Show lines 100-150 of build.log" → gitlab://projects/current/jobs/12123/artifacts/build.log?offset=100&lines=50
- "Show entire artifact file" → gitlab://projects/current/jobs/12123/artifacts/output.txt?lines=all

Token Efficiency:
- Use /status for merge readiness checks (85-90% token savings vs separate calls)
- Use comprehensive resource for full overview: gitlab://projects/{id}/merge-requests/{iid}
- Use granular resources when you only need specific data: /discussions, /changes, /commits, /approvals, /pipeline-jobs

CI/CD Variables (Security):
- Read access returns metadata only (key, type, protected, masked, environment_scope)
- Values are NEVER exposed for security
- Use to check if a variable exists or verify its configuration
- Use set_project_ci_variable() to update values

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
            "mr_status": {
                "uri": "gitlab://projects/{project_id}/merge-requests/{mr_iid}/status",
                "examples": [
                    "gitlab://projects/current/merge-requests/current/status",
                    "gitlab://projects/qodev%2Fhandbook/merge-requests/20/status",
                ],
                "description": "⭐ RECOMMENDED: Lightweight merge readiness check (85-90% token savings vs separate calls)",
                "queries": ["Is this MR ready to merge?", "What's blocking my MR?", "Can I merge this?", "Check MR status"],
                "includes": ["ready_to_merge boolean", "blockers array", "pipeline status with failed job IDs", "unresolved discussion IDs", "approval status"],
            },
            "comprehensive_mr": {
                "uri": "gitlab://projects/{project_id}/merge-requests/{mr_iid}",
                "examples": [
                    "gitlab://projects/current/merge-requests/current (current repo & branch)",
                    "gitlab://projects/qodev%2Fhandbook/merge-requests/20 (specific project & MR)",
                    "gitlab://projects/123/merge-requests/20 (numeric IDs)",
                ],
                "description": "Complete MR overview (discussions, changes, commits, pipeline, approvals)",
                "queries": ["Show me everything about MR !20", "Summarize the MR"],
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
            "project_releases": {
                "uri": "gitlab://projects/{project_id}/releases/",
                "examples": ["gitlab://projects/current/releases/"],
                "description": "All releases for a project (newest first)",
                "queries": ["What releases exist?", "Show me all releases"],
            },
            "specific_release": {
                "uri": "gitlab://projects/{project_id}/releases/{tag_name}",
                "examples": ["gitlab://projects/current/releases/v1.0.0"],
                "description": "Details of a specific release by tag name",
                "queries": ["Show me release v1.0.0", "What's in the latest release?"],
            },
        },
        "tools": {
            "create_release": {
                "signature": "create_release(project_id, tag_name, name, description, ref, ...)",
                "supports_current": True,
                "description": "Create a new release. Auto-detects ref from current branch if not provided.",
                "examples": [
                    "create_release('current', 'v1.0.0', name='Release 1.0.0', description='Initial release')",
                    "create_release('current', 'v1.1.0', ref='main', description='Bug fixes and improvements')",
                    "create_release('qodev/handbook', 'v2.0.0', name='Version 2.0', description='Major update')",
                ],
            },
            "create_merge_request": {
                "signature": "create_merge_request(project_id, title, source_branch, target_branch, ...)",
                "supports_current": True,
                "description": "Create a new merge request. Auto-detects source_branch if not provided.",
                "examples": [
                    "create_merge_request('current', 'Add new feature')",
                    "create_merge_request('current', 'Bug fix', source_branch='feature', target_branch='dev')",
                    "create_merge_request('qodev/handbook', 'Update docs', source_branch='docs-update')",
                ],
            },
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
        "token_efficiency_tip": "Use /status for merge readiness checks (85-90% savings). Use granular resources (/discussions, /changes, etc.) when you only need specific data instead of the comprehensive MR overview",
        "common_questions": [
            "Is this MR ready to merge? → gitlab://projects/current/merge-requests/current/status",
            "What's blocking my MR? → gitlab://projects/current/merge-requests/current/status",
            "What discussions are on my MR? → gitlab://projects/current/merge-requests/current/discussions",
            "Show me MR !20 in qodev/handbook → gitlab://projects/qodev%2Fhandbook/merge-requests/20",
            "Create MR for current branch → create_merge_request('current', 'Title')",
            "Comment on my MR → comment_on_merge_request('current', 'current', 'message')",
            "Merge my MR → merge_merge_request('current', 'current')",
            "Any open MRs? → gitlab://projects/current/merge-requests/",
            "Pipeline status? → gitlab://projects/current/pipelines/",
            "What releases exist? → gitlab://projects/current/releases/",
            "Show me release v1.0.0 → gitlab://projects/current/releases/v1.0.0",
            "Create a release → create_release('current', 'v1.0.0', name='Version 1.0', description='Release notes')",
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

    # Enrich failed jobs with last 10 lines of logs
    enriched_jobs = gitlab_client.enrich_jobs_with_failure_logs(resolved_project_id, jobs)

    return {
        "pipeline": {
            "id": latest_pipeline["id"],
            "status": latest_pipeline["status"],
            "ref": latest_pipeline["ref"],
            "web_url": latest_pipeline.get("web_url"),
            "created_at": latest_pipeline.get("created_at"),
        },
        "jobs": enriched_jobs,
        "summary": {
            "total_jobs": len(jobs),
            "failed_jobs": len([j for j in jobs if j.get("status") == "failed"]),
            "successful_jobs": len([j for j in jobs if j.get("status") == "success"]),
        },
    }


@mcp.resource("gitlab://projects/{project_id}/merge-requests/{mr_iid}/status")
async def project_merge_request_status(ctx: Context, project_id: str, mr_iid: str) -> dict[str, Any]:
    """Get merge readiness status for a merge request (supports project_id="current" and mr_iid="current")

    Lightweight resource that answers "Is this MR ready to merge?" by checking:
    - Pipeline status (passing/failed)
    - Discussion threads (resolved/unresolved)
    - Approval status (if configured)
    - Merge conflicts

    Returns a summary with blockers and actionable IDs for follow-up.
    """
    resolved_project_id, _ = await resolve_project_id(ctx, project_id)
    if not resolved_project_id:
        return create_repo_not_found_error(gitlab_client.base_url)

    resolved_mr_iid = await resolve_mr_iid(ctx, resolved_project_id, mr_iid)
    if not resolved_mr_iid:
        return {"error": f"Could not resolve MR IID '{mr_iid}'"}

    try:
        # Fetch core MR data
        mr = gitlab_client.get_merge_request(resolved_project_id, resolved_mr_iid)

        # Fetch pipeline + jobs (if pipeline exists)
        pipelines = gitlab_client.get_mr_pipelines(resolved_project_id, resolved_mr_iid)
        latest_pipeline = pipelines[0] if pipelines else None

        pipeline_status = None
        failed_jobs = []
        if latest_pipeline:
            jobs = gitlab_client.get_pipeline_jobs(resolved_project_id, latest_pipeline["id"])
            failed_jobs = [
                {
                    "id": j["id"],
                    "name": j["name"],
                    "stage": j.get("stage"),
                    "web_url": j.get("web_url"),
                }
                for j in jobs
                if j.get("status") == "failed"
            ]
            pipeline_status = {
                "id": latest_pipeline["id"],
                "status": latest_pipeline["status"],
                "web_url": latest_pipeline.get("web_url"),
                "failed_jobs": failed_jobs,
            }

        # Fetch discussions
        discussions = gitlab_client.get_mr_discussions(resolved_project_id, resolved_mr_iid)
        unresolved_discussions = [d for d in discussions if not d.get("notes", [{}])[0].get("resolved", False)]
        unresolved_ids = [d["id"] for d in unresolved_discussions]

        # Fetch approvals (may not be available)
        approvals_data = None
        try:
            approvals = gitlab_client.get_mr_approvals(resolved_project_id, resolved_mr_iid)
            approvals_data = {
                "approved": approvals.get("approved", False),
                "approvals_required": approvals.get("approvals_required", 0),
                "approvals_left": approvals.get("approvals_left", 0),
                "approved_by": [u["user"]["username"] for u in approvals.get("approved_by", [])],
            }
        except Exception:
            approvals_data = {"note": "Approvals not available or not configured"}

        # Calculate blockers
        blockers = []
        if latest_pipeline and latest_pipeline["status"] in ["failed", "canceled"]:
            blockers.append("pipeline_failed")
        if latest_pipeline and latest_pipeline["status"] in ["pending", "running", "created"]:
            blockers.append("pipeline_running")
        if len(unresolved_discussions) > 0:
            blockers.append("unresolved_discussions")
        if approvals_data and not approvals_data.get("note"):
            if not approvals_data.get("approved"):
                blockers.append("approvals_required")
        if mr.get("merge_status") == "cannot_be_merged":
            blockers.append("merge_conflicts")
        if mr.get("draft") or mr.get("work_in_progress"):
            blockers.append("draft")

        ready_to_merge = (
            len(blockers) == 0 and mr.get("state") == "opened" and (not latest_pipeline or latest_pipeline["status"] == "success")
        )

        return {
            "ready_to_merge": ready_to_merge,
            "blockers": blockers,
            "merge_request": {
                "iid": mr["iid"],
                "title": mr["title"],
                "state": mr["state"],
                "merge_status": mr.get("merge_status"),
                "draft": mr.get("draft", False),
                "web_url": mr.get("web_url"),
            },
            "pipeline": pipeline_status,
            "discussions": {
                "total": len(discussions),
                "unresolved": len(unresolved_discussions),
                "unresolved_ids": unresolved_ids,
            },
            "approvals": approvals_data,
        }
    except Exception as e:
        return {"error": f"Failed to fetch MR status: {str(e)}"}


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

    # Enrich failed jobs with last 10 lines of logs
    enriched_jobs = gitlab_client.enrich_jobs_with_failure_logs(resolved_id, jobs)

    return {
        "pipeline_id": int(pipeline_id),
        "jobs": enriched_jobs,
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


@mcp.resource("gitlab://projects/{project_id}/jobs/{job_id}/artifacts")
async def project_job_artifacts(ctx: Context, project_id: str, job_id: str) -> str | dict[str, Any]:
    """List all artifacts for a job (supports project_id="current")

    Returns JSON with job details and available artifacts including:
    - job_id: Job ID
    - job_name: Job name
    - status: Job status
    - artifacts: Array of artifact objects with filename, size, file_type
    """
    resolved_id, _ = await resolve_project_id(ctx, project_id)
    if not resolved_id:
        return create_repo_not_found_error(gitlab_client.base_url)

    try:
        import json

        job = gitlab_client.get_job(resolved_id, int(job_id))

        result = {
            "job_id": job.get("id"),
            "job_name": job.get("name"),
            "status": job.get("status"),
            "artifacts_file": job.get("artifacts_file", {}),
            "artifacts": job.get("artifacts", []),
        }

        return json.dumps(result, indent=2)
    except httpx.HTTPStatusError as e:
        return json.dumps({"error": f"Failed to get job {job_id}: {e.response.status_code}"})
    except Exception as e:
        return json.dumps({"error": f"Unexpected error: {str(e)}"})


@mcp.resource("gitlab://projects/{project_id}/jobs/{job_id}/artifacts/{artifact_path}")
async def project_job_artifact(
    ctx: Context, project_id: str, job_id: str, artifact_path: str
) -> str:
    """Read a specific artifact file from a job (supports project_id="current")

    Args:
        project_id: Project ID or "current"
        job_id: Job ID
        artifact_path: Path to artifact file (e.g., "logs.txt?lines=50", "build/output.log?lines=all")
            Supports query params: ?lines=N (default 10), ?offset=M (default 0), ?lines=all

    Returns:
        For text files: Content with optional line range
        For binary files: Base64-encoded content with prefix
    """
    from urllib.parse import parse_qs

    # Parse query params from artifact_path (MCP includes them in path segment)
    if "?" in artifact_path:
        path_part, query_part = artifact_path.split("?", 1)
        params = parse_qs(query_part)
        lines = params.get("lines", ["10"])[0]
        offset = params.get("offset", ["0"])[0]
        artifact_path = path_part
    else:
        lines = "10"
        offset = "0"

    resolved_id, _ = await resolve_project_id(ctx, project_id)
    if not resolved_id:
        return create_repo_not_found_error(gitlab_client.base_url)

    try:
        import base64

        # Download artifact
        content_bytes = gitlab_client.get_job_artifact(resolved_id, int(job_id), artifact_path)

        # Try to decode as UTF-8 text
        try:
            content_text = content_bytes.decode("utf-8")

            # Handle line range for text files
            if lines == "all":
                # Return entire file
                return content_text
            else:
                # Parse line parameters
                try:
                    lines_int = int(lines)
                    offset_int = int(offset)
                except ValueError:
                    return f"Error: 'lines' and 'offset' must be integers or 'all'. Got lines={lines}, offset={offset}"

                # Split into lines and apply range
                all_lines = content_text.splitlines(keepends=True)
                total_lines = len(all_lines)

                if offset_int < 0:
                    # Negative offset means from end
                    start_idx = max(0, total_lines + offset_int)
                elif offset_int == 0 and lines_int > 0:
                    # Default: show last N lines
                    start_idx = max(0, total_lines - lines_int)
                else:
                    # Positive offset: start from that line
                    start_idx = offset_int

                end_idx = min(total_lines, start_idx + lines_int) if lines_int > 0 else total_lines

                selected_lines = all_lines[start_idx:end_idx]

                # Format with line numbers (like cat -n, starting from 1)
                formatted_lines = [f"{start_idx + i + 1:6d}\t{line}" for i, line in enumerate(selected_lines)]

                result = "".join(formatted_lines)

                # Add metadata header if lines were truncated
                if start_idx > 0 or end_idx < total_lines:
                    header = f"[Showing lines {start_idx + 1}-{end_idx} of {total_lines} total lines]\n"
                    header += "[Hint: Use ?lines=all for full file, or download_artifact tool for local access]\n\n"
                    result = header + result

                return result

        except UnicodeDecodeError:
            # Binary file - return base64 encoded
            encoded = base64.b64encode(content_bytes).decode("utf-8")
            return f"[Binary file - base64 encoded]\nSize: {len(content_bytes)} bytes\n\n{encoded}"

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return f"Error: Artifact '{artifact_path}' not found in job {job_id}"
        else:
            return f"Error: Failed to get artifact (HTTP {e.response.status_code})"
    except Exception as e:
        return f"Error: {str(e)}"


@mcp.resource("gitlab://projects/{project_id}/releases/")
async def project_releases(ctx: Context, project_id: str) -> list[dict[str, Any]] | dict[str, Any]:
    """Get all releases for a project (supports project_id="current")

    Returns releases sorted by released_at in descending order (newest first).
    """
    resolved_id, _ = await resolve_project_id(ctx, project_id)
    if not resolved_id:
        return create_repo_not_found_error(gitlab_client.base_url)
    return gitlab_client.get_releases(resolved_id)


@mcp.resource("gitlab://projects/{project_id}/releases/{tag_name}")
async def project_release(ctx: Context, project_id: str, tag_name: str) -> dict[str, Any]:
    """Get a specific release by tag name (supports project_id="current")"""
    resolved_id, _ = await resolve_project_id(ctx, project_id)
    if not resolved_id:
        return create_repo_not_found_error(gitlab_client.base_url)

    try:
        return gitlab_client.get_release(resolved_id, tag_name)
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            return {"error": f"Release with tag '{tag_name}' not found in project {project_id}"}
        return {"error": f"Failed to fetch release '{tag_name}': {e.response.text[:200]}"}


@mcp.resource("gitlab://projects/{project_id}/variables/")
async def project_variables(ctx: Context, project_id: str) -> list[dict[str, Any]] | dict[str, Any]:
    """List all CI/CD variables for a project (metadata only, values not exposed for security)

    Supports project_id="current" for current repository.

    Returns variable metadata: key, variable_type, protected, masked, raw, environment_scope, description.
    Values are NEVER exposed for security reasons.
    """
    resolved_id, _ = await resolve_project_id(ctx, project_id)
    if not resolved_id:
        return create_repo_not_found_error(gitlab_client.base_url)
    return gitlab_client.list_project_variables(resolved_id)


@mcp.resource("gitlab://projects/{project_id}/variables/{key}")
async def project_variable(ctx: Context, project_id: str, key: str) -> dict[str, Any]:
    """Get a specific CI/CD variable's metadata (value not exposed for security)

    Supports project_id="current" for current repository.

    Returns: key, variable_type, protected, masked, raw, environment_scope, description.
    Value is NEVER exposed for security reasons. Use set_project_ci_variable() to update values.
    """
    resolved_id, _ = await resolve_project_id(ctx, project_id)
    if not resolved_id:
        return create_repo_not_found_error(gitlab_client.base_url)

    var = gitlab_client.get_project_variable(resolved_id, key)
    if not var:
        return {"error": f"Variable '{key}' not found in project", "key": key}

    return gitlab_client._sanitize_variable(var)


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
async def reply_to_discussion(
    ctx: Context, project_id: str, mr_iid: str | int, discussion_id: str, comment: str
) -> dict[str, Any]:
    """Reply to an existing discussion thread on a merge request

    Args:
        project_id: Project ID, path, or "current" (e.g., "mygroup/myproject", "123", or "current")
        mr_iid: Merge request IID or "current" (the !number, or "current" for current branch MR)
        discussion_id: Discussion thread ID to reply to
        comment: Reply text to post (supports Markdown formatting)

    Returns:
        Result of reply operation with created note details

    Raises:
        Error if reply creation fails
    """
    resolved_project_id, _ = await resolve_project_id(ctx, project_id)
    if not resolved_project_id:
        return {"success": False, "error": f"Could not resolve project '{project_id}'"}

    resolved_mr_iid = await resolve_mr_iid(ctx, resolved_project_id, str(mr_iid))
    if not resolved_mr_iid:
        return {"success": False, "error": f"Could not resolve MR IID '{mr_iid}'"}

    try:
        note = gitlab_client.reply_to_discussion(
            project_id=resolved_project_id,
            mr_iid=resolved_mr_iid,
            discussion_id=discussion_id,
            body=comment,
        )

        return {
            "success": True,
            "message": f"Successfully replied to discussion {discussion_id} on MR !{resolved_mr_iid} in project {project_id}",
            "note": note,
            "project_id": project_id,
            "mr_iid": resolved_mr_iid,
            "discussion_id": discussion_id,
        }
    except httpx.HTTPStatusError as e:
        error_msg = e.response.text if e.response.text else str(e)
        return {
            "success": False,
            "error": f"Failed to reply to discussion {discussion_id} on MR !{resolved_mr_iid} in project {project_id}: {error_msg}",
            "status_code": e.response.status_code,
            "project_id": project_id,
            "mr_iid": resolved_mr_iid,
            "discussion_id": discussion_id,
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Unexpected error while replying to discussion {discussion_id} on MR !{resolved_mr_iid} in project {project_id}: {str(e)}",
            "project_id": project_id,
            "mr_iid": resolved_mr_iid,
            "discussion_id": discussion_id,
        }


@mcp.tool()
async def resolve_discussion_thread(
    ctx: Context, project_id: str, mr_iid: str | int, discussion_id: str, resolved: bool = True
) -> dict[str, Any]:
    """Resolve or unresolve a discussion thread on a merge request

    Args:
        project_id: Project ID, path, or "current" (e.g., "mygroup/myproject", "123", or "current")
        mr_iid: Merge request IID or "current" (the !number, or "current" for current branch MR)
        discussion_id: Discussion thread ID to resolve/unresolve
        resolved: True to resolve the thread, False to unresolve it (default: True)

    Returns:
        Result of resolve/unresolve operation with updated discussion details

    Raises:
        Error if resolve/unresolve operation fails
    """
    resolved_project_id, _ = await resolve_project_id(ctx, project_id)
    if not resolved_project_id:
        return {"success": False, "error": f"Could not resolve project '{project_id}'"}

    resolved_mr_iid = await resolve_mr_iid(ctx, resolved_project_id, str(mr_iid))
    if not resolved_mr_iid:
        return {"success": False, "error": f"Could not resolve MR IID '{mr_iid}'"}

    try:
        discussion = gitlab_client.resolve_discussion(
            project_id=resolved_project_id,
            mr_iid=resolved_mr_iid,
            discussion_id=discussion_id,
            resolved=resolved,
        )

        action = "resolved" if resolved else "unresolved"
        return {
            "success": True,
            "message": f"Successfully {action} discussion {discussion_id} on MR !{resolved_mr_iid} in project {project_id}",
            "discussion": discussion,
            "project_id": project_id,
            "mr_iid": resolved_mr_iid,
            "discussion_id": discussion_id,
            "resolved": resolved,
        }
    except httpx.HTTPStatusError as e:
        error_msg = e.response.text if e.response.text else str(e)
        action = "resolve" if resolved else "unresolve"
        return {
            "success": False,
            "error": f"Failed to {action} discussion {discussion_id} on MR !{resolved_mr_iid} in project {project_id}: {error_msg}",
            "status_code": e.response.status_code,
            "project_id": project_id,
            "mr_iid": resolved_mr_iid,
            "discussion_id": discussion_id,
        }
    except Exception as e:
        action = "resolve" if resolved else "unresolve"
        return {
            "success": False,
            "error": f"Unexpected error while trying to {action} discussion {discussion_id} on MR !{resolved_mr_iid} in project {project_id}: {str(e)}",
            "project_id": project_id,
            "mr_iid": resolved_mr_iid,
            "discussion_id": discussion_id,
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
async def close_merge_request(
    ctx: Context,
    project_id: str,
    mr_iid: str | int,
) -> dict[str, Any]:
    """Close a specific merge request by project and MR IID

    Args:
        project_id: Project ID, path, or "current" (e.g., "mygroup/myproject", "123", or "current")
        mr_iid: Merge request IID or "current" (the !number, or "current" for current branch MR)

    Returns:
        Result of close operation with closed MR details

    Raises:
        Error if close operation fails
    """
    resolved_project_id, _ = await resolve_project_id(ctx, project_id)
    if not resolved_project_id:
        return {"success": False, "error": f"Could not resolve project '{project_id}'"}

    resolved_mr_iid = await resolve_mr_iid(ctx, resolved_project_id, str(mr_iid))
    if not resolved_mr_iid:
        return {"success": False, "error": f"Could not resolve MR IID '{mr_iid}'"}

    try:
        result = gitlab_client.close_mr(
            project_id=resolved_project_id,
            mr_iid=resolved_mr_iid,
        )

        return {
            "success": True,
            "message": f"Successfully closed MR !{resolved_mr_iid} in project {project_id}",
            "merge_request": result,
        }
    except httpx.HTTPStatusError as e:
        import json

        # Parse GitLab error response
        try:
            error_json = json.loads(e.response.text)
            error_message = error_json.get("message", "Unknown error")
        except (json.JSONDecodeError, AttributeError):
            error_message = e.response.text if e.response.text else str(e)

        return {
            "success": False,
            "error": f"Failed to close MR !{resolved_mr_iid} in project {project_id}: {error_message}",
            "status_code": e.response.status_code,
            "project_id": project_id,
            "mr_iid": resolved_mr_iid,
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Unexpected error while closing MR !{resolved_mr_iid} in project {project_id}: {str(e)}",
            "project_id": project_id,
            "mr_iid": resolved_mr_iid,
        }


@mcp.tool()
async def update_merge_request(
    ctx: Context,
    project_id: str,
    mr_iid: str | int,
    title: str | None = None,
    description: str | None = None,
    target_branch: str | None = None,
    state_event: str | None = None,
    assignee_ids: list[int] | None = None,
    reviewer_ids: list[int] | None = None,
    labels: str | None = None,
) -> dict[str, Any]:
    """Update a merge request's title, description, or other properties

    Args:
        project_id: Project ID, path, or "current" (e.g., "mygroup/myproject", "123", or "current")
        mr_iid: Merge request IID or "current" (the !number, or "current" for current branch MR)
        title: New MR title (optional)
        description: New MR description (optional)
        target_branch: New target branch (optional)
        state_event: Change state: "open", "close", "reopen" (optional)
        assignee_ids: List of assignee user IDs (optional)
        reviewer_ids: List of reviewer user IDs (optional)
        labels: Comma-separated label names (optional)

    Returns:
        Result with success status and updated MR details

    Raises:
        Error if update fails
    """
    resolved_project_id, _ = await resolve_project_id(ctx, project_id)
    if not resolved_project_id:
        return {"success": False, "error": f"Could not resolve project '{project_id}'"}

    resolved_mr_iid = await resolve_mr_iid(ctx, resolved_project_id, str(mr_iid))
    if not resolved_mr_iid:
        return {"success": False, "error": f"Could not resolve MR IID '{mr_iid}'"}

    try:
        result = gitlab_client.update_mr(
            project_id=resolved_project_id,
            mr_iid=resolved_mr_iid,
            title=title,
            description=description,
            target_branch=target_branch,
            state_event=state_event,
            assignee_ids=assignee_ids,
            reviewer_ids=reviewer_ids,
            labels=labels,
        )

        return {
            "success": True,
            "message": f"Successfully updated MR !{resolved_mr_iid} in project {project_id}",
            "merge_request": {
                "iid": result.get("iid"),
                "title": result.get("title"),
                "description": result.get("description"),
                "state": result.get("state"),
                "web_url": result.get("web_url"),
            },
            "project_id": project_id,
            "mr_iid": resolved_mr_iid,
        }
    except httpx.HTTPStatusError as e:
        import json

        # Parse GitLab error response
        try:
            error_json = json.loads(e.response.text)
            error_message = error_json.get("message", "Unknown error")
        except (json.JSONDecodeError, AttributeError):
            error_message = e.response.text if e.response.text else str(e)

        return {
            "success": False,
            "error": f"Failed to update MR !{resolved_mr_iid} in project {project_id}: {error_message}",
            "status_code": e.response.status_code,
            "project_id": project_id,
            "mr_iid": resolved_mr_iid,
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Unexpected error while updating MR !{resolved_mr_iid} in project {project_id}: {str(e)}",
            "project_id": project_id,
            "mr_iid": resolved_mr_iid,
        }


@mcp.tool()
async def wait_for_pipeline(
    ctx: Context,
    project_id: str,
    pipeline_id: str | int | None = None,
    mr_iid: str | int | None = None,
    timeout_seconds: int = 3600,
    check_interval: int = 10,
    include_failed_logs: bool = True,
) -> dict[str, Any]:
    """Wait for a GitLab pipeline to complete (success or failure)

    Args:
        project_id: Project ID, path, or "current" (e.g., "mygroup/myproject", "123", or "current")
        pipeline_id: Pipeline ID to wait for (required if mr_iid not provided)
        mr_iid: MR IID to get latest pipeline from (alternative to pipeline_id, supports "current")
        timeout_seconds: Maximum time to wait in seconds (default: 3600/1 hour)
        check_interval: How often to check status in seconds (default: 10)
        include_failed_logs: Include last 10 lines of failed job logs (default: True)

    Returns:
        Result with final status, duration, job summary, and optionally failed job logs

    Raises:
        Error if wait operation fails
    """
    # Resolve project_id
    resolved_project_id, _ = await resolve_project_id(ctx, project_id)
    if not resolved_project_id:
        return {"success": False, "error": f"Could not resolve project '{project_id}'"}

    # Validate that either pipeline_id or mr_iid is provided (but not both)
    if pipeline_id is None and mr_iid is None:
        return {
            "success": False,
            "error": "Must provide either 'pipeline_id' or 'mr_iid'",
        }

    if pipeline_id is not None and mr_iid is not None:
        return {
            "success": False,
            "error": "Cannot provide both 'pipeline_id' and 'mr_iid' - choose one",
        }

    # If mr_iid provided, get the latest pipeline from the MR
    resolved_pipeline_id = None
    if mr_iid is not None:
        resolved_mr_iid = await resolve_mr_iid(ctx, resolved_project_id, str(mr_iid))
        if not resolved_mr_iid:
            return {"success": False, "error": f"Could not resolve MR IID '{mr_iid}'"}

        try:
            pipelines = gitlab_client.get_mr_pipelines(resolved_project_id, resolved_mr_iid)
            if not pipelines:
                return {
                    "success": False,
                    "error": f"No pipelines found for MR !{resolved_mr_iid}",
                    "project_id": project_id,
                    "mr_iid": resolved_mr_iid,
                }
            # Get the latest pipeline (first in list)
            latest_pipeline = pipelines[0]
            resolved_pipeline_id = latest_pipeline["id"]
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to get pipelines for MR !{resolved_mr_iid}: {str(e)}",
                "project_id": project_id,
                "mr_iid": resolved_mr_iid,
            }
    else:
        # Use provided pipeline_id
        try:
            resolved_pipeline_id = int(pipeline_id)
        except (ValueError, TypeError):
            return {
                "success": False,
                "error": f"Invalid pipeline_id: '{pipeline_id}' (must be an integer)",
            }

    # Wait for the pipeline
    try:
        result = gitlab_client.wait_for_pipeline(
            project_id=resolved_project_id,
            pipeline_id=resolved_pipeline_id,
            timeout_seconds=timeout_seconds,
            check_interval=check_interval,
            include_failed_logs=include_failed_logs,
        )

        # Determine success based on final status
        final_status = result.get("final_status")
        is_success = final_status == "success"

        return {
            "success": is_success,
            "message": f"Pipeline {resolved_pipeline_id} completed with status '{final_status}' "
            f"after {result.get('total_duration')}s",
            **result,
            "project_id": project_id,
        }
    except httpx.HTTPStatusError as e:
        import json

        # Parse GitLab error response
        try:
            error_json = json.loads(e.response.text)
            error_message = error_json.get("message", "Unknown error")
        except (json.JSONDecodeError, AttributeError):
            error_message = e.response.text if e.response.text else str(e)

        return {
            "success": False,
            "error": f"Failed to wait for pipeline {resolved_pipeline_id} in project {project_id}: {error_message}",
            "status_code": e.response.status_code,
            "project_id": project_id,
            "pipeline_id": resolved_pipeline_id,
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Unexpected error while waiting for pipeline {resolved_pipeline_id} in project {project_id}: {str(e)}",
            "project_id": project_id,
            "pipeline_id": resolved_pipeline_id,
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


@mcp.tool()
async def create_merge_request(
    ctx: Context,
    project_id: str,
    title: str,
    source_branch: str | None = None,
    target_branch: str = "main",
    description: str | None = None,
    assignee_ids: list[int] | None = None,
    reviewer_ids: list[int] | None = None,
    labels: str | None = None,
    remove_source_branch: bool = True,
    squash: bool | None = None,
    allow_collaboration: bool = False,
) -> dict[str, Any]:
    """Create a new merge request in a project

    Args:
        project_id: Project ID, path, or "current" (e.g., "mygroup/myproject", "123", or "current")
        title: MR title (required)
        source_branch: Source branch name (defaults to current branch if None)
        target_branch: Target branch name (default: "main")
        description: MR description/body (optional, supports Markdown)
        assignee_ids: List of user IDs to assign (optional)
        reviewer_ids: List of user IDs to review (optional)
        labels: Comma-separated label names (optional, e.g., "bug,urgent")
        remove_source_branch: Remove source branch after merge (default: True)
        squash: Squash commits on merge (None = use project settings, True = squash, False = don't squash)
        allow_collaboration: Allow commits from members with merge access (default: False)

    Returns:
        Result with success status and created MR details including web URL

    Raises:
        Error if MR creation fails
    """
    resolved_project_id, repo_info = await resolve_project_id(ctx, project_id)
    if not resolved_project_id:
        return {"success": False, "error": f"Could not resolve project '{project_id}'"}

    # Auto-detect source branch if not provided
    if source_branch is None:
        if not repo_info:
            # Need to detect repo to get branch
            repo_info = await detect_current_repo(ctx, gitlab_client)
            if not repo_info:
                return {
                    "success": False,
                    "error": "Could not detect current branch. Please specify source_branch parameter.",
                }

        git_root = repo_info["git_root"]
        source_branch = get_current_branch(git_root)

        if not source_branch:
            return {
                "success": False,
                "error": "Could not detect current branch. Please specify source_branch parameter.",
            }

        logger.info(f"Auto-detected source branch: {source_branch}")

    try:
        result = gitlab_client.create_merge_request(
            project_id=resolved_project_id,
            source_branch=source_branch,
            target_branch=target_branch,
            title=title,
            description=description,
            assignee_ids=assignee_ids,
            reviewer_ids=reviewer_ids,
            labels=labels,
            remove_source_branch=remove_source_branch,
            squash=squash,
            allow_collaboration=allow_collaboration,
        )

        return {
            "success": True,
            "message": f"Successfully created MR !{result.get('iid')} in project {project_id}",
            "merge_request": {
                "iid": result.get("iid"),
                "title": result.get("title"),
                "description": result.get("description"),
                "source_branch": result.get("source_branch"),
                "target_branch": result.get("target_branch"),
                "state": result.get("state"),
                "web_url": result.get("web_url"),
                "author": result.get("author"),
            },
            "project_id": project_id,
        }
    except httpx.HTTPStatusError as e:
        import json

        # Parse GitLab error response
        try:
            error_json = json.loads(e.response.text)
            error_message = error_json.get("message", "Unknown error")
        except (json.JSONDecodeError, AttributeError):
            error_message = e.response.text if e.response.text else str(e)

        helpful_message = f"Failed to create MR in project {project_id}: {error_message}"
        suggestions = []

        # Add context-specific suggestions
        if e.response.status_code == 409:
            # Conflict - usually means MR already exists
            helpful_message = f"Cannot create MR: A merge request already exists for branch '{source_branch}'"
            suggestions.append("Check existing open MRs for this branch")
        elif e.response.status_code == 400:
            # Bad request - usually validation error
            suggestions.append("Check that source and target branches exist")
            suggestions.append("Verify that source branch differs from target branch")
        elif e.response.status_code == 404:
            # Not found - project or branch doesn't exist
            helpful_message = f"Cannot create MR: Project or branch not found"
            suggestions.append(f"Verify project '{project_id}' exists")
            suggestions.append(f"Verify branches '{source_branch}' and '{target_branch}' exist")

        return {
            "success": False,
            "error": helpful_message,
            "suggestions": suggestions,
            "status_code": e.response.status_code,
            "project_id": project_id,
            "source_branch": source_branch,
            "target_branch": target_branch,
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Unexpected error while creating MR in project {project_id}: {str(e)}",
            "project_id": project_id,
            "source_branch": source_branch,
            "target_branch": target_branch,
        }


@mcp.tool()
async def create_release(
    ctx: Context,
    project_id: str,
    tag_name: str,
    name: str | None = None,
    description: str | None = None,
    ref: str | None = None,
    milestones: list[str] | None = None,
    released_at: str | None = None,
    assets_links: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Create a new release in a project

    Args:
        project_id: Project ID, path, or "current" (e.g., "mygroup/myproject", "123", or "current")
        tag_name: Tag name for the release (required)
        name: Release title (optional, defaults to tag_name)
        description: Release description/notes (optional, supports Markdown)
        ref: Commit SHA, branch, or existing tag (required only if tag_name doesn't exist yet; auto-detects from current branch if not provided)
        milestones: List of milestone titles to associate (optional)
        released_at: ISO 8601 datetime for release (optional, defaults to current time)
        assets_links: List of asset link dicts with 'name', 'url', and optional 'direct_asset_path' (optional)

    Returns:
        Result with success status and created release details

    Raises:
        Error if release creation fails
    """
    resolved_project_id, repo_info = await resolve_project_id(ctx, project_id)
    if not resolved_project_id:
        return {"success": False, "error": f"Could not resolve project '{project_id}'"}

    # Auto-detect ref from current branch if not provided
    if ref is None:
        if not repo_info:
            # Need to detect repo to get branch
            repo_info = await detect_current_repo(ctx, gitlab_client)

        if repo_info:
            git_root = repo_info["git_root"]
            current_branch = get_current_branch(git_root)

            if current_branch:
                ref = current_branch
                logger.info(f"Auto-detected ref from current branch: {ref}")

    try:
        result = gitlab_client.create_release(
            project_id=resolved_project_id,
            tag_name=tag_name,
            name=name,
            description=description,
            ref=ref,
            milestones=milestones,
            released_at=released_at,
            assets_links=assets_links,
        )

        return {
            "success": True,
            "message": f"Successfully created release '{tag_name}' in project {project_id}",
            "release": {
                "tag_name": result.get("tag_name"),
                "name": result.get("name"),
                "description": result.get("description"),
                "created_at": result.get("created_at"),
                "released_at": result.get("released_at"),
                "author": result.get("author"),
                "commit": result.get("commit"),
                "milestones": result.get("milestones"),
                "assets": result.get("assets"),
            },
            "project_id": project_id,
        }
    except httpx.HTTPStatusError as e:
        import json

        # Parse GitLab error response
        try:
            error_json = json.loads(e.response.text)
            error_message = error_json.get("message", "Unknown error")
        except (json.JSONDecodeError, AttributeError):
            error_message = e.response.text if e.response.text else str(e)

        helpful_message = f"Failed to create release '{tag_name}' in project {project_id}: {error_message}"
        suggestions = []

        # Add context-specific suggestions
        if e.response.status_code == 409:
            # Conflict - release already exists
            helpful_message = f"Cannot create release: Release with tag '{tag_name}' already exists"
            suggestions.append(f"Use a different tag name or update the existing release")
            suggestions.append(f"View existing release: gitlab://projects/{project_id}/releases/{tag_name}")
        elif e.response.status_code == 400:
            # Bad request - usually validation error
            if "Tag does not exist" in error_message or "ref" in error_message.lower():
                helpful_message = f"Cannot create release: Tag '{tag_name}' does not exist"
                suggestions.append(f"Create the tag first, or provide 'ref' parameter to create tag from a commit/branch")
                if ref:
                    suggestions.append(f"Current ref value: '{ref}' - verify this commit/branch exists")
                else:
                    suggestions.append("No ref provided - specify ref parameter or create the tag manually first")
            else:
                suggestions.append("Check that all parameters are valid")
                suggestions.append("Verify tag_name format is correct")
        elif e.response.status_code == 404:
            # Not found - project doesn't exist
            helpful_message = f"Cannot create release: Project '{project_id}' not found"
            suggestions.append(f"Verify project '{project_id}' exists and you have access")
        elif e.response.status_code == 403:
            # Forbidden - insufficient permissions
            helpful_message = f"Cannot create release: Insufficient permissions"
            suggestions.append("You need Developer level access or higher to create releases")
            suggestions.append("Check your role in the project")

        return {
            "success": False,
            "error": helpful_message,
            "suggestions": suggestions,
            "status_code": e.response.status_code,
            "project_id": project_id,
            "tag_name": tag_name,
            "ref": ref,
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Unexpected error while creating release '{tag_name}' in project {project_id}: {str(e)}",
            "project_id": project_id,
            "tag_name": tag_name,
        }


if __name__ == "__main__":
    mcp.run()
