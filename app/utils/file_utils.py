"""File utilities for handling Telegram files."""
import os
import tempfile
from pathlib import Path
from typing import BinaryIO

from PIL import Image


def ensure_temp_dir() -> Path:
    """Ensure temp directory exists."""
    temp_dir = Path("/app/temp")
    temp_dir.mkdir(parents=True, exist_ok=True)
    return temp_dir


def download_file_to_temp(file_path: str, content: bytes) -> Path:
    """Download file content to temporary file."""
    temp_dir = ensure_temp_dir()
    temp_file = temp_dir / f"temp_{os.urandom(8).hex()}_{Path(file_path).name}"
    temp_file.write_bytes(content)
    return temp_file


def auto_rotate_image(image_path: Path) -> Path:
    """Auto-rotate image based on EXIF orientation."""
    try:
        with Image.open(image_path) as img:
            # Check if image has EXIF data
            if hasattr(img, "_getexif") and img._getexif() is not None:
                exif = img._getexif()
                orientation = exif.get(0x0112)  # EXIF orientation tag

                if orientation == 3:
                    img = img.rotate(180, expand=True)
                elif orientation == 6:
                    img = img.rotate(270, expand=True)
                elif orientation == 8:
                    img = img.rotate(90, expand=True)

                # Save rotated image
                rotated_path = image_path.parent / f"rotated_{image_path.name}"
                img.save(rotated_path)
                return rotated_path
    except Exception:
        # If rotation fails, return original
        pass

    return image_path


def get_file_extension(mime_type: str | None) -> str:
    """Get file extension from MIME type."""
    if not mime_type:
        return ""
    mime_map = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "audio/ogg": ".ogg",
        "audio/mpeg": ".mp3",
        "audio/wav": ".wav",
        "audio/x-m4a": ".m4a",
    }
    return mime_map.get(mime_type, "")

