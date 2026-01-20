"""File operations client mixin."""

import base64
import binascii
import logging
import os
from typing import Any, cast
from urllib.parse import quote

import httpx

from gitlab_mcp.client.base import BaseClientMixin
from gitlab_mcp.models import FileFromPath, FileSource

logger = logging.getLogger(__name__)


class FilesMixin(BaseClientMixin):
    """Mixin for file operations."""

    def get_file_content(self, project_id: str, file_path: str, ref: str) -> str:
        """Get raw file content at a specific ref (commit SHA, branch, tag).

        Args:
            project_id: Project ID or path
            file_path: Path to file in repository
            ref: Git ref (commit SHA, branch name, or tag)

        Returns:
            Raw file content as string

        Raises:
            httpx.HTTPStatusError: If file not found or API request fails
        """
        encoded_id = self._encode_project_id(project_id)
        encoded_path = quote(file_path, safe="")
        try:
            logger.debug(f"GET /projects/{encoded_id}/repository/files/{encoded_path}/raw?ref={ref}")
            response = self.client.get(
                f"/projects/{encoded_id}/repository/files/{encoded_path}/raw",
                params={"ref": ref},
            )
            response.raise_for_status()
            return response.text
        except httpx.HTTPStatusError as e:
            logger.error(f"GitLab API error fetching file {file_path} at {ref}: {e.response.status_code}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Network error fetching file {file_path} at {ref}: {e}")
            raise
        except Exception as e:
            logger.exception(f"Unexpected error fetching file {file_path} at {ref}: {e}")
            raise

    def upload_file(self, project_id: str, source: FileSource) -> dict[str, Any]:
        """Upload a file to GitLab for use in markdown.

        Uses the GitLab Markdown Uploads API to upload a file that can be
        embedded in issues, merge requests, comments, or releases.

        Args:
            project_id: Project ID or path
            source: Either FileFromPath ({"path": "/local/file.png"}) or
                    FileFromBase64 ({"base64": "...", "filename": "name.png"})

        Returns:
            Dict with: id, alt, url, full_path, markdown
            The 'markdown' field contains a ready-to-use markdown image tag.

        Raises:
            FileNotFoundError: If file_path doesn't exist
            ValueError: If base64 data is invalid
            httpx.HTTPStatusError: If upload fails
        """
        encoded_id = self._encode_project_id(project_id)

        if "path" in source:
            # FileFromPath variant - read file from disk
            file_path = cast(FileFromPath, source)["path"]
            with open(file_path, "rb") as f:
                file_content = f.read()
            filename = os.path.basename(file_path)
        else:
            # FileFromBase64 variant - decode base64
            try:
                file_content = base64.b64decode(source["base64"], validate=True)
            except binascii.Error as e:
                raise ValueError(f"Invalid base64 data: {e}") from e
            filename = source["filename"]

        # Use separate request without JSON Content-Type header
        # The default self.client has Content-Type: application/json which breaks multipart
        files = {"file": (filename, file_content)}
        try:
            logger.info(f"Uploading file '{filename}' to project {project_id}")
            response = httpx.post(
                f"{self.api_url}/projects/{encoded_id}/uploads",
                files=files,
                headers={"PRIVATE-TOKEN": str(self.token)},
                timeout=30.0,
            )
            response.raise_for_status()
            result = response.json()
            logger.info(f"Successfully uploaded file '{filename}' to project {project_id}")
            return result
        except httpx.HTTPStatusError as e:
            error_detail = e.response.text[:500] if e.response.text else "No error details"
            logger.error(f"Failed to upload file '{filename}': {e.response.status_code} - {error_detail}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Network error while uploading file '{filename}': {e}")
            raise
        except Exception as e:
            logger.exception(f"Unexpected error while uploading file '{filename}': {e}")
            raise
