"""Type definitions for gitlab-mcp."""

from typing import NotRequired

from typing_extensions import TypedDict


class FileFromPath(TypedDict):
    """File input from local filesystem path."""

    path: str


class FileFromBase64(TypedDict):
    """File input from base64-encoded data."""

    base64: str
    filename: str


# Union type - either path OR base64+filename, not both
FileSource = FileFromPath | FileFromBase64


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


class DiffPosition(TypedDict):
    """Position in a merge request diff for inline comments."""

    file_path: str
    new_line: NotRequired[int]
    old_line: NotRequired[int]
    new_line_content: NotRequired[str]
    old_line_content: NotRequired[str]
    base_sha: NotRequired[str]
    head_sha: NotRequired[str]
    start_sha: NotRequired[str]
