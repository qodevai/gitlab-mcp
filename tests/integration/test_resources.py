"""Integration tests for GitLab MCP resources.

These tests require a valid GITLAB_TOKEN environment variable
and will make real API calls to GitLab.
"""

import os
import tempfile

import pytest


@pytest.mark.integration
class TestGitLabClientIntegration:
    """Integration tests for GitLabClient."""

    def test_client_initialization(self, skip_without_token: None, gitlab_token: str, gitlab_url: str) -> None:
        """Test that client can connect to GitLab."""
        from gitlab_mcp import GitLabClient

        # Should not raise
        client = GitLabClient(token=gitlab_token, base_url=gitlab_url, validate=True)
        assert client.token == gitlab_token

    def test_get_version(self, skip_without_token: None, gitlab_token: str, gitlab_url: str) -> None:
        """Test getting GitLab version."""
        from gitlab_mcp import GitLabClient

        client = GitLabClient(token=gitlab_token, base_url=gitlab_url, validate=False)
        version_info = client.get("/version")

        assert "version" in version_info
        assert isinstance(version_info["version"], str)

    def test_get_projects(self, skip_without_token: None, gitlab_token: str, gitlab_url: str) -> None:
        """Test listing projects."""
        from gitlab_mcp import GitLabClient

        client = GitLabClient(token=gitlab_token, base_url=gitlab_url, validate=False)
        projects = client.get_projects(membership=True)

        # User should have access to at least some projects
        assert isinstance(projects, list)
        # Each project should have required fields
        if projects:
            project = projects[0]
            assert "id" in project
            assert "name" in project
            assert "path_with_namespace" in project


@pytest.mark.integration
class TestCurrentProjectDetection:
    """Integration tests for 'current' project detection."""

    def test_get_current_branch_in_repo(self) -> None:
        """Test that current branch detection works in a git repository."""
        from gitlab_mcp import get_current_branch

        # Get current working directory (should be the gitlab-mcp repo)
        cwd = os.getcwd()

        # Should return branch name or None
        branch = get_current_branch(cwd)
        assert branch is None or isinstance(branch, str)

    def test_parse_gitlab_remote_in_repo(self) -> None:
        """Test that remote parsing works in a git repository."""
        from gitlab_mcp import parse_gitlab_remote

        # Get current working directory (should be the gitlab-mcp repo)
        cwd = os.getcwd()
        base_url = "https://gitlab.com"

        # Should return project path or None
        project_path = parse_gitlab_remote(cwd, base_url)
        assert project_path is None or isinstance(project_path, str)


class TestGitLabHelpers:
    """Tests for helper functions (don't require GitLab access)."""

    def test_get_current_branch_not_a_repo(self) -> None:
        """Test getting branch in non-git directory."""
        from gitlab_mcp import get_current_branch

        with tempfile.TemporaryDirectory() as tmpdir:
            result = get_current_branch(tmpdir)
            assert result is None

    def test_parse_gitlab_remote_not_a_repo(self) -> None:
        """Test parsing remote in non-git directory."""
        from gitlab_mcp import parse_gitlab_remote

        with tempfile.TemporaryDirectory() as tmpdir:
            result = parse_gitlab_remote(tmpdir, "https://gitlab.com")
            assert result is None

    def test_gitlab_client_encode_project_id(self) -> None:
        """Test URL encoding of project IDs."""
        from gitlab_mcp import GitLabClient

        # Simple numeric ID
        assert GitLabClient._encode_project_id("123") == "123"

        # Path with slash
        assert GitLabClient._encode_project_id("group/project") == "group%2Fproject"

        # Nested path
        encoded = GitLabClient._encode_project_id("org/group/subgroup/project")
        assert encoded == "org%2Fgroup%2Fsubgroup%2Fproject"
