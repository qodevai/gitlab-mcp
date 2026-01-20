"""GitLab API client composed from mixins."""

from gitlab_mcp.client.files import FilesMixin
from gitlab_mcp.client.issues import IssuesMixin
from gitlab_mcp.client.merge_requests import MergeRequestsMixin
from gitlab_mcp.client.pipelines import PipelinesMixin
from gitlab_mcp.client.releases import ReleasesMixin
from gitlab_mcp.client.variables import VariablesMixin


class GitLabClient(
    MergeRequestsMixin,
    PipelinesMixin,
    IssuesMixin,
    ReleasesMixin,
    VariablesMixin,
    FilesMixin,
):
    """GitLab API client composed from mixins.

    This client provides methods for interacting with GitLab's API including:
    - Projects
    - Merge requests and discussions
    - Pipelines and jobs
    - Issues
    - Releases
    - CI/CD variables
    - File uploads
    """


__all__ = ["GitLabClient"]
