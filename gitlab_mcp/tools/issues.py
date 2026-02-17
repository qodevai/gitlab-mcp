"""Issue tools for gitlab-mcp."""

from typing import Any

from fastmcp import Context

from gitlab_client import APIError, GitLabError
from gitlab_mcp.models import ImageInput
from gitlab_mcp.server import gitlab_client, mcp
from gitlab_mcp.utils.images import prepare_description_with_images, process_images
from gitlab_mcp.utils.resolvers import resolve_project_id


@mcp.tool()
async def create_issue(
    ctx: Context,
    project_id: str,
    title: str,
    description: str | None = None,
    labels: str | None = None,
    assignee_ids: list[int] | None = None,
    images: list[ImageInput] | None = None,
) -> dict[str, Any]:
    """Create a new issue in a project

    Args:
        project_id: Project ID, path, or "current" (e.g., "mygroup/myproject", "123", or "current")
        title: Issue title (required)
        description: Issue description (optional, supports Markdown)
        labels: Comma-separated label names (optional, e.g., "bug,urgent")
        assignee_ids: List of user IDs to assign (optional)
        images: List of images to attach. Each image is either {"path": "/local/file.png"}
                or {"base64": "...", "filename": "name.png", "alt": "optional alt text"}

    Returns:
        Result with success status and created issue details including web URL

    Raises:
        Error if issue creation fails
    """
    resolved_project_id, _ = await resolve_project_id(ctx, gitlab_client, project_id)
    if not resolved_project_id:
        return {"success": False, "error": f"Could not resolve project '{project_id}'"}

    try:
        # Process images and append markdown to description
        image_markdown = process_images(gitlab_client, resolved_project_id, images)
        final_description = (description or "") + image_markdown if image_markdown else description

        result = gitlab_client.create_issue(
            project_id=resolved_project_id,
            title=title,
            description=final_description,
            labels=labels,
            assignee_ids=assignee_ids,
        )

        return {
            "success": True,
            "message": f"Successfully created issue #{result.get('iid')} in project {project_id}",
            "issue": {
                "iid": result.get("iid"),
                "title": result.get("title"),
                "description": result.get("description"),
                "state": result.get("state"),
                "web_url": result.get("web_url"),
                "labels": result.get("labels"),
            },
            "project_id": project_id,
        }
    except APIError as e:
        return {
            "success": False,
            "error": f"Failed to create issue in project {project_id}: {e}",
            "status_code": e.status_code,
            "project_id": project_id,
        }
    except GitLabError as e:
        return {
            "success": False,
            "error": f"Failed to create issue in project {project_id}: {e}",
            "project_id": project_id,
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Unexpected error while creating issue in project {project_id}: {str(e)}",
            "project_id": project_id,
        }


@mcp.tool()
async def update_issue(
    ctx: Context,
    project_id: str,
    issue_iid: int,
    title: str | None = None,
    description: str | None = None,
    labels: str | None = None,
    assignee_ids: list[int] | None = None,
    state_event: str | None = None,
    images: list[ImageInput] | None = None,
) -> dict[str, Any]:
    """Update an existing issue's title, description, or other properties

    Args:
        project_id: Project ID, path, or "current" (e.g., "mygroup/myproject", "123", or "current")
        issue_iid: Issue IID (the #number)
        title: New issue title (optional)
        description: New issue description (optional)
        labels: New comma-separated label names (optional)
        assignee_ids: New list of assignee user IDs (optional)
        state_event: Change state: "close" or "reopen" (optional)
        images: List of images to attach. Each image is either {"path": "/local/file.png"}
                or {"base64": "...", "filename": "name.png", "alt": "optional alt text"}

    Returns:
        Result with success status and updated issue details

    Raises:
        Error if update fails
    """
    resolved_project_id, _ = await resolve_project_id(ctx, gitlab_client, project_id)
    if not resolved_project_id:
        return {"success": False, "error": f"Could not resolve project '{project_id}'"}

    try:
        # Process images and prepare description
        image_markdown = process_images(gitlab_client, resolved_project_id, images)
        final_description = prepare_description_with_images(
            image_markdown,
            description,
            lambda: gitlab_client.get_issue(resolved_project_id, issue_iid).get("description"),
        )

        result = gitlab_client.update_issue(
            project_id=resolved_project_id,
            issue_iid=issue_iid,
            title=title,
            description=final_description,
            state_event=state_event,
            labels=labels,
            assignee_ids=assignee_ids,
        )

        return {
            "success": True,
            "message": f"Successfully updated issue #{issue_iid} in project {project_id}",
            "issue": {
                "iid": result.get("iid"),
                "title": result.get("title"),
                "description": result.get("description"),
                "state": result.get("state"),
                "web_url": result.get("web_url"),
                "labels": result.get("labels"),
            },
            "project_id": project_id,
            "issue_iid": issue_iid,
        }
    except APIError as e:
        return {
            "success": False,
            "error": f"Failed to update issue #{issue_iid} in project {project_id}: {e}",
            "status_code": e.status_code,
            "project_id": project_id,
            "issue_iid": issue_iid,
        }
    except GitLabError as e:
        return {
            "success": False,
            "error": f"Failed to update issue #{issue_iid} in project {project_id}: {e}",
            "project_id": project_id,
            "issue_iid": issue_iid,
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Unexpected error while updating issue #{issue_iid} in project {project_id}: {str(e)}",
            "project_id": project_id,
            "issue_iid": issue_iid,
        }


@mcp.tool()
async def close_issue(
    ctx: Context,
    project_id: str,
    issue_iid: int,
) -> dict[str, Any]:
    """Close a specific issue by project and issue IID

    Args:
        project_id: Project ID, path, or "current" (e.g., "mygroup/myproject", "123", or "current")
        issue_iid: Issue IID (the #number)

    Returns:
        Result of close operation with updated issue details

    Raises:
        Error if close operation fails
    """
    resolved_project_id, _ = await resolve_project_id(ctx, gitlab_client, project_id)
    if not resolved_project_id:
        return {"success": False, "error": f"Could not resolve project '{project_id}'"}

    try:
        result = gitlab_client.close_issue(resolved_project_id, issue_iid)

        return {
            "success": True,
            "message": f"Successfully closed issue #{issue_iid} in project {project_id}",
            "issue": {
                "iid": result.get("iid"),
                "title": result.get("title"),
                "state": result.get("state"),
                "web_url": result.get("web_url"),
            },
            "project_id": project_id,
            "issue_iid": issue_iid,
        }
    except APIError as e:
        return {
            "success": False,
            "error": f"Failed to close issue #{issue_iid} in project {project_id}: {e}",
            "status_code": e.status_code,
            "project_id": project_id,
            "issue_iid": issue_iid,
        }
    except GitLabError as e:
        return {
            "success": False,
            "error": f"Failed to close issue #{issue_iid} in project {project_id}: {e}",
            "project_id": project_id,
            "issue_iid": issue_iid,
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Unexpected error while closing issue #{issue_iid} in project {project_id}: {str(e)}",
            "project_id": project_id,
            "issue_iid": issue_iid,
        }


@mcp.tool()
async def comment_on_issue(
    ctx: Context,
    project_id: str,
    issue_iid: int,
    comment: str,
    images: list[ImageInput] | None = None,
) -> dict[str, Any]:
    """Leave a comment on a specific issue by project and issue IID

    Args:
        project_id: Project ID, path, or "current" (e.g., "mygroup/myproject", "123", or "current")
        issue_iid: Issue IID (the #number)
        comment: Comment text to post (supports Markdown formatting)
        images: List of images to attach. Each image is either {"path": "/local/file.png"}
                or {"base64": "...", "filename": "name.png", "alt": "optional alt text"}

    Returns:
        Result of comment operation with created note details

    Raises:
        Error if comment creation fails
    """
    resolved_project_id, _ = await resolve_project_id(ctx, gitlab_client, project_id)
    if not resolved_project_id:
        return {"success": False, "error": f"Could not resolve project '{project_id}'"}

    try:
        # Process images and append markdown to comment
        image_markdown = process_images(gitlab_client, resolved_project_id, images)
        final_comment = comment + image_markdown if image_markdown else comment

        result = gitlab_client.create_issue_note(
            project_id=resolved_project_id,
            issue_iid=issue_iid,
            body=final_comment,
        )

        return {
            "success": True,
            "message": f"Successfully posted comment on issue #{issue_iid} in project {project_id}",
            "note": result,
            "project_id": project_id,
            "issue_iid": issue_iid,
        }
    except APIError as e:
        return {
            "success": False,
            "error": f"Failed to comment on issue #{issue_iid} in project {project_id}: {e}",
            "status_code": e.status_code,
            "project_id": project_id,
            "issue_iid": issue_iid,
        }
    except GitLabError as e:
        return {
            "success": False,
            "error": f"Failed to comment on issue #{issue_iid} in project {project_id}: {e}",
            "project_id": project_id,
            "issue_iid": issue_iid,
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Unexpected error while commenting on issue #{issue_iid} in project {project_id}: {str(e)}",
            "project_id": project_id,
            "issue_iid": issue_iid,
        }
