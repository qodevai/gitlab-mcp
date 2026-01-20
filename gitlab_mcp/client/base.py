"""Base GitLab client mixin with HTTP primitives."""

import logging
import os
from typing import Any
from urllib.parse import quote

import httpx
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

logger = logging.getLogger(__name__)


class BaseClientMixin:
    """Base mixin providing HTTP primitives and initialization."""

    token: str | None
    base_url: str
    api_url: str
    client: httpx.Client

    def __init__(self, token: str | None = None, base_url: str | None = None, validate: bool = True):
        """Initialize GitLab API client.

        Args:
            token: GitLab personal access token
            base_url: GitLab instance URL
            validate: Whether to validate configuration and test connectivity on init
        """
        self.token = token or os.getenv("GITLAB_TOKEN")
        self.base_url = (
            base_url or os.getenv("GITLAB_BASE_URL") or os.getenv("GITLAB_URL") or "https://gitlab.com"
        ).rstrip("/")

        self._validate_configuration()

        self.api_url = f"{self.base_url}/api/v4"
        # Type assertion: self.token is guaranteed to be str after validation
        headers: dict[str, str] = {"PRIVATE-TOKEN": str(self.token), "Content-Type": "application/json"}
        self.client = httpx.Client(
            base_url=self.api_url,
            headers=headers,
            timeout=30.0,
        )

        if validate:
            self._test_connectivity()
        else:
            logger.info(f"GitLab client initialized for {self.base_url} (validation skipped)")

    def _validate_configuration(self) -> None:
        """Validate token and URL configuration."""
        if not self.token:
            logger.error("GITLAB_TOKEN not set in environment variables")
            raise ValueError("GITLAB_TOKEN environment variable is required. Set it in your .env file or environment.")

        if not self.base_url.startswith(("http://", "https://")):
            logger.error(f"Invalid GITLAB_URL: {self.base_url}")
            raise ValueError(f"GITLAB_URL must start with http:// or https://, got: {self.base_url}")

    def _test_connectivity(self) -> None:
        """Test connectivity to GitLab instance."""
        try:
            version_info = self.get("/version")
            logger.info(f"Connected to GitLab {version_info.get('version', 'unknown')} at {self.base_url}")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                logger.error("GitLab authentication failed - check your GITLAB_TOKEN")
                raise ValueError("Invalid GITLAB_TOKEN - authentication failed") from e
            logger.error(f"GitLab API returned error: {e.response.status_code}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Failed to connect to GitLab at {self.base_url}: {e}")
            raise ValueError(f"Cannot connect to GitLab at {self.base_url}. Check your GITLAB_URL.") from e
        except Exception as e:
            logger.exception(f"Unexpected error during GitLab client initialization: {e}")
            raise

    @staticmethod
    def _encode_project_id(project_id: str) -> str:
        """Encode project ID for URL path (DRY principle)."""
        return quote(project_id, safe="")

    def get(self, endpoint: str, params: dict[str, Any] | None = None) -> Any:
        """GET request to GitLab API with error handling."""
        try:
            logger.debug(f"GET {endpoint} with params={params}")
            response = self.client.get(endpoint, params=params)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"GitLab API error for GET {endpoint}: {e.response.status_code} - {e.response.text[:200]}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Network error for GET {endpoint}: {e}")
            raise
        except Exception as e:
            logger.exception(f"Unexpected error for GET {endpoint}: {e}")
            raise

    def get_paginated(
        self, endpoint: str, params: dict[str, Any] | None = None, per_page: int = 100, max_pages: int = 100
    ) -> list[Any]:
        """GET request with pagination support and safety limits.

        Args:
            endpoint: API endpoint to call
            params: Query parameters
            per_page: Results per page (max 100, GitLab limit)
            max_pages: Maximum number of pages to fetch (prevents infinite loops)

        Returns:
            List of results from all pages
        """
        params = params or {}
        params["per_page"] = min(per_page, 100)  # GitLab maximum is 100
        params["page"] = 1

        all_results = []
        pages_fetched = 0

        try:
            while pages_fetched < max_pages:
                logger.debug(f"GET {endpoint} page {params['page']} (per_page={params['per_page']})")
                response = self.client.get(endpoint, params=params)
                response.raise_for_status()
                results = response.json()

                if not results:
                    break

                all_results.extend(results)
                pages_fetched += 1

                # Check if there are more pages
                if "x-next-page" not in response.headers or not response.headers["x-next-page"]:
                    break

                params["page"] += 1

            if pages_fetched >= max_pages:
                logger.warning(f"Hit max_pages limit ({max_pages}) for {endpoint}. Results may be incomplete.")

            logger.debug(f"Fetched {len(all_results)} results from {pages_fetched} pages for {endpoint}")
            return all_results

        except httpx.HTTPStatusError as e:
            logger.error(f"GitLab API error during pagination of {endpoint}: {e.response.status_code}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Network error during pagination of {endpoint}: {e}")
            raise
        except Exception as e:
            logger.exception(f"Unexpected error during pagination of {endpoint}: {e}")
            raise

    def get_projects(self, owned: bool = False, membership: bool = True) -> list[dict[str, Any]]:
        """Get all projects."""
        params = {"membership": membership, "owned": owned}
        return self.get_paginated("/projects", params=params)

    def get_project(self, project_id: str) -> dict[str, Any]:
        """Get a specific project by ID or path."""
        encoded_id = self._encode_project_id(project_id)
        return self.get(f"/projects/{encoded_id}")
