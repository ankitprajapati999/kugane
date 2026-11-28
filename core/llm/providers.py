# -*- coding: utf-8 -*-
"""
core/llm/providers.py — Swappable LangChain LLM / VLM provider factory.

Supports:
  - "gemini"    : Official Google Gemini via langchain-google-genai (default)
  - "flask_vlm" : Custom LangChain BaseChatModel pointing to a local/LAN Flask
                  server running a VLM model on another laptop.
"""
from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any, Callable, Iterator, Optional, Sequence

import requests
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage,
)
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from langchain_core.utils.function_calling import convert_to_openai_tool
from pydantic import Field

log = logging.getLogger(__name__)


class ProviderConfigError(Exception):
    """Raised when the configured LLM or VLM provider cannot be initialised."""


def _extract_data_url_b64(url: str) -> str:
    if ";base64," in url:
        return url.split(";base64,", 1)[1]
    return url


def _serialize_message(msg: BaseMessage) -> dict[str, Any]:
    """Serialize a LangChain BaseMessage into a clean JSON-friendly dict for Flask VLM."""
    if isinstance(msg, SystemMessage):
        role = "system"
    elif isinstance(msg, HumanMessage):
        role = "user"
    elif isinstance(msg, AIMessage):
        role = "assistant"
    elif isinstance(msg, ToolMessage):
        role = "tool"
    else:
        role = "user"

    text_parts: list[str] = []
    images_b64: list[str] = []
    media_items: list[dict[str, str]] = []

    content = msg.content
    if isinstance(content, str):
        text_parts.append(content)
    elif isinstance(content, list):
        for block in content:
            if isinstance(block, str):
                text_parts.append(block)
            elif isinstance(block, dict):
                btype = block.get("type", "")
                if btype == "text":
                    text_parts.append(str(block.get("text", "")))
                elif btype == "image_url":
                    raw_url = block.get("image_url", "")
                    if isinstance(raw_url, dict):
                        raw_url = raw_url.get("url", "")
                    if raw_url:
                        images_b64.append(_extract_data_url_b64(str(raw_url)))
                elif btype == "media":
                    mime = str(block.get("mime_type", "application/octet-stream"))
                    data = str(block.get("data", ""))
                    if mime.startswith("image/") and data:
                        images_b64.append(data)
                    elif data:
                        media_items.append({"mime_type": mime, "data": data})

    payload: dict[str, Any] = {
        "role": role,
        "content": "\n".join(p for p in text_parts if p).strip(),
    }
    if images_b64:
        payload["images"] = images_b64
    if media_items:
        payload["media"] = media_items
    if isinstance(msg, ToolMessage):
        payload["tool_call_id"] = msg.tool_call_id
        payload["name"] = msg.name or ""
    if isinstance(msg, AIMessage) and msg.tool_calls:
        payload["tool_calls"] = msg.tool_calls
    return payload


class FlaskVLMChatModel(BaseChatModel):
    """
    Custom LangChain BaseChatModel that forwards chat + images + tool schemas
    to a Flask VLM endpoint running on a connected laptop.

    Expected Flask JSON request:
        {
            "messages": [{"role": "user", "content": "...", "images": ["<b64>"]}],
            "tools": [...],       # optional OpenAI-schema tool definitions
            "temperature": 0.3
        }

    Accepted Flask JSON responses:
        - {"response": "..."} or {"text": "..."} or {"content": "..."}
        - {"tool_calls": [{"name": "...", "args": {...}, "id": "..."}]}
        - OpenAI-compatible {"choices": [{"message": {"content": "...", "tool_calls": [...]}}]}
    """

    endpoint_url: str = Field(...)
    timeout: float = Field(default=120.0)
    api_key: str = Field(default="")
    temperature: float = Field(default=0.3)
    bound_tools: list[dict[str, Any]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "flask_vlm"

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | Callable | BaseTool],
        *,
        tool_choice: Optional[str] = None,
        **kwargs: Any,
    ) -> Runnable[Any, AIMessage]:
        formatted = [convert_to_openai_tool(t) for t in tools]
        return self.model_copy(update={"bound_tools": formatted})

    def _parse_response_payload(self, data: dict[str, Any]) -> AIMessage:
        # OpenAI-compatible envelope
        if "choices" in data and isinstance(data["choices"], list) and data["choices"]:
            msg_obj = data["choices"][0].get("message", {}) or {}
            content = str(msg_obj.get("content") or "")
            raw_calls = msg_obj.get("tool_calls") or []
            parsed_calls = self._normalize_tool_calls(raw_calls)
            return AIMessage(content=content, tool_calls=parsed_calls)

        content = str(
            data.get("response")
            or data.get("content")
            or data.get("text")
            or data.get("output")
            or ""
        )
        raw_calls = data.get("tool_calls") or []
        parsed_calls = self._normalize_tool_calls(raw_calls)

        # Fallback: parse <tool_call>{"name": ..., "arguments": {...}}</tool_call>
        if not parsed_calls and "<tool_call>" in content:
            matches = re.findall(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", content, re.DOTALL)
            for raw_json in matches:
                try:
                    tc = json.loads(raw_json)
                    parsed_calls.append(
                        {
                            "name": str(tc["name"]),
                            "args": tc.get("args") or tc.get("arguments") or {},
                            "id": str(tc.get("id") or f"call_{uuid.uuid4().hex[:8]}"),
                            "type": "tool_call",
                        }
                    )
                except Exception:
                    continue
            content = re.sub(r"<tool_call>.*?</tool_call>", "", content, flags=re.DOTALL).strip()

        return AIMessage(content=content, tool_calls=parsed_calls)

    @staticmethod
    def _normalize_tool_calls(raw_calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for tc in raw_calls:
            if not isinstance(tc, dict):
                continue
            if "function" in tc and isinstance(tc["function"], dict):
                fn = tc["function"]
                raw_args = fn.get("arguments", {})
                args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
                out.append(
                    {
                        "name": str(fn.get("name", "")),
                        "args": args,
                        "id": str(tc.get("id") or f"call_{uuid.uuid4().hex[:8]}"),
                        "type": "tool_call",
                    }
                )
            elif "name" in tc:
                raw_args = tc.get("args") or tc.get("arguments") or {}
                args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                out.append(
                    {
                        "name": str(tc["name"]),
                        "args": args,
                        "id": str(tc.get("id") or f"call_{uuid.uuid4().hex[:8]}"),
                        "type": "tool_call",
                    }
                )
        return out

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: Optional[list[str]] = None,
        run_manager: Optional[CallbackManagerForLLMRun] = None,
        **kwargs: Any,
    ) -> ChatResult:
        payload: dict[str, Any] = {
            "messages": [_serialize_message(m) for m in messages],
            "temperature": self.temperature,
        }
        if self.bound_tools:
            payload["tools"] = self.bound_tools
        if stop:
            payload["stop"] = stop

        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            resp = requests.post(
                self.endpoint_url,
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            raise RuntimeError(
                f"Flask VLM server error at {self.endpoint_url}: {exc}"
            ) from exc
        except ValueError as exc:
            raise RuntimeError(
                f"Invalid JSON returned by Flask VLM server at {self.endpoint_url}: {exc}"
            ) from exc

        ai_msg = self._parse_response_payload(data)
        return ChatResult(generations=[ChatGeneration(message=ai_msg)])


def build_chat_model(
    provider: str = "gemini",
    api_key: str = "",
    model: str = "gemini-3.5-flash-lite",
    flask_url: str = "http://127.0.0.1:5000/chat",
    flask_timeout: float = 120.0,
    flask_api_key: str = "",
    temperature: float = 0.3,
) -> BaseChatModel:
    """
    Factory returning the active LangChain BaseChatModel.

    Switch between Gemini API and the remote laptop Flask VLM server via
    LLM_PROVIDER=gemini | flask_vlm.
    """
    chosen = (provider or "gemini").strip().lower()
    if chosen == "flask_vlm":
        if not flask_url:
            raise ProviderConfigError(
                "FLASK_VLM_URL is missing. Set it in .env (e.g. http://192.168.x.x:5000/chat)."
            )
        log.info("Using FlaskVLMChatModel -> %s", flask_url)
        return FlaskVLMChatModel(
            endpoint_url=flask_url,
            timeout=flask_timeout,
            api_key=flask_api_key,
            temperature=temperature,
        )

    if not api_key or api_key.startswith("your_"):
        raise ProviderConfigError(
            "GEMINI_API_KEY is missing or still set to the placeholder value.\n"
            "Add your key to the .env file:\n"
            "  GEMINI_API_KEY=your_actual_key_here"
        )

    from langchain_google_genai import ChatGoogleGenerativeAI

    log.info("Using ChatGoogleGenerativeAI -> model=%s", model)
    return ChatGoogleGenerativeAI(
        model=model,
        google_api_key=api_key,
        temperature=temperature,
    )
