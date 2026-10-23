"""Thin Ollama chat client (stdlib urllib — no pip deps required)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


class OllamaError(RuntimeError):
    pass


class OllamaClient:
    def __init__(self, base_url: str, model: str, timeout: int = 180) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def ping(self) -> bool:
        try:
            req = urllib.request.Request(f"{self.base_url}/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status == 200
        except (urllib.error.URLError, TimeoutError, OSError):
            return False

    def list_models(self) -> list[str]:
        data = self._request("GET", "/api/tags")
        return [m.get("name", "") for m in data.get("models", []) if m.get("name")]

    def chat(self, system: str, user: str) -> str:
        payload = {
            "model": self.model,
            "stream": False,
            "format": "json",
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "options": {
                "temperature": 0.7,
            },
        }
        data = self._request("POST", "/api/chat", payload)
        message = data.get("message") or {}
        content = message.get("content", "").strip()
        if not content:
            raise OllamaError("Ollama returned an empty response")
        return content

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict:
        url = f"{self.base_url}{path}"
        body = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")
            raise OllamaError(f"Ollama HTTP {e.code}: {detail}") from e
        except urllib.error.URLError as e:
            raise OllamaError(
                f"Cannot reach Ollama at {self.base_url}. "
                "Start it with: ollama serve"
            ) from e
        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            raise OllamaError(f"Invalid JSON from Ollama: {raw[:200]}") from e
