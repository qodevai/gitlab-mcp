"""MCP-specific type definitions for gitlab-mcp.

Note: Common types (FileSource, DiffPosition, etc.) are in the gitlab-client library.
This module contains only MCP-specific types like ImageInput.
"""

from typing import NotRequired

from typing_extensions import TypedDict


class ImageFromPath(TypedDict):
    """Image input from local file path."""

    path: str
    alt: NotRequired[str]


class ImageFromBase64(TypedDict):
    """Image input from base64-encoded data."""

    base64: str
    filename: str
    alt: NotRequired[str]


# Union type for images parameter
ImageInput = ImageFromPath | ImageFromBase64
