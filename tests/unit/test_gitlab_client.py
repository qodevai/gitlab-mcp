"""Unit tests for GitLabClient."""

from unittest.mock import MagicMock, patch

import httpx
import pytest
from gitlab_client import APIError, ConfigurationError, NotFoundError


class TestGitLabClientInit:
    """Tests for GitLabClient initialization."""

    def test_init_requires_token(self) -> None:
        """Test that GitLabClient requires a token."""
        from gitlab_mcp import GitLabClient

        # Pass no token and ensure GITLAB_TOKEN env var is cleared
        with (
            patch.dict("os.environ", {"GITLAB_TOKEN": ""}, clear=False),
            pytest.raises(ConfigurationError, match="GITLAB_TOKEN"),
        ):
            GitLabClient(token=None, validate=False)

    def test_init_with_token_env_var(self, mock_env_vars: dict) -> None:
        """Test initialization with token from environment."""
        with patch("gitlab_client._base.httpx.Client"):
            from gitlab_mcp import GitLabClient

            client = GitLabClient(validate=False)
            assert client.token == mock_env_vars["GITLAB_TOKEN"]
            assert client.base_url == mock_env_vars["GITLAB_URL"]

    def test_init_with_explicit_token(self, mock_env_vars: dict) -> None:
        """Test initialization with explicitly passed token."""
        with patch("gitlab_client._base.httpx.Client"):
            from gitlab_mcp import GitLabClient

            client = GitLabClient(token="explicit-token", validate=False)
            assert client.token == "explicit-token"

    def test_init_invalid_url(self) -> None:
        """Test that invalid URL raises error."""
        with patch.dict("os.environ", {"GITLAB_TOKEN": "test", "GITLAB_URL": "invalid-url"}, clear=True):
            from gitlab_mcp import GitLabClient

            with pytest.raises(ConfigurationError, match="must start with http"):
                GitLabClient(validate=False)

    def test_init_strips_trailing_slash(self) -> None:
        """Test that trailing slash is stripped from base URL."""
        with (
            patch.dict("os.environ", {"GITLAB_TOKEN": "test", "GITLAB_URL": "https://gitlab.com/"}, clear=True),
            patch("gitlab_client._base.httpx.Client"),
        ):
            from gitlab_mcp import GitLabClient

            client = GitLabClient(validate=False)
            assert client.base_url == "https://gitlab.com"


class TestGitLabClientEncoding:
    """Tests for URL encoding."""

    def test_encode_project_id_simple(self) -> None:
        """Test encoding simple project ID."""
        from gitlab_mcp import GitLabClient

        encoded = GitLabClient._encode_project_id("123")
        assert encoded == "123"

    def test_encode_project_id_with_slash(self) -> None:
        """Test encoding project path with slash."""
        from gitlab_mcp import GitLabClient

        encoded = GitLabClient._encode_project_id("group/project")
        assert encoded == "group%2Fproject"

    def test_encode_project_id_nested(self) -> None:
        """Test encoding deeply nested project path."""
        from gitlab_mcp import GitLabClient

        encoded = GitLabClient._encode_project_id("org/group/subgroup/project")
        assert encoded == "org%2Fgroup%2Fsubgroup%2Fproject"


class TestGitLabClientRequests:
    """Tests for GitLabClient HTTP requests."""

    def test_get_success(self, mock_env_vars: dict, mock_httpx_client: MagicMock) -> None:
        """Test successful GET request."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"version": "16.0.0"}
        mock_response.raise_for_status = MagicMock()
        mock_httpx_client.get.return_value = mock_response

        from gitlab_mcp import GitLabClient

        client = GitLabClient(validate=False)
        result = client.get("/version")

        assert result == {"version": "16.0.0"}
        mock_httpx_client.get.assert_called_once_with("/version", params=None)

    def test_get_with_params(self, mock_env_vars: dict, mock_httpx_client: MagicMock) -> None:
        """Test GET request with query parameters."""
        mock_response = MagicMock()
        mock_response.json.return_value = []
        mock_response.raise_for_status = MagicMock()
        mock_httpx_client.get.return_value = mock_response

        from gitlab_mcp import GitLabClient

        client = GitLabClient(validate=False)
        client.get("/projects", params={"owned": True})

        mock_httpx_client.get.assert_called_once_with("/projects", params={"owned": True})

    def test_get_http_error_404(self, mock_env_vars: dict, mock_httpx_client: MagicMock) -> None:
        """Test GET request with 404 error raises NotFoundError."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not found"
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Not found", request=MagicMock(), response=mock_response
        )
        mock_httpx_client.get.return_value = mock_response

        from gitlab_mcp import GitLabClient

        client = GitLabClient(validate=False)

        with pytest.raises(NotFoundError):
            client.get("/nonexistent")

    def test_get_http_error_500(self, mock_env_vars: dict, mock_httpx_client: MagicMock) -> None:
        """Test GET request with 500 error raises APIError."""
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Server Error", request=MagicMock(), response=mock_response
        )
        mock_httpx_client.get.return_value = mock_response

        from gitlab_mcp import GitLabClient

        client = GitLabClient(validate=False)

        with pytest.raises(APIError):
            client.get("/error")


class TestGitLabClientPagination:
    """Tests for paginated requests."""

    def test_get_paginated_single_page(self, mock_env_vars: dict, mock_httpx_client: MagicMock) -> None:
        """Test pagination with single page of results."""
        mock_response = MagicMock()
        mock_response.json.return_value = [{"id": 1}, {"id": 2}]
        mock_response.raise_for_status = MagicMock()
        mock_response.headers = {}  # No x-next-page header
        mock_httpx_client.get.return_value = mock_response

        from gitlab_mcp import GitLabClient

        client = GitLabClient(validate=False)
        results = client.get_paginated("/projects")

        assert len(results) == 2
        assert results[0]["id"] == 1

    def test_get_paginated_multiple_pages(self, mock_env_vars: dict, mock_httpx_client: MagicMock) -> None:
        """Test pagination with multiple pages."""
        # First page
        mock_response1 = MagicMock()
        mock_response1.json.return_value = [{"id": 1}, {"id": 2}]
        mock_response1.raise_for_status = MagicMock()
        mock_response1.headers = {"x-next-page": "2"}

        # Second page
        mock_response2 = MagicMock()
        mock_response2.json.return_value = [{"id": 3}]
        mock_response2.raise_for_status = MagicMock()
        mock_response2.headers = {}  # No more pages

        mock_httpx_client.get.side_effect = [mock_response1, mock_response2]

        from gitlab_mcp import GitLabClient

        client = GitLabClient(validate=False)
        results = client.get_paginated("/projects")

        assert len(results) == 3
        assert mock_httpx_client.get.call_count == 2

    def test_get_paginated_respects_max_pages(self, mock_env_vars: dict, mock_httpx_client: MagicMock) -> None:
        """Test that max_pages limit is respected."""

        # Create responses that always have a next page
        def create_response():
            mock_response = MagicMock()
            mock_response.json.return_value = [{"id": 1}]
            mock_response.raise_for_status = MagicMock()
            mock_response.headers = {"x-next-page": "999"}
            return mock_response

        mock_httpx_client.get.side_effect = [create_response() for _ in range(10)]

        from gitlab_mcp import GitLabClient

        client = GitLabClient(validate=False)
        results = client.get_paginated("/projects", max_pages=3)

        assert len(results) == 3
        assert mock_httpx_client.get.call_count == 3

    def test_get_paginated_empty_results(self, mock_env_vars: dict, mock_httpx_client: MagicMock) -> None:
        """Test pagination with empty results."""
        mock_response = MagicMock()
        mock_response.json.return_value = []
        mock_response.raise_for_status = MagicMock()
        mock_response.headers = {}
        mock_httpx_client.get.return_value = mock_response

        from gitlab_mcp import GitLabClient

        client = GitLabClient(validate=False)
        results = client.get_paginated("/projects")

        assert results == []


class TestGitLabClientMethods:
    """Tests for specific GitLabClient methods."""

    def test_get_project(self, mock_env_vars: dict, mock_httpx_client: MagicMock, sample_project: dict) -> None:
        """Test getting a specific project."""
        mock_response = MagicMock()
        mock_response.json.return_value = sample_project
        mock_response.raise_for_status = MagicMock()
        mock_httpx_client.get.return_value = mock_response

        from gitlab_mcp import GitLabClient

        client = GitLabClient(validate=False)
        result = client.get_project("group/test-project")

        assert result["name"] == "test-project"
        # Check that the project ID was properly encoded
        call_args = mock_httpx_client.get.call_args
        assert "group%2Ftest-project" in call_args[0][0]

    def test_get_merge_request(
        self, mock_env_vars: dict, mock_httpx_client: MagicMock, sample_merge_request: dict
    ) -> None:
        """Test getting a specific merge request."""
        mock_response = MagicMock()
        mock_response.json.return_value = sample_merge_request
        mock_response.raise_for_status = MagicMock()
        mock_httpx_client.get.return_value = mock_response

        from gitlab_mcp import GitLabClient

        client = GitLabClient(validate=False)
        result = client.get_merge_request("123", 1)

        assert result["title"] == "Add new feature"
        assert result["iid"] == 1

    def test_get_pipelines(self, mock_env_vars: dict, mock_httpx_client: MagicMock, sample_pipeline: dict) -> None:
        """Test getting pipelines with default limit of 3."""
        mock_response = MagicMock()
        mock_response.json.return_value = [sample_pipeline]
        mock_response.raise_for_status = MagicMock()
        mock_response.headers = {}
        mock_httpx_client.get.return_value = mock_response

        from gitlab_mcp import GitLabClient

        client = GitLabClient(validate=False)
        result = client.get_pipelines("123")

        assert len(result) == 1
        assert result[0]["status"] == "success"
        # Verify per_page was set to 3 (default for pipelines)
        call_args = mock_httpx_client.get.call_args
        assert call_args[1]["params"]["per_page"] == 3


class TestDiscussionFiltering:
    """Tests for discussion filtering helpers."""

    def test_is_user_discussion_with_user_note(self) -> None:
        """User notes should return True."""
        from gitlab_mcp import is_user_discussion

        discussion = {"notes": [{"system": False, "body": "LGTM"}]}
        assert is_user_discussion(discussion) is True

    def test_is_user_discussion_with_system_note(self) -> None:
        """System notes should return False."""
        from gitlab_mcp import is_user_discussion

        discussion = {"notes": [{"system": True, "body": "assigned to @user"}]}
        assert is_user_discussion(discussion) is False

    def test_is_user_discussion_with_empty_notes(self) -> None:
        """Empty discussions should return False."""
        from gitlab_mcp import is_user_discussion

        discussion = {"notes": []}
        assert is_user_discussion(discussion) is False

    def test_is_user_discussion_missing_system_field(self) -> None:
        """Missing 'system' field should default to user note (backward compatible)."""
        from gitlab_mcp import is_user_discussion

        discussion = {"notes": [{"body": "Comment"}]}
        assert is_user_discussion(discussion) is True

    def test_filter_actionable_discussions(self) -> None:
        """Should only include unresolved, resolvable user discussions."""
        from gitlab_mcp import filter_actionable_discussions

        discussions = [
            {"notes": [{"system": False, "resolvable": True, "resolved": False, "body": "Fix this"}]},  # KEEP
            {"notes": [{"system": False, "resolvable": True, "resolved": True, "body": "Done"}]},  # EXCLUDE (resolved)
            {
                "notes": [{"system": True, "resolvable": True, "resolved": False, "body": "assigned"}]
            },  # EXCLUDE (system)
            {"notes": [{"system": True, "resolvable": True, "resolved": True, "body": "merged"}]},  # EXCLUDE (both)
            {"notes": []},  # EXCLUDE (empty)
        ]
        result = filter_actionable_discussions(discussions)
        assert len(result) == 1
        assert result[0]["notes"][0]["body"] == "Fix this"

    def test_filter_actionable_discussions_excludes_non_resolvable(self) -> None:
        """Should exclude discussions that are not resolvable (like individual_note comments)."""
        from gitlab_mcp import filter_actionable_discussions

        discussions = [
            # individual_note comments have resolvable=false and should be excluded
            {"notes": [{"system": False, "resolvable": False, "resolved": False, "body": "Summary comment"}]},
            {"notes": [{"system": False, "resolvable": False, "resolved": False, "body": "Ship it!"}]},
            # Resolvable DiffNote discussion that IS unresolved - should be kept
            {"notes": [{"system": False, "resolvable": True, "resolved": False, "body": "Fix this bug"}]},
            # Resolvable DiffNote discussion that is resolved - should be excluded
            {"notes": [{"system": False, "resolvable": True, "resolved": True, "body": "Fixed"}]},
        ]
        result = filter_actionable_discussions(discussions)
        assert len(result) == 1
        assert result[0]["notes"][0]["body"] == "Fix this bug"

    def test_filter_actionable_discussions_backward_compatible(self) -> None:
        """Should handle old API format without 'resolvable' field (defaults to false = excluded)."""
        from gitlab_mcp import filter_actionable_discussions

        # Without resolvable field, defaults to False and should be excluded
        discussions = [{"notes": [{"resolved": False, "body": "Comment"}]}]
        result = filter_actionable_discussions(discussions)
        assert len(result) == 0  # Should exclude (not resolvable)


class TestMergeRequestOperations:
    """Tests for merge request operations."""

    def test_close_mr_success(
        self, mock_env_vars: dict, mock_httpx_client: MagicMock, sample_merge_request: dict
    ) -> None:
        """Test successfully closing a merge request."""
        closed_mr = {**sample_merge_request, "state": "closed"}
        mock_response = MagicMock()
        mock_response.json.return_value = closed_mr
        mock_response.raise_for_status = MagicMock()
        mock_httpx_client.put.return_value = mock_response

        from gitlab_mcp import GitLabClient

        client = GitLabClient(validate=False)
        result = client.close_mr("123", 1)

        assert result["state"] == "closed"
        assert result["iid"] == 1
        # Verify PUT request was made with correct parameters
        mock_httpx_client.put.assert_called_once()
        call_args = mock_httpx_client.put.call_args
        assert "123/merge_requests/1" in call_args[0][0]
        assert call_args[1]["json"]["state_event"] == "close"

    def test_create_mr_note_success(self, mock_env_vars: dict, mock_httpx_client: MagicMock, sample_note: dict) -> None:
        """Test successfully creating a note/comment on a merge request."""
        mock_response = MagicMock()
        mock_response.json.return_value = sample_note
        mock_response.raise_for_status = MagicMock()
        mock_httpx_client.post.return_value = mock_response

        from gitlab_mcp import GitLabClient

        client = GitLabClient(validate=False)
        result = client.create_mr_note("123", 1, "LGTM!")

        assert result["body"] == "Closing this MR"
        assert result["id"] == 2001
        # Verify POST request was made with correct parameters
        mock_httpx_client.post.assert_called_once()
        call_args = mock_httpx_client.post.call_args
        assert "123/merge_requests/1/notes" in call_args[0][0]
        assert call_args[1]["json"]["body"] == "LGTM!"

    def test_close_mr_http_error(self, mock_env_vars: dict, mock_httpx_client: MagicMock) -> None:
        """Test close_mr handles HTTP errors correctly."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = '{"message": "Not found"}'
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Not found", request=MagicMock(), response=mock_response
        )
        mock_httpx_client.put.return_value = mock_response

        from gitlab_mcp import GitLabClient

        client = GitLabClient(validate=False)
        with pytest.raises(NotFoundError):
            client.close_mr("123", 999)

    def test_create_mr_note_http_error(self, mock_env_vars: dict, mock_httpx_client: MagicMock) -> None:
        """Test create_mr_note handles HTTP errors correctly."""
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.text = '{"message": "Forbidden"}'
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Forbidden", request=MagicMock(), response=mock_response
        )
        mock_httpx_client.post.return_value = mock_response

        from gitlab_mcp import GitLabClient

        client = GitLabClient(validate=False)
        with pytest.raises(APIError):
            client.create_mr_note("123", 1, "Comment")


class TestJobOperations:
    """Tests for job operations."""

    def test_retry_job_success(self, mock_env_vars: dict, mock_httpx_client: MagicMock, sample_job: dict) -> None:
        """Test successfully retrying a job."""
        new_job = {**sample_job, "id": 1002, "status": "pending"}
        mock_response = MagicMock()
        mock_response.json.return_value = new_job
        mock_response.raise_for_status = MagicMock()
        mock_httpx_client.post.return_value = mock_response

        from gitlab_mcp import GitLabClient

        client = GitLabClient(validate=False)
        result = client.retry_job("123", 1001)

        assert result["id"] == 1002
        assert result["status"] == "pending"
        # Verify POST request was made with correct endpoint
        mock_httpx_client.post.assert_called_once()
        call_args = mock_httpx_client.post.call_args
        assert "123/jobs/1001/retry" in call_args[0][0]

    def test_retry_job_http_error(self, mock_env_vars: dict, mock_httpx_client: MagicMock) -> None:
        """Test retry_job handles HTTP errors correctly."""
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.text = '{"message": "Forbidden"}'
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Forbidden", request=MagicMock(), response=mock_response
        )
        mock_httpx_client.post.return_value = mock_response

        from gitlab_mcp import GitLabClient

        client = GitLabClient(validate=False)
        with pytest.raises(APIError):
            client.retry_job("123", 1001)

    def test_retry_job_not_found(self, mock_env_vars: dict, mock_httpx_client: MagicMock) -> None:
        """Test retry_job handles 404 not found correctly."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = '{"message": "Job not found"}'
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Not found", request=MagicMock(), response=mock_response
        )
        mock_httpx_client.post.return_value = mock_response

        from gitlab_mcp import GitLabClient

        client = GitLabClient(validate=False)
        with pytest.raises(NotFoundError):
            client.retry_job("123", 99999)

    def test_retry_job_encodes_project_path(
        self, mock_env_vars: dict, mock_httpx_client: MagicMock, sample_job: dict
    ) -> None:
        """Test retry_job properly encodes project path with slashes."""
        new_job = {**sample_job, "id": 1002, "status": "pending"}
        mock_response = MagicMock()
        mock_response.json.return_value = new_job
        mock_response.raise_for_status = MagicMock()
        mock_httpx_client.post.return_value = mock_response

        from gitlab_mcp import GitLabClient

        client = GitLabClient(validate=False)
        client.retry_job("group/project", 1001)

        # Verify project path was URL-encoded
        call_args = mock_httpx_client.post.call_args
        assert "group%2Fproject/jobs/1001/retry" in call_args[0][0]


class TestFileUploadOperations:
    """Tests for file upload operations.

    Note: These tests work with individual GitLabClient instances created with validate=False.
    They don't test the global gitlab_client which requires mocking at import time.
    """

    def test_upload_file_from_path(self, mock_env_vars: dict, mock_httpx_client: MagicMock, tmp_path) -> None:
        """Test uploading a file from filesystem path."""
        # Create a test file
        test_file = tmp_path / "test_image.png"
        test_file.write_bytes(b"fake image content")

        upload_response = {
            "id": 5,
            "alt": "test_image",
            "url": "/uploads/abc123/test_image.png",
            "full_path": "/-/project/123/uploads/abc123/test_image.png",
            "markdown": "![test_image](/uploads/abc123/test_image.png)",
        }

        with patch("gitlab_client._files.httpx.post") as mock_post:
            mock_response = MagicMock()
            mock_response.json.return_value = upload_response
            mock_response.raise_for_status = MagicMock()
            mock_post.return_value = mock_response

            from gitlab_mcp import GitLabClient

            client = GitLabClient(validate=False)
            result = client.upload_file("123", {"path": str(test_file)})

            assert result["markdown"] == "![test_image](/uploads/abc123/test_image.png)"
            assert result["url"] == "/uploads/abc123/test_image.png"

            # Verify the POST was called with correct parameters
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert "123/uploads" in call_args[0][0]
            assert "files" in call_args[1]

    def test_upload_file_from_base64(self, mock_env_vars: dict, mock_httpx_client: MagicMock) -> None:
        """Test uploading a file from base64-encoded data."""
        import base64

        upload_response = {
            "id": 6,
            "alt": "screenshot",
            "url": "/uploads/def456/screenshot.png",
            "full_path": "/-/project/123/uploads/def456/screenshot.png",
            "markdown": "![screenshot](/uploads/def456/screenshot.png)",
        }

        with patch("gitlab_client._files.httpx.post") as mock_post:
            mock_response = MagicMock()
            mock_response.json.return_value = upload_response
            mock_response.raise_for_status = MagicMock()
            mock_post.return_value = mock_response

            from gitlab_mcp import GitLabClient

            client = GitLabClient(validate=False)
            b64_data = base64.b64encode(b"test data").decode()
            result = client.upload_file("123", {"base64": b64_data, "filename": "screenshot.png"})

            assert result["markdown"] == "![screenshot](/uploads/def456/screenshot.png)"

    def test_upload_file_invalid_base64(self, mock_env_vars: dict, mock_httpx_client: MagicMock) -> None:
        """Test that invalid base64 data raises ValueError."""
        from gitlab_mcp import GitLabClient

        client = GitLabClient(validate=False)

        with pytest.raises(ValueError, match="Invalid base64"):
            client.upload_file("123", {"base64": "not-valid-base64!!!", "filename": "test.png"})

    def test_upload_file_file_not_found(self, mock_env_vars: dict, mock_httpx_client: MagicMock) -> None:
        """Test that non-existent file path raises FileNotFoundError."""
        from gitlab_mcp import GitLabClient

        client = GitLabClient(validate=False)

        with pytest.raises(FileNotFoundError):
            client.upload_file("123", {"path": "/nonexistent/file.png"})

    def test_upload_file_http_error(self, mock_env_vars: dict, mock_httpx_client: MagicMock, tmp_path) -> None:
        """Test that HTTP errors are raised as APIError."""
        test_file = tmp_path / "test.png"
        test_file.write_bytes(b"content")

        with patch("gitlab_client._files.httpx.post") as mock_post:
            mock_response = MagicMock()
            mock_response.status_code = 413
            mock_response.text = "File too large"
            mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
                "Too large", request=MagicMock(), response=mock_response
            )
            mock_post.return_value = mock_response

            from gitlab_mcp import GitLabClient

            client = GitLabClient(validate=False)

            with pytest.raises(APIError):
                client.upload_file("123", {"path": str(test_file)})


class TestProcessImages:
    """Tests for process_images helper function.

    Note: process_images uses the global gitlab_client, so these tests
    mock gitlab_client after the module is imported.
    """

    def test_process_images_empty_list(self, mock_env_vars: dict, mock_httpx_client: MagicMock) -> None:
        """Test that empty images list returns empty string."""
        from gitlab_mcp import process_images

        result = process_images("123", [])
        assert result == ""

    def test_process_images_none(self, mock_env_vars: dict, mock_httpx_client: MagicMock) -> None:
        """Test that None images returns empty string."""
        from gitlab_mcp import process_images

        result = process_images("123", None)
        assert result == ""

    def test_process_images_single_image(self, mock_env_vars: dict, mock_httpx_client: MagicMock, tmp_path) -> None:
        """Test processing a single image."""
        test_file = tmp_path / "image.png"
        test_file.write_bytes(b"image data")

        upload_response = {
            "alt": "image",
            "url": "/uploads/abc/image.png",
            "markdown": "![image](/uploads/abc/image.png)",
        }

        with patch("gitlab_mcp.gitlab_client") as mock_client:
            mock_client.upload_file.return_value = upload_response

            from gitlab_mcp import process_images

            result = process_images("123", [{"path": str(test_file)}])

            assert result == "\n\n![image](/uploads/abc/image.png)"

    def test_process_images_with_custom_alt(self, mock_env_vars: dict, mock_httpx_client: MagicMock, tmp_path) -> None:
        """Test that custom alt text is used."""
        test_file = tmp_path / "screenshot.png"
        test_file.write_bytes(b"image data")

        upload_response = {
            "alt": "screenshot",
            "url": "/uploads/abc/screenshot.png",
        }

        with patch("gitlab_mcp.gitlab_client") as mock_client:
            mock_client.upload_file.return_value = upload_response

            from gitlab_mcp import process_images

            result = process_images("123", [{"path": str(test_file), "alt": "My custom alt text"}])

            assert "![My custom alt text]" in result

    def test_process_images_multiple(self, mock_env_vars: dict, mock_httpx_client: MagicMock, tmp_path) -> None:
        """Test processing multiple images."""
        test_file1 = tmp_path / "img1.png"
        test_file2 = tmp_path / "img2.png"
        test_file1.write_bytes(b"image1")
        test_file2.write_bytes(b"image2")

        upload_responses = [
            {"alt": "img1", "url": "/uploads/a/img1.png"},
            {"alt": "img2", "url": "/uploads/b/img2.png"},
        ]

        with patch("gitlab_mcp.gitlab_client") as mock_client:
            mock_client.upload_file.side_effect = upload_responses

            from gitlab_mcp import process_images

            result = process_images("123", [{"path": str(test_file1)}, {"path": str(test_file2)}])

            assert "![img1]" in result
            assert "![img2]" in result
            assert result.startswith("\n\n")

    def test_process_images_from_base64(self, mock_env_vars: dict, mock_httpx_client: MagicMock) -> None:
        """Test processing image from base64."""
        import base64

        upload_response = {
            "alt": "encoded",
            "url": "/uploads/xyz/encoded.png",
        }

        with patch("gitlab_mcp.gitlab_client") as mock_client:
            mock_client.upload_file.return_value = upload_response

            from gitlab_mcp import process_images

            b64_data = base64.b64encode(b"test").decode()
            result = process_images("123", [{"base64": b64_data, "filename": "encoded.png"}])

            assert "![encoded]" in result
