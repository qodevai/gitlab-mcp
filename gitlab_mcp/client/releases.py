"""Release client mixin."""

import logging
from typing import Any
from urllib.parse import quote

import httpx

from gitlab_mcp.client.base import BaseClientMixin

logger = logging.getLogger(__name__)


class ReleasesMixin(BaseClientMixin):
    """Mixin for release operations."""

    def get_releases(self, project_id: str, order_by: str = "released_at", sort: str = "desc") -> list[dict[str, Any]]:
        """Get all releases for a project.

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
        """Get a specific release by tag name.

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
        encoded_tag = quote(tag_name, safe="")
        return self.get(f"/projects/{encoded_id}/releases/{encoded_tag}")

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
        """Create a new release.

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
            logger.error(
                f"Failed to create release '{tag_name}' in project {project_id}: {e.response.status_code} - {error_detail}"
            )
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
        """Update an existing release.

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
            logger.error(
                f"Failed to update release '{tag_name}' in project {project_id}: {e.response.status_code} - {error_detail}"
            )
            raise
        except httpx.RequestError as e:
            logger.error(f"Network error while updating release '{tag_name}' in project {project_id}: {e}")
            raise
        except Exception as e:
            logger.exception(f"Unexpected error while updating release '{tag_name}' in project {project_id}: {e}")
            raise

    def delete_release(self, project_id: str, tag_name: str) -> None:
        """Delete a release (note: does not delete the associated tag).

        Args:
            project_id: Project ID or path
            tag_name: Tag name of the release to delete

        Raises:
            httpx.HTTPStatusError: If release deletion fails
        """
        encoded_id = self._encode_project_id(project_id)

        # Tag name needs to be URL encoded
        encoded_tag = quote(tag_name, safe="")

        try:
            logger.info(f"Deleting release '{tag_name}' in project {project_id}")
            response = self.client.delete(f"/projects/{encoded_id}/releases/{encoded_tag}")
            response.raise_for_status()
            logger.info(f"Successfully deleted release '{tag_name}' in project {project_id} (tag preserved)")
        except httpx.HTTPStatusError as e:
            error_detail = e.response.text[:500] if e.response.text else "No error details"
            logger.error(
                f"Failed to delete release '{tag_name}' in project {project_id}: {e.response.status_code} - {error_detail}"
            )
            raise
        except httpx.RequestError as e:
            logger.error(f"Network error while deleting release '{tag_name}' in project {project_id}: {e}")
            raise
        except Exception as e:
            logger.exception(f"Unexpected error while deleting release '{tag_name}' in project {project_id}: {e}")
            raise
