"""Image processing helpers for qodev-gitlab-mcp."""

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, cast

from qodev_gitlab_api import FileSource

from qodev_gitlab_mcp.models import ImageFromPath, ImageInput

if TYPE_CHECKING:
    from qodev_gitlab_api import GitLabClient

# Separator between content and appended images
IMAGE_MARKDOWN_SEPARATOR = "\n\n"


def prepare_description_with_images(
    image_markdown: str,
    new_description: str | None,
    fetch_current_description: Callable[[], str | None] | None = None,
) -> str | None:
    """Prepare final description by appending image markdown.

    Handles the common pattern where:
    - If images provided but no new description, append to current description
    - If images and new description provided, append images to new description
    - If no images, return the new description as-is

    Args:
        image_markdown: Markdown string from process_images (may be empty)
        new_description: New description provided by user (may be None)
        fetch_current_description: Callable to fetch current description if needed
            (only called if image_markdown is non-empty and new_description is None)

    Returns:
        Final description with images appended, or None if no description
    """
    if not image_markdown:
        return new_description

    if new_description is not None:
        return new_description + image_markdown

    # Images provided but no new description - fetch current and append
    if fetch_current_description:
        current = fetch_current_description() or ""
        return current + image_markdown

    return image_markdown


def process_images(client: "GitLabClient", project_id: str, images: list[ImageInput] | None) -> str:
    """Process image list and return markdown to append.

    Uploads each image to GitLab and returns markdown image tags.
    This helper is used by tools that support the `images` parameter.

    Args:
        client: GitLab API client instance
        project_id: Resolved project ID (must already be resolved, not "current")
        images: List of ImageInput (either ImageFromPath or ImageFromBase64)

    Returns:
        Markdown string with all uploaded images prefixed with newlines,
        or empty string if no images provided.

    Raises:
        FileNotFoundError: If a file path doesn't exist
        ValueError: If base64 data is invalid
    """
    if not images:
        return ""

    markdown_parts = []
    for img in images:
        # Convert ImageInput to FileSource (strip alt text for upload)
        if "path" in img:
            source: FileSource = {"path": cast(ImageFromPath, img)["path"]}
        else:
            source = {"base64": img["base64"], "filename": img["filename"]}

        result: dict[str, Any] = client.upload_file(project_id, source)

        # Use custom alt text if provided, otherwise use GitLab's default
        alt = img.get("alt", result.get("alt", "image"))
        markdown_parts.append(f"![{alt}]({result['url']})")

    # markdown_parts is always non-empty here since we return early if not images
    return IMAGE_MARKDOWN_SEPARATOR + "\n".join(markdown_parts)
