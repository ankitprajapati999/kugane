# -*- coding: utf-8 -*-
"""core/media — Modular media inspection, text extraction, and Gemini attachment building."""

from core.media.file_processor import (
    MEDIA_CATEGORIES,
    MediaCategory,
    MediaAttachment,
    FileProcessor,
)

__all__ = [
    "MEDIA_CATEGORIES",
    "MediaCategory",
    "MediaAttachment",
    "FileProcessor",
]
