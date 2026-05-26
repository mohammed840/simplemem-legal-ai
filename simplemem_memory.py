#!/usr/bin/env python3
"""
Conversation memory adapter for the Legal AI prototype.

Option B architecture:
- Legal RAG stays separate and source-grounded.
- SimpleMem is used for user/session/matter memory when available.
- A small JSONL memory fallback keeps the app usable without heavy local deps.
"""

from __future__ import annotations

import json
import os
import re
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


APP_DIR = Path(__file__).resolve().parent
REPO_ROOT = APP_DIR.parent
ENV_PATH = REPO_ROOT / ".env"
FALLBACK_MEMORY_PATH = APP_DIR / "legal_ai_memory_log.jsonl"
SIMPLEMEM_DB_PATH = APP_DIR / "simplemem_memory_data"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def load_env(path: Path = ENV_PATH) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def env_value(*names: str, default: str = "") -> str:
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return default


def tokenize(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]{3,}", value.lower())
        if token not in {"the", "and", "for", "that", "with", "this", "from", "are", "was", "what"}
    }


class LegalConversationMemory:
    def __init__(self) -> None:
        load_env()
        self.provider = "jsonl"
        self.status = "fallback_ready"
        self.error = ""
        self._mem: Any | None = None
        self._init_started = False
        self._init_lock = threading.Lock()

        if os.environ.get("LEGAL_AI_SIMPLEMEM_AUTOSTART", "0") == "1":
            self.start_simplemem_background()

    def start_simplemem_background(self) -> None:
        with self._init_lock:
            if self._init_started or self._mem is not None:
                return
            self._init_started = True
            self.status = "simplemem_initializing"
            thread = threading.Thread(target=self._initialize_simplemem, daemon=True)
            thread.start()

    def _initialize_simplemem(self) -> None:
        try:
            from simplemem import create

            mem = create(
                mode="text",
                api_key=env_value("OPENROUTER_API_KEY", "OPENAI_API_KEY"),
                base_url=env_value("OPENROUTER_BASE_URL", "OPENAI_BASE_URL", default="https://openrouter.ai/api/v1"),
                model=env_value("CHAT_MODEL", "LLM_MODEL", default="anthropic/claude-sonnet-4.5"),
                db_path=str(SIMPLEMEM_DB_PATH),
                table_name="legal_ai_conversation_memory",
                clear_db=False,
                use_streaming=False,
            )
            self._mem = mem
            self.provider = "simplemem"
            self.status = "active"
        except Exception as exc:
            self.provider = "jsonl"
            self.status = "fallback"
            self.error = str(exc)

    def status_payload(self) -> dict[str, str]:
        return {
            "provider": self.provider,
            "status": self.status,
            "error": self.error,
        }

    def recall(self, case_name: str, question: str, limit: int = 4) -> str:
        self.start_simplemem_background()
        if self._mem is not None:
            try:
                response = self._mem.ask(
                    "Recall concise prior context relevant to this legal chat. "
                    f"Current case: {case_name}. Current question: {question}"
                )
                if response:
                    return str(response)
            except Exception as exc:
                self.error = str(exc)

        return self._recall_from_jsonl(case_name, question, limit)

    def remember(
        self,
        case_name: str,
        question: str,
        answer: str,
        law_sources: list[str],
    ) -> None:
        self.start_simplemem_background()
        timestamp = datetime.now(timezone.utc).isoformat()
        summary = (
            f"Case: {case_name}\n"
            f"User question: {question}\n"
            f"AI answer summary: {answer[:1200]}\n"
            f"Law sources: {', '.join(law_sources[:8])}"
        )

        if self._mem is not None:
            try:
                self._mem.add_dialogue("user", f"[{case_name}] {question}", timestamp)
                self._mem.add_dialogue("assistant", summary, timestamp)
                self._mem.finalize()
            except Exception as exc:
                self.error = str(exc)

        FALLBACK_MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "timestamp": timestamp,
            "case_name": case_name,
            "question": question,
            "answer": answer,
            "law_sources": law_sources,
        }
        with FALLBACK_MEMORY_PATH.open("a", encoding="utf-8") as file:
            file.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def _recall_from_jsonl(self, case_name: str, question: str, limit: int) -> str:
        if not FALLBACK_MEMORY_PATH.exists():
            return "No prior memory found for this session."

        query_tokens = tokenize(f"{case_name} {question}")
        rows = []
        for line in FALLBACK_MEMORY_PATH.read_text().splitlines():
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            haystack = f"{item.get('case_name', '')} {item.get('question', '')} {item.get('answer', '')}"
            score = len(query_tokens & tokenize(haystack))
            if score:
                rows.append((score, item))

        rows.sort(key=lambda pair: pair[0], reverse=True)
        if not rows:
            return "No prior memory found for this case/question."

        memories = []
        for _, item in rows[:limit]:
            memories.append(
                f"- Prior case: {item.get('case_name')}\n"
                f"  Prior question: {item.get('question')}\n"
                f"  Prior answer excerpt: {str(item.get('answer', ''))[:500]}"
            )
        return "\n".join(memories)
