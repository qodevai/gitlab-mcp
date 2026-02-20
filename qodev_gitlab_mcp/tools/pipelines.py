"""Pipeline and job tools for qodev-gitlab-mcp."""

import os
import tempfile
from pathlib import Path
from typing import Any

from fastmcp import Context
from qodev_gitlab_api import APIError, GitLabError, NotFoundError

from qodev_gitlab_mcp.server import gitlab_client, mcp
from qodev_gitlab_mcp.utils.resolvers import resolve_mr_iid, resolve_project_id


@mcp.tool()
async def wait_for_pipeline(
    ctx: Context,
    project_id: str,
    pipeline_id: str | int | None = None,
    mr_iid: str | int | None = None,
    timeout_seconds: int = 3600,
    check_interval: int = 10,
    include_failed_logs: bool = True,
) -> dict[str, Any]:
    """Wait for a GitLab pipeline to complete (success or failure)

    Args:
        project_id: Project ID, path, or "current" (e.g., "mygroup/myproject", "123", or "current")
        pipeline_id: Pipeline ID to wait for (required if mr_iid not provided)
        mr_iid: MR IID to get latest pipeline from (alternative to pipeline_id, supports "current")
        timeout_seconds: Maximum time to wait in seconds (default: 3600/1 hour)
        check_interval: How often to check status in seconds (default: 10)
        include_failed_logs: Include last 10 lines of failed job logs (default: True)

    Returns:
        Result with final status, duration, job summary, and optionally failed job logs

    Raises:
        Error if wait operation fails
    """
    # Resolve project_id
    resolved_project_id, _ = await resolve_project_id(ctx, gitlab_client, project_id)
    if not resolved_project_id:
        return {"success": False, "error": f"Could not resolve project '{project_id}'"}

    # Validate that either pipeline_id or mr_iid is provided (but not both)
    if pipeline_id is None and mr_iid is None:
        return {
            "success": False,
            "error": "Must provide either 'pipeline_id' or 'mr_iid'",
        }

    if pipeline_id is not None and mr_iid is not None:
        return {
            "success": False,
            "error": "Cannot provide both 'pipeline_id' and 'mr_iid' - choose one",
        }

    # If mr_iid provided, get the latest pipeline from the MR
    resolved_pipeline_id = None
    if mr_iid is not None:
        resolved_mr_iid = await resolve_mr_iid(ctx, gitlab_client, resolved_project_id, str(mr_iid))
        if not resolved_mr_iid:
            return {"success": False, "error": f"Could not resolve MR IID '{mr_iid}'"}

        try:
            pipelines = gitlab_client.get_mr_pipelines(resolved_project_id, resolved_mr_iid)
            if not pipelines:
                return {
                    "success": False,
                    "error": f"No pipelines found for MR !{resolved_mr_iid}",
                    "project_id": project_id,
                    "mr_iid": resolved_mr_iid,
                }
            # Get the latest pipeline (first in list)
            latest_pipeline = pipelines[0]
            resolved_pipeline_id = latest_pipeline["id"]
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to get pipelines for MR !{resolved_mr_iid}: {str(e)}",
                "project_id": project_id,
                "mr_iid": resolved_mr_iid,
            }
    else:
        # Use provided pipeline_id
        if pipeline_id is None:
            return {
                "success": False,
                "error": "pipeline_id is required when mr_iid is not provided",
            }
        try:
            resolved_pipeline_id = int(pipeline_id)
        except (ValueError, TypeError):
            return {
                "success": False,
                "error": f"Invalid pipeline_id: '{pipeline_id}' (must be an integer)",
            }

    # Wait for the pipeline
    try:
        result = gitlab_client.wait_for_pipeline(
            project_id=resolved_project_id,
            pipeline_id=resolved_pipeline_id,
            timeout_seconds=timeout_seconds,
            check_interval=check_interval,
            include_failed_logs=include_failed_logs,
        )

        # Determine success based on final status
        final_status = result.get("final_status")
        is_success = final_status == "success"

        return {
            "success": is_success,
            "message": f"Pipeline {resolved_pipeline_id} completed with status '{final_status}' "
            f"after {result.get('total_duration')}s",
            **result,
            "project_id": project_id,
        }
    except APIError as e:
        return {
            "success": False,
            "error": f"Failed to wait for pipeline {resolved_pipeline_id} in project {project_id}: {e}",
            "status_code": e.status_code,
            "project_id": project_id,
            "pipeline_id": resolved_pipeline_id,
        }
    except GitLabError as e:
        return {
            "success": False,
            "error": f"Failed to wait for pipeline {resolved_pipeline_id} in project {project_id}: {e}",
            "project_id": project_id,
            "pipeline_id": resolved_pipeline_id,
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Unexpected error while waiting for pipeline {resolved_pipeline_id} in project {project_id}: {str(e)}",
            "project_id": project_id,
            "pipeline_id": resolved_pipeline_id,
        }


@mcp.tool()
async def download_artifact(
    ctx: Context,
    project_id: str,
    job_id: int,
    artifact_path: str,
    destination: str | None = None,
) -> dict[str, Any]:
    """Download an artifact file to local filesystem for analysis with shell tools.

    Downloads the complete artifact file (no truncation) to a local path.
    Useful for large files that need analysis with grep, wc, awk, etc.

    Args:
        project_id: Project ID, path, or "current" (e.g., "mygroup/myproject", "123", or "current")
        job_id: Job ID
        artifact_path: Path to artifact within job (e.g., "logs.txt", "build/output.log")
        destination: Local path to save file (optional, defaults to temp file)

    Returns:
        Result with success status and file path for shell tool access

    Raises:
        Error if download fails
    """
    resolved_id, _ = await resolve_project_id(ctx, gitlab_client, project_id)
    if not resolved_id:
        return {"success": False, "error": f"Could not resolve project '{project_id}'"}

    try:
        # Download artifact bytes
        content = gitlab_client.get_job_artifact(resolved_id, job_id, artifact_path)

        # Determine destination path
        if destination:
            file_path = Path(destination)
            file_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            # Use temp file with meaningful name
            suffix = Path(artifact_path).suffix or ".txt"
            fd, temp_path = tempfile.mkstemp(suffix=suffix, prefix=f"artifact_{job_id}_")
            os.close(fd)  # Close the file descriptor to avoid leak
            file_path = Path(temp_path)

        # Write to file
        file_path.write_bytes(content)

        return {
            "success": True,
            "message": f"Downloaded artifact to {file_path}",
            "file_path": str(file_path),
            "size_bytes": len(content),
            "job_id": job_id,
            "artifact_path": artifact_path,
        }

    except NotFoundError:
        return {
            "success": False,
            "error": f"Artifact '{artifact_path}' not found in job {job_id}",
            "job_id": job_id,
            "artifact_path": artifact_path,
        }
    except APIError as e:
        return {
            "success": False,
            "error": f"Failed to download artifact: HTTP {e.status_code}",
            "job_id": job_id,
            "artifact_path": artifact_path,
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Error downloading artifact: {str(e)}",
            "job_id": job_id,
            "artifact_path": artifact_path,
        }


@mcp.tool()
async def retry_job(
    ctx: Context,
    project_id: str,
    job_id: int,
) -> dict[str, Any]:
    """Retry a specific job by project and job ID

    Args:
        project_id: Project ID, path, or "current" (e.g., "mygroup/myproject", "123", or "current")
        job_id: Job ID to retry

    Returns:
        Result with success status and new job details

    Raises:
        Error if job retry fails
    """
    resolved_id, _ = await resolve_project_id(ctx, gitlab_client, project_id)
    if not resolved_id:
        return {"success": False, "error": f"Could not resolve project '{project_id}'"}

    try:
        result = gitlab_client.retry_job(resolved_id, job_id)

        return {
            "success": True,
            "message": f"Successfully retried job {job_id} in project {project_id}",
            "new_job": {
                "id": result.get("id"),
                "name": result.get("name"),
                "status": result.get("status"),
                "web_url": result.get("web_url"),
            },
            "project_id": project_id,
            "original_job_id": job_id,
        }
    except APIError as e:
        return {
            "success": False,
            "error": f"Failed to retry job {job_id} in project {project_id}: {e}",
            "status_code": e.status_code,
            "project_id": project_id,
            "job_id": job_id,
        }
    except GitLabError as e:
        return {
            "success": False,
            "error": f"Failed to retry job {job_id} in project {project_id}: {e}",
            "project_id": project_id,
            "job_id": job_id,
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Unexpected error while retrying job {job_id} in project {project_id}: {str(e)}",
            "project_id": project_id,
            "job_id": job_id,
        }
