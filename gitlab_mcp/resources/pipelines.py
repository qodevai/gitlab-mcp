"""Pipeline and job resources for gitlab-mcp."""

import base64
import json
import logging
from typing import Any
from urllib.parse import parse_qs

from fastmcp import Context
from gitlab_client import APIError, GitLabError, NotFoundError

from gitlab_mcp.server import gitlab_client, mcp
from gitlab_mcp.utils.errors import create_repo_not_found_error
from gitlab_mcp.utils.resolvers import resolve_project_id

logger = logging.getLogger(__name__)


@mcp.resource("gitlab://projects/{project_id}/pipelines/")
async def project_pipelines(ctx: Context, project_id: str) -> list[dict[str, Any]] | dict[str, Any]:
    """Get pipelines for a project (supports project_id="current")"""
    resolved_id, _ = await resolve_project_id(ctx, gitlab_client, project_id)
    if not resolved_id:
        return create_repo_not_found_error(gitlab_client.base_url)
    return gitlab_client.get_pipelines(resolved_id)


@mcp.resource("gitlab://projects/{project_id}/pipelines/{pipeline_id}")
async def project_pipeline(ctx: Context, project_id: str, pipeline_id: str) -> dict[str, Any]:
    """Get specific pipeline (supports project_id="current")"""
    resolved_id, _ = await resolve_project_id(ctx, gitlab_client, project_id)
    if not resolved_id:
        return create_repo_not_found_error(gitlab_client.base_url)
    return gitlab_client.get_pipeline(resolved_id, int(pipeline_id))


@mcp.resource("gitlab://projects/{project_id}/pipelines/{pipeline_id}/jobs")
async def project_pipeline_jobs(ctx: Context, project_id: str, pipeline_id: str) -> dict[str, Any]:
    """Get jobs for a specific pipeline (supports project_id="current")"""
    resolved_id, _ = await resolve_project_id(ctx, gitlab_client, project_id)
    if not resolved_id:
        return create_repo_not_found_error(gitlab_client.base_url)
    jobs = gitlab_client.get_pipeline_jobs(resolved_id, int(pipeline_id))

    # Enrich failed jobs with last 10 lines of logs
    enriched_jobs = gitlab_client.enrich_jobs_with_failure_logs(resolved_id, jobs)

    return {
        "pipeline_id": int(pipeline_id),
        "jobs": enriched_jobs,
        "summary": {
            "total_jobs": len(jobs),
            "failed_jobs": len([j for j in jobs if j.get("status") == "failed"]),
            "successful_jobs": len([j for j in jobs if j.get("status") == "success"]),
        },
    }


@mcp.resource("gitlab://projects/{project_id}/jobs/{job_id}/log")
async def project_job_log(ctx: Context, project_id: str, job_id: str) -> str | dict[str, Any]:
    """Get log for a specific job (supports project_id="current")

    Returns the raw log text for the job.
    """
    resolved_id, _ = await resolve_project_id(ctx, gitlab_client, project_id)
    if not resolved_id:
        return create_repo_not_found_error(gitlab_client.base_url)
    return gitlab_client.get_job_log(resolved_id, int(job_id))


@mcp.resource("gitlab://projects/{project_id}/jobs/{job_id}/artifacts")
async def project_job_artifacts(ctx: Context, project_id: str, job_id: str) -> str | dict[str, Any]:
    """List all artifacts for a job (supports project_id="current")

    Returns JSON with job details and available artifacts including:
    - job_id: Job ID
    - job_name: Job name
    - status: Job status
    - artifacts: Array of artifact objects with filename, size, file_type
    """
    resolved_id, _ = await resolve_project_id(ctx, gitlab_client, project_id)
    if not resolved_id:
        return create_repo_not_found_error(gitlab_client.base_url)

    try:
        job = gitlab_client.get_job(resolved_id, int(job_id))

        result = {
            "job_id": job.get("id"),
            "job_name": job.get("name"),
            "status": job.get("status"),
            "artifacts_file": job.get("artifacts_file", {}),
            "artifacts": job.get("artifacts", []),
        }

        return json.dumps(result, indent=2)
    except APIError as e:
        return json.dumps({"error": f"Failed to get job {job_id}: {e.status_code}"})
    except GitLabError as e:
        return json.dumps({"error": f"Failed to get job {job_id}: {e}"})
    except Exception as e:
        return json.dumps({"error": f"Unexpected error: {str(e)}"})


@mcp.resource("gitlab://projects/{project_id}/jobs/{job_id}/artifacts/{artifact_path}")
async def project_job_artifact(ctx: Context, project_id: str, job_id: str, artifact_path: str) -> str:
    """Read a specific artifact file from a job (supports project_id="current")

    Args:
        project_id: Project ID or "current"
        job_id: Job ID
        artifact_path: Path to artifact file (e.g., "logs.txt?lines=50", "build/output.log?lines=all")
            Supports query params: ?lines=N (default 10), ?offset=M (default 0), ?lines=all

    Returns:
        For text files: Content with optional line range
        For binary files: Base64-encoded content with prefix
    """
    # Parse query params from artifact_path (MCP includes them in path segment)
    if "?" in artifact_path:
        path_part, query_part = artifact_path.split("?", 1)
        params = parse_qs(query_part)
        lines = params.get("lines", ["10"])[0]
        offset = params.get("offset", ["0"])[0]
        artifact_path = path_part
    else:
        lines = "10"
        offset = "0"

    resolved_id, _ = await resolve_project_id(ctx, gitlab_client, project_id)
    if not resolved_id:
        return json.dumps(create_repo_not_found_error(gitlab_client.base_url))

    try:
        # Download artifact
        content_bytes = gitlab_client.get_job_artifact(resolved_id, int(job_id), artifact_path)

        # Try to decode as UTF-8 text
        try:
            content_text = content_bytes.decode("utf-8")

            # Handle line range for text files
            if lines == "all":
                # Return entire file
                return content_text
            else:
                # Parse line parameters
                try:
                    lines_int = int(lines)
                    offset_int = int(offset)
                except ValueError:
                    return f"Error: 'lines' and 'offset' must be integers or 'all'. Got lines={lines}, offset={offset}"

                # Split into lines and apply range
                all_lines = content_text.splitlines(keepends=True)
                total_lines = len(all_lines)

                if offset_int < 0:
                    # Negative offset means from end
                    start_idx = max(0, total_lines + offset_int)
                elif offset_int == 0 and lines_int > 0:
                    # Default: show last N lines
                    start_idx = max(0, total_lines - lines_int)
                else:
                    # Positive offset: start from that line
                    start_idx = offset_int

                end_idx = min(total_lines, start_idx + lines_int) if lines_int > 0 else total_lines

                selected_lines = all_lines[start_idx:end_idx]

                # Format with line numbers (like cat -n, starting from 1)
                formatted_lines = [f"{start_idx + i + 1:6d}\t{line}" for i, line in enumerate(selected_lines)]

                result = "".join(formatted_lines)

                # Add metadata header if lines were truncated
                if start_idx > 0 or end_idx < total_lines:
                    header = f"[Showing lines {start_idx + 1}-{end_idx} of {total_lines} total lines]\n"
                    header += "[Hint: Use ?lines=all for full file, or download_artifact tool for local access]\n\n"
                    result = header + result

                return result

        except UnicodeDecodeError:
            # Binary file - return base64 encoded
            encoded = base64.b64encode(content_bytes).decode("utf-8")
            return f"[Binary file - base64 encoded]\nSize: {len(content_bytes)} bytes\n\n{encoded}"

    except NotFoundError:
        return f"Error: Artifact '{artifact_path}' not found in job {job_id}"
    except APIError as e:
        return f"Error: Failed to get artifact (HTTP {e.status_code})"
    except Exception as e:
        return f"Error: {str(e)}"
