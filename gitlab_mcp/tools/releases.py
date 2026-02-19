"""Release tools for gitlab-mcp."""

from typing import Any

from fastmcp import Context
from gitlab_client import APIError, GitLabError

from gitlab_mcp.models import ImageInput
from gitlab_mcp.server import gitlab_client, mcp
from gitlab_mcp.utils.git import get_current_branch
from gitlab_mcp.utils.images import process_images
from gitlab_mcp.utils.resolvers import detect_current_repo, resolve_project_id


@mcp.tool()
async def create_release(
    ctx: Context,
    project_id: str,
    tag_name: str,
    name: str | None = None,
    description: str | None = None,
    ref: str | None = None,
    milestones: list[str] | None = None,
    released_at: str | None = None,
    assets_links: list[dict[str, str]] | None = None,
    images: list[ImageInput] | None = None,
) -> dict[str, Any]:
    """Create a new release in a project

    Args:
        project_id: Project ID, path, or "current" (e.g., "mygroup/myproject", "123", or "current")
        tag_name: Tag name for the release (required)
        name: Release title (optional, defaults to tag_name)
        description: Release description/notes (optional, supports Markdown)
        ref: Commit SHA, branch, or existing tag (required only if tag_name doesn't exist yet; auto-detects from current branch if not provided)
        milestones: List of milestone titles to associate (optional)
        released_at: ISO 8601 datetime for release (optional, defaults to current time)
        assets_links: List of asset link dicts with 'name', 'url', and optional 'direct_asset_path' (optional)
        images: List of images to attach. Each image is either {"path": "/local/file.png"}
                or {"base64": "...", "filename": "name.png", "alt": "optional alt text"}

    Returns:
        Result with success status and created release details

    Raises:
        Error if release creation fails
    """
    resolved_project_id, repo_info = await resolve_project_id(ctx, gitlab_client, project_id)
    if not resolved_project_id:
        return {"success": False, "error": f"Could not resolve project '{project_id}'"}

    # Auto-detect ref from current branch if not provided
    if ref is None:
        if repo_info and "git_root" in repo_info:
            ref = get_current_branch(repo_info["git_root"])
        else:
            # Try to detect current repo for branch info
            detected_repo = await detect_current_repo(ctx, gitlab_client)
            if detected_repo and "git_root" in detected_repo:
                ref = get_current_branch(detected_repo["git_root"])
        # ref being None is acceptable - GitLab will use the tag if it exists

    try:
        # Process images and append markdown to description
        image_markdown = process_images(gitlab_client, resolved_project_id, images)
        final_description = (description or "") + image_markdown if image_markdown else description

        result = gitlab_client.create_release(
            project_id=resolved_project_id,
            tag_name=tag_name,
            name=name,
            description=final_description,
            ref=ref,
            milestones=milestones,
            released_at=released_at,
            assets_links=assets_links,
        )

        return {
            "success": True,
            "message": f"Successfully created release '{tag_name}' in project {project_id}",
            "release": {
                "tag_name": result.get("tag_name"),
                "name": result.get("name"),
                "description": result.get("description"),
                "created_at": result.get("created_at"),
                "released_at": result.get("released_at"),
                "_links": result.get("_links"),
            },
            "project_id": project_id,
        }
    except APIError as e:
        return {
            "success": False,
            "error": f"Failed to create release '{tag_name}' in project {project_id}: {e}",
            "status_code": e.status_code,
            "project_id": project_id,
            "tag_name": tag_name,
        }
    except GitLabError as e:
        return {
            "success": False,
            "error": f"Failed to create release '{tag_name}' in project {project_id}: {e}",
            "project_id": project_id,
            "tag_name": tag_name,
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Unexpected error while creating release '{tag_name}' in project {project_id}: {str(e)}",
            "project_id": project_id,
            "tag_name": tag_name,
        }
