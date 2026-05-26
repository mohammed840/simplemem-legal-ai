#!/usr/bin/env python3
"""General-purpose Ask AI engine for the Legal AI app."""

from __future__ import annotations

import hashlib
import html
import json
import math
import os
import re
import threading
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from simplemem_memory import LegalConversationMemory


APP_DIR = Path(__file__).resolve().parent
REPO_ROOT = APP_DIR.parent
ENV_PATH = REPO_ROOT / ".env"
ASK_AI_DOCS_PATH = APP_DIR / "ask_ai_documents.json"
ASK_AI_UPLOAD_DIR = APP_DIR / "ask_ai_uploads"
ASK_AI_EMBEDDING_CACHE_PATH = APP_DIR / "ask_ai_embedding_cache.json"
ASK_AI_MEMORY_PATH = APP_DIR / "ask_ai_memory_log.jsonl"
ASK_AI_RETRIEVAL_CONFIG_PATH = APP_DIR / "ask_ai_retrieval_config.json"
ASK_AI_SIMPLEMEM_CONFIG_PATH = APP_DIR / "ask_ai_simplemem_config.json"
ASK_AI_SIMPLEMEM_DB_PATH = APP_DIR / "ask_ai_simplemem_data"
ASK_AI_SIMPLEMEM_CACHE_DIR = APP_DIR / "ask_ai_simplemem_evolvemem_cache"
ASK_AI_SIMPLEMEM_RESULTS_DIR = APP_DIR / "ask_ai_simplemem_evolvemem_results"
ASK_AI_FULL_EVOLVEMEM_CACHE_DIR = APP_DIR / "ask_ai_full_evolvemem_cache"
ASK_AI_FULL_EVOLVEMEM_RESULTS_DIR = APP_DIR / "ask_ai_full_evolvemem_results"
ASK_AI_FULL_EVOLVEMEM_SUMMARY_PATH = APP_DIR / "ask_ai_full_evolvemem_summary.json"
ASK_AI_AUTO_IMPROVE_STATE_PATH = APP_DIR / "ask_ai_auto_improve_state.json"
ASK_AI_FAILURE_LOG_PATH = APP_DIR / "ask_ai_evolvemem_failure_log.jsonl"
ASK_AI_EVOLUTION_HISTORY_PATH = APP_DIR / "ask_ai_evolvemem_history.jsonl"
ASK_AI_AUTO_IMPROVE_QUESTION_INTERVAL = 5
AI_LEGAL_CLAUDE_DIR = APP_DIR / "ai_legal_claude_skills"
AI_LEGAL_CLAUDE_SOURCE_URL = "https://github.com/zubair-trabzada/ai-legal-claude"


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


def clean_space(value: str) -> str:
    return " ".join(str(value or "").replace("\xa0", " ").split())


def tokenize(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]{3,}", str(value or "").lower())
        if token not in {"the", "and", "for", "that", "with", "this", "from", "are", "was"}
    }


LEGAL_EVAL_SET = [
    {
        "id": "us_contractor_misclassification",
        "category": "classification",
        "mode": "clause_risk",
        "question": "Under U.S. law, what mistakes create independent contractor misclassification risk?",
        "expected_points": [
            "behavioral control",
            "financial control",
            "relationship",
            "economic realities",
            "ABC test",
            "benefits",
            "tools",
            "permanence",
        ],
    },
    {
        "id": "us_noncompete_enforceability",
        "category": "restrictive_covenants",
        "mode": "general",
        "question": "Under U.S. law, when is a non-compete agreement enforceable?",
        "expected_points": [
            "state law",
            "legitimate business interest",
            "reasonable duration",
            "geographic scope",
            "restricted activity",
            "consideration",
            "California",
        ],
    },
    {
        "id": "contractor_missing_protections",
        "category": "missing_protections",
        "mode": "missing_protections",
        "question": "What protections are normally missing from startup contractor agreements?",
        "expected_points": [
            "IP ownership",
            "confidentiality",
            "payment terms",
            "termination",
            "limitation of liability",
            "indemnification",
            "dispute resolution",
            "data protection",
        ],
    },
    {
        "id": "privacy_policy_compliance",
        "category": "privacy",
        "mode": "compliance",
        "question": "What privacy compliance issues should a startup check before launching a website?",
        "expected_points": [
            "data collected",
            "privacy policy",
            "cookies",
            "consumer rights",
            "CCPA",
            "GDPR",
            "service providers",
            "security",
        ],
    },
    {
        "id": "contract_negotiation_priorities",
        "category": "negotiation",
        "mode": "negotiation",
        "question": "What contract terms should a startup negotiate first before signing a vendor agreement?",
        "expected_points": [
            "liability cap",
            "indemnification",
            "termination",
            "payment",
            "data protection",
            "IP",
            "auto-renewal",
            "governing law",
        ],
    },
]


LEGAL_EVAL_SOURCE_SNIPPETS = {
    "us_contractor_misclassification": (
        "U.S. contractor classification depends on substance over labels. Key checks include "
        "IRS common-law behavioral control, financial control, and relationship factors; the "
        "Department of Labor economic realities test; and stricter state tests such as the ABC "
        "test in California and other states. Red flags include company-controlled schedule, "
        "tools, training, employee-like benefits, permanence, full-time exclusivity, no profit/loss "
        "opportunity, and work inside the company's usual business."
    ),
    "us_noncompete_enforceability": (
        "U.S. non-compete enforceability is mainly state-law specific. Common checks include a "
        "legitimate business interest, reasonable duration, reasonable geographic scope, narrow "
        "restricted activities, adequate consideration, employee role and compensation, and public "
        "policy. Some states, including California, broadly restrict or ban employee non-competes."
    ),
    "contractor_missing_protections": (
        "Startup contractor agreements often need clear IP ownership and assignment, confidentiality, "
        "payment terms, milestone acceptance, termination rights, limitation of liability, indemnity, "
        "dispute resolution, data protection, tax/benefits classification language, and return of "
        "materials at termination."
    ),
    "privacy_policy_compliance": (
        "Website privacy compliance starts by mapping data collected, cookies and tracking, vendors "
        "and service providers, security controls, privacy policy disclosures, consumer rights, breach "
        "response, and cross-border transfers. CCPA/CPRA, GDPR, sector laws, and state privacy laws "
        "may apply depending on users, revenue, data volume, and geography."
    ),
    "contract_negotiation_priorities": (
        "Startup vendor agreement negotiation priorities commonly include liability cap, indemnity, "
        "termination rights, payment and renewal terms, auto-renewal notice, data protection, IP "
        "ownership and licenses, service levels, audit rights, confidentiality, governing law, and "
        "dispute resolution."
    ),
}


class AskAIEmbedder:
    """Embedder adapter for SimpleMem's full EvolutionEngine."""

    def __init__(self, engine: "AskAIEngine") -> None:
        self.engine = engine

    def encode(self, texts: Any, normalize_embeddings: bool = False, **_: Any):
        import numpy as np

        single = isinstance(texts, str)
        batch = [texts] if single else list(texts)
        vectors = self.engine.embed_texts([str(text) for text in batch])
        arr = np.array(vectors, dtype="float32")
        if normalize_embeddings and arr.size:
            norms = np.linalg.norm(arr, axis=1, keepdims=True)
            arr = arr / np.maximum(norms, 1e-12)
        return arr[0] if single else arr


LEGAL_WORKFLOW_BASE = (
    "Adapt to the user's input. If uploaded documents are provided, analyze those documents. "
    "If no uploaded document is provided, answer the user's legal query directly using model "
    "knowledge and clean Ask AI memory where relevant. Never tell the user an upload is required "
    "unless they specifically ask for document review but no document text exists. Be practical, "
    "jurisdiction-aware, and clear that this is legal information, not legal advice."
)


AI_LEGAL_CLAUDE_COMMAND_SKILLS = {
    "review": "skills/legal-review/SKILL.md",
    "risks": "skills/legal-risks/SKILL.md",
    "compare": "skills/legal-compare/SKILL.md",
    "plain": "skills/legal-plain/SKILL.md",
    "negotiate": "skills/legal-negotiate/SKILL.md",
    "missing": "skills/legal-missing/SKILL.md",
    "nda": "skills/legal-nda/SKILL.md",
    "terms": "skills/legal-terms/SKILL.md",
    "privacy": "skills/legal-privacy/SKILL.md",
    "agreement": "skills/legal-agreement/SKILL.md",
    "freelancer": "skills/legal-freelancer/SKILL.md",
    "compliance": "skills/legal-compliance/SKILL.md",
    "report-pdf": "skills/legal-report-pdf/SKILL.md",
}


AI_LEGAL_CLAUDE_COMMAND_MODES = {
    "review": "contract_review",
    "risks": "clause_risk",
    "compare": "clause_risk",
    "plain": "plain_english",
    "negotiate": "negotiation",
    "missing": "missing_protections",
    "nda": "contract_review",
    "terms": "compliance",
    "privacy": "compliance",
    "agreement": "contract_review",
    "freelancer": "clause_risk",
    "compliance": "compliance",
    "report-pdf": "document_summary",
}


AI_LEGAL_CLAUDE_MODE_SKILLS = {
    "general": "legal/SKILL.md",
    "contract_review": "skills/legal-review/SKILL.md",
    "clause_risk": "skills/legal-risks/SKILL.md",
    "plain_english": "skills/legal-plain/SKILL.md",
    "compliance": "skills/legal-compliance/SKILL.md",
    "negotiation": "skills/legal-negotiate/SKILL.md",
    "missing_protections": "skills/legal-missing/SKILL.md",
    "document_summary": "skills/legal-review/SKILL.md",
}


WORKFLOW_LABELS = {
    "general": "General Legal Question",
    "contract_review": "Contract Review",
    "clause_risk": "Clause Risk Analysis",
    "plain_english": "Plain English Explanation",
    "compliance": "Compliance Check",
    "negotiation": "Negotiation Suggestions",
    "missing_protections": "Missing Protections",
    "document_summary": "Document Summary",
}


AI_LEGAL_CLAUDE_REVIEW_AGENT_FILES = [
    "agents/legal-clauses.md",
    "agents/legal-risks.md",
    "agents/legal-compliance.md",
    "agents/legal-terms.md",
    "agents/legal-recommendations.md",
]


_AI_LEGAL_CLAUDE_CACHE: dict[str, str] = {}


def _read_ai_legal_claude_file(relative_path: str) -> str:
    path = AI_LEGAL_CLAUDE_DIR / relative_path
    if not path.exists():
        return ""
    cache_key = str(path)
    if cache_key not in _AI_LEGAL_CLAUDE_CACHE:
        _AI_LEGAL_CLAUDE_CACHE[cache_key] = path.read_text(encoding="utf-8")
    return _AI_LEGAL_CLAUDE_CACHE[cache_key]


def _ai_legal_claude_command_from_question(question: str) -> str:
    match = re.match(r"\s*/legal\s+([a-z-]+)", question.strip(), flags=re.I)
    return match.group(1).lower() if match else ""


def ai_legal_claude_skill_bundle(mode: str, question: str) -> str:
    command = _ai_legal_claude_command_from_question(question)
    relative_path = AI_LEGAL_CLAUDE_COMMAND_SKILLS.get(command) or AI_LEGAL_CLAUDE_MODE_SKILLS.get(mode)
    if not relative_path:
        return ""

    skill_text = _read_ai_legal_claude_file(relative_path)
    if not skill_text:
        return ""

    bundle_parts = [
        f"Source: {AI_LEGAL_CLAUDE_SOURCE_URL}",
        f"Loaded skill file: {relative_path}",
        skill_text,
    ]

    if relative_path == "skills/legal-review/SKILL.md":
        for agent_file in AI_LEGAL_CLAUDE_REVIEW_AGENT_FILES:
            agent_text = _read_ai_legal_claude_file(agent_file)
            if agent_text:
                bundle_parts.append(f"\n--- Supporting agent file: {agent_file} ---\n{agent_text}")

    return "\n\n".join(bundle_parts)


WORKFLOW_PROMPTS = {
    "general": (
        f"{LEGAL_WORKFLOW_BASE} Use an issue-first legal answer structure: identify the legal "
        "question, give the governing rule or test, apply it to the user's facts, then give risks "
        "and practical next steps. Use tables when comparison helps."
    ),
    "contract_review": (
        f"{LEGAL_WORKFLOW_BASE} Use the imported ai-legal-claude contract-review skill as the primary "
        "workflow: identify contract type, parties, governing law, key clauses, high/medium/low risks, "
        "missing protections, obligations/deadlines, negotiation priorities, and next steps. If this "
        "is only a general query, explain how those contract-review concepts apply generally."
    ),
    "clause_risk": (
        f"{LEGAL_WORKFLOW_BASE} Use a clause risk workflow: classify clause category, identify risk "
        "dimensions such as financial exposure, liability transfer, one-sided terms, unclear terms, "
        "broad indemnity, non-compete overreach, auto-renewal traps, and missing protections. Score "
        "risk on a 1-10 scale when enough facts exist and suggest safer language where useful."
    ),
    "plain_english": (
        f"{LEGAL_WORKFLOW_BASE} Translate legal concepts or document text into plain English. Keep "
        "legal meaning intact, define jargon, explain consequences, and separate 'what it says' from "
        "'what it means for you'."
    ),
    "compliance": (
        f"{LEGAL_WORKFLOW_BASE} Use a compliance workflow: identify applicable legal/regulatory "
        "frameworks, assumptions, likely obligations, red flags, missing controls, and action items. "
        "For contracts, consider privacy/data protection, employment classification, non-competes, "
        "consumer protection, industry-specific rules, notice duties, and enforceability concerns."
    ),
    "negotiation": (
        f"{LEGAL_WORKFLOW_BASE} Use a negotiation workflow: rank priorities, explain why each issue "
        "matters, provide proposed replacement language when possible, give fallback positions, and "
        "mark dealbreakers versus nice-to-have improvements."
    ),
    "missing_protections": (
        f"{LEGAL_WORKFLOW_BASE} Use a missing-protections workflow: identify provisions that should "
        "normally appear for this kind of legal issue or document, explain why each matters, assign "
        "risk level, and suggest concise language or next steps."
    ),
    "document_summary": (
        f"{LEGAL_WORKFLOW_BASE} Summarize the document or legal issue, extract parties, dates, "
        "obligations, deadlines, rights, restrictions, citations, unusual terms, and important risks. "
        "If no document exists, summarize the legal topic in the same structured style."
    ),
}


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if not left_norm or not right_norm:
        return 0.0
    return dot / (left_norm * right_norm)


def chunk_text(text: str, chunk_words: int = 420, overlap_words: int = 70) -> list[dict[str, Any]]:
    words = clean_space(text).split()
    if not words:
        return []
    chunks = []
    step = max(1, chunk_words - overlap_words)
    for start in range(0, len(words), step):
        chunk_words_slice = words[start : start + chunk_words]
        if not chunk_words_slice:
            continue
        chunks.append(
            {
                "chunk_id": f"chunk-{len(chunks) + 1:04d}",
                "word_start": start,
                "word_end": start + len(chunk_words_slice),
                "text": " ".join(chunk_words_slice),
            }
        )
        if start + chunk_words >= len(words):
            break
    return chunks


def extract_text_from_file(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        try:
            import fitz
        except ImportError as error:
            raise ValueError("PDF upload needs PyMuPDF installed") from error
        pages = []
        with fitz.open(path) as document:
            for page in document:
                pages.append(page.get_text("text") or "")
        text = "\n\n".join(pages)
    else:
        text = path.read_text(encoding="utf-8", errors="replace")
        if suffix in {".html", ".htm", ".xml"}:
            text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", text)
            text = re.sub(r"(?s)<[^>]+>", " ", text)
            text = html.unescape(text)
        if suffix == ".json":
            try:
                text = json.dumps(json.loads(text), indent=2, ensure_ascii=False)
            except json.JSONDecodeError:
                pass
    text = "\n".join(clean_space(line) for line in text.splitlines())
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not text:
        raise ValueError("Could not extract text from this file")
    return text


class AskAIEngine:
    def __init__(self, legislation: list[dict[str, Any]]) -> None:
        load_env()
        self.legislation = legislation
        self.api_key = env_value("OPENROUTER_API_KEY", "OPENAI_API_KEY")
        self.base_url = env_value(
            "OPENROUTER_BASE_URL",
            "OPENAI_BASE_URL",
            default="https://openrouter.ai/api/v1",
        )
        self.chat_model = env_value(
            "ASK_AI_MODEL",
            "CHAT_MODEL",
            "LLM_MODEL",
            default="anthropic/claude-sonnet-4.5",
        )
        self.embedding_model = env_value("EMBEDDING_MODEL", default="qwen/qwen3-embedding-0.6b")
        self.memory = LegalConversationMemory()
        self.documents = self._load_documents()
        self.embedding_cache = self._load_embedding_cache()
        self.auto_improve_state = self._load_auto_improve_state()
        self.auto_improve_lock = threading.Lock()
        self.simplemem = None
        self.simplemem_error = ""
        self.simplemem_lock = threading.Lock()

    def ask(self, question: str, mode: str = "auto") -> dict[str, Any]:
        if not self.api_key:
            return {
                "answer": "OpenRouter is not configured. Add an OpenRouter-compatible API key before using Ask AI.",
                "sources": [],
                "memory": self.memory.status_payload(),
                "model": self.chat_model,
                "embedding_model": self.embedding_model,
            }
        mode = self.detect_workflow_mode(question, has_documents=bool(self.documents))
        clean_memory = self.retrieve_clean_memory(question, top_k=self._memory_top_k())
        docs = self.retrieve_documents(question, top_k=self._doc_top_k()) if self._should_use_uploaded_documents(question, mode) else []
        laws: list[dict[str, Any]] = []
        auto_improve_before = self.auto_improve_status()
        sources = self.format_sources(clean_memory, docs, laws, question)
        answer = self.generate_answer(question, mode, clean_memory, docs, laws, auto_improve_before)
        answer = self.ensure_response_sections(answer, mode, clean_memory, docs, auto_improve_before)
        answer = self.verify_answer_if_enabled(question, answer, sources, auto_improve_before)
        answer = self.ensure_response_sections(answer, mode, clean_memory, docs, auto_improve_before)
        eval_result = self.score_answer_against_legal_eval(question, answer, mode, sources)
        self.write_failure_log(question, answer, mode, clean_memory, docs, laws, sources, eval_result)
        self.remember_clean_interaction(question, answer, mode, docs)
        auto_improve = self.record_auto_improve_event("question")
        return {
            "answer": answer,
            "sources": sources,
            "memory": self.memory.status_payload(),
            "model": self.chat_model,
            "embedding_model": self.embedding_model,
            "mode": mode,
            "workflow_label": WORKFLOW_LABELS.get(mode, mode),
            "retrieval": {
                "uploaded_documents": len(docs),
                "law_chunks": len(laws),
                "clean_memory": len(clean_memory),
            },
            "auto_improve": auto_improve,
            "eval": eval_result,
        }

    def detect_workflow_mode(self, question: str, has_documents: bool = False) -> str:
        command = _ai_legal_claude_command_from_question(question)
        if command in AI_LEGAL_CLAUDE_COMMAND_MODES:
            return AI_LEGAL_CLAUDE_COMMAND_MODES[command]

        lowered = f" {question.lower()} "

        if any(
            phrase in lowered
            for phrase in (
                " contract review",
                " review this",
                " review the",
                " review my",
                " before signing",
                " as if i am signing",
                " as if i'm signing",
                " signing it",
            )
        ):
            return "contract_review"

        if any(
            phrase in lowered
            for phrase in (
                " plain english",
                "plain-language",
                "plain language",
                "explain simply",
                "simple terms",
                "what does this mean",
                "translate this",
                "legalese",
            )
        ):
            return "plain_english"

        if any(
            phrase in lowered
            for phrase in (
                " negotiate",
                "counter-proposal",
                "counter proposal",
                "push back",
                "fallback position",
                "rewrite",
                "replacement language",
                "make it safer",
                "safer alternative",
            )
        ):
            return "negotiation"

        if any(
            phrase in lowered
            for phrase in (
                " missing protection",
                "missing clause",
                "what is missing",
                "protections are missing",
                "gap",
                "gaps",
                "should be included",
            )
        ):
            return "missing_protections"

        if any(
            phrase in lowered
            for phrase in (
                " compliance",
                "regulatory",
                "privacy",
                "data protection",
                "security",
                "hipaa",
                "gdpr",
                "ccpa",
                "cpra",
                "soc 2",
                "pci",
                "audit",
            )
        ):
            return "compliance"

        if any(
            phrase in lowered
            for phrase in (
                " summarize",
                "summary",
                "key terms",
                "extract",
                "obligations",
                "deadlines",
                "timeline",
            )
        ):
            return "document_summary"

        if any(
            phrase in lowered
            for phrase in (
                " risk",
                "risky",
                "red flag",
                "red flags",
                "liability",
                "misclassification",
                "non-compete",
                "indemnity",
                "indemnification",
                "liability cap",
                "highest-risk",
                "highest risk",
                "risk table",
            )
        ):
            return "clause_risk"

        if has_documents or any(
            phrase in lowered
            for phrase in (
                " review this",
                "review the",
                "contract",
                "agreement",
                "clause",
                "document",
                "uploaded",
                "file",
            )
        ):
            return "contract_review"

        return "general"

    def ingest_file(self, path: Path) -> dict[str, Any]:
        text = extract_text_from_file(path)
        doc_id = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
        chunks = chunk_text(text)
        metadata = self.extract_legal_metadata(path.name, text)
        record = {
            "id": doc_id,
            "filename": path.name,
            "path": str(path),
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
            "char_count": len(text),
            "chunk_count": len(chunks),
            "metadata": metadata,
            "chunks": chunks,
        }
        self.documents = [item for item in self.documents if item.get("id") != doc_id]
        self.documents.append(record)
        self._save_documents()
        self.memory.remember(
            case_name="Ask AI Upload",
            question=f"Uploaded document: {path.name}",
            answer=f"Stored {path.name} with {len(chunks)} text chunks for Ask AI retrieval.",
            law_sources=[],
        )
        record["auto_improve"] = self.record_auto_improve_event("upload")
        return record

    def retrieve_documents(self, question: str, top_k: int = 8) -> list[dict[str, Any]]:
        chunks = []
        for document in self.documents:
            for chunk in document.get("chunks", []):
                chunks.append(
                    {
                        "kind": "uploaded_document",
                        "title": document.get("filename", "Uploaded document"),
                        "identifier": document.get("path", ""),
                        "section_number": chunk.get("chunk_id", ""),
                        "section_heading": self._metadata_heading(document),
                        "text": chunk.get("text", ""),
                        "metadata": document.get("metadata", {}),
                    }
                )
        return self._rank_chunks(question, chunks, top_k)

    def _metadata_heading(self, document: dict[str, Any]) -> str:
        metadata = document.get("metadata") or {}
        labels = [
            metadata.get("document_type"),
            metadata.get("jurisdiction"),
            ", ".join((metadata.get("clause_types") or [])[:3]),
        ]
        heading = " / ".join(item for item in labels if item)
        return heading or "Uploaded document chunk"

    def retrieve_legislation(self, question: str, top_k: int = 6) -> list[dict[str, Any]]:
        chunks = []
        for record in self.legislation:
            for chunk in record.get("chunks", []):
                chunks.append(
                    {
                        "kind": "law",
                        "title": record.get("title", "Unknown legislation"),
                        "identifier": record.get("identifier", ""),
                        "section_number": chunk.get("section_number", ""),
                        "section_heading": chunk.get("section_heading", ""),
                        "text": clean_space(chunk.get("text", "")),
                    }
                )
        return self._rank_chunks(question, chunks, top_k)

    def extract_legal_metadata(self, filename: str, text: str) -> dict[str, Any]:
        lowered = text[:20000].lower()
        type_patterns = [
            ("non-disclosure agreement", "NDA"),
            ("confidentiality agreement", "NDA"),
            ("master services agreement", "MSA"),
            ("statement of work", "SOW"),
            ("employment agreement", "employment agreement"),
            ("independent contractor", "contractor agreement"),
            ("consulting agreement", "consulting agreement"),
            ("privacy policy", "privacy policy"),
            ("terms of service", "terms of service"),
            ("lease", "lease"),
        ]
        clause_patterns = {
            "payment": r"\b(payment|fees|invoice|compensation)\b",
            "termination": r"\b(termination|terminate|expiration)\b",
            "IP ownership": r"\b(intellectual property|work product|assignment|license)\b",
            "confidentiality": r"\b(confidential|non-disclosure|trade secret)\b",
            "indemnification": r"\b(indemnif|hold harmless|defend)\b",
            "liability cap": r"\b(limitation of liability|liability cap|consequential damages)\b",
            "non-compete": r"\b(non-compete|noncompetition|restrictive covenant)\b",
            "non-solicitation": r"\b(non-solicit|non solicitation)\b",
            "governing law": r"\b(governing law|jurisdiction|venue)\b",
            "data protection": r"\b(data protection|personal data|privacy|security)\b",
            "auto-renewal": r"\b(auto-renew|automatic renewal|renewal term)\b",
        }
        jurisdiction_patterns = [
            ("California", r"\b(california|state of california|cal\.)\b"),
            ("Delaware", r"\b(delaware|state of delaware)\b"),
            ("New York", r"\b(new york|state of new york|ny)\b"),
            ("Texas", r"\b(texas|state of texas)\b"),
            ("Florida", r"\b(florida|state of florida)\b"),
            ("United States", r"\b(united states|u\.s\.|usa|federal)\b"),
            ("United Kingdom", r"\b(united kingdom|england and wales|uk)\b"),
            ("European Union", r"\b(european union|eu|gdpr)\b"),
        ]
        document_type = next((label for pattern, label in type_patterns if pattern in lowered), "")
        clause_types = [label for label, pattern in clause_patterns.items() if re.search(pattern, lowered)]
        jurisdiction = next((label for label, pattern in jurisdiction_patterns if re.search(pattern, lowered)), "")
        parties = []
        party_match = re.search(r"(?i)\bbetween\s+(.{2,90}?)\s+and\s+(.{2,90}?)(?:\.|,|\n|$)", text[:4000])
        if party_match:
            parties = [clean_space(party_match.group(1)), clean_space(party_match.group(2))]
        dates = sorted(set(re.findall(r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4}-\d{2}-\d{2}|(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4})\b", text[:12000], flags=re.I)))[:8]
        return {
            "document_type": document_type or Path(filename).suffix.lower().lstrip(".") or "document",
            "jurisdiction": jurisdiction,
            "clause_types": clause_types[:12],
            "parties": parties[:4],
            "dates": dates,
            "memory_type": "uploaded_legal_document",
        }

    def _rank_chunks(self, question: str, chunks: list[dict[str, Any]], top_k: int) -> list[dict[str, Any]]:
        query_tokens = tokenize(question)
        lexical = []
        for chunk in chunks:
            text = f"{chunk.get('title', '')} {chunk.get('section_heading', '')} {chunk.get('text', '')}"
            overlap = len(query_tokens & tokenize(text))
            if overlap:
                item = dict(chunk)
                item["score"] = overlap / max(4, len(query_tokens))
                lexical.append(item)
        lexical.sort(key=lambda item: item["score"], reverse=True)
        lexical = lexical[:40]
        if not lexical:
            return []
        try:
            texts = [question] + [item["text"] for item in lexical]
            embeddings = self.embed_texts(texts)
            query_embedding = embeddings[0]
            ranked = []
            for item, embedding in zip(lexical, embeddings[1:]):
                item = dict(item)
                item["score"] = cosine_similarity(query_embedding, embedding)
                ranked.append(item)
            ranked.sort(key=lambda item: item["score"], reverse=True)
            return ranked[:top_k]
        except Exception:
            return lexical[:top_k]

    def generate_answer(
        self,
        question: str,
        mode: str,
        clean_memory: list[dict[str, Any]],
        docs: list[dict[str, Any]],
        laws: list[dict[str, Any]],
        auto_improve_status: dict[str, Any],
    ) -> str:
        memory_context = self._source_context(clean_memory, "Clean Ask AI memory")
        document_context = self._source_context(docs, "Uploaded documents")
        auto_improve_summary = self._auto_improve_prompt_summary(auto_improve_status)
        ai_legal_claude_skill = ai_legal_claude_skill_bundle(mode, question)
        has_uploaded_context = bool(docs)
        system = (
            "You are Ask AI inside a legal AI application. You can answer general legal, contract, "
            "compliance, drafting, and document-review questions. Use only the clean Ask AI memory and "
            "uploaded documents provided in this prompt. Do not use or reference the app's old UK case "
            "or legislation dataset. For general questions, answer from the model's own legal knowledge "
            "plus clean memory when relevant. If jurisdiction matters, explain that the answer depends "
            "on jurisdiction. Do not invent citations. When ai-legal-claude skill instructions are "
            "provided, treat them as the primary workflow shape and adapt them to this chat interface; "
            "do not claim you launched real parallel subagents or wrote files unless that actually "
            "happened in the app. Provide practical, structured output. Use "
            "Markdown headings and markdown tables when a comparison, checklist, risk matrix, or "
            "clause inventory would make the answer clearer. Include a Sources Used section only when "
            "uploaded document sources are provided. Before the answer, show a brief user-facing "
            "reasoning process. This must be a concise explanation of the legal/source checks, not "
            "hidden private chain-of-thought."
        )
        user = (
            f"Workflow mode: {mode}\n"
            f"Workflow instructions: {WORKFLOW_PROMPTS[mode]}\n\n"
            "Imported ai-legal-claude skill instructions:\n"
            f"{ai_legal_claude_skill or 'No ai-legal-claude skill file was found for this mode.'}\n\n"
            f"Uploaded document context available: {'yes' if has_uploaded_context else 'no'}\n"
            "If uploaded document context is 'no', still answer the user's query directly using the "
            "selected workflow as the structure. Do not say the user must upload a document unless "
            "the question cannot be answered without seeing a specific document.\n\n"
            f"{memory_context}\n\n"
            f"{document_context}\n\n"
            f"AutoResearch / auto-improve status:\n{auto_improve_summary}\n\n"
            "Return the response with these exact Markdown headings:\n"
            "### Reasoning Process\n"
            "Briefly explain the jurisdiction, source check, and legal framework you are using.\n\n"
            "### AutoResearch Reasoning\n"
            "Briefly explain whether clean memory/upload retrieval was used, whether native SimpleMem "
            "optimization config is active, and why that matters for this answer.\n\n"
            "### Answer\n"
            "Give the answer. Use markdown tables where helpful.\n\n"
            f"User question:\n{question}"
        )
        response = self._post_json(
            "/chat/completions",
            {
                "model": self.chat_model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.2,
                "max_tokens": 2200,
            },
        )
        return response["choices"][0]["message"]["content"]

    def ensure_response_sections(
        self,
        answer: str,
        mode: str,
        clean_memory: list[dict[str, Any]],
        docs: list[dict[str, Any]],
        auto_improve_status: dict[str, Any],
    ) -> str:
        if self._has_response_section(answer, "Reasoning Process") and self._has_response_section(
            answer,
            "AutoResearch Reasoning",
        ) and self._has_response_section(answer, "Answer"):
            return answer

        workflow = WORKFLOW_LABELS.get(mode, mode)
        memory_count = len(clean_memory)
        doc_count = len(docs)
        active_config = auto_improve_status.get("active_config") or {}
        simplemem_status = (auto_improve_status.get("simplemem") or {}).get("status", "unknown")
        config_note = (
            f"Auto-improve config `{active_config.get('method')}` is active."
            if active_config.get("method")
            else "No optimized retrieval config was active for this turn."
        )
        document_note = (
            f"{doc_count} uploaded document chunk(s) were retrieved and used as the source layer."
            if doc_count
            else "No uploaded document chunks were retrieved for this turn."
        )
        memory_note = (
            f"{memory_count} clean SimpleMem memory entr{'y was' if memory_count == 1 else 'ies were'} retrieved."
            if memory_count
            else "No clean SimpleMem memory entries were retrieved."
        )

        return (
            "### Reasoning Process\n"
            f"I detected the best workflow as **{workflow}** from the user's question and available "
            "document context. I am applying the matching legal workflow skill, checking the retrieved "
            "source material, and then structuring the answer around the legal/business risks raised "
            "by the question.\n\n"
            "### AutoResearch Reasoning\n"
            f"{memory_note} {document_note} Native SimpleMem status is `{simplemem_status}`. "
            f"{config_note} This determines what context is passed into the legal answer before the "
            "final response is generated.\n\n"
            "### Answer\n"
            f"{answer.strip()}"
        )

    def _has_response_section(self, answer: str, title: str) -> bool:
        return bool(re.search(rf"^###?\s+{re.escape(title)}\s*$", answer, flags=re.M))

    def verify_answer_if_enabled(
        self,
        question: str,
        answer: str,
        sources: list[dict[str, Any]],
        auto_improve_status: dict[str, Any],
    ) -> str:
        config = auto_improve_status.get("active_config") or {}
        enabled = bool(config.get("enable_answer_verification")) or env_value(
            "ASK_AI_ANSWER_VERIFICATION",
            default="false",
        ).strip().lower() in {"1", "true", "yes", "on"}
        if not enabled:
            return answer
        context = "\n\n".join(
            f"Source {index}: {source.get('title')} / {source.get('section_heading')}\n"
            f"Quote: {source.get('quote')}"
            for index, source in enumerate(sources[:8], start=1)
        )
        if not context:
            context = "No retrieved sources; verify only legal structure, jurisdiction caveats, and unsupported citation risk."
        try:
            response = self._post_json(
                "/chat/completions",
                {
                    "model": self.chat_model,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "You are a legal answer verifier. Keep the user's answer if it is sound. "
                                "Only revise unsupported source claims, wrong jurisdiction assumptions, missing "
                                "legal caveats, or invented citations. Preserve the same Markdown sections."
                            ),
                        },
                        {
                            "role": "user",
                            "content": (
                                f"Question:\n{question}\n\n"
                                f"Retrieved context:\n{context}\n\n"
                                f"Candidate answer:\n{answer}\n\n"
                                "Return the verified final answer only."
                            ),
                        },
                    ],
                    "temperature": 0.0,
                    "max_tokens": 1800,
                },
            )
            verified = response["choices"][0]["message"]["content"].strip()
            return verified or answer
        except Exception as error:
            self.simplemem_error = str(error)
            return answer

    def score_answer_against_legal_eval(
        self,
        question: str,
        answer: str,
        mode: str,
        sources: list[dict[str, Any]],
    ) -> dict[str, Any]:
        profile = self.match_legal_eval_profile(question, mode)
        if not profile:
            return {
                "matched": False,
                "score": None,
                "eval_id": "",
                "category": "ad_hoc",
                "missing_points": [],
                "covered_points": [],
            }
        answer_tokens = tokenize(answer)
        covered = []
        missing = []
        for point in profile["expected_points"]:
            point_tokens = tokenize(point)
            if point_tokens and (point_tokens <= answer_tokens or point.lower() in answer.lower()):
                covered.append(point)
            else:
                missing.append(point)
        score = len(covered) / max(1, len(profile["expected_points"]))
        if sources:
            score = min(1.0, score + 0.05)
        return {
            "matched": True,
            "score": round(score, 4),
            "eval_id": profile["id"],
            "category": profile["category"],
            "expected_points": profile["expected_points"],
            "covered_points": covered,
            "missing_points": missing,
        }

    def match_legal_eval_profile(self, question: str, mode: str) -> dict[str, Any] | None:
        query_tokens = tokenize(question)
        best = None
        best_score = 0.0
        for profile in LEGAL_EVAL_SET:
            profile_tokens = tokenize(profile["question"])
            overlap = len(query_tokens & profile_tokens) / max(1, len(query_tokens | profile_tokens))
            if profile.get("mode") == mode:
                overlap += 0.08
            if overlap > best_score:
                best = profile
                best_score = overlap
        return best if best and best_score >= 0.16 else None

    def write_failure_log(
        self,
        question: str,
        answer: str,
        mode: str,
        clean_memory: list[dict[str, Any]],
        docs: list[dict[str, Any]],
        laws: list[dict[str, Any]],
        sources: list[dict[str, Any]],
        eval_result: dict[str, Any],
    ) -> None:
        score = eval_result.get("score")
        failure_reason = self.classify_failure(eval_result, clean_memory, docs, sources)
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "question": question,
            "mode": mode,
            "prediction": clean_space(answer[:2500]),
            "score": score,
            "eval_id": eval_result.get("eval_id", ""),
            "category": eval_result.get("category", "ad_hoc"),
            "expected_points": eval_result.get("expected_points", []),
            "covered_points": eval_result.get("covered_points", []),
            "missing_points": eval_result.get("missing_points", []),
            "retrieved_sources": [
                {
                    "title": source.get("title", ""),
                    "kind": source.get("kind", ""),
                    "identifier": source.get("identifier", ""),
                    "section_heading": source.get("section_heading", ""),
                    "score": source.get("score", 0),
                    "quote": source.get("quote", ""),
                }
                for source in sources[:10]
            ],
            "retrieval_counts": {
                "clean_memory": len(clean_memory),
                "uploaded_documents": len(docs),
                "law_chunks": len(laws),
            },
            "failure_reason": failure_reason,
        }
        with ASK_AI_FAILURE_LOG_PATH.open("a", encoding="utf-8") as file:
            file.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def classify_failure(
        self,
        eval_result: dict[str, Any],
        clean_memory: list[dict[str, Any]],
        docs: list[dict[str, Any]],
        sources: list[dict[str, Any]],
    ) -> str:
        score = eval_result.get("score")
        if score is None:
            return "ad_hoc_unscored"
        if score >= 0.8:
            return "pass"
        if not clean_memory and not docs:
            return "insufficient_memory_or_upload_context"
        if eval_result.get("missing_points"):
            return "answer_missing_expected_legal_points"
        if not sources:
            return "retrieval_returned_no_sources"
        return "low_score_unknown_root_cause"

    def retrieve_clean_memory(self, question: str, top_k: int = 4) -> list[dict[str, Any]]:
        native = self.retrieve_simplemem_memory(question, top_k=top_k)
        if native:
            return native
        if not ASK_AI_MEMORY_PATH.exists():
            return []
        query_tokens = tokenize(question)
        matches = []
        for line_number, line in enumerate(ASK_AI_MEMORY_PATH.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            text = (
                f"Workflow: {item.get('mode', 'general')}. "
                f"Prior question: {item.get('question', '')}. "
                f"Prior answer: {item.get('answer', '')}"
            )
            overlap = len(query_tokens & tokenize(text))
            if not overlap:
                continue
            matches.append(
                {
                    "kind": "clean_memory",
                    "title": "Ask AI clean memory",
                    "identifier": f"ask-ai-memory:{line_number}",
                    "section_number": item.get("timestamp", ""),
                    "section_heading": item.get("mode", "general"),
                    "text": clean_space(text[:1800]),
                    "score": overlap / max(4, len(query_tokens)),
                }
            )
        matches.sort(key=lambda item: item["score"], reverse=True)
        return matches[:top_k]

    def retrieve_simplemem_memory(self, question: str, top_k: int = 4) -> list[dict[str, Any]]:
        mem = self.get_simplemem()
        if mem is None:
            return []
        try:
            vector_store = getattr(mem, "vector_store", None)
            if vector_store is None:
                return []
            self.apply_simplemem_config(mem)
            top_k = max(1, min(6, top_k))
            semantic_entries = vector_store.semantic_search(question, top_k=top_k)
            keyword_entries = vector_store.keyword_search(list(tokenize(question))[:8], top_k=top_k)
            entries = self._dedupe_simplemem_entries([*semantic_entries, *keyword_entries])[:top_k]
            contexts = []
            for index, entry in enumerate(entries, start=1):
                text = getattr(entry, "lossless_restatement", "") or ""
                if not text:
                    continue
                contexts.append(
                    {
                        "kind": "simplemem_memory",
                        "title": "SimpleMem Ask AI memory",
                        "identifier": getattr(entry, "entry_id", f"simplemem-memory-{index}"),
                        "section_number": getattr(entry, "timestamp", "") or "",
                        "section_heading": getattr(entry, "topic", None) or "native SimpleMem retrieval",
                        "text": clean_space(text),
                        "score": 1.0,
                    }
                )
            return contexts
        except Exception as error:
            self.simplemem_error = str(error)
            return []

    def _dedupe_simplemem_entries(self, entries: list[Any]) -> list[Any]:
        seen = set()
        deduped = []
        for entry in entries:
            key = getattr(entry, "entry_id", None) or getattr(entry, "lossless_restatement", "")
            if key in seen:
                continue
            seen.add(key)
            deduped.append(entry)
        return deduped

    def remember_clean_interaction(
        self,
        question: str,
        answer: str,
        mode: str,
        docs: list[dict[str, Any]],
    ) -> None:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "mode": mode,
            "question": question,
            "answer": answer[:2400],
            "uploaded_sources": [source.get("title", "") for source in docs[:8]],
        }
        with ASK_AI_MEMORY_PATH.open("a", encoding="utf-8") as file:
            file.write(json.dumps(payload, ensure_ascii=False) + "\n")
        thread = threading.Thread(
            target=self._remember_simplemem_interaction,
            args=(payload,),
            name="ask-ai-simplemem-save",
            daemon=True,
        )
        thread.start()

    def _remember_simplemem_interaction(self, payload: dict[str, Any]) -> None:
        mem = self.get_simplemem()
        if mem is not None:
            try:
                timestamp = payload["timestamp"]
                mode = payload.get("mode", "general")
                mem.add_dialogue("user", f"[Ask AI / {mode}] {payload.get('question', '')}", timestamp)
                mem.add_dialogue("assistant", f"[Ask AI / {mode}] {payload.get('answer', '')[:2200]}", timestamp)
                mem.finalize()
            except Exception as error:
                self.simplemem_error = str(error)

    def _should_use_uploaded_documents(self, question: str, mode: str) -> bool:
        if not self.documents:
            return False
        if mode in {
            "contract_review",
            "clause_risk",
            "plain_english",
            "compliance",
            "negotiation",
            "missing_protections",
            "document_summary",
        }:
            return True
        lowered = question.lower()
        document_terms = {
            "uploaded",
            "upload",
            "document",
            "file",
            "contract",
            "clause",
            "agreement",
            "pdf",
            "attachment",
            "summarize this",
            "review this",
        }
        return any(term in lowered for term in document_terms)

    def run_autoresearch(self) -> dict[str, Any]:
        return self.run_clean_auto_improve()

    def run_clean_auto_improve(self) -> dict[str, Any]:
        full_engine = self.run_full_simplemem_evolvemem()
        if full_engine.get("ok") and full_engine.get("evaluated_qa_pairs", 0):
            return full_engine

        guarded = self.run_guarded_legal_evolvemem()
        if guarded.get("ok") and guarded.get("evaluated_logs", 0):
            return guarded

        mem = self.get_simplemem()
        dev_questions = self.make_simplemem_dev_questions()
        if mem is not None and len(dev_questions) >= 2:
            try:
                import simplemem

                max_rounds = int(env_value("ASK_AI_SIMPLEMEM_OPTIMIZE_ROUNDS", default="1") or "1")
                config = simplemem.optimize(
                    mem,
                    dev_questions,
                    max_rounds=max(1, max_rounds),
                    benchmark_name="ask_ai_clean_memory",
                    cache_dir=str(ASK_AI_SIMPLEMEM_CACHE_DIR),
                    results_dir=str(ASK_AI_SIMPLEMEM_RESULTS_DIR),
                )
                config.save(str(ASK_AI_SIMPLEMEM_CONFIG_PATH))
                self.apply_simplemem_config(mem)
                mapped = self.write_ask_ai_retrieval_config_from_simplemem(config, len(dev_questions))
                return {
                    "ok": True,
                    "stdout": "Ran native simplemem.optimize() over clean Ask AI dev questions.",
                    "stderr": "",
                    "config": mapped,
                    "simplemem_config": getattr(config, "__dict__", {}),
                }
            except Exception as error:
                self.simplemem_error = str(error)

        memory_count = self._clean_memory_count()
        document_count = len(self.documents)
        total_chunks = sum(int(document.get("chunk_count", 0) or 0) for document in self.documents)
        doc_top_k = 0
        if total_chunks:
            doc_top_k = min(12, max(6, int(math.sqrt(total_chunks)) + 4))
        memory_top_k = min(6, max(2, int(math.sqrt(memory_count)) + 1)) if memory_count else 0
        config = {
            "method": "ask_ai_clean_memory_uploaded_docs_v1",
            "doc_top_k": doc_top_k,
            "memory_top_k": memory_top_k,
            "document_count": document_count,
            "uploaded_chunk_count": total_chunks,
            "clean_memory_count": memory_count,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        ASK_AI_RETRIEVAL_CONFIG_PATH.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n")
        return {
            "ok": True,
            "stdout": (
                "Optimized Ask AI retrieval over clean memory and uploaded documents only. "
                f"memory_top_k={memory_top_k}, doc_top_k={doc_top_k}"
            ),
            "stderr": "",
            "config": config,
        }

    def run_full_simplemem_evolvemem(self) -> dict[str, Any]:
        if not self._full_evolvemem_enabled():
            return {
                "ok": True,
                "stdout": "Full SimpleMem EvolutionEngine disabled; using lighter fallback.",
                "stderr": "",
                "config": self.current_ask_ai_config(),
                "evaluated_qa_pairs": 0,
            }
        if not self.api_key:
            return {
                "ok": False,
                "stdout": "",
                "stderr": "Full SimpleMem EvolutionEngine needs an OpenRouter/OpenAI key.",
                "config": self.current_ask_ai_config(),
                "evaluated_qa_pairs": 0,
            }
        try:
            from simplemem.evolver.evolution import (
                EvolutionConfig,
                EvolutionEngine,
                weak_initial_config,
            )
            from simplemem.evolver.extractor import ExtractionConfig

            max_rounds = int(env_value("ASK_AI_FULL_EVOLVEMEM_ROUNDS", default="2") or "2")
            max_qa = int(env_value("ASK_AI_FULL_EVOLVEMEM_MAX_QA", default="2") or "2")
            smoke_preextracted = env_value(
                "ASK_AI_FULL_EVOLVEMEM_PREEXTRACTED",
                default="true",
            ).strip().lower() not in {"0", "false", "no", "off"}
            adapter, sessions, qa_pairs, sample_count = self.build_ask_ai_evolvemem_benchmark(max_qa)
            if not qa_pairs:
                return {
                    "ok": True,
                    "stdout": "Ask AI benchmark returned no QA pairs; using lighter fallback.",
                    "stderr": "",
                    "config": self.current_ask_ai_config(),
                    "evaluated_qa_pairs": 0,
                }

            config = EvolutionConfig(
                max_rounds=max(1, max_rounds),
                initial_retrieval_config=weak_initial_config(),
                extraction_config=ExtractionConfig(
                    window_size=int(env_value("ASK_AI_FULL_EVOLVEMEM_WINDOW", default="12") or "12"),
                    overlap=1,
                    max_retries=int(env_value("ASK_AI_FULL_EVOLVEMEM_RETRIES", default="2") or "2"),
                    chunk_size_on_failure=6,
                ),
                cache_dir=str(ASK_AI_FULL_EVOLVEMEM_CACHE_DIR),
                results_dir=str(ASK_AI_FULL_EVOLVEMEM_RESULTS_DIR),
            )
            engine = EvolutionEngine(
                llm_call=self.make_evolvemem_llm_call(),
                embedder=AskAIEmbedder(self),
                config=config,
                adapter=adapter,
                llm_call_factory=self.make_evolvemem_llm_factory(),
            )
            initial_memories = (
                self.preextract_memories_from_sessions(sessions)
                if smoke_preextracted
                else None
            )
            result = engine.evolve(
                sessions=sessions,
                qa_pairs=qa_pairs,
                initial_memories=initial_memories,
            )
            mapped = self.write_ask_ai_retrieval_config_from_full_evolvemem(
                result.final_config,
                result.best_round,
                result.best_f1,
                sample_count,
                len(sessions),
                len(qa_pairs),
                smoke_preextracted,
            )
            summary = {
                "benchmark": "ask_ai_legal",
                "samples": sample_count,
                "sessions": len(sessions),
                "qa_pairs": len(qa_pairs),
                "best_round": result.best_round,
                "best_score": result.best_f1,
                "final_config": result.final_config,
                "trajectory": [
                    {
                        "round": round_result.round_id,
                        "legal_score": round_result.f1,
                        "zero_count": round_result.zero_f1_count,
                        "metrics": round_result.all_metrics,
                        "subcategory_scores": round_result.subcategory_scores,
                        "improvements": round_result.improvements_applied,
                    }
                    for round_result in result.rounds
                ],
                "ask_ai_config": mapped,
            }
            ASK_AI_FULL_EVOLVEMEM_SUMMARY_PATH.write_text(
                json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            return {
                "ok": True,
                "stdout": (
                    "Ran full SimpleMem EvolutionEngine with Ask AI legal benchmark; "
                    f"best_score={result.best_f1:.4f}, best_round={result.best_round}."
                ),
                "stderr": "",
                "config": mapped,
                "score": result.best_f1,
                "evaluated_qa_pairs": len(qa_pairs),
                "results_dir": str(ASK_AI_FULL_EVOLVEMEM_RESULTS_DIR),
                "summary_path": str(ASK_AI_FULL_EVOLVEMEM_SUMMARY_PATH),
            }
        except Exception as error:
            self.simplemem_error = str(error)
            return {
                "ok": False,
                "stdout": "",
                "stderr": f"Full SimpleMem EvolutionEngine failed: {error}",
                "config": self.current_ask_ai_config(),
                "evaluated_qa_pairs": 0,
            }

    def write_ask_ai_retrieval_config_from_full_evolvemem(
        self,
        config: dict[str, Any],
        best_round: int,
        best_score: float,
        sample_count: int,
        session_count: int,
        qa_count: int,
        smoke_preextracted: bool,
    ) -> dict[str, Any]:
        payload = {
            "method": "full_simplemem_evolution_engine_v1",
            "doc_top_k": max(0, min(12, int(config.get("max_context", 8) or 8))),
            "memory_top_k": max(
                1,
                min(
                    6,
                    max(
                        int(config.get("semantic_top_k", 0) or 0),
                        int(config.get("keyword_top_k", 0) or 0),
                        int(config.get("structured_top_k", 0) or 0),
                        4,
                    ),
                ),
            ),
            "fusion_mode": config.get("fusion_mode", "rrf"),
            "enable_answer_verification": bool(config.get("enable_answer_verification", False)),
            "enable_query_decomposition": bool(config.get("enable_query_decomposition", False)),
            "enable_entity_swap": bool(config.get("enable_entity_swap", False)),
            "enable_structured_metadata": int(config.get("structured_top_k", 0) or 0) > 0,
            "full_evolvemem": {
                "best_round": best_round,
                "best_score": best_score,
                "samples": sample_count,
                "sessions": session_count,
                "qa_pairs": qa_count,
                "preextracted_sessions": smoke_preextracted,
                "final_config": config,
                "results_dir": str(ASK_AI_FULL_EVOLVEMEM_RESULTS_DIR),
            },
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        ASK_AI_RETRIEVAL_CONFIG_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
        return payload

    def make_evolvemem_llm_call(self):
        def llm_call(messages, max_tokens: int = 4096, temperature: float = 0.1) -> str:
            try:
                response = self._post_json(
                    "/chat/completions",
                    {
                        "model": self.chat_model,
                        "messages": messages,
                        "temperature": temperature,
                        "max_tokens": max_tokens,
                    },
                )
                return response["choices"][0]["message"]["content"] or ""
            except Exception as error:
                self.simplemem_error = str(error)
                return ""

        return llm_call

    def make_evolvemem_llm_factory(self):
        def factory(model: str):
            def llm_call(messages, max_tokens: int = 4096, temperature: float = 0.1) -> str:
                try:
                    response = self._post_json(
                        "/chat/completions",
                        {
                            "model": model,
                            "messages": messages,
                            "temperature": temperature,
                            "max_tokens": max_tokens,
                        },
                    )
                    return response["choices"][0]["message"]["content"] or ""
                except Exception as error:
                    self.simplemem_error = str(error)
                    return ""

            return llm_call

        return factory

    def build_ask_ai_evolvemem_benchmark(self, max_qa: int):
        from simplemem.evolver.benchmarks.base import BenchmarkAdapter, QuestionMeta

        class AskAIBenchmarkAdapter(BenchmarkAdapter):
            name = "ask_ai_legal"
            primary_metric = "legal_score"
            subcategory_keys = ("category",)

            def load(self, path: str, **kwargs):
                return []

            def score(self, prediction: str, reference: str, qa: dict) -> float:
                return float(self.score_all(prediction, reference, qa)[self.primary_metric])

            def score_all(self, prediction: str, reference: str, qa: dict) -> dict:
                expected_points = ((qa.get("meta") or {}).get("extras") or {}).get("expected_points", [])
                pred_tokens = tokenize(prediction)
                covered = 0
                for point in expected_points:
                    point_tokens = tokenize(point)
                    if point_tokens and (point_tokens <= pred_tokens or str(point).lower() in prediction.lower()):
                        covered += 1
                point_coverage = covered / max(1, len(expected_points))
                f1 = self._token_f1(prediction, reference)
                return {
                    "legal_score": (0.7 * point_coverage) + (0.3 * f1),
                    "point_coverage": point_coverage,
                    "f1": f1,
                }

            def build_answer_prompt(self, question: str, context: str, qa: dict) -> tuple[str, str]:
                meta = qa.get("meta") or {}
                extras = meta.get("extras") if isinstance(meta, dict) else {}
                expected_points = extras.get("expected_points", []) if isinstance(extras, dict) else []
                system = (
                    "You are an Ask AI legal benchmark assistant. Answer only from the provided "
                    "legal reference context. Return JSON only."
                )
                user = (
                    f"Question: {question}\n\n"
                    f"Expected legal points to cover:\n"
                    + "\n".join(f"- {point}" for point in expected_points)
                    + f"\n\nContext:\n{context}\n\n"
                    "Return JSON: {\"reasoning\":\"brief source-grounded reasoning\","
                    "\"answer\":\"concise legal answer\"}"
                )
                return system, user

            @staticmethod
            def _token_f1(prediction: str, reference: str) -> float:
                pred = list(tokenize(prediction))
                ref = list(tokenize(reference))
                if not pred or not ref:
                    return 0.0
                ref_remaining = list(ref)
                overlap = 0
                for token in pred:
                    if token in ref_remaining:
                        overlap += 1
                        ref_remaining.remove(token)
                if not overlap:
                    return 0.0
                precision = overlap / len(pred)
                recall = overlap / len(ref)
                return (2 * precision * recall) / (precision + recall)

        adapter = AskAIBenchmarkAdapter()
        selected = LEGAL_EVAL_SET[: max(1, max_qa)]
        sessions = []
        qa_pairs = []
        category_map = {
            "classification": 101,
            "restrictive_covenants": 102,
            "missing_protections": 103,
            "privacy": 104,
            "negotiation": 105,
        }
        for item in selected:
            source = LEGAL_EVAL_SOURCE_SNIPPETS.get(item["id"], " ".join(item["expected_points"]))
            sessions.append(
                (
                    f"{item['id']}_reference",
                    "",
                    [{"speaker": "legal_reference", "text": source}],
                )
            )
            qa_pairs.append(
                {
                    "question": item["question"],
                    "answer": " ".join(item["expected_points"]),
                    "category": category_map.get(item["category"], 199),
                    "meta": QuestionMeta(
                        qid=item["id"],
                        qtype=item["category"],
                        extras={
                            "expected_points": item["expected_points"],
                            "mode": item["mode"],
                        },
                    ).__dict__,
                }
            )
        return adapter, sessions, qa_pairs, len(selected)

    def preextract_memories_from_sessions(self, sessions: list[tuple[str, str, list[dict]]]) -> list[dict[str, Any]]:
        memories = []
        for session_id, date_str, turns in sessions:
            for index, turn in enumerate(turns):
                text = clean_space(turn.get("text", ""))
                if not text:
                    continue
                memories.append(
                    {
                        "content": text,
                        "keywords": sorted(tokenize(text))[:40],
                        "timestamp": date_str or None,
                        "location": None,
                        "persons": [],
                        "entities": [],
                        "topic": turn.get("speaker", "legal_reference"),
                        "session_id": session_id,
                        "source": f"{session_id}:{index}",
                    }
                )
        return memories

    def _full_evolvemem_enabled(self) -> bool:
        return env_value("ASK_AI_USE_FULL_EVOLVEMEM", default="true").strip().lower() not in {
            "0",
            "false",
            "no",
            "off",
        }

    def make_simplemem_dev_questions(self, limit: int = 12) -> list[tuple[str, str]]:
        if not ASK_AI_MEMORY_PATH.exists():
            return []
        rows = []
        for line in ASK_AI_MEMORY_PATH.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            question = clean_space(item.get("question", ""))
            answer = clean_space(item.get("answer", ""))
            if question and answer:
                rows.append((question, answer[:900]))
        return rows[-limit:]

    def write_ask_ai_retrieval_config_from_simplemem(self, config: Any, dev_question_count: int) -> dict[str, Any]:
        payload = {
            "method": "native_simplemem_optimize_v1",
            "doc_top_k": self._doc_top_k(),
            "memory_top_k": max(
                int(getattr(config, "k_sem", 0) or 0),
                int(getattr(config, "k_kw", 0) or 0),
                int(getattr(config, "k_str", 0) or 0),
                2,
            ),
            "simplemem": {
                "k_sem": getattr(config, "k_sem", 0),
                "k_kw": getattr(config, "k_kw", 0),
                "k_str": getattr(config, "k_str", 0),
                "context_budget": getattr(config, "context_budget", 8),
                "fusion_mode": getattr(config, "fusion_mode", "sum"),
                "fusion_weights": getattr(config, "fusion_weights", {}),
                "answer_style": getattr(config, "answer_style", "concise"),
                "enable_query_decomposition": getattr(config, "enable_query_decomposition", False),
                "enable_answer_verification": getattr(config, "enable_answer_verification", False),
                "evolved": getattr(config, "evolved", False),
                "evolution_rounds": getattr(config, "evolution_rounds", 0),
                "source_benchmark": getattr(config, "source_benchmark", "ask_ai_clean_memory"),
            },
            "dev_question_count": dev_question_count,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        ASK_AI_RETRIEVAL_CONFIG_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
        return payload

    def run_guarded_legal_evolvemem(self) -> dict[str, Any]:
        logs = self.load_recent_failure_logs(limit=24)
        scored_logs = [item for item in logs if isinstance(item.get("score"), (int, float))]
        if not scored_logs:
            return {
                "ok": True,
                "stdout": "No scored legal failure logs yet; waiting for Ask AI eval traffic.",
                "stderr": "",
                "config": self.current_ask_ai_config(),
                "evaluated_logs": 0,
            }
        current_score = sum(float(item["score"]) for item in scored_logs) / len(scored_logs)
        current_config = self.current_ask_ai_config()
        best = self.best_evolution_snapshot()
        if best and current_score < float(best.get("score", 0)) - 0.01:
            best_config = best.get("config") or current_config
            ASK_AI_RETRIEVAL_CONFIG_PATH.write_text(json.dumps(best_config, indent=2, ensure_ascii=False) + "\n")
            self.append_evolution_history(
                {
                    "stage": "revert",
                    "score": round(current_score, 4),
                    "best_score": best.get("score"),
                    "reason": "Recent scored logs regressed below best accepted config.",
                    "config": best_config,
                }
            )
            return {
                "ok": True,
                "stdout": "Guard reverted Ask AI retrieval config to best prior EvolveMem snapshot.",
                "stderr": "",
                "config": best_config,
                "score": round(current_score, 4),
                "evaluated_logs": len(scored_logs),
                "diagnosis": {"action": "revert"},
            }

        diagnosis = self.diagnose_failure_logs(logs, current_config, current_score)
        candidate = self.apply_diagnosis_to_config(current_config, diagnosis, scored_logs)
        ASK_AI_RETRIEVAL_CONFIG_PATH.write_text(json.dumps(candidate, indent=2, ensure_ascii=False) + "\n")
        self.append_evolution_history(
            {
                "stage": "accept",
                "score": round(current_score, 4),
                "reason": diagnosis.get("root_cause", ""),
                "diagnosis": diagnosis,
                "config": candidate,
            }
        )
        return {
            "ok": True,
            "stdout": "Ran guarded legal EvolveMem loop over Ask AI failure logs.",
            "stderr": "",
            "config": candidate,
            "score": round(current_score, 4),
            "evaluated_logs": len(scored_logs),
            "diagnosis": diagnosis,
        }

    def current_ask_ai_config(self) -> dict[str, Any]:
        if ASK_AI_RETRIEVAL_CONFIG_PATH.exists():
            try:
                loaded = json.loads(ASK_AI_RETRIEVAL_CONFIG_PATH.read_text())
                if isinstance(loaded, dict):
                    return loaded
            except json.JSONDecodeError:
                pass
        return {
            "method": "guarded_legal_evolvemem_v1",
            "doc_top_k": 8,
            "memory_top_k": 4,
            "fusion_mode": "rrf",
            "enable_answer_verification": False,
            "enable_structured_metadata": True,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    def load_recent_failure_logs(self, limit: int = 24) -> list[dict[str, Any]]:
        if not ASK_AI_FAILURE_LOG_PATH.exists():
            return []
        rows = []
        for line in ASK_AI_FAILURE_LOG_PATH.read_text(encoding="utf-8").splitlines()[-limit:]:
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return rows

    def best_evolution_snapshot(self) -> dict[str, Any] | None:
        if not ASK_AI_EVOLUTION_HISTORY_PATH.exists():
            return None
        best = None
        for line in ASK_AI_EVOLUTION_HISTORY_PATH.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if item.get("stage") != "accept" or not isinstance(item.get("score"), (int, float)):
                continue
            if best is None or float(item["score"]) > float(best.get("score", 0)):
                best = item
        return best

    def append_evolution_history(self, payload: dict[str, Any]) -> None:
        item = dict(payload)
        item["timestamp"] = datetime.now(timezone.utc).isoformat()
        with ASK_AI_EVOLUTION_HISTORY_PATH.open("a", encoding="utf-8") as file:
            file.write(json.dumps(item, ensure_ascii=False) + "\n")

    def diagnose_failure_logs(
        self,
        logs: list[dict[str, Any]],
        current_config: dict[str, Any],
        current_score: float,
    ) -> dict[str, Any]:
        if self.api_key:
            try:
                compact_logs = [
                    {
                        "question": item.get("question", "")[:240],
                        "mode": item.get("mode", ""),
                        "score": item.get("score"),
                        "failure_reason": item.get("failure_reason", ""),
                        "missing_points": item.get("missing_points", [])[:6],
                        "retrieval_counts": item.get("retrieval_counts", {}),
                    }
                    for item in logs[-10:]
                ]
                response = self._post_json(
                    "/chat/completions",
                    {
                        "model": self.chat_model,
                        "messages": [
                            {
                                "role": "system",
                                "content": (
                                    "You diagnose legal AI retrieval failures using an EvolveMem-style rubric. "
                                    "Return strict JSON only. Suggest small safe config changes."
                                ),
                            },
                            {
                                "role": "user",
                                "content": (
                                    f"Current config:\n{json.dumps(current_config, ensure_ascii=False)}\n\n"
                                    f"Average score: {current_score:.4f}\n\n"
                                    f"Recent raw failure logs:\n{json.dumps(compact_logs, ensure_ascii=False)}\n\n"
                                    "Return JSON with keys: root_cause, parameter_suggestions, "
                                    "enable_answer_verification, rationale. Allowed parameter_suggestions keys: "
                                    "memory_top_k, doc_top_k, fusion_mode, enable_structured_metadata."
                                ),
                            },
                        ],
                        "temperature": 0.0,
                        "max_tokens": 700,
                    },
                )
                content = response["choices"][0]["message"]["content"].strip()
                content = re.sub(r"^```(?:json)?|```$", "", content, flags=re.I | re.M).strip()
                parsed = json.loads(content)
                if isinstance(parsed, dict):
                    return parsed
            except Exception as error:
                self.simplemem_error = str(error)
        return self.heuristic_failure_diagnosis(logs, current_score)

    def heuristic_failure_diagnosis(self, logs: list[dict[str, Any]], current_score: float) -> dict[str, Any]:
        reasons = [str(item.get("failure_reason", "")) for item in logs]
        retrieval_counts = [item.get("retrieval_counts", {}) for item in logs]
        missing_context = reasons.count("insufficient_memory_or_upload_context")
        missing_points = reasons.count("answer_missing_expected_legal_points")
        low_doc_hits = sum(1 for item in retrieval_counts if int(item.get("uploaded_documents", 0) or 0) == 0)
        suggestions: dict[str, Any] = {"fusion_mode": "rrf", "enable_structured_metadata": True}
        if missing_context:
            suggestions["memory_top_k"] = 6
        if low_doc_hits < len(retrieval_counts):
            suggestions["doc_top_k"] = 10
        if missing_points or current_score < 0.72:
            suggestions["memory_top_k"] = max(int(suggestions.get("memory_top_k", 4)), 5)
        return {
            "root_cause": "heuristic: missing expected legal points or insufficient retrieved context",
            "parameter_suggestions": suggestions,
            "enable_answer_verification": current_score < 0.75,
            "rationale": "Fallback diagnosis used because LLM diagnosis was unavailable or invalid.",
        }

    def apply_diagnosis_to_config(
        self,
        current_config: dict[str, Any],
        diagnosis: dict[str, Any],
        scored_logs: list[dict[str, Any]],
    ) -> dict[str, Any]:
        candidate = dict(current_config)
        suggestions = diagnosis.get("parameter_suggestions") or {}
        if "memory_top_k" in suggestions:
            candidate["memory_top_k"] = max(0, min(6, int(suggestions["memory_top_k"])))
        if "doc_top_k" in suggestions:
            candidate["doc_top_k"] = max(0, min(12, int(suggestions["doc_top_k"])))
        if suggestions.get("fusion_mode") in {"sum", "rrf", "weighted_sum"}:
            candidate["fusion_mode"] = suggestions["fusion_mode"]
        if "enable_structured_metadata" in suggestions:
            candidate["enable_structured_metadata"] = bool(suggestions["enable_structured_metadata"])
        if "enable_answer_verification" in diagnosis:
            candidate["enable_answer_verification"] = bool(diagnosis["enable_answer_verification"])
        elif scored_logs:
            avg = sum(float(item["score"]) for item in scored_logs) / len(scored_logs)
            candidate["enable_answer_verification"] = avg < 0.75
        candidate["method"] = "guarded_legal_evolvemem_v1"
        candidate["last_diagnosis"] = {
            "root_cause": diagnosis.get("root_cause", ""),
            "rationale": diagnosis.get("rationale", ""),
        }
        candidate["evaluated_log_count"] = len(scored_logs)
        candidate["updated_at"] = datetime.now(timezone.utc).isoformat()
        return candidate

    def record_auto_improve_event(self, event: str) -> dict[str, Any]:
        if not self._auto_improve_enabled():
            return self.auto_improve_status()
        with self.auto_improve_lock:
            if event == "upload":
                self.auto_improve_state["uploads_since_optimize"] = int(
                    self.auto_improve_state.get("uploads_since_optimize", 0)
                ) + 1
                should_start = True
                reason = "upload"
            else:
                self.auto_improve_state["questions_since_optimize"] = int(
                    self.auto_improve_state.get("questions_since_optimize", 0)
                ) + 1
                should_start = (
                    int(self.auto_improve_state.get("questions_since_optimize", 0))
                    >= ASK_AI_AUTO_IMPROVE_QUESTION_INTERVAL
                )
                reason = "question_batch"
            self._save_auto_improve_state_unlocked()
        if should_start:
            self.start_auto_improve(reason)
        return self.auto_improve_status()

    def start_auto_improve(self, reason: str) -> bool:
        if not self._auto_improve_enabled():
            return False
        with self.auto_improve_lock:
            if self.auto_improve_state.get("status") == "running":
                return False
            self.auto_improve_state.update(
                {
                    "status": "running",
                    "last_reason": reason,
                    "last_started_at": datetime.now(timezone.utc).isoformat(),
                    "last_error": "",
                }
            )
            self._save_auto_improve_state_unlocked()
        thread = threading.Thread(target=self._auto_improve_worker, name="ask-ai-auto-improve", daemon=True)
        thread.start()
        return True

    def auto_improve_status(self) -> dict[str, Any]:
        with self.auto_improve_lock:
            state = dict(self.auto_improve_state)
        state["enabled"] = self._auto_improve_enabled()
        state["question_interval"] = ASK_AI_AUTO_IMPROVE_QUESTION_INTERVAL
        if ASK_AI_RETRIEVAL_CONFIG_PATH.exists():
            try:
                state["active_config"] = json.loads(ASK_AI_RETRIEVAL_CONFIG_PATH.read_text())
            except json.JSONDecodeError:
                state["active_config"] = {}
        state["evolvemem"] = self.evolvemem_status()
        state["simplemem"] = self.simplemem_status()
        return state

    def evolvemem_status(self) -> dict[str, Any]:
        logs = self.load_recent_failure_logs(limit=500)
        scored = [item for item in logs if isinstance(item.get("score"), (int, float))]
        best = self.best_evolution_snapshot()
        last_log = logs[-1] if logs else {}
        return {
            "failure_log_path": str(ASK_AI_FAILURE_LOG_PATH),
            "history_path": str(ASK_AI_EVOLUTION_HISTORY_PATH),
            "failure_log_count": len(logs),
            "scored_log_count": len(scored),
            "legal_eval_count": len(LEGAL_EVAL_SET),
            "last_score": last_log.get("score"),
            "last_failure_reason": last_log.get("failure_reason", ""),
            "best_score": best.get("score") if best else None,
            "best_stage": best.get("stage") if best else "",
        }

    def simplemem_status(self) -> dict[str, Any]:
        mem = self.get_simplemem()
        count = 0
        if mem is not None:
            try:
                count = len(mem.get_all_memories())
            except Exception as error:
                self.simplemem_error = str(error)
        return {
            "provider": "simplemem",
            "status": "active" if mem is not None else "unavailable",
            "memory_count": count,
            "config_path": str(ASK_AI_SIMPLEMEM_CONFIG_PATH),
            "config_exists": ASK_AI_SIMPLEMEM_CONFIG_PATH.exists(),
            "error": self.simplemem_error,
        }

    def _auto_improve_worker(self) -> None:
        try:
            result = self.run_autoresearch()
            with self.auto_improve_lock:
                self.auto_improve_state.update(
                    {
                        "status": "idle",
                        "questions_since_optimize": 0,
                        "uploads_since_optimize": 0,
                        "last_completed_at": datetime.now(timezone.utc).isoformat(),
                        "last_ok": bool(result.get("ok")),
                        "last_stdout": str(result.get("stdout", ""))[-2000:],
                        "last_stderr": str(result.get("stderr", ""))[-2000:],
                        "last_config": result.get("config", {}),
                        "last_error": "" if result.get("ok") else str(result.get("stderr", ""))[-500:],
                    }
                )
                self._save_auto_improve_state_unlocked()
        except Exception as error:
            with self.auto_improve_lock:
                self.auto_improve_state.update(
                    {
                        "status": "idle",
                        "questions_since_optimize": 0,
                        "uploads_since_optimize": 0,
                        "last_completed_at": datetime.now(timezone.utc).isoformat(),
                        "last_ok": False,
                        "last_error": str(error),
                    }
                )
                self._save_auto_improve_state_unlocked()

    def format_sources(
        self,
        clean_memory: list[dict[str, Any]],
        docs: list[dict[str, Any]],
        laws: list[dict[str, Any]],
        question: str,
    ) -> list[dict[str, Any]]:
        sources = []
        for chunk in [*clean_memory, *docs, *laws]:
            kind = chunk.get("kind", "source")
            if kind == "simplemem_memory":
                relevance = "Retrieved by native SimpleMem hybrid retrieval from clean Ask AI memory."
            elif kind == "clean_memory":
                relevance = "Retrieved from clean Ask AI memory fallback; no bundled source dataset was used."
            elif kind == "uploaded_document":
                relevance = "Retrieved from a user-uploaded document using OpenRouter embeddings."
            else:
                relevance = f"Retrieved by Ask AI from {kind}."
            sources.append(
                {
                    "title": chunk.get("title", ""),
                    "identifier": chunk.get("identifier", ""),
                    "section_number": chunk.get("section_number", ""),
                    "section_heading": chunk.get("section_heading", ""),
                    "score": round(float(chunk.get("score", 0)), 4),
                    "quote": self.quote_snippet(chunk.get("text", ""), question),
                    "relevance": relevance,
                    "kind": kind,
                    "metadata": chunk.get("metadata", {}),
                }
            )
        return sources

    def _auto_improve_prompt_summary(self, status: dict[str, Any]) -> str:
        active_config = status.get("active_config") or {}
        simplemem_status = status.get("simplemem") or {}
        evolvemem = status.get("evolvemem") or {}
        return (
            f"enabled={status.get('enabled')}; "
            f"status={status.get('status')}; "
            f"question_interval={status.get('question_interval')}; "
            f"questions_since_optimize={status.get('questions_since_optimize')}; "
            f"active_config_method={active_config.get('method', 'none')}; "
            f"answer_verification={active_config.get('enable_answer_verification', False)}; "
            f"evolvemem_logs={evolvemem.get('failure_log_count', 0)}; "
            f"evolvemem_best_score={evolvemem.get('best_score', 'none')}; "
            f"simplemem_status={simplemem_status.get('status', 'unknown')}; "
            f"simplemem_memory_count={simplemem_status.get('memory_count', 0)}; "
            "No bundled legal source dataset is available to this Ask AI prompt."
        )

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        results: list[list[float] | None] = []
        missing_indices = []
        missing_texts = []
        for index, text in enumerate(texts):
            cache_key = self._embedding_cache_key(text)
            cached = self.embedding_cache.get(cache_key)
            if cached is None:
                results.append(None)
                missing_indices.append(index)
                missing_texts.append(text[:8000])
            else:
                results.append(cached)
        if missing_texts:
            response = self._post_json("/embeddings", {"model": self.embedding_model, "input": missing_texts})
            embeddings = [item["embedding"] for item in response.get("data", [])]
            if len(embeddings) != len(missing_texts):
                raise RuntimeError("Embedding response length did not match request")
            for result_index, text, embedding in zip(missing_indices, missing_texts, embeddings):
                self.embedding_cache[self._embedding_cache_key(text)] = embedding
                results[result_index] = embedding
            self._save_embedding_cache()
        return [item or [] for item in results]

    def quote_snippet(self, text: str, question: str, limit: int = 360) -> str:
        text = clean_space(text)
        if len(text) <= limit:
            return text
        tokens = tokenize(question)
        best_index = 0
        best_score = -1
        for match in re.finditer(r"\b[A-Za-z0-9][A-Za-z0-9'()-]{2,}\b", text):
            window = text[max(0, match.start() - 160) : match.start() + 240].lower()
            score = sum(1 for token in tokens if token in window)
            if score > best_score:
                best_score = score
                best_index = max(0, match.start() - 100)
        snippet = text[best_index : best_index + limit].strip()
        if best_index:
            snippet = "... " + snippet
        if best_index + limit < len(text):
            snippet += " ..."
        return snippet

    def _source_context(self, chunks: list[dict[str, Any]], label: str) -> str:
        if not chunks:
            return f"{label}: none retrieved."
        body = []
        for index, chunk in enumerate(chunks, start=1):
            body.append(
                f"{label} {index}: {chunk.get('title')}"
                f"{' / ' + chunk.get('section_number', '') if chunk.get('section_number') else ''}"
                f"{' - ' + chunk.get('section_heading', '') if chunk.get('section_heading') else ''}\n"
                f"{chunk.get('text', '')}"
            )
        return "\n\n".join(body)

    def _doc_top_k(self) -> int:
        return self._retrieval_config_int("doc_top_k", 8)

    def _memory_top_k(self) -> int:
        return self._retrieval_config_int("memory_top_k", 4, cap=6)

    def _retrieval_config_int(self, key: str, default: int, cap: int = 20) -> int:
        if ASK_AI_RETRIEVAL_CONFIG_PATH.exists():
            try:
                value = int(json.loads(ASK_AI_RETRIEVAL_CONFIG_PATH.read_text()).get(key, default))
                return max(0, min(cap, value))
            except (json.JSONDecodeError, ValueError, TypeError):
                return default
        return default

    def get_simplemem(self):
        with self.simplemem_lock:
            if self.simplemem is not None:
                return self.simplemem
            try:
                from simplemem import create

                self.simplemem = create(
                    mode="text",
                    api_key=self.api_key,
                    base_url=self.base_url,
                    model=self.chat_model,
                    db_path=str(ASK_AI_SIMPLEMEM_DB_PATH),
                    table_name="ask_ai_clean_memory",
                    clear_db=False,
                    use_streaming=False,
                    enable_planning=False,
                    enable_reflection=False,
                )
                self.apply_simplemem_config(self.simplemem)
                self.simplemem_error = ""
                return self.simplemem
            except Exception as error:
                self.simplemem_error = str(error)
                return None

    def apply_simplemem_config(self, mem: Any) -> None:
        if not ASK_AI_SIMPLEMEM_CONFIG_PATH.exists():
            return
        try:
            from simplemem import load_config

            config = load_config(str(ASK_AI_SIMPLEMEM_CONFIG_PATH))
            retriever = getattr(mem, "hybrid_retriever", None)
            if retriever is not None:
                if getattr(config, "k_sem", 0):
                    retriever.semantic_top_k = min(6, config.k_sem)
                if getattr(config, "k_kw", 0):
                    retriever.keyword_top_k = min(6, config.k_kw)
                if getattr(config, "k_str", 0):
                    retriever.structured_top_k = min(6, config.k_str)
                retriever.enable_planning = False
                retriever.enable_reflection = False
                if getattr(config, "context_budget", 0):
                    retriever.max_reflection_rounds = 1
        except Exception as error:
            self.simplemem_error = str(error)

    def _clean_memory_count(self) -> int:
        if not ASK_AI_MEMORY_PATH.exists():
            return 0
        return sum(1 for line in ASK_AI_MEMORY_PATH.read_text(encoding="utf-8").splitlines() if line.strip())

    def _auto_improve_enabled(self) -> bool:
        return env_value("ASK_AI_AUTO_IMPROVE", default="true").strip().lower() not in {
            "0",
            "false",
            "no",
            "off",
        }

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = self.base_url.rstrip("/") + path
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "http://127.0.0.1:8088",
                "X-Title": "Legal AI Ask AI",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"OpenRouter HTTP {error.code}: {body}") from error

    def _embedding_cache_key(self, text: str) -> str:
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return f"{self.embedding_model}:{digest}"

    def _load_documents(self) -> list[dict[str, Any]]:
        if ASK_AI_DOCS_PATH.exists():
            try:
                return json.loads(ASK_AI_DOCS_PATH.read_text())
            except json.JSONDecodeError:
                return []
        return []

    def _save_documents(self) -> None:
        ASK_AI_DOCS_PATH.write_text(json.dumps(self.documents, indent=2, ensure_ascii=False) + "\n")

    def _load_embedding_cache(self) -> dict[str, list[float]]:
        if ASK_AI_EMBEDDING_CACHE_PATH.exists():
            try:
                return json.loads(ASK_AI_EMBEDDING_CACHE_PATH.read_text())
            except json.JSONDecodeError:
                return {}
        return {}

    def _save_embedding_cache(self) -> None:
        ASK_AI_EMBEDDING_CACHE_PATH.write_text(json.dumps(self.embedding_cache))

    def _load_auto_improve_state(self) -> dict[str, Any]:
        default = {
            "status": "idle",
            "questions_since_optimize": 0,
            "uploads_since_optimize": 0,
            "last_reason": "",
            "last_started_at": "",
            "last_completed_at": "",
            "last_ok": None,
            "last_error": "",
            "last_stdout": "",
            "last_stderr": "",
            "last_config": {},
        }
        if ASK_AI_AUTO_IMPROVE_STATE_PATH.exists():
            try:
                loaded = json.loads(ASK_AI_AUTO_IMPROVE_STATE_PATH.read_text())
                if isinstance(loaded, dict):
                    default.update(loaded)
            except json.JSONDecodeError:
                pass
        if default.get("status") == "running":
            default["status"] = "idle"
        return default

    def _save_auto_improve_state_unlocked(self) -> None:
        ASK_AI_AUTO_IMPROVE_STATE_PATH.write_text(
            json.dumps(self.auto_improve_state, indent=2, ensure_ascii=False) + "\n"
        )
