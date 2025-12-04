"""Unit tests for GitLabClient."""

from unittest.mock import MagicMock, patch

import httpx
import pytest


class TestGitLabClientInit:
    """Tests for GitLabClient initialization."""

    def test_init_requires_token(self) -> None:
        """Test that GitLabClient requires a token."""
        from gitlab_mcp import GitLabClient

        # Pass no token and ensure GITLAB_TOKEN env var is cleared
        with (
            patch.dict("os.environ", {"GITLAB_TOKEN": ""}, clear=False),
            pytest.raises(ValueError, match="GITLAB_TOKEN"),
        ):
            GitLabClient(token=None, validate=False)

    def test_init_with_token_env_var(self, mock_env_vars: dict) -> None:
        """Test initialization with token from environment."""
        with patch("gitlab_mcp.httpx.Client"):
            from gitlab_mcp import GitLabClient

            client = GitLabClient(validate=False)
            assert client.token == mock_env_vars["GITLAB_TOKEN"]
            assert client.base_url == mock_env_vars["GITLAB_URL"]

    def test_init_with_explicit_token(self, mock_env_vars: dict) -> None:
        """Test initialization with explicitly passed token."""
        with patch("gitlab_mcp.httpx.Client"):
            from gitlab_mcp import GitLabClient

            client = GitLabClient(token="explicit-token", validate=False)
            assert client.token == "explicit-token"

    def test_init_invalid_url(self) -> None:
        """Test that invalid URL raises error."""
        with patch.dict("os.environ", {"GITLAB_TOKEN": "test", "GITLAB_URL": "invalid-url"}, clear=True):
            from gitlab_mcp import GitLabClient

            with pytest.raises(ValueError, match="must start with http"):
                GitLabClient(validate=False)

    def test_init_strips_trailing_slash(self) -> None:
        """Test that trailing slash is stripped from base URL."""
        with (
            patch.dict("os.environ", {"GITLAB_TOKEN": "test", "GITLAB_URL": "https://gitlab.com/"}, clear=True),
            patch("gitlab_mcp.httpx.Client"),
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

    def test_get_http_error(self, mock_env_vars: dict, mock_httpx_client: MagicMock) -> None:
        """Test GET request with HTTP error."""
        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_response.text = "Not found"
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Not found", request=MagicMock(), response=mock_response
        )
        mock_httpx_client.get.return_value = mock_response

        from gitlab_mcp import GitLabClient

        client = GitLabClient(validate=False)

        with pytest.raises(httpx.HTTPStatusError):
            client.get("/nonexistent")


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
