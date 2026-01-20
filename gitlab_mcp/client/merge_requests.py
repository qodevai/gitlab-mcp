"""Merge request client mixin."""

import json
import logging
from typing import Any

import httpx

from gitlab_mcp.client.base import BaseClientMixin
from gitlab_mcp.models import DiffPosition

logger = logging.getLogger(__name__)


class MergeRequestsMixin(BaseClientMixin):
    """Mixin for merge request operations."""

    def get_merge_requests(self, project_id: str, state: str = "opened") -> list[dict[str, Any]]:
        """Get merge requests for a project."""
        encoded_id = self._encode_project_id(project_id)
        params = {"state": state}
        return self.get_paginated(f"/projects/{encoded_id}/merge_requests", params=params)

    def get_merge_request(self, project_id: str, mr_iid: int) -> dict[str, Any]:
        """Get a specific merge request."""
        encoded_id = self._encode_project_id(project_id)
        return self.get(f"/projects/{encoded_id}/merge_requests/{mr_iid}")

    def get_mr_discussions(self, project_id: str, mr_iid: int) -> list[dict[str, Any]]:
        """Get all discussions (comments/threads) for a merge request."""
        encoded_id = self._encode_project_id(project_id)
        return self.get_paginated(f"/projects/{encoded_id}/merge_requests/{mr_iid}/discussions")

    def get_mr_changes(self, project_id: str, mr_iid: int) -> dict[str, Any]:
        """Get the diff/changes for a merge request."""
        encoded_id = self._encode_project_id(project_id)
        return self.get(f"/projects/{encoded_id}/merge_requests/{mr_iid}/changes")

    def get_mr_commits(self, project_id: str, mr_iid: int) -> list[dict[str, Any]]:
        """Get commits for a merge request."""
        encoded_id = self._encode_project_id(project_id)
        return self.get_paginated(f"/projects/{encoded_id}/merge_requests/{mr_iid}/commits")

    def get_mr_approvals(self, project_id: str, mr_iid: int) -> dict[str, Any]:
        """Get approval status for a merge request."""
        encoded_id = self._encode_project_id(project_id)
        return self.get(f"/projects/{encoded_id}/merge_requests/{mr_iid}/approvals")

    def get_mr_pipelines(self, project_id: str, mr_iid: int) -> list[dict[str, Any]]:
        """Get pipelines for a merge request."""
        encoded_id = self._encode_project_id(project_id)
        return self.get(f"/projects/{encoded_id}/merge_requests/{mr_iid}/pipelines")

    def create_mr_note(self, project_id: str, mr_iid: int, body: str) -> dict[str, Any]:
        """Create a comment/note on a merge request.

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

    def reply_to_discussion(self, project_id: str, mr_iid: int, discussion_id: str, body: str) -> dict[str, Any]:
        """Reply to an existing discussion thread on a merge request.

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

    def create_mr_discussion(
        self,
        project_id: str,
        mr_iid: int,
        body: str,
        position: DiffPosition | None = None,
    ) -> dict[str, Any]:
        """Create a discussion on a merge request, optionally as an inline comment on a specific line.

        Args:
            project_id: Project ID or path
            mr_iid: Merge request IID
            body: Comment text (supports Markdown)
            position: Position for inline comments (file path, line numbers, and commit SHAs)

        Returns:
            Created discussion data

        Raises:
            httpx.HTTPStatusError: If discussion creation fails
        """
        encoded_id = self._encode_project_id(project_id)

        data: dict[str, Any] = {"body": body}

        if position:
            gitlab_position: dict[str, Any] = {
                "position_type": "text",
                "new_path": position["file_path"],
                "old_path": position["file_path"],
            }
            if "new_line" in position:
                gitlab_position["new_line"] = position["new_line"]
            if "old_line" in position:
                gitlab_position["old_line"] = position["old_line"]
            if "base_sha" in position:
                gitlab_position["base_sha"] = position["base_sha"]
            if "head_sha" in position:
                gitlab_position["head_sha"] = position["head_sha"]
            if "start_sha" in position:
                gitlab_position["start_sha"] = position["start_sha"]
            data["position"] = gitlab_position

        try:
            if position:
                logger.info(
                    f"Creating inline discussion on {position['file_path']} in MR !{mr_iid} in project {project_id}"
                )
            else:
                logger.info(f"Creating discussion on MR !{mr_iid} in project {project_id}")
            response = self.client.post(
                f"/projects/{encoded_id}/merge_requests/{mr_iid}/discussions",
                json=data,
            )
            response.raise_for_status()
            logger.info(f"Successfully created discussion on MR !{mr_iid}")
            return response.json()
        except httpx.HTTPStatusError as e:
            error_detail = e.response.text[:500] if e.response.text else "No error details"
            logger.error(f"Failed to create discussion on MR !{mr_iid}: {e.response.status_code} - {error_detail}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Network error while creating discussion on MR !{mr_iid}: {e}")
            raise
        except Exception as e:
            logger.exception(f"Unexpected error while creating discussion on MR !{mr_iid}: {e}")
            raise

    def resolve_discussion(self, project_id: str, mr_iid: int, discussion_id: str, resolved: bool) -> dict[str, Any]:
        """Resolve or unresolve a discussion thread on a merge request.

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
        """Create a new merge request.

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
        """Merge a merge request.

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
            raise error from e
        except httpx.RequestError as e:
            logger.error(f"Network error while merging MR !{mr_iid}: {e}")
            raise
        except Exception as e:
            logger.exception(f"Unexpected error while merging MR !{mr_iid}: {e}")
            raise

    def close_mr(self, project_id: str, mr_iid: int) -> dict[str, Any]:
        """Close a merge request.

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
            logger.error(f"Failed to close MR !{mr_iid}: {e.response.status_code} - {error_detail}")
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
        """Update a merge request.

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
            logger.error(f"Failed to update MR !{mr_iid}: {e.response.status_code} - {error_detail}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Network error while updating MR !{mr_iid}: {e}")
            raise
        except Exception as e:
            logger.exception(f"Unexpected error while updating MR !{mr_iid}: {e}")
            raise
