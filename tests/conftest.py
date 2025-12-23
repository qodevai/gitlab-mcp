"""Shared test fixtures for gitlab-mcp tests."""

import os
from collections.abc import Generator
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_env_vars() -> Generator[dict[str, str], None, None]:
    """Set up test environment variables."""
    env = {
        "GITLAB_TOKEN": "test-token-12345",
        "GITLAB_URL": "https://gitlab.example.com",
    }
    with patch.dict(os.environ, env, clear=False):
        yield env


@pytest.fixture
def mock_httpx_client() -> Generator[MagicMock, None, None]:
    """Mock httpx.Client for unit tests."""
    with patch("gitlab_mcp.httpx.Client") as mock_client_class:
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        yield mock_client


@pytest.fixture
def sample_project() -> dict:
    """Sample GitLab project response."""
    return {
        "id": 123,
        "name": "test-project",
        "path_with_namespace": "group/test-project",
        "web_url": "https://gitlab.example.com/group/test-project",
        "default_branch": "main",
        "description": "A test project",
        "visibility": "private",
        "squash_option": "default_on",
    }


@pytest.fixture
def sample_merge_request() -> dict:
    """Sample GitLab merge request response."""
    return {
        "id": 456,
        "iid": 1,
        "title": "Add new feature",
        "description": "This MR adds a new feature",
        "state": "opened",
        "source_branch": "feature-branch",
        "target_branch": "main",
        "author": {"id": 1, "username": "testuser", "name": "Test User"},
        "web_url": "https://gitlab.example.com/group/test-project/-/merge_requests/1",
        "draft": False,
        "merge_status": "can_be_merged",
        "has_conflicts": False,
    }


@pytest.fixture
def sample_pipeline() -> dict:
    """Sample GitLab pipeline response."""
    return {
        "id": 789,
        "iid": 10,
        "status": "success",
        "ref": "main",
        "sha": "abc123def456",
        "web_url": "https://gitlab.example.com/group/test-project/-/pipelines/789",
        "created_at": "2024-01-15T10:00:00Z",
        "updated_at": "2024-01-15T10:15:00Z",
    }


@pytest.fixture
def sample_job() -> dict:
    """Sample GitLab job response."""
    return {
        "id": 1001,
        "name": "test",
        "status": "success",
        "stage": "test",
        "web_url": "https://gitlab.example.com/group/test-project/-/jobs/1001",
        "duration": 120.5,
        "started_at": "2024-01-15T10:00:00Z",
        "finished_at": "2024-01-15T10:02:00Z",
    }


@pytest.fixture
def sample_discussion() -> dict:
    """Sample GitLab discussion response."""
    return {
        "id": "abc123",
        "individual_note": False,
        "notes": [
            {
                "id": 1,
                "body": "This looks good!",
                "author": {"username": "reviewer", "name": "Reviewer"},
                "created_at": "2024-01-15T10:00:00Z",
                "resolvable": True,
                "resolved": False,
            }
        ],
    }


@pytest.fixture
def sample_issue() -> dict:
    """Sample GitLab issue response."""
    return {
        "id": 999,
        "iid": 42,
        "title": "Bug in login",
        "description": "Users cannot log in",
        "state": "opened",
        "author": {"id": 1, "username": "testuser", "name": "Test User"},
        "web_url": "https://gitlab.example.com/group/test-project/-/issues/42",
        "labels": ["bug"],
        "created_at": "2024-01-15T10:00:00Z",
    }


@pytest.fixture
def sample_note() -> dict:
    """Sample GitLab note/comment response."""
    return {
        "id": 2001,
        "type": "DiscussionNote",
        "body": "Closing this MR",
        "author": {"id": 1, "username": "testuser", "name": "Test User"},
        "created_at": "2024-01-15T10:00:00Z",
        "updated_at": "2024-01-15T10:00:00Z",
        "system": False,
        "noteable_id": 456,
        "noteable_type": "MergeRequest",
        "noteable_iid": 1,
    }


# Integration test fixtures


@pytest.fixture
def gitlab_token() -> str | None:
    """Get GitLab token from environment for integration tests."""
    return os.getenv("GITLAB_TOKEN")


@pytest.fixture
def gitlab_url() -> str:
    """Get GitLab URL from environment for integration tests."""
    return os.getenv("GITLAB_URL", "https://gitlab.com")


@pytest.fixture
def skip_without_token(gitlab_token: str | None) -> None:
    """Skip test if GITLAB_TOKEN is not set."""
    if not gitlab_token:
        pytest.skip("GITLAB_TOKEN not set - skipping integration test")
