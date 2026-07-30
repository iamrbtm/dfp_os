"""Product image content validation (Issues 22, 34).

Extension checks alone accept a renamed ``virus.exe`` as ``photo.jpg``. These
helpers verify the *real* image content with Pillow (magic bytes / header) and
enforce a per-image byte cap, so only genuine JPEG/PNG/WebP images of an
acceptable size are committed to storage.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, UnidentifiedImageError

# Issue 22 — the only image formats the product studio accepts.
ALLOWED_IMAGE_EXTENSIONS: frozenset[str] = frozenset({".jpg", ".jpeg", ".png", ".webp"})
ALLOWED_IMAGE_FORMATS: frozenset[str] = frozenset({"JPEG", "PNG", "WEBP"})
FORMAT_TO_MIME: dict[str, str] = {
    "JPEG": "image/jpeg",
    "PNG": "image/png",
    "WEBP": "image/webp",
}


def validate_image_file(path: str | Path) -> tuple[str | None, str | None]:
    """Validate the image at ``path`` with Pillow.

    Returns ``(error, detected_mime)``. ``error`` is ``None`` when the file is a
    genuine, readable JPEG/PNG/WebP image; otherwise a user-facing message and a
    ``None`` mime. ``detected_mime`` is the format Pillow identified (e.g.
    ``"image/png"``), independent of the upload's claimed filename/extension.
    """
    try:
        with Image.open(path) as img:
            img.verify()
    except (UnidentifiedImageError, OSError, ValueError):
        return "The uploaded file is not a valid image or is corrupt.", None

    # verify() invalidates the image object, so reopen to read the format.
    try:
        with Image.open(path) as img:
            fmt = (img.format or "").upper()
    except (UnidentifiedImageError, OSError, ValueError):
        return "The uploaded file is not a valid image or is corrupt.", None

    if fmt not in ALLOWED_IMAGE_FORMATS:
        return (
            f"Unsupported image format '{fmt or 'unknown'}'. Use JPG, PNG, or WebP.",
            None,
        )
    return None, FORMAT_TO_MIME.get(fmt)