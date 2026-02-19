"""File upload tools for gitlab-mcp."""

from typing import Any

from fastmcp import Context
from gitlab_client import APIError, FileSource, GitLabError

from gitlab_mcp.server import gitlab_client, mcp
from gitlab_mcp.utils.resolvers import resolve_project_id


@mcp.tool()
async def upload_file(
    ctx: Context,
    project_id: str,
    source: FileSource,
) -> dict[str, Any]:
    """Upload a file to GitLab for embedding in issues, MRs, or comments.

    Uploads a file to GitLab's project uploads and returns a markdown-ready
    image/file tag that can be embedded in descriptions or comments.

    Args:
        project_id: Project ID, path, or "current"
        source: File source - either {"path": "/local/file.png"} for local files
                or {"base64": "...", "filename": "name.png"} for base64 data

    Returns:
        { success, markdown, url, full_path, alt }
        The 'markdown' field contains a ready-to-use markdown tag.

    Examples:
        upload_file("current", {"path": "/tmp/screenshot.png"})
        upload_file("current", {"base64": "iVBORw0KGgo...", "filename": "image.png"})

    Raises:
        Error if upload fails
    """
    resolved_project_id, _ = await resolve_project_id(ctx, gitlab_client, project_id)
    if not resolved_project_id:
        return {"success": False, "error": f"Could not resolve project '{project_id}'"}

    try:
        result = gitlab_client.upload_file(resolved_project_id, source)
        filename = result.get("alt", "file")
        return {
            "success": True,
            "message": f"Successfully uploaded '{filename}' to project {project_id}",
            "markdown": result["markdown"],
            "url": result["url"],
            "full_path": result.get("full_path"),
            "alt": result.get("alt"),
            "project_id": project_id,
        }
    except FileNotFoundError as e:
        return {
            "success": False,
            "error": f"File not found: {str(e)}",
            "project_id": project_id,
        }
    except APIError as e:
        return {
            "success": False,
            "error": f"Failed to upload file: {e}",
            "status_code": e.status_code,
            "project_id": project_id,
        }
    except GitLabError as e:
        return {
            "success": False,
            "error": f"Failed to upload file: {e}",
            "project_id": project_id,
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Unexpected error uploading file: {str(e)}",
            "project_id": project_id,
        }
