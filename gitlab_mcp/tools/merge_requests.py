"""Merge request tools for gitlab-mcp."""

import json
from typing import Any

import httpx
from fastmcp import Context

from gitlab_client import APIError, DiffPosition, GitLabError
from gitlab_mcp.models import ImageInput
from gitlab_mcp.server import gitlab_client, mcp
from gitlab_mcp.utils.git import get_current_branch
from gitlab_mcp.utils.images import prepare_description_with_images, process_images
from gitlab_mcp.utils.resolvers import detect_current_repo, resolve_mr_iid, resolve_project_id


def resolve_line_from_content(file_content: str, target_content: str) -> tuple[int | None, int]:
    """Find line number (1-based) matching content, ignoring leading/trailing whitespace.

    Args:
        file_content: Full file content
        target_content: Content to search for

    Returns:
        Tuple of (line_number, match_count) where line_number is the 1-based line number
        if exactly one match found, None otherwise. match_count is the number of matches.
    """
    target_stripped = target_content.strip()
    matches = []
    for i, line in enumerate(file_content.splitlines(), start=1):
        if line.strip() == target_stripped:
            matches.append(i)

    if len(matches) == 1:
        return matches[0], 1
    return None, len(matches)


def resolve_content_to_line(
    project_id: str,
    file_path: str,
    ref: str,
    content: str,
    version_label: str = "",
) -> tuple[int, None] | tuple[None, dict[str, Any]]:
    """Resolve line content to a line number by fetching file and matching.

    Args:
        project_id: Resolved project ID
        file_path: Path to file in repository
        ref: Git ref (commit SHA) to fetch file at
        content: Content to search for
        version_label: Label for error messages (e.g., "(base version)")

    Returns:
        Tuple of (line_number, None) on success, or (None, error_dict) on failure.
    """
    file_content = gitlab_client.get_file_content(project_id, file_path, ref)
    line_num, match_count = resolve_line_from_content(file_content, content)
    if line_num is not None:
        return line_num, None

    suffix = f" {version_label}" if version_label else ""
    if match_count == 0:
        return None, {
            "success": False,
            "error": f"Could not find line matching content '{content}' in {file_path}{suffix}",
        }
    return None, {
        "success": False,
        "error": f"Content '{content}' matches {match_count} lines in {file_path}{suffix}. Use line number instead.",
    }


@mcp.tool()
async def comment_on_merge_request(
    ctx: Context,
    project_id: str,
    mr_iid: str | int,
    comment: str,
    images: list[ImageInput] | None = None,
) -> dict[str, Any]:
    """Leave a comment on a specific merge request by project and MR IID

    Args:
        project_id: Project ID, path, or "current" (e.g., "mygroup/myproject", "123", or "current")
        mr_iid: Merge request IID or "current" (the !number, or "current" for current branch MR)
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

    resolved_mr_iid = await resolve_mr_iid(ctx, gitlab_client, resolved_project_id, str(mr_iid))
    if not resolved_mr_iid:
        return {"success": False, "error": f"Could not resolve MR IID '{mr_iid}'"}

    try:
        # Process images and append markdown to comment
        image_markdown = process_images(gitlab_client, resolved_project_id, images)
        final_comment = comment + image_markdown if image_markdown else comment

        note = gitlab_client.create_mr_note(
            project_id=resolved_project_id,
            mr_iid=resolved_mr_iid,
            body=final_comment,
        )

        return {
            "success": True,
            "message": f"Successfully posted comment on MR !{resolved_mr_iid} in project {project_id}",
            "note": note,
            "project_id": project_id,
            "mr_iid": resolved_mr_iid,
        }
    except APIError as e:
        return {
            "success": False,
            "error": f"Failed to comment on MR !{resolved_mr_iid} in project {project_id}: {e}",
            "status_code": e.status_code,
            "project_id": project_id,
            "mr_iid": resolved_mr_iid,
        }
    except GitLabError as e:
        return {
            "success": False,
            "error": f"Failed to comment on MR !{resolved_mr_iid} in project {project_id}: {e}",
            "project_id": project_id,
            "mr_iid": resolved_mr_iid,
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Unexpected error while commenting on MR !{resolved_mr_iid} in project {project_id}: {str(e)}",
            "project_id": project_id,
            "mr_iid": resolved_mr_iid,
        }


@mcp.tool()
async def reply_to_discussion(
    ctx: Context,
    project_id: str,
    mr_iid: str | int,
    discussion_id: str,
    comment: str,
    images: list[ImageInput] | None = None,
) -> dict[str, Any]:
    """Reply to an existing discussion thread on a merge request

    Args:
        project_id: Project ID, path, or "current" (e.g., "mygroup/myproject", "123", or "current")
        mr_iid: Merge request IID or "current" (the !number, or "current" for current branch MR)
        discussion_id: Discussion thread ID to reply to
        comment: Reply text to post (supports Markdown formatting)
        images: List of images to attach. Each image is either {"path": "/local/file.png"}
                or {"base64": "...", "filename": "name.png", "alt": "optional alt text"}

    Returns:
        Result of reply operation with created note details

    Raises:
        Error if reply creation fails
    """
    resolved_project_id, _ = await resolve_project_id(ctx, gitlab_client, project_id)
    if not resolved_project_id:
        return {"success": False, "error": f"Could not resolve project '{project_id}'"}

    resolved_mr_iid = await resolve_mr_iid(ctx, gitlab_client, resolved_project_id, str(mr_iid))
    if not resolved_mr_iid:
        return {"success": False, "error": f"Could not resolve MR IID '{mr_iid}'"}

    try:
        # Process images and append markdown to comment
        image_markdown = process_images(gitlab_client, resolved_project_id, images)
        final_comment = comment + image_markdown if image_markdown else comment

        note = gitlab_client.reply_to_discussion(
            project_id=resolved_project_id,
            mr_iid=resolved_mr_iid,
            discussion_id=discussion_id,
            body=final_comment,
        )

        return {
            "success": True,
            "message": f"Successfully replied to discussion {discussion_id} on MR !{resolved_mr_iid} in project {project_id}",
            "note": note,
            "project_id": project_id,
            "mr_iid": resolved_mr_iid,
            "discussion_id": discussion_id,
        }
    except APIError as e:
        return {
            "success": False,
            "error": f"Failed to reply to discussion {discussion_id} on MR !{resolved_mr_iid} in project {project_id}: {e}",
            "status_code": e.status_code,
            "project_id": project_id,
            "mr_iid": resolved_mr_iid,
            "discussion_id": discussion_id,
        }
    except GitLabError as e:
        return {
            "success": False,
            "error": f"Failed to reply to discussion {discussion_id} on MR !{resolved_mr_iid} in project {project_id}: {e}",
            "project_id": project_id,
            "mr_iid": resolved_mr_iid,
            "discussion_id": discussion_id,
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Unexpected error while replying to discussion {discussion_id} on MR !{resolved_mr_iid} in project {project_id}: {str(e)}",
            "project_id": project_id,
            "mr_iid": resolved_mr_iid,
            "discussion_id": discussion_id,
        }


@mcp.tool()
async def create_inline_comment(
    ctx: Context,
    project_id: str,
    mr_iid: str | int,
    comment: str,
    position: DiffPosition,
    images: list[ImageInput] | None = None,
) -> dict[str, Any]:
    """Create an inline comment on a specific line in a merge request diff

    Args:
        project_id: Project ID, path, or "current" (e.g., "mygroup/myproject", "123", or "current")
        mr_iid: Merge request IID or "current" (the !number, or "current" for current branch MR)
        comment: Comment text to post (supports Markdown formatting)
        position: Position specifying where to place the comment. Must include:
            - file_path: Path to the file in the diff
            - new_line: Line number (1-based) in the new version (for added/unchanged lines)
            - old_line: Line number (1-based) in the old version (for deleted/unchanged lines)
            - new_line_content: Alternative to new_line - content to match (whitespace-insensitive, must be unique)
            - old_line_content: Alternative to old_line - content to match (whitespace-insensitive, must be unique)
            At least one of new_line or old_line must be provided.
            Optionally include base_sha, head_sha, start_sha (auto-fetched from MR if omitted)
        images: List of images to attach. Each image is either {"path": "/local/file.png"}
                or {"base64": "...", "filename": "name.png", "alt": "optional alt text"}

    Returns:
        Result of comment operation with created discussion details

    Raises:
        Error if inline comment creation fails
    """
    resolved_project_id, _ = await resolve_project_id(ctx, gitlab_client, project_id)
    if not resolved_project_id:
        return {"success": False, "error": f"Could not resolve project '{project_id}'"}

    resolved_mr_iid = await resolve_mr_iid(ctx, gitlab_client, resolved_project_id, str(mr_iid))
    if not resolved_mr_iid:
        return {"success": False, "error": f"Could not resolve MR IID '{mr_iid}'"}

    # Check if we have any line reference (number or content)
    has_new_line_ref = "new_line" in position or "new_line_content" in position
    has_old_line_ref = "old_line" in position or "old_line_content" in position
    if not has_new_line_ref and not has_old_line_ref:
        return {
            "success": False,
            "error": "At least one of new_line, old_line, new_line_content, or old_line_content must be provided",
        }

    try:
        # Fetch MR to get diff_refs (needed for SHAs and potentially content resolution)
        mr = gitlab_client.get_merge_request(resolved_project_id, resolved_mr_iid)
        diff_refs = mr.get("diff_refs", {})
        if not diff_refs:
            return {
                "success": False,
                "error": "Could not get diff_refs from MR. The MR may not have any changes.",
            }

        # Resolve content to line numbers if needed
        file_path = position["file_path"]
        if not file_path or not file_path.strip():
            return {"success": False, "error": "file_path must be a non-empty string"}

        # Resolve new_line from content if needed
        if "new_line_content" in position and "new_line" not in position:
            head_sha = position.get("head_sha") or diff_refs.get("head_sha")
            resolved_line, error = resolve_content_to_line(
                resolved_project_id, file_path, head_sha, position["new_line_content"]
            )
            if error:
                return error
            assert resolved_line is not None  # Guaranteed when error is None
            position = {**position, "new_line": resolved_line}

        # Resolve old_line from content if needed
        if "old_line_content" in position and "old_line" not in position:
            base_sha = position.get("base_sha") or diff_refs.get("base_sha")
            resolved_line, error = resolve_content_to_line(
                resolved_project_id, file_path, base_sha, position["old_line_content"], "(base version)"
            )
            if error:
                return error
            assert resolved_line is not None  # Guaranteed when error is None
            position = {**position, "old_line": resolved_line}

        # Validate that at least one line number is now provided (after content resolution)
        if "new_line" not in position and "old_line" not in position:
            return {
                "success": False,
                "error": "Could not resolve any line number from provided content",
            }

        # Fill in SHAs if not provided
        position = {
            **position,
            "base_sha": position.get("base_sha") or diff_refs.get("base_sha"),
            "head_sha": position.get("head_sha") or diff_refs.get("head_sha"),
            "start_sha": position.get("start_sha") or diff_refs.get("start_sha"),
        }

        # Process images and append markdown to comment
        image_markdown = process_images(gitlab_client, resolved_project_id, images)
        final_comment = comment + image_markdown if image_markdown else comment

        discussion = gitlab_client.create_mr_discussion(
            project_id=resolved_project_id,
            mr_iid=resolved_mr_iid,
            body=final_comment,
            position=position,
        )

        return {
            "success": True,
            "message": f"Successfully created inline comment on {position['file_path']} in MR !{resolved_mr_iid}",
            "discussion": discussion,
            "project_id": project_id,
            "mr_iid": resolved_mr_iid,
            "file_path": position["file_path"],
            "new_line": position.get("new_line"),
            "old_line": position.get("old_line"),
        }
    except APIError as e:
        return {
            "success": False,
            "error": f"Failed to create inline comment on MR !{resolved_mr_iid} in project {project_id}: {e}",
            "status_code": e.status_code,
            "project_id": project_id,
            "mr_iid": resolved_mr_iid,
        }
    except GitLabError as e:
        return {
            "success": False,
            "error": f"Failed to create inline comment on MR !{resolved_mr_iid} in project {project_id}: {e}",
            "project_id": project_id,
            "mr_iid": resolved_mr_iid,
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Unexpected error while creating inline comment on MR !{resolved_mr_iid} in project {project_id}: {str(e)}",
            "project_id": project_id,
            "mr_iid": resolved_mr_iid,
        }


@mcp.tool()
async def resolve_discussion_thread(
    ctx: Context, project_id: str, mr_iid: str | int, discussion_id: str, resolved: bool = True
) -> dict[str, Any]:
    """Resolve or unresolve a discussion thread on a merge request

    Args:
        project_id: Project ID, path, or "current" (e.g., "mygroup/myproject", "123", or "current")
        mr_iid: Merge request IID or "current" (the !number, or "current" for current branch MR)
        discussion_id: Discussion thread ID to resolve/unresolve
        resolved: True to resolve the thread, False to unresolve it (default: True)

    Returns:
        Result of resolve/unresolve operation with updated discussion details

    Raises:
        Error if resolve/unresolve operation fails
    """
    resolved_project_id, _ = await resolve_project_id(ctx, gitlab_client, project_id)
    if not resolved_project_id:
        return {"success": False, "error": f"Could not resolve project '{project_id}'"}

    resolved_mr_iid = await resolve_mr_iid(ctx, gitlab_client, resolved_project_id, str(mr_iid))
    if not resolved_mr_iid:
        return {"success": False, "error": f"Could not resolve MR IID '{mr_iid}'"}

    try:
        discussion = gitlab_client.resolve_discussion(
            project_id=resolved_project_id,
            mr_iid=resolved_mr_iid,
            discussion_id=discussion_id,
            resolved=resolved,
        )

        action = "resolved" if resolved else "unresolved"
        return {
            "success": True,
            "message": f"Successfully {action} discussion {discussion_id} on MR !{resolved_mr_iid} in project {project_id}",
            "discussion": discussion,
            "project_id": project_id,
            "mr_iid": resolved_mr_iid,
            "discussion_id": discussion_id,
            "resolved": resolved,
        }
    except APIError as e:
        action = "resolve" if resolved else "unresolve"
        return {
            "success": False,
            "error": f"Failed to {action} discussion {discussion_id} on MR !{resolved_mr_iid} in project {project_id}: {e}",
            "status_code": e.status_code,
            "project_id": project_id,
            "mr_iid": resolved_mr_iid,
            "discussion_id": discussion_id,
        }
    except GitLabError as e:
        action = "resolve" if resolved else "unresolve"
        return {
            "success": False,
            "error": f"Failed to {action} discussion {discussion_id} on MR !{resolved_mr_iid} in project {project_id}: {e}",
            "project_id": project_id,
            "mr_iid": resolved_mr_iid,
            "discussion_id": discussion_id,
        }
    except Exception as e:
        action = "resolve" if resolved else "unresolve"
        return {
            "success": False,
            "error": f"Unexpected error while trying to {action} discussion {discussion_id} on MR !{resolved_mr_iid} in project {project_id}: {str(e)}",
            "project_id": project_id,
            "mr_iid": resolved_mr_iid,
            "discussion_id": discussion_id,
        }


@mcp.tool()
async def merge_merge_request(
    ctx: Context,
    project_id: str,
    mr_iid: str | int,
    merge_commit_message: str | None = None,
    squash_commit_message: str | None = None,
    should_remove_source_branch: bool = True,
    merge_when_pipeline_succeeds: bool = False,
    squash: bool | None = None,
) -> dict[str, Any]:
    """Merge a specific merge request by project and MR IID

    Args:
        project_id: Project ID, path, or "current" (e.g., "mygroup/myproject", "123", or "current")
        mr_iid: Merge request IID or "current" (the !number, or "current" for current branch MR)
        merge_commit_message: Custom merge commit message (optional)
        squash_commit_message: Custom squash commit message (optional, used if squashing)
        should_remove_source_branch: Remove source branch after merge (default: True)
        merge_when_pipeline_succeeds: Wait for pipeline to succeed before merging (default: False)
        squash: Squash commits on merge (None = use project/MR settings, True = squash, False = don't squash)

    Returns:
        Result of merge operation with merged MR details

    Raises:
        Error if merge fails (not mergeable, conflicts, not approved, etc.)
    """
    resolved_project_id, _ = await resolve_project_id(ctx, gitlab_client, project_id)
    if not resolved_project_id:
        return {"success": False, "error": f"Could not resolve project '{project_id}'"}

    resolved_mr_iid = await resolve_mr_iid(ctx, gitlab_client, resolved_project_id, str(mr_iid))
    if not resolved_mr_iid:
        return {"success": False, "error": f"Could not resolve MR IID '{mr_iid}'"}

    # Get MR details to check status
    try:
        mr = gitlab_client.get_merge_request(resolved_project_id, resolved_mr_iid)
        merge_status = mr.get("merge_status")
        detailed_merge_status = mr.get("detailed_merge_status")
        has_conflicts = mr.get("has_conflicts", False)

        # Get pipeline status
        try:
            pipelines = gitlab_client.get_mr_pipelines(resolved_project_id, resolved_mr_iid)
            latest_pipeline = pipelines[0] if pipelines else None
            pipeline_status = latest_pipeline.get("status") if latest_pipeline else None
        except Exception:
            pipeline_status = None
    except Exception:
        # If we can't get MR details, proceed with merge attempt
        mr = None
        merge_status = None
        detailed_merge_status = None
        has_conflicts = False
        pipeline_status = None

    try:
        result = gitlab_client.merge_mr(
            project_id=resolved_project_id,
            mr_iid=resolved_mr_iid,
            merge_commit_message=merge_commit_message,
            squash_commit_message=squash_commit_message,
            should_remove_source_branch=should_remove_source_branch,
            merge_when_pipeline_succeeds=merge_when_pipeline_succeeds,
            squash=squash,
        )

        return {
            "success": True,
            "message": f"Successfully merged MR !{resolved_mr_iid} in project {project_id}",
            "merged_mr": result,
            "branch_removed": should_remove_source_branch,
        }
    except APIError as e:
        # Parse GitLab error response
        try:
            error_json = json.loads(e.response_body)
            error_message = error_json.get("message", "Unknown error")
        except (json.JSONDecodeError, AttributeError):
            error_message = str(e)

        # Build helpful error message with context
        helpful_message = f"Failed to merge MR !{resolved_mr_iid} in project {project_id}: {error_message}"
        suggestions = []

        # Add context-specific suggestions
        if e.status_code in (405, 406):
            # Method Not Allowed or Not Acceptable - usually means merge is blocked
            if pipeline_status == "running":
                helpful_message = (
                    f"Cannot merge MR !{resolved_mr_iid}: Pipeline is still running (status: {pipeline_status})"
                )
                suggestions.append(
                    "Wait for the pipeline to complete, or use merge_when_pipeline_succeeds=True to queue the merge"
                )
            elif pipeline_status == "failed":
                helpful_message = f"Cannot merge MR !{resolved_mr_iid}: Pipeline failed (status: {pipeline_status})"
                suggestions.append("Fix the pipeline failures before merging")
            elif has_conflicts:
                helpful_message = f"Cannot merge MR !{resolved_mr_iid}: MR has merge conflicts"
                suggestions.append("Resolve merge conflicts before merging")
            elif merge_status == "cannot_be_merged":
                helpful_message = f"Cannot merge MR !{resolved_mr_iid}: Merge status is 'cannot_be_merged'"
                if detailed_merge_status:
                    helpful_message += f" (detailed status: {detailed_merge_status})"
                suggestions.append("Check the MR in GitLab UI for blocking conditions (approvals, conflicts, etc.)")
            else:
                suggestions.append("Check the MR status in GitLab UI for blocking conditions")
                if merge_status:
                    suggestions.append(f"Current merge_status: {merge_status}")
                if detailed_merge_status:
                    suggestions.append(f"Detailed status: {detailed_merge_status}")

        response = {
            "success": False,
            "error": helpful_message,
            "suggestions": suggestions,
            "status_code": e.status_code,
            "project_id": project_id,
            "mr_iid": resolved_mr_iid,
        }

        if mr:
            response["merge_request"] = {
                "iid": mr["iid"],
                "title": mr.get("title"),
                "web_url": mr.get("web_url"),
                "merge_status": merge_status,
                "detailed_merge_status": detailed_merge_status,
                "has_conflicts": has_conflicts,
                "pipeline_status": pipeline_status,
            }

        return response
    except GitLabError as e:
        return {
            "success": False,
            "error": f"Failed to merge MR !{resolved_mr_iid} in project {project_id}: {e}",
            "project_id": project_id,
            "mr_iid": resolved_mr_iid,
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Unexpected error while merging MR !{resolved_mr_iid} in project {project_id}: {str(e)}",
            "project_id": project_id,
            "mr_iid": resolved_mr_iid,
        }


@mcp.tool()
async def close_merge_request(
    ctx: Context,
    project_id: str,
    mr_iid: str | int,
    comment: str | None = None,
) -> dict[str, Any]:
    """Close a specific merge request by project and MR IID

    Args:
        project_id: Project ID, path, or "current" (e.g., "mygroup/myproject", "123", or "current")
        mr_iid: Merge request IID or "current" (the !number, or "current" for current branch MR)
        comment: Optional comment to post when closing (supports Markdown formatting)

    Returns:
        Result of close operation with closed MR details

    Raises:
        Error if close operation fails
    """
    resolved_project_id, _ = await resolve_project_id(ctx, gitlab_client, project_id)
    if not resolved_project_id:
        return {"success": False, "error": f"Could not resolve project '{project_id}'"}

    resolved_mr_iid = await resolve_mr_iid(ctx, gitlab_client, resolved_project_id, str(mr_iid))
    if not resolved_mr_iid:
        return {"success": False, "error": f"Could not resolve MR IID '{mr_iid}'"}

    try:
        result = gitlab_client.close_mr(
            project_id=resolved_project_id,
            mr_iid=resolved_mr_iid,
        )

        response = {
            "success": True,
            "message": f"Successfully closed MR !{resolved_mr_iid} in project {project_id}",
            "merge_request": result,
        }

        # If comment provided, attempt to post it
        if comment:
            try:
                note = gitlab_client.create_mr_note(
                    project_id=resolved_project_id,
                    mr_iid=resolved_mr_iid,
                    body=comment,
                )
                response["comment"] = note
                response["message"] = f"Successfully closed MR !{resolved_mr_iid} with comment in project {project_id}"
            except (GitLabError, httpx.RequestError) as comment_error:
                # Non-fatal: MR is closed, just warn about comment failure
                response["warning"] = f"Failed to post closing comment: {str(comment_error)}"

        return response
    except APIError as e:
        # Parse GitLab error response
        try:
            error_json = json.loads(e.response_body)
            error_message = error_json.get("message", "Unknown error")
        except (json.JSONDecodeError, AttributeError):
            error_message = str(e)

        return {
            "success": False,
            "error": f"Failed to close MR !{resolved_mr_iid} in project {project_id}: {error_message}",
            "status_code": e.status_code,
            "project_id": project_id,
            "mr_iid": resolved_mr_iid,
        }
    except GitLabError as e:
        return {
            "success": False,
            "error": f"Failed to close MR !{resolved_mr_iid} in project {project_id}: {e}",
            "project_id": project_id,
            "mr_iid": resolved_mr_iid,
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Unexpected error while closing MR !{resolved_mr_iid} in project {project_id}: {str(e)}",
            "project_id": project_id,
            "mr_iid": resolved_mr_iid,
        }


@mcp.tool()
async def update_merge_request(
    ctx: Context,
    project_id: str,
    mr_iid: str | int,
    title: str | None = None,
    description: str | None = None,
    target_branch: str | None = None,
    state_event: str | None = None,
    assignee_ids: list[int] | None = None,
    reviewer_ids: list[int] | None = None,
    labels: str | None = None,
    images: list[ImageInput] | None = None,
) -> dict[str, Any]:
    """Update a merge request's title, description, or other properties

    Args:
        project_id: Project ID, path, or "current" (e.g., "mygroup/myproject", "123", or "current")
        mr_iid: Merge request IID or "current" (the !number, or "current" for current branch MR)
        title: New MR title (optional)
        description: New MR description (optional)
        target_branch: New target branch (optional)
        state_event: Change state: "open", "close", "reopen" (optional)
        assignee_ids: List of assignee user IDs (optional)
        reviewer_ids: List of reviewer user IDs (optional)
        labels: Comma-separated label names (optional)
        images: List of images to attach. Each image is either {"path": "/local/file.png"}
                or {"base64": "...", "filename": "name.png", "alt": "optional alt text"}

    Returns:
        Result with success status and updated MR details

    Raises:
        Error if update fails
    """
    resolved_project_id, _ = await resolve_project_id(ctx, gitlab_client, project_id)
    if not resolved_project_id:
        return {"success": False, "error": f"Could not resolve project '{project_id}'"}

    resolved_mr_iid = await resolve_mr_iid(ctx, gitlab_client, resolved_project_id, str(mr_iid))
    if not resolved_mr_iid:
        return {"success": False, "error": f"Could not resolve MR IID '{mr_iid}'"}

    try:
        # Process images and prepare description
        image_markdown = process_images(gitlab_client, resolved_project_id, images)
        final_description = prepare_description_with_images(
            image_markdown,
            description,
            lambda: gitlab_client.get_merge_request(resolved_project_id, resolved_mr_iid).get("description"),
        )

        result = gitlab_client.update_mr(
            project_id=resolved_project_id,
            mr_iid=resolved_mr_iid,
            title=title,
            description=final_description,
            target_branch=target_branch,
            state_event=state_event,
            assignee_ids=assignee_ids,
            reviewer_ids=reviewer_ids,
            labels=labels,
        )

        return {
            "success": True,
            "message": f"Successfully updated MR !{resolved_mr_iid} in project {project_id}",
            "merge_request": {
                "iid": result.get("iid"),
                "title": result.get("title"),
                "description": result.get("description"),
                "state": result.get("state"),
                "web_url": result.get("web_url"),
            },
            "project_id": project_id,
            "mr_iid": resolved_mr_iid,
        }
    except APIError as e:
        # Parse GitLab error response
        try:
            error_json = json.loads(e.response_body)
            error_message = error_json.get("message", "Unknown error")
        except (json.JSONDecodeError, AttributeError):
            error_message = str(e)

        return {
            "success": False,
            "error": f"Failed to update MR !{resolved_mr_iid} in project {project_id}: {error_message}",
            "status_code": e.status_code,
            "project_id": project_id,
            "mr_iid": resolved_mr_iid,
        }
    except GitLabError as e:
        return {
            "success": False,
            "error": f"Failed to update MR !{resolved_mr_iid} in project {project_id}: {e}",
            "project_id": project_id,
            "mr_iid": resolved_mr_iid,
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Unexpected error while updating MR !{resolved_mr_iid} in project {project_id}: {str(e)}",
            "project_id": project_id,
            "mr_iid": resolved_mr_iid,
        }


@mcp.tool()
async def create_merge_request(
    ctx: Context,
    project_id: str,
    title: str,
    source_branch: str | None = None,
    target_branch: str = "main",
    description: str | None = None,
    assignee_ids: list[int] | None = None,
    reviewer_ids: list[int] | None = None,
    labels: str | None = None,
    remove_source_branch: bool = True,
    squash: bool | None = None,
    allow_collaboration: bool = False,
    images: list[ImageInput] | None = None,
) -> dict[str, Any]:
    """Create a new merge request in a project

    Args:
        project_id: Project ID, path, or "current" (e.g., "mygroup/myproject", "123", or "current")
        title: MR title (required)
        source_branch: Source branch name (defaults to current branch if None)
        target_branch: Target branch name (default: "main")
        description: MR description/body (optional, supports Markdown)
        assignee_ids: List of user IDs to assign (optional)
        reviewer_ids: List of user IDs to review (optional)
        labels: Comma-separated label names (optional, e.g., "bug,urgent")
        remove_source_branch: Remove source branch after merge (default: True)
        squash: Squash commits on merge (None = use project settings, True = squash, False = don't squash)
        allow_collaboration: Allow commits from members with merge access (default: False)
        images: List of images to attach. Each image is either {"path": "/local/file.png"}
                or {"base64": "...", "filename": "name.png", "alt": "optional alt text"}

    Returns:
        Result with success status and created MR details including web URL

    Raises:
        Error if MR creation fails
    """
    resolved_project_id, repo_info = await resolve_project_id(ctx, gitlab_client, project_id)
    if not resolved_project_id:
        return {"success": False, "error": f"Could not resolve project '{project_id}'"}

    # Auto-detect source_branch from current branch if not provided
    if source_branch is None:
        if repo_info and "git_root" in repo_info:
            source_branch = get_current_branch(repo_info["git_root"])
            if not source_branch:
                return {
                    "success": False,
                    "error": "Could not detect current branch. Please specify source_branch explicitly.",
                }
        else:
            # Try to detect current repo for branch info
            detected_repo = await detect_current_repo(ctx, gitlab_client)
            if detected_repo and "git_root" in detected_repo:
                source_branch = get_current_branch(detected_repo["git_root"])
                if not source_branch:
                    return {
                        "success": False,
                        "error": "Could not detect current branch. Please specify source_branch explicitly.",
                    }
            else:
                return {
                    "success": False,
                    "error": "Could not detect current branch. Please specify source_branch explicitly.",
                }

    try:
        # Process images and append markdown to description
        image_markdown = process_images(gitlab_client, resolved_project_id, images)
        final_description = (description or "") + image_markdown if image_markdown else description

        result = gitlab_client.create_merge_request(
            project_id=resolved_project_id,
            source_branch=source_branch,
            target_branch=target_branch,
            title=title,
            description=final_description,
            assignee_ids=assignee_ids,
            reviewer_ids=reviewer_ids,
            labels=labels,
            remove_source_branch=remove_source_branch,
            squash=squash,
            allow_collaboration=allow_collaboration,
        )

        return {
            "success": True,
            "message": f"Successfully created MR !{result.get('iid')} in project {project_id}",
            "merge_request": {
                "iid": result.get("iid"),
                "title": result.get("title"),
                "description": result.get("description"),
                "state": result.get("state"),
                "source_branch": result.get("source_branch"),
                "target_branch": result.get("target_branch"),
                "web_url": result.get("web_url"),
            },
            "project_id": project_id,
        }
    except APIError as e:
        # Parse GitLab error response
        try:
            error_json = json.loads(e.response_body)
            error_message = error_json.get("message", "Unknown error")
        except (json.JSONDecodeError, AttributeError):
            error_message = str(e)

        return {
            "success": False,
            "error": f"Failed to create MR in project {project_id}: {error_message}",
            "status_code": e.status_code,
            "project_id": project_id,
            "source_branch": source_branch,
            "target_branch": target_branch,
        }
    except GitLabError as e:
        return {
            "success": False,
            "error": f"Failed to create MR in project {project_id}: {e}",
            "project_id": project_id,
            "source_branch": source_branch,
            "target_branch": target_branch,
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Unexpected error while creating MR in project {project_id}: {str(e)}",
            "project_id": project_id,
            "source_branch": source_branch,
            "target_branch": target_branch,
        }
