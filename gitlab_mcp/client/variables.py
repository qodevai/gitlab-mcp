"""CI/CD variables client mixin."""

import logging
from typing import Any
from urllib.parse import quote

import httpx

from gitlab_mcp.client.base import BaseClientMixin

logger = logging.getLogger(__name__)


class VariablesMixin(BaseClientMixin):
    """Mixin for CI/CD variable operations."""

    def get_project_variable(self, project_id: str, key: str) -> dict[str, Any] | None:
        """Get a specific CI/CD variable for a project.

        Args:
            project_id: Project ID or path
            key: Variable key/name

        Returns:
            Variable data if exists, None if not found

        Raises:
            httpx.HTTPStatusError: If API error (except 404)
        """
        encoded_id = self._encode_project_id(project_id)

        try:
            logger.debug(f"Getting CI/CD variable '{key}' from project {project_id}")
            # URL encode the key to handle special characters
            encoded_key = quote(key, safe="")
            response = self.client.get(f"/projects/{encoded_id}/variables/{encoded_key}")
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                # Variable doesn't exist - this is expected for upsert logic
                logger.debug(f"CI/CD variable '{key}' not found in project {project_id}")
                return None
            logger.error(f"API error getting CI/CD variable '{key}': {e.response.status_code}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Network error getting CI/CD variable '{key}': {e}")
            raise
        except Exception as e:
            logger.exception(f"Unexpected error getting CI/CD variable '{key}': {e}")
            raise

    def _sanitize_variable(self, var: dict[str, Any]) -> dict[str, Any]:
        """Remove sensitive value field from variable data.

        Args:
            var: Variable data from GitLab API

        Returns:
            Variable metadata without the value field (for security)
        """
        return {
            "key": var.get("key"),
            "variable_type": var.get("variable_type"),
            "protected": var.get("protected"),
            "masked": var.get("masked"),
            "raw": var.get("raw"),
            "environment_scope": var.get("environment_scope"),
            "description": var.get("description"),
        }

    def list_project_variables(
        self,
        project_id: str,
        per_page: int = 100,
        max_pages: int = 100,
    ) -> list[dict[str, Any]]:
        """List all CI/CD variables for a project (values not included for security).

        Args:
            project_id: Project ID or path
            per_page: Results per page (default: 100)
            max_pages: Max pages to fetch (default: 100)

        Returns:
            List of variable metadata (without values)
        """
        encoded_id = self._encode_project_id(project_id)
        logger.debug(f"Listing CI/CD variables for project {project_id}")
        variables = self.get_paginated(
            f"/projects/{encoded_id}/variables",
            per_page=per_page,
            max_pages=max_pages,
        )
        # Sanitize: remove value field for security
        return [self._sanitize_variable(var) for var in variables]

    def create_project_variable(
        self,
        project_id: str,
        key: str,
        value: str,
        variable_type: str = "env_var",
        protected: bool = False,
        masked: bool = False,
        raw: bool = False,
        environment_scope: str = "*",
        description: str | None = None,
    ) -> dict[str, Any]:
        """Create a new CI/CD variable for a project.

        Args:
            project_id: Project ID or path
            key: Variable key/name
            value: Variable value
            variable_type: Type of variable ("env_var" or "file")
            protected: Whether variable is only available in protected branches
            masked: Whether variable is hidden in job logs
            raw: Whether to disable variable expansion
            environment_scope: Environment scope (e.g., "*", "production", "staging")
            description: Optional description of the variable

        Returns:
            Created variable data

        Raises:
            httpx.HTTPStatusError: If variable creation fails
        """
        encoded_id = self._encode_project_id(project_id)

        data: dict[str, Any] = {
            "key": key,
            "value": value,
            "variable_type": variable_type,
            "protected": protected,
            "masked": masked,
            "raw": raw,
            "environment_scope": environment_scope,
        }

        if description is not None:
            data["description"] = description

        try:
            logger.info(f"Creating CI/CD variable '{key}' in project {project_id}")
            response = self.client.post(f"/projects/{encoded_id}/variables", json=data)
            response.raise_for_status()
            logger.info(f"Successfully created CI/CD variable '{key}'")
            return response.json()
        except httpx.HTTPStatusError as e:
            error_detail = e.response.text[:500] if e.response.text else "No error details"
            logger.error(f"Failed to create CI/CD variable '{key}': {e.response.status_code} - {error_detail}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Network error while creating CI/CD variable '{key}': {e}")
            raise
        except Exception as e:
            logger.exception(f"Unexpected error while creating CI/CD variable '{key}': {e}")
            raise

    def update_project_variable(
        self,
        project_id: str,
        key: str,
        value: str,
        variable_type: str = "env_var",
        protected: bool = False,
        masked: bool = False,
        raw: bool = False,
        environment_scope: str = "*",
        description: str | None = None,
    ) -> dict[str, Any]:
        """Update an existing CI/CD variable for a project.

        Args:
            project_id: Project ID or path
            key: Variable key/name
            value: Variable value
            variable_type: Type of variable ("env_var" or "file")
            protected: Whether variable is only available in protected branches
            masked: Whether variable is hidden in job logs
            raw: Whether to disable variable expansion
            environment_scope: Environment scope (e.g., "*", "production", "staging")
            description: Optional description of the variable

        Returns:
            Updated variable data

        Raises:
            httpx.HTTPStatusError: If variable update fails
        """
        encoded_id = self._encode_project_id(project_id)

        data: dict[str, Any] = {
            "value": value,
            "variable_type": variable_type,
            "protected": protected,
            "masked": masked,
            "raw": raw,
            "environment_scope": environment_scope,
        }

        if description is not None:
            data["description"] = description

        try:
            logger.info(f"Updating CI/CD variable '{key}' in project {project_id}")
            # URL encode the key to handle special characters
            encoded_key = quote(key, safe="")
            response = self.client.put(f"/projects/{encoded_id}/variables/{encoded_key}", json=data)
            response.raise_for_status()
            logger.info(f"Successfully updated CI/CD variable '{key}'")
            return response.json()
        except httpx.HTTPStatusError as e:
            error_detail = e.response.text[:500] if e.response.text else "No error details"
            logger.error(f"Failed to update CI/CD variable '{key}': {e.response.status_code} - {error_detail}")
            raise
        except httpx.RequestError as e:
            logger.error(f"Network error while updating CI/CD variable '{key}': {e}")
            raise
        except Exception as e:
            logger.exception(f"Unexpected error while updating CI/CD variable '{key}': {e}")
            raise

    def set_project_variable(
        self,
        project_id: str,
        key: str,
        value: str,
        variable_type: str = "env_var",
        protected: bool = False,
        masked: bool = False,
        raw: bool = False,
        environment_scope: str = "*",
        description: str | None = None,
    ) -> tuple[dict[str, Any], str]:
        """Set a CI/CD variable (upsert: update if exists, create if not).

        Args:
            project_id: Project ID or path
            key: Variable key/name
            value: Variable value
            variable_type: Type of variable ("env_var" or "file")
            protected: Whether variable is only available in protected branches
            masked: Whether variable is hidden in job logs
            raw: Whether to disable variable expansion
            environment_scope: Environment scope (e.g., "*", "production", "staging")
            description: Optional description of the variable

        Returns:
            Tuple of (variable data, action) where action is "created" or "updated"

        Raises:
            httpx.HTTPStatusError: If variable operation fails
        """
        # Check if variable exists
        existing_var = self.get_project_variable(project_id, key)

        if existing_var:
            # Variable exists - update it
            variable = self.update_project_variable(
                project_id=project_id,
                key=key,
                value=value,
                variable_type=variable_type,
                protected=protected,
                masked=masked,
                raw=raw,
                environment_scope=environment_scope,
                description=description,
            )
            return variable, "updated"
        else:
            # Variable doesn't exist - create it
            variable = self.create_project_variable(
                project_id=project_id,
                key=key,
                value=value,
                variable_type=variable_type,
                protected=protected,
                masked=masked,
                raw=raw,
                environment_scope=environment_scope,
                description=description,
            )
            return variable, "created"
