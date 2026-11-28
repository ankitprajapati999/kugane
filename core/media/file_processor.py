# -*- coding: utf-8 -*-
"""
core/media/file_processor.py — Modular file & media processor for Kugane.

Responsibilities:
  - Define media upload categories (Photos, Documents/PDFs, Videos, Audio, Code, Any File).
  - Detect accurate MIME types and human-readable file metadata.
  - Extract readable text from Office documents (.docx, .xlsx, .pptx) using stdlib.
  - Convert local files into google-genai Part (inline bytes) or Files API objects
    so Gemini can read PDFs, images, videos, audio, and docs across multi-turn chat.
"""
from __future__ import annotations

import base64
import logging
import mimetypes
import time
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class MediaCategory:
    """Represents a selectable category in the UI upload menu."""

    key: str
    label: str
    badge: str
    dialog_filter: str


MEDIA_CATEGORIES: tuple[MediaCategory, ...] = (
    MediaCategory(
        key="photo",
        label="Photo / Image",
        badge="IMG",
        dialog_filter="Images (*.png *.jpg *.jpeg *.webp *.gif *.bmp *.heic)",
    ),
    MediaCategory(
        key="file",
        label="File",
        badge="FILE",
        dialog_filter="All Files (*)",
    ),
)

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".heic", ".heif"}
_VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".mpeg", ".mpg"}
_AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac", ".opus"}
_DOC_EXTS = {".pdf", ".docx", ".xlsx", ".pptx", ".rtf"}
_TEXT_EXTS = {
    ".txt", ".md", ".markdown", ".py", ".js", ".ts", ".tsx", ".jsx",
    ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".env",
    ".csv", ".tsv", ".log", ".sql", ".xml", ".html", ".htm", ".css",
    ".sh", ".bash", ".ps1", ".bat", ".cmd", ".rs", ".go", ".java",
    ".c", ".h", ".cpp", ".hpp", ".cs", ".rb", ".php",
}

_EXT_MIME_OVERRIDES = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".heic": "image/heic",
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".webm": "video/webm",
    ".mkv": "video/x-matroska",
    ".avi": "video/x-msvideo",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".m4a": "audio/mp4",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
    ".aac": "audio/aac",
    ".csv": "text/csv",
    ".json": "application/json",
    ".html": "text/html",
    ".htm": "text/html",
    ".css": "text/css",
}


@dataclass(frozen=True)
class MediaAttachment:
    """Lightweight UI & logging descriptor for an attached local file."""

    path: str
    name: str
    badge: str
    size_label: str
    mime_type: str


def _format_size(num_bytes: int) -> str:
    if num_bytes < 1024:
        return f"{num_bytes} B"
    if num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.1f} KB"
    return f"{num_bytes / (1024 * 1024):.1f} MB"


class FileProcessor:
    """Prepares local media and document files for Gemini multimodal chat."""

    _INLINE_MIME_PREFIXES = ("image/", "text/", "audio/", "video/")
    _INLINE_MIME_EXACT = {"application/pdf", "application/json"}
    _MAX_INLINE_BYTES = 15 * 1024 * 1024

    @classmethod
    def guess_mime_type(cls, path: Path) -> str:
        ext = path.suffix.lower()
        if ext in _EXT_MIME_OVERRIDES:
            return _EXT_MIME_OVERRIDES[ext]
        if ext in _TEXT_EXTS:
            return "text/plain"
        mime, _ = mimetypes.guess_type(str(path))
        return mime or "application/octet-stream"

    @classmethod
    def classify_badge(cls, path: Path) -> str:
        ext = path.suffix.lower()
        if ext == ".pdf":
            return "PDF"
        if ext in _IMAGE_EXTS:
            return "IMG"
        if ext in _VIDEO_EXTS:
            return "VID"
        if ext in _AUDIO_EXTS:
            return "AUD"
        if ext in _DOC_EXTS:
            return "DOC"
        if ext in _TEXT_EXTS:
            return "CODE" if ext not in {".txt", ".md", ".markdown", ".csv", ".log"} else "DOC"
        return "FILE"

    @classmethod
    def describe(cls, file_path: str) -> MediaAttachment:
        path = Path(file_path)
        size = path.stat().st_size if path.is_file() else 0
        return MediaAttachment(
            path=str(path),
            name=path.name,
            badge=cls.classify_badge(path),
            size_label=_format_size(size),
            mime_type=cls.guess_mime_type(path),
        )

    @classmethod
    def _extract_office_text(cls, path: Path) -> str:
        """Extract readable text from .docx / .pptx / .xlsx without external deps."""
        ext = path.suffix.lower()
        chunks: list[str] = []
        with zipfile.ZipFile(path, "r") as zf:
            names = zf.namelist()
            if ext == ".docx" and "word/document.xml" in names:
                root = ET.fromstring(zf.read("word/document.xml"))
                for elem in root.iter():
                    if elem.tag.endswith("}p"):
                        texts = [t.text for t in elem.iter() if t.tag.endswith("}t") and t.text]
                        if texts:
                            chunks.append("".join(texts))
            elif ext == ".pptx":
                slides = sorted(
                    n for n in names if n.startswith("ppt/slides/slide") and n.endswith(".xml")
                )
                for idx, slide_name in enumerate(slides, start=1):
                    root = ET.fromstring(zf.read(slide_name))
                    texts = [t.text for t in root.iter() if t.tag.endswith("}t") and t.text]
                    if texts:
                        chunks.append(f"[Slide {idx}]\n" + "\n".join(texts))
            elif ext == ".xlsx":
                shared: list[str] = []
                if "xl/sharedStrings.xml" in names:
                    sroot = ET.fromstring(zf.read("xl/sharedStrings.xml"))
                    for si in sroot.iter():
                        if si.tag.endswith("}si"):
                            texts = [t.text for t in si.iter() if t.tag.endswith("}t") and t.text]
                            shared.append("".join(texts))
                sheets = sorted(
                    n for n in names if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")
                )
                for sidx, sheet_name in enumerate(sheets, start=1):
                    root = ET.fromstring(zf.read(sheet_name))
                    rows_out: list[str] = []
                    for row in root.iter():
                        if row.tag.endswith("}row"):
                            vals: list[str] = []
                            for cell in row:
                                ctype = cell.attrib.get("t", "")
                                v_el = next((c for c in cell if c.tag.endswith("}v")), None)
                                if v_el is None or v_el.text is None:
                                    continue
                                if ctype == "s":
                                    idx = int(v_el.text)
                                    vals.append(shared[idx] if 0 <= idx < len(shared) else v_el.text)
                                else:
                                    vals.append(v_el.text)
                            if vals:
                                rows_out.append(" | ".join(vals))
                    if rows_out:
                        chunks.append(f"[Sheet {sidx}]\n" + "\n".join(rows_out))
        return "\n".join(chunks).strip()

    @classmethod
    def to_gemini_part(cls, file_path: str, genai_module: Any, client: Any) -> Any:
        """
        Convert a local file into a google-genai Part or uploaded File object.

        - Text/code files are normalized to UTF-8 with filename context.
        - Office docs (.docx/.xlsx/.pptx) have their text extracted cleanly.
        - PDFs, images, audio, and video <= 15 MB use Part.from_bytes; larger
          files upload via the Gemini Files API and wait until active.
        """
        path = Path(file_path)
        if not path.is_file():
            raise RuntimeError(f"Attached file not found: {file_path}")

        ext = path.suffix.lower()
        mime_type = cls.guess_mime_type(path)
        size_bytes = path.stat().st_size

        # 1. Office documents -> extracted structured text part
        if ext in {".docx", ".xlsx", ".pptx"}:
            try:
                extracted = cls._extract_office_text(path)
            except Exception as exc:
                raise RuntimeError(f"Could not read document {path.name}: {exc}") from exc
            if not extracted:
                extracted = "(Document appears empty or contains only non-text elements.)"
            payload = f"[Uploaded Document: {path.name}]\n{extracted}".encode("utf-8")
            return genai_module.types.Part.from_bytes(data=payload, mime_type="text/plain")

        # 2. Plain text / code -> UTF-8 normalized text part with filename header
        if mime_type.startswith("text/") or mime_type == "application/json":
            raw_text = path.read_bytes().decode("utf-8", errors="replace")
            payload = f"[Uploaded File: {path.name} ({mime_type})]\n{raw_text}".encode("utf-8")
            return genai_module.types.Part.from_bytes(data=payload, mime_type="text/plain")

        # 3. Native multimodal inline bytes (PDFs, images, audio, video <= 15 MB)
        is_inline_type = (
            mime_type.startswith(cls._INLINE_MIME_PREFIXES)
            or mime_type in cls._INLINE_MIME_EXACT
        )
        if is_inline_type and size_bytes <= cls._MAX_INLINE_BYTES:
            return genai_module.types.Part.from_bytes(
                data=path.read_bytes(),
                mime_type=mime_type,
            )

        # 4. Large media / PDFs -> Gemini Files API upload
        uploaded = client.files.upload(
            file=str(path),
            config={"mime_type": mime_type, "display_name": path.name},
        )
        deadline = time.monotonic() + 45.0
        while getattr(getattr(uploaded, "state", None), "name", None) == "PROCESSING":
            if time.monotonic() >= deadline:
                raise RuntimeError(f"Timed out waiting for Gemini to process {path.name}.")
            time.sleep(0.5)
            uploaded = client.files.get(name=uploaded.name)
        if getattr(getattr(uploaded, "state", None), "name", None) == "FAILED":
            raise RuntimeError(f"Gemini failed to process uploaded file: {path.name}")
        return uploaded

    @classmethod
    def to_langchain_block(cls, file_path: str) -> dict[str, Any]:
        """
        Convert a local file into a provider-agnostic LangChain content block
        compatible with both ChatGoogleGenerativeAI and FlaskVLMChatModel.
        """
        path = Path(file_path)
        if not path.is_file():
            raise RuntimeError(f"Attached file not found: {file_path}")

        ext = path.suffix.lower()
        mime_type = cls.guess_mime_type(path)
        size_bytes = path.stat().st_size

        # 1. Office documents -> extracted structured text
        if ext in {".docx", ".xlsx", ".pptx"}:
            try:
                extracted = cls._extract_office_text(path)
            except Exception as exc:
                raise RuntimeError(f"Could not read document {path.name}: {exc}") from exc
            if not extracted:
                extracted = "(Document appears empty or contains only non-text elements.)"
            return {
                "type": "text",
                "text": f"[Uploaded Document: {path.name}]\n{extracted}",
            }

        # 2. Plain text / code -> UTF-8 normalized text block
        if mime_type.startswith("text/") or mime_type == "application/json":
            raw_text = path.read_bytes().decode("utf-8", errors="replace")
            return {
                "type": "text",
                "text": f"[Uploaded File: {path.name} ({mime_type})]\n{raw_text}",
            }

        # 3. Images -> standard base64 data URL (works across Gemini & Flask VLM)
        if mime_type.startswith("image/"):
            b64 = base64.b64encode(path.read_bytes()).decode("ascii")
            return {
                "type": "image_url",
                "image_url": {"url": f"data:{mime_type};base64,{b64}"},
            }

        # 4. PDFs, audio, video <= 15 MB -> LangChain multimodal "media" block
        is_inline_type = (
            mime_type.startswith(("audio/", "video/"))
            or mime_type in cls._INLINE_MIME_EXACT
        )
        if is_inline_type and size_bytes <= cls._MAX_INLINE_BYTES:
            b64 = base64.b64encode(path.read_bytes()).decode("ascii")
            return {
                "type": "media",
                "data": b64,
                "mime_type": mime_type,
            }

        raise RuntimeError(
            f"File {path.name} ({mime_type}, {_format_size(size_bytes)}) exceeds "
            "the 15 MB inline limit for multimodal chat."
        )
