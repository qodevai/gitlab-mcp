"""Issue client mixin."""

import logging
from typing import Any

import httpx

from gitlab_mcp.client.base import BaseClientMixin

logger = logging.getLogger(__name__)


class IssuesMixin(BaseClientMixin):
    """Mixin for issue operations."""

    def get_issues(
        self,
        project_id: str,
        state: str = "opened",
        labels: str | None = None,
        assignee_id: int | None = None,
        milestone: str | None = None,
        per_page: int = 20,
        max_pages: int = 10,
    ) -> list[dict[str, Any]]:
        """Get issues for a project with optional filters.

        Args:
            project_id: Project ID or path
            state: Issue state - "opened" (default), "closed", or "all"
            labels: Comma-separated label names to filter by
            assignee_id: Filter by assignee user ID
            milestone: Filter by milestone title
            per_page: Results per page (default: 20)
            max_pages: Maximum pages to fetch (default: 10)

        Returns:
            List of issue data dictionaries

        Raises:
            httpx.HTTPStatusError: If API request fails
        """
        encoded_id = self._encode_project_id(project_id)
        params: dict[str, Any] = {"state": state}

        if labels:
            params["labels"] = labels
        if assignee_id is not None:
            params["assignee_id"] = assignee_id
        if milestone:
            params["milestone"] = milestone

        return self.get_paginated(
            f"/projects/{encoded_id}/issues",
            params=params,
            per_page=per_page,
            max_pages=max_pages,
        )

    def get_issue(self, project_id: str, issue_iid: int) -> dict[str, Any]:
        """Get a specific issue by IID.

        Args:
            project_id: Project ID or path
            issue_iid: Issue IID (the #number)

        Returns:
            Issue data dictionary

        Raises:
            httpx.HTTPStatusError: If issue not found or request fails
        """
        encoded_id = self._encode_project_id(project_id)
        return self.get(f"/projects/{encoded_id}/issues/{issue_iid}")

    def create_issue(
        self,
        project_id: str,
        title: str,
        description: str | None = None,
        labels: str | None = None,
        assignee_ids: list[int] | None = None,
        milestone_id: int | None = None,
    ) -> dict[str, Any]:
        """Create a new issue.

        Args:
            project_id: Project ID or path
            title: Issue title (required)
            description: Issue description (optional, supports Markdown)
            labels: Comma-separated label names
            assignee_ids: List of user IDs to assign
            milestone_id: Milestone ID to assign

        Returns:
            Created issue data

        Raises:
            httpx.HTTPStatusError: If creation fails
        """
        encoded_id = self._encode_project_id(project_id)

        data: dict[str, Any] = {"title": title}

        if description:
            data["description"] = description
        if labels:
            data["labels"] = labels
        if assignee_ids:
            data["assignee_ids"] = assignee_ids
        if milestone_id is not None:
            data["milestone_id"] = milestone_id

        try:
            logger.info(f"Creating issue '{title}' in project {project_id}")
            response = self.client.post(
                f"/projects/{encoded_id}/issues",
                json=data,
            )
            response.raise_for_status()
            logger.info(f"Successfully created issue in project {project_id}")
            return response.json()
        except httpx.HTTPStatusError as e:
            error_detail = e.response.text[:500] if e.response.text else "No error details"
            logger.error(f"Failed to create issue in project {project_id}: {e.response.status_code} - {error_detail}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Network error while creating issue in project {project_id}: {e}")
            raise
        except Exception as e:
            logger.exception(f"Unexpected error while creating issue in project {project_id}: {e}")
            raise

    def update_issue(
        self,
        project_id: str,
        issue_iid: int,
        title: str | None = None,
        description: str | None = None,
        state_event: str | None = None,
        labels: str | None = None,
        assignee_ids: list[int] | None = None,
        milestone_id: int | None = None,
    ) -> dict[str, Any]:
        """Update an existing issue.

        Args:
            project_id: Project ID or path
            issue_iid: Issue IID
            title: New title (optional)
            description: New description (optional)
            state_event: "close" to close, "reopen" to reopen (optional)
            labels: New comma-separated label names (optional)
            assignee_ids: New list of assignee IDs (optional)
            milestone_id: New milestone ID (optional)

        Returns:
            Updated issue data

        Raises:
            httpx.HTTPStatusError: If update fails
        """
        encoded_id = self._encode_project_id(project_id)

        data: dict[str, Any] = {}

        if title:
            data["title"] = title
        if description is not None:
            data["description"] = description
        if state_event:
            data["state_event"] = state_event
        if labels is not None:
            data["labels"] = labels
        if assignee_ids is not None:
            data["assignee_ids"] = assignee_ids
        if milestone_id is not None:
            data["milestone_id"] = milestone_id

        try:
            logger.info(f"Updating issue #{issue_iid} in project {project_id}")
            response = self.client.put(
                f"/projects/{encoded_id}/issues/{issue_iid}",
                json=data,
            )
            response.raise_for_status()
            logger.info(f"Successfully updated issue #{issue_iid} in project {project_id}")
            return response.json()
        except httpx.HTTPStatusError as e:
            error_detail = e.response.text[:500] if e.response.text else "No error details"
            logger.error(
                f"Failed to update issue #{issue_iid} in project {project_id}: {e.response.status_code} - {error_detail}"
            )
            raise
        except httpx.RequestError as e:
            logger.error(f"Network error while updating issue #{issue_iid} in project {project_id}: {e}")
            raise
        except Exception as e:
            logger.exception(f"Unexpected error while updating issue #{issue_iid} in project {project_id}: {e}")
            raise

    def close_issue(self, project_id: str, issue_iid: int) -> dict[str, Any]:
        """Close an issue (convenience wrapper for update_issue).

        Args:
            project_id: Project ID or path
            issue_iid: Issue IID

        Returns:
            Updated issue data

        Raises:
            httpx.HTTPStatusError: If close fails
        """
        return self.update_issue(project_id, issue_iid, state_event="close")

    def get_issue_notes(self, project_id: str, issue_iid: int) -> list[dict[str, Any]]:
        """Get comments/notes on an issue.

        Args:
            project_id: Project ID or path
            issue_iid: Issue IID

        Returns:
            List of note data dictionaries

        Raises:
            httpx.HTTPStatusError: If request fails
        """
        encoded_id = self._encode_project_id(project_id)
        return self.get_paginated(f"/projects/{encoded_id}/issues/{issue_iid}/notes")

    def create_issue_note(self, project_id: str, issue_iid: int, body: str) -> dict[str, Any]:
        """Create a comment/note on an issue.

        Args:
            project_id: Project ID or path
            issue_iid: Issue IID
            body: Comment text (supports Markdown)

        Returns:
            Created note data

        Raises:
            httpx.HTTPStatusError: If creation fails
        """
        encoded_id = self._encode_project_id(project_id)

        data = {"body": body}

        try:
            logger.info(f"Creating note on issue #{issue_iid} in project {project_id}")
            response = self.client.post(
                f"/projects/{encoded_id}/issues/{issue_iid}/notes",
                json=data,
            )
            response.raise_for_status()
            logger.info(f"Successfully created note on issue #{issue_iid}")
            return response.json()
        except httpx.HTTPStatusError as e:
            error_detail = e.response.text[:500] if e.response.text else "No error details"
            logger.error(f"Failed to create note on issue #{issue_iid}: {e.response.status_code} - {error_detail}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Network error while creating note on issue #{issue_iid}: {e}")
            raise
        except Exception as e:
            logger.exception(f"Unexpected error while creating note on issue #{issue_iid}: {e}")
            raise
