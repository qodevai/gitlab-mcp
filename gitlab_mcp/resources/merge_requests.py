"""Merge request resources for gitlab-mcp."""

import logging
from typing import Any

from fastmcp import Context

from gitlab_mcp.server import gitlab_client, mcp
from gitlab_mcp.utils.discussions import filter_actionable_discussions
from gitlab_mcp.utils.errors import create_repo_not_found_error
from gitlab_mcp.utils.resolvers import resolve_mr_iid, resolve_project_id

logger = logging.getLogger(__name__)


@mcp.resource("gitlab://projects/")
def all_projects() -> list[dict[str, Any]]:
    """List of all GitLab projects you have access to"""
    return gitlab_client.get_projects()


@mcp.resource("gitlab://projects/{project_id}")
async def project_by_id(ctx: Context, project_id: str) -> dict[str, Any]:
    """Get specific project by ID (supports project_id="current" for current repo)"""
    resolved_id, repo_info = await resolve_project_id(ctx, gitlab_client, project_id)
    if not resolved_id:
        return create_repo_not_found_error(gitlab_client.base_url)

    # If we already have the project info from resolution, use it
    if repo_info:
        return repo_info["project"]

    return gitlab_client.get_project(resolved_id)


@mcp.resource("gitlab://projects/{project_id}/merge-requests/")
async def project_merge_requests(ctx: Context, project_id: str) -> list[dict[str, Any]] | dict[str, Any]:
    """Get open merge requests for a project (supports project_id="current")"""
    resolved_id, _ = await resolve_project_id(ctx, gitlab_client, project_id)
    if not resolved_id:
        return create_repo_not_found_error(gitlab_client.base_url)
    return gitlab_client.get_merge_requests(resolved_id, state="opened")


@mcp.resource("gitlab://projects/{project_id}/merge-requests/{mr_iid}")
async def project_merge_request(ctx: Context, project_id: str, mr_iid: str) -> dict[str, Any]:
    """Get comprehensive MR overview (supports project_id="current" and mr_iid="current")

    Returns complete MR information including discussions, changes, commits, pipeline, and approvals.
    For granular access to specific data, use the dedicated resources (/discussions, /changes, etc.)
    """
    resolved_project_id, _ = await resolve_project_id(ctx, gitlab_client, project_id)
    if not resolved_project_id:
        return create_repo_not_found_error(gitlab_client.base_url)

    resolved_mr_iid = await resolve_mr_iid(ctx, gitlab_client, resolved_project_id, mr_iid)
    if not resolved_mr_iid:
        return {"error": f"Could not resolve MR IID '{mr_iid}'"}

    try:
        mr = gitlab_client.get_merge_request(resolved_project_id, resolved_mr_iid)
        discussions = gitlab_client.get_mr_discussions(resolved_project_id, resolved_mr_iid)
        changes = gitlab_client.get_mr_changes(resolved_project_id, resolved_mr_iid)
        commits = gitlab_client.get_mr_commits(resolved_project_id, resolved_mr_iid)
        pipelines = gitlab_client.get_mr_pipelines(resolved_project_id, resolved_mr_iid)

        # Try to get approvals (might fail if not available in GitLab edition)
        try:
            approvals = gitlab_client.get_mr_approvals(resolved_project_id, resolved_mr_iid)
        except Exception:
            approvals = None

        # Analyze discussions
        total_discussions = len(discussions)
        unresolved_discussions = filter_actionable_discussions(discussions)

        # Extract changed files list
        changed_files = [
            {
                "old_path": change.get("old_path"),
                "new_path": change.get("new_path"),
                "new_file": change.get("new_file", False),
                "renamed_file": change.get("renamed_file", False),
                "deleted_file": change.get("deleted_file", False),
            }
            for change in changes.get("changes", [])
        ]

        latest_pipeline = pipelines[0] if pipelines else None

        return {
            "merge_request": {
                "iid": mr["iid"],
                "title": mr["title"],
                "description": mr.get("description"),
                "state": mr["state"],
                "source_branch": mr["source_branch"],
                "target_branch": mr["target_branch"],
                "author": mr["author"],
                "web_url": mr.get("web_url"),
                "created_at": mr.get("created_at"),
                "updated_at": mr.get("updated_at"),
                "merge_status": mr.get("merge_status"),
                "draft": mr.get("draft", False),
                "work_in_progress": mr.get("work_in_progress", False),
            },
            "discussions_summary": {
                "total": total_discussions,
                "unresolved": len(unresolved_discussions),
                "resolved": total_discussions - len(unresolved_discussions),
                "unresolved_threads": unresolved_discussions,
            },
            "changes_summary": {"total_files_changed": len(changed_files), "changed_files": changed_files},
            "commits_summary": {
                "total_commits": len(commits),
                "commits": [
                    {
                        "id": c.get("id"),
                        "short_id": c.get("short_id"),
                        "title": c.get("title"),
                        "message": c.get("message"),
                        "author_name": c.get("author_name"),
                        "created_at": c.get("created_at"),
                    }
                    for c in commits
                ],
            },
            "pipeline_summary": {
                "latest_pipeline": {
                    "id": latest_pipeline["id"],
                    "status": latest_pipeline["status"],
                    "ref": latest_pipeline["ref"],
                    "web_url": latest_pipeline.get("web_url"),
                }
                if latest_pipeline
                else None
            },
            "approvals_summary": approvals if approvals else {"note": "Approvals not available or not configured"},
        }
    except Exception as e:
        return {"error": f"Failed to fetch complete MR data: {str(e)}"}


@mcp.resource("gitlab://projects/{project_id}/merge-requests/{mr_iid}/discussions")
async def project_merge_request_discussions(ctx: Context, project_id: str, mr_iid: str) -> dict[str, Any]:
    """Get discussions for a specific merge request (supports project_id="current" and mr_iid="current")"""
    resolved_project_id, _ = await resolve_project_id(ctx, gitlab_client, project_id)
    if not resolved_project_id:
        return create_repo_not_found_error(gitlab_client.base_url)

    resolved_mr_iid = await resolve_mr_iid(ctx, gitlab_client, resolved_project_id, mr_iid)
    if not resolved_mr_iid:
        return {"error": f"Could not resolve MR IID '{mr_iid}'"}

    discussions = gitlab_client.get_mr_discussions(resolved_project_id, resolved_mr_iid)

    total_discussions = len(discussions)
    unresolved_discussions = filter_actionable_discussions(discussions)

    return {
        "summary": {
            "total_discussions": total_discussions,
            "unresolved_count": len(unresolved_discussions),
            "resolved_count": total_discussions - len(unresolved_discussions),
        },
        "discussions": discussions,
        "unresolved_discussions": unresolved_discussions,
    }


@mcp.resource("gitlab://projects/{project_id}/merge-requests/{mr_iid}/changes")
async def project_merge_request_changes(ctx: Context, project_id: str, mr_iid: str) -> dict[str, Any]:
    """Get code changes/diff for a specific merge request (supports project_id="current" and mr_iid="current")"""
    resolved_project_id, _ = await resolve_project_id(ctx, gitlab_client, project_id)
    if not resolved_project_id:
        return create_repo_not_found_error(gitlab_client.base_url)

    resolved_mr_iid = await resolve_mr_iid(ctx, gitlab_client, resolved_project_id, mr_iid)
    if not resolved_mr_iid:
        return {"error": f"Could not resolve MR IID '{mr_iid}'"}

    return gitlab_client.get_mr_changes(resolved_project_id, resolved_mr_iid)


@mcp.resource("gitlab://projects/{project_id}/merge-requests/{mr_iid}/commits")
async def project_merge_request_commits(ctx: Context, project_id: str, mr_iid: str) -> dict[str, Any]:
    """Get commits for a specific merge request (supports project_id="current" and mr_iid="current")"""
    resolved_project_id, _ = await resolve_project_id(ctx, gitlab_client, project_id)
    if not resolved_project_id:
        return create_repo_not_found_error(gitlab_client.base_url)

    resolved_mr_iid = await resolve_mr_iid(ctx, gitlab_client, resolved_project_id, mr_iid)
    if not resolved_mr_iid:
        return {"error": f"Could not resolve MR IID '{mr_iid}'"}

    commits = gitlab_client.get_mr_commits(resolved_project_id, resolved_mr_iid)
    return {
        "total_commits": len(commits),
        "commits": commits,
    }


@mcp.resource("gitlab://projects/{project_id}/merge-requests/{mr_iid}/approvals")
async def project_merge_request_approvals(ctx: Context, project_id: str, mr_iid: str) -> dict[str, Any]:
    """Get approval status for a specific merge request (supports project_id="current" and mr_iid="current")"""
    resolved_project_id, _ = await resolve_project_id(ctx, gitlab_client, project_id)
    if not resolved_project_id:
        return create_repo_not_found_error(gitlab_client.base_url)

    resolved_mr_iid = await resolve_mr_iid(ctx, gitlab_client, resolved_project_id, mr_iid)
    if not resolved_mr_iid:
        return {"error": f"Could not resolve MR IID '{mr_iid}'"}

    try:
        return gitlab_client.get_mr_approvals(resolved_project_id, resolved_mr_iid)
    except Exception as e:
        return {
            "error": f"Failed to fetch approvals: {str(e)}",
            "note": "Approvals may not be available in this GitLab edition",
        }


@mcp.resource("gitlab://projects/{project_id}/merge-requests/{mr_iid}/pipeline-jobs")
async def project_merge_request_pipeline_jobs(ctx: Context, project_id: str, mr_iid: str) -> dict[str, Any]:
    """Get jobs for the latest pipeline of a merge request (supports project_id="current" and mr_iid="current")"""
    resolved_project_id, _ = await resolve_project_id(ctx, gitlab_client, project_id)
    if not resolved_project_id:
        return create_repo_not_found_error(gitlab_client.base_url)

    resolved_mr_iid = await resolve_mr_iid(ctx, gitlab_client, resolved_project_id, mr_iid)
    if not resolved_mr_iid:
        return {"error": f"Could not resolve MR IID '{mr_iid}'"}

    # Get pipelines for this MR
    pipelines = gitlab_client.get_mr_pipelines(resolved_project_id, resolved_mr_iid)
    if not pipelines:
        return {"error": "No pipelines found for this merge request"}

    latest_pipeline = pipelines[0]
    jobs = gitlab_client.get_pipeline_jobs(resolved_project_id, latest_pipeline["id"])

    # Enrich failed jobs with last 10 lines of logs
    enriched_jobs = gitlab_client.enrich_jobs_with_failure_logs(resolved_project_id, jobs)

    return {
        "pipeline": {
            "id": latest_pipeline["id"],
            "status": latest_pipeline["status"],
            "ref": latest_pipeline["ref"],
            "web_url": latest_pipeline.get("web_url"),
            "created_at": latest_pipeline.get("created_at"),
        },
        "jobs": enriched_jobs,
        "summary": {
            "total_jobs": len(jobs),
            "failed_jobs": len([j for j in jobs if j.get("status") == "failed"]),
            "successful_jobs": len([j for j in jobs if j.get("status") == "success"]),
        },
    }


@mcp.resource("gitlab://projects/{project_id}/merge-requests/{mr_iid}/status")
async def project_merge_request_status(ctx: Context, project_id: str, mr_iid: str) -> dict[str, Any]:
    """Get merge readiness status for a merge request (supports project_id="current" and mr_iid="current")

    Lightweight resource that answers "Is this MR ready to merge?" by checking:
    - Pipeline status (passing/failed)
    - Discussion threads (resolved/unresolved)
    - Approval status (if configured)
    - Merge conflicts
    """
    resolved_project_id, _ = await resolve_project_id(ctx, gitlab_client, project_id)
    if not resolved_project_id:
        return create_repo_not_found_error(gitlab_client.base_url)

    resolved_mr_iid = await resolve_mr_iid(ctx, gitlab_client, resolved_project_id, mr_iid)
    if not resolved_mr_iid:
        return {"error": f"Could not resolve MR IID '{mr_iid}'"}

    try:
        # Fetch core MR data
        mr = gitlab_client.get_merge_request(resolved_project_id, resolved_mr_iid)

        # Fetch pipeline + jobs (if pipeline exists)
        pipelines = gitlab_client.get_mr_pipelines(resolved_project_id, resolved_mr_iid)
        latest_pipeline = pipelines[0] if pipelines else None

        pipeline_status = None
        failed_jobs = []
        if latest_pipeline:
            jobs = gitlab_client.get_pipeline_jobs(resolved_project_id, latest_pipeline["id"])
            failed_jobs = [
                {
                    "id": j["id"],
                    "name": j["name"],
                    "stage": j.get("stage"),
                    "web_url": j.get("web_url"),
                }
                for j in jobs
                if j.get("status") == "failed"
            ]
            pipeline_status = {
                "id": latest_pipeline["id"],
                "status": latest_pipeline["status"],
                "web_url": latest_pipeline.get("web_url"),
                "failed_jobs": failed_jobs,
            }

        # Fetch discussions
        discussions = gitlab_client.get_mr_discussions(resolved_project_id, resolved_mr_iid)
        unresolved_discussions = filter_actionable_discussions(discussions)
        unresolved_ids = [d["id"] for d in unresolved_discussions]

        # Fetch approvals (may not be available)
        approvals_data = None
        try:
            approvals = gitlab_client.get_mr_approvals(resolved_project_id, resolved_mr_iid)
            approvals_data = {
                "approved": approvals.get("approved", False),
                "approvals_required": approvals.get("approvals_required", 0),
                "approvals_left": approvals.get("approvals_left", 0),
                "approved_by": [u["user"]["username"] for u in approvals.get("approved_by", [])],
            }
        except Exception:
            approvals_data = {"note": "Approvals not available or not configured"}

        # Calculate blockers
        blockers = []
        if latest_pipeline and latest_pipeline["status"] in ["failed", "canceled"]:
            blockers.append("pipeline_failed")
        if latest_pipeline and latest_pipeline["status"] in ["pending", "running", "created"]:
            blockers.append("pipeline_running")
        if len(unresolved_discussions) > 0:
            blockers.append("unresolved_discussions")
        if approvals_data and not approvals_data.get("note") and not approvals_data.get("approved"):
            blockers.append("approvals_required")
        if mr.get("merge_status") == "cannot_be_merged":
            blockers.append("merge_conflicts")
        if mr.get("draft") or mr.get("work_in_progress"):
            blockers.append("draft")

        ready_to_merge = (
            len(blockers) == 0
            and mr.get("state") == "opened"
            and (not latest_pipeline or latest_pipeline["status"] == "success")
        )

        return {
            "ready_to_merge": ready_to_merge,
            "blockers": blockers,
            "merge_request": {
                "iid": mr["iid"],
                "title": mr["title"],
                "state": mr["state"],
                "merge_status": mr.get("merge_status"),
                "draft": mr.get("draft", False),
                "web_url": mr.get("web_url"),
            },
            "pipeline": pipeline_status,
            "discussions": {
                "total": len(discussions),
                "unresolved": len(unresolved_discussions),
                "unresolved_ids": unresolved_ids,
            },
            "approvals": approvals_data,
        }
    except Exception as e:
        return {"error": f"Failed to fetch MR status: {str(e)}"}
