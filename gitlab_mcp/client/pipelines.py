"""Pipeline and job client mixin."""

import logging
import time
from typing import Any

import httpx

from gitlab_mcp.client.base import BaseClientMixin

logger = logging.getLogger(__name__)


class PipelinesMixin(BaseClientMixin):
    """Mixin for pipeline and job operations."""

    def get_pipelines(
        self,
        project_id: str,
        ref: str | None = None,
        per_page: int = 3,
        max_pages: int = 1,
    ) -> list[dict[str, Any]]:
        """Get pipelines for a project.

        Args:
            project_id: Project ID or path
            ref: Optional branch/tag to filter by
            per_page: Number of pipelines per page (default: 3)
            max_pages: Maximum number of pages to fetch (default: 1)

        Returns:
            List of pipeline objects (default: 3 most recent)
        """
        encoded_id = self._encode_project_id(project_id)
        params = {"ref": ref} if ref else {}
        return self.get_paginated(
            f"/projects/{encoded_id}/pipelines", params=params, per_page=per_page, max_pages=max_pages
        )

    def get_pipeline(self, project_id: str, pipeline_id: int) -> dict[str, Any]:
        """Get a specific pipeline."""
        encoded_id = self._encode_project_id(project_id)
        return self.get(f"/projects/{encoded_id}/pipelines/{pipeline_id}")

    def get_pipeline_jobs(self, project_id: str, pipeline_id: int) -> list[dict[str, Any]]:
        """Get jobs for a specific pipeline."""
        encoded_id = self._encode_project_id(project_id)
        return self.get_paginated(f"/projects/{encoded_id}/pipelines/{pipeline_id}/jobs")

    def get_job_log(self, project_id: str, job_id: int) -> str:
        """Get logs for a specific job.

        Args:
            project_id: Project ID or path
            job_id: Job ID

        Returns:
            Raw log text as string
        """
        encoded_id = self._encode_project_id(project_id)
        try:
            logger.debug(f"GET /projects/{encoded_id}/jobs/{job_id}/trace")
            response = self.client.get(f"/projects/{encoded_id}/jobs/{job_id}/trace")
            response.raise_for_status()
            # Job logs are returned as plain text, not JSON
            return response.text
        except httpx.HTTPStatusError as e:
            logger.error(f"GitLab API error for GET job {job_id} trace: {e.response.status_code}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Network error for GET job {job_id} trace: {e}")
            raise
        except Exception as e:
            logger.exception(f"Unexpected error for GET job {job_id} trace: {e}")
            raise

    def get_job(self, project_id: str, job_id: int) -> dict[str, Any]:
        """Get job details including artifact metadata.

        Args:
            project_id: Project ID or path
            job_id: Job ID

        Returns:
            Job details dictionary including artifacts array

        Raises:
            httpx.HTTPStatusError: If job not found or access denied
        """
        encoded_id = self._encode_project_id(project_id)
        try:
            logger.debug(f"GET /projects/{encoded_id}/jobs/{job_id}")
            response = self.client.get(f"/projects/{encoded_id}/jobs/{job_id}")
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"GitLab API error for GET job {job_id}: {e.response.status_code}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Network error for GET job {job_id}: {e}")
            raise
        except Exception as e:
            logger.exception(f"Unexpected error for GET job {job_id}: {e}")
            raise

    def retry_job(self, project_id: str, job_id: int) -> dict[str, Any]:
        """Retry a job (creates a new job).

        Args:
            project_id: Project ID or path
            job_id: Job ID to retry

        Returns:
            New job details dictionary

        Raises:
            httpx.HTTPStatusError: If job not found or cannot be retried
        """
        encoded_id = self._encode_project_id(project_id)
        try:
            logger.info(f"Retrying job {job_id} in project {project_id}")
            response = self.client.post(f"/projects/{encoded_id}/jobs/{job_id}/retry")
            response.raise_for_status()
            logger.info(f"Successfully retried job {job_id}")
            return response.json()
        except httpx.HTTPStatusError as e:
            error_detail = e.response.text[:500] if e.response.text else "No error details"
            logger.error(f"Failed to retry job {job_id}: {e.response.status_code} - {error_detail}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Network error while retrying job {job_id}: {e}")
            raise
        except Exception as e:
            logger.exception(f"Unexpected error while retrying job {job_id}: {e}")
            raise

    def get_job_artifact(self, project_id: str, job_id: int, artifact_path: str) -> bytes:
        """Download a specific artifact file from a job.

        Args:
            project_id: Project ID or path
            job_id: Job ID
            artifact_path: Path to the artifact file within the job's artifact archive

        Returns:
            Raw bytes of the artifact file

        Raises:
            httpx.HTTPStatusError: If artifact not found or access denied
        """
        encoded_id = self._encode_project_id(project_id)
        try:
            logger.debug(f"GET /projects/{encoded_id}/jobs/{job_id}/artifacts/{artifact_path}")
            response = self.client.get(f"/projects/{encoded_id}/jobs/{job_id}/artifacts/{artifact_path}")
            response.raise_for_status()
            # Return raw bytes for artifact content
            return response.content
        except httpx.HTTPStatusError as e:
            logger.error(f"GitLab API error for GET job {job_id} artifact {artifact_path}: {e.response.status_code}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Network error for GET job {job_id} artifact {artifact_path}: {e}")
            raise
        except Exception as e:
            logger.exception(f"Unexpected error for GET job {job_id} artifact {artifact_path}: {e}")
            raise

    def enrich_jobs_with_failure_logs(self, project_id: str, jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Enrich failed jobs with last 10 lines of their logs.

        Args:
            project_id: Project ID or path
            jobs: List of job objects

        Returns:
            Jobs list with failure_log_tail added to failed jobs
        """
        enriched_jobs = []
        for job in jobs:
            job_copy = job.copy()
            if job.get("status") == "failed":
                try:
                    full_log = self.get_job_log(project_id, job["id"])
                    log_lines = full_log.split("\n")
                    # Get last 10 non-empty lines
                    last_lines = [line for line in log_lines if line.strip()][-10:]
                    job_copy["failure_log_tail"] = "\n".join(last_lines)
                    job_copy["log_note"] = (
                        f"Showing last 10 lines. Full log: gitlab://projects/{project_id}/jobs/{job['id']}/log"
                    )
                except Exception as e:
                    logger.warning(f"Failed to fetch log for job {job['id']}: {e}")
                    job_copy["log_note"] = (
                        f"Failed to fetch log. Full log: gitlab://projects/{project_id}/jobs/{job['id']}/log"
                    )
            enriched_jobs.append(job_copy)
        return enriched_jobs

    def wait_for_pipeline(
        self,
        project_id: str,
        pipeline_id: int,
        timeout_seconds: int = 3600,
        check_interval: int = 10,
        include_failed_logs: bool = True,
    ) -> dict[str, Any]:
        """Wait for a pipeline to complete (success or failure).

        Args:
            project_id: Project ID or path
            pipeline_id: Pipeline ID to wait for
            timeout_seconds: Maximum time to wait in seconds (default: 3600/1 hour)
            check_interval: How often to check status in seconds (default: 10)
            include_failed_logs: Include last 10 lines of failed job logs (default: True)

        Returns:
            Dict with status, duration, job summary, and optionally failed job logs

        Raises:
            httpx.HTTPStatusError: If API calls fail
        """
        start_time = time.time()
        checks = 0

        logger.info(
            f"Waiting for pipeline {pipeline_id} in project {project_id} "
            f"(timeout: {timeout_seconds}s, interval: {check_interval}s)"
        )

        final_status = None
        pipeline = None

        try:
            while True:
                checks += 1
                elapsed = time.time() - start_time

                # Get current pipeline status
                pipeline = self.get_pipeline(project_id, pipeline_id)
                status = pipeline.get("status")

                logger.debug(f"Check #{checks}: Pipeline {pipeline_id} status = {status} " f"(elapsed: {elapsed:.1f}s)")

                # Check if pipeline has completed
                if status in ["success", "failed", "canceled", "skipped"]:
                    final_status = status
                    logger.info(
                        f"Pipeline {pipeline_id} completed with status '{status}' "
                        f"after {elapsed:.1f}s ({checks} checks)"
                    )
                    break

                # Check timeout
                if elapsed > timeout_seconds:
                    final_status = "timeout"
                    logger.warning(f"Pipeline {pipeline_id} timed out after {elapsed:.1f}s " f"(status was '{status}')")
                    break

                # Wait before next check
                time.sleep(check_interval)

        except httpx.HTTPStatusError as e:
            error_detail = e.response.text[:500] if e.response.text else "No error details"
            logger.error(f"Failed to check pipeline {pipeline_id}: {e.response.status_code} - {error_detail}")
            raise
        except Exception as e:
            logger.exception(f"Unexpected error while waiting for pipeline {pipeline_id}: {e}")
            raise

        # Build response
        total_duration = time.time() - start_time
        result: dict[str, Any] = {
            "final_status": final_status,
            "pipeline_id": pipeline_id,
            "pipeline_url": pipeline.get("web_url") if pipeline else None,
            "total_duration": round(total_duration, 2),
            "checks_performed": checks,
        }

        # Get job summary if pipeline completed
        if pipeline and final_status != "timeout":
            try:
                jobs = self.get_pipeline_jobs(project_id, pipeline_id)
                job_summary = {
                    "total": len(jobs),
                    "success": len([j for j in jobs if j.get("status") == "success"]),
                    "failed": len([j for j in jobs if j.get("status") == "failed"]),
                }
                result["job_summary"] = job_summary

                # Include failed job logs if requested
                if include_failed_logs and final_status == "failed":
                    failed_jobs = [j for j in jobs if j.get("status") == "failed"]
                    failed_job_details = []

                    for job in failed_jobs[:5]:  # Limit to first 5 failed jobs
                        job_detail = {
                            "id": job.get("id"),
                            "name": job.get("name"),
                            "status": job.get("status"),
                            "web_url": job.get("web_url"),
                        }

                        # Try to fetch last 10 lines of log
                        try:
                            log = self.get_job_log(project_id, job["id"])
                            lines = log.strip().split("\n")
                            job_detail["last_log_lines"] = "\n".join(lines[-10:])
                        except Exception as log_error:
                            logger.warning(f"Could not fetch log for job {job['id']}: {log_error}")
                            job_detail["last_log_lines"] = "(log unavailable)"

                        failed_job_details.append(job_detail)

                    result["failed_jobs"] = failed_job_details

            except Exception as job_error:
                logger.warning(f"Could not fetch job details: {job_error}")

        return result
