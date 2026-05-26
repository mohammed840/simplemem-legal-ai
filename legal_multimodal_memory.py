#!/usr/bin/env python3
"""Legal multimodal memory using SimpleMem's native omni backend.

This is the legal-project adapter around SimpleMem multimodality. It does not
invent a separate image/audio store; it calls the repository's own omni API:

    simplemem.create(mode="omni", config=...)
    mem.add_text(...)
    mem.add_image_on_demand_caption_only(...)
    mem.add_audio(...)
    mem.add_video(...)
    mem.answer(...)

PDFs are treated as legal bundles:
  - extracted text is chunked into text MAUs
  - selected pages are rendered as images and stored with raw page images in
    cold storage, retrievable through caption/text summaries
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable


APP_DIR = Path(__file__).resolve().parent
REPO_ROOT = APP_DIR.parent
DEFAULT_DATA_DIR = APP_DIR / "legal_omni_memory_data"
DEFAULT_MANIFEST = APP_DIR / "legal_multimodal_manifest.jsonl"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".webm"}
TEXT_EXTS = {".txt", ".md", ".json", ".xml", ".html", ".csv"}
PDF_EXTS = {".pdf"}


def load_env(path: Path = REPO_ROOT / ".env") -> None:
    if not path.exists():
        return
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def make_omni_memory(data_dir: Path):
    import simplemem
    from simplemem.multimodal import OmniMemoryConfig

    config = OmniMemoryConfig.create_default()
    config.storage.base_dir = str(data_dir)
    config.storage.cold_storage_dir = str(data_dir / "cold_storage")
    config.storage.index_dir = str(data_dir / "index")

    api_key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENAI_API_KEY")
    base_url = (
        os.environ.get("OPENROUTER_BASE_URL")
        or os.environ.get("OPENAI_BASE_URL")
        or "https://openrouter.ai/api/v1"
    )
    model = (
        os.environ.get("CHAT_MODEL")
        or os.environ.get("LLM_MODEL")
        or "anthropic/claude-sonnet-4.5"
    )
    if api_key:
        config.llm.api_key = api_key
    config.llm.api_base_url = base_url
    config.llm.summary_model = model
    config.llm.query_model = model
    config.llm.caption_model = model

    # Keep text embeddings local and dimension-correct. This avoids OpenRouter
    # embedding endpoint issues while still using SimpleMem's EmbeddingService.
    config.embedding.model_name = "sentence-transformers/all-MiniLM-L6-v2"
    config.embedding.embedding_dim = 384
    config.embedding.visual_embedding_dim = 768

    config.retrieval.default_top_k = 10
    config.retrieval.max_expanded_items = 5
    config.retrieval.enable_hybrid_search = True
    config.ensure_directories()
    return simplemem.create(mode="omni", config=config, data_dir=str(data_dir))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def append_manifest(record: dict[str, Any], manifest_path: Path) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def iter_files(paths: Iterable[Path]) -> Iterable[Path]:
    for path in paths:
        if path.is_dir():
            for child in sorted(path.rglob("*")):
                if child.is_file():
                    yield child
        elif path.is_file():
            yield path


def chunk_text(text: str, chunk_chars: int = 3500, overlap: int = 350) -> list[str]:
    text = "\n".join(line.rstrip() for line in str(text or "").splitlines())
    text = text.strip()
    if not text:
        return []
    chunks = []
    start = 0
    while start < len(text):
        end = min(len(text), start + chunk_chars)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(end - overlap, start + 1)
    return chunks


def extract_pdf_pages(pdf_path: Path, max_pages: int | None = None) -> list[dict[str, Any]]:
    import fitz

    pages = []
    doc = fitz.open(str(pdf_path))
    try:
        total = doc.page_count if max_pages is None else min(doc.page_count, max_pages)
        for page_index in range(total):
            page = doc.load_page(page_index)
            text = page.get_text("text") or ""
            pages.append({
                "page_number": page_index + 1,
                "text": text.strip(),
                "page": page,
            })
    finally:
        # The caller cannot use page objects after close, so only close in the
        # render helper. This function returns text-only data.
        doc.close()
    return [{"page_number": p["page_number"], "text": p["text"]} for p in pages]


def render_pdf_page(pdf_path: Path, page_number: int, dpi: int = 144) -> Path:
    import fitz
    from PIL import Image

    doc = fitz.open(str(pdf_path))
    try:
        page = doc.load_page(page_number - 1)
        pix = page.get_pixmap(dpi=dpi)
        img_data = pix.tobytes("png")
    finally:
        doc.close()

    tmp = tempfile.NamedTemporaryFile(
        suffix=f".page-{page_number}.png",
        delete=False,
    )
    tmp.close()
    image = Image.open(__import__("io").BytesIO(img_data))
    image.save(tmp.name)
    return Path(tmp.name)


def add_text_chunk(mem: Any, text: str, session_id: str, tags: list[str], source_label: str):
    wrapped = f"[Legal document source: {source_label}]\n\n{text}"
    result = mem.add_text(wrapped, session_id=session_id, tags=tags, force=True)
    return result


def ingest_text_file(mem: Any, path: Path, args: argparse.Namespace) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    session_id = f"legal_text_{path.stem}_{sha256_file(path)[:10]}"
    tags = ["legal_multimodal", "legal_text", path.stem]
    stored = 0
    for idx, chunk in enumerate(chunk_text(text, args.chunk_chars), start=1):
        source = f"{path.name} chunk {idx}"
        result = add_text_chunk(mem, chunk, session_id, tags + [f"chunk_{idx}"], source)
        stored += int(bool(result.success and result.mau))
    return {"kind": "text", "path": str(path), "chunks_stored": stored}


def ingest_pdf(mem: Any, path: Path, args: argparse.Namespace) -> dict[str, Any]:
    digest = sha256_file(path)[:10]
    session_id = f"legal_pdf_{path.stem}_{digest}"
    tags = ["legal_multimodal", "legal_pdf", path.stem]
    pages = extract_pdf_pages(path, args.max_pages)
    text_chunks = 0
    image_pages = 0

    for page in pages:
        page_number = page["page_number"]
        page_text = page["text"]
        page_tags = tags + [f"page_{page_number}"]

        for idx, chunk in enumerate(chunk_text(page_text, args.chunk_chars), start=1):
            source = f"{path.name} page {page_number} text chunk {idx}"
            result = add_text_chunk(mem, chunk, session_id, page_tags, source)
            text_chunks += int(bool(result.success and result.mau))

        if args.render_pdf_pages:
            page_image = render_pdf_page(path, page_number, dpi=args.pdf_dpi)
            try:
                if page_text:
                    caption = (
                        f"Rendered legal PDF page {page_number} from {path.name}. "
                        f"OCR/extracted text excerpt: {page_text[:1200]}"
                    )
                else:
                    caption = (
                        f"Rendered scanned legal PDF page {page_number} from {path.name}. "
                        "Use the raw page image for visual evidence."
                    )
                result = mem.add_image_on_demand_caption_only(
                    str(page_image),
                    caption_text=caption,
                    session_id=session_id,
                    tags=page_tags + ["pdf_page_image", "vision_on_demand"],
                    force=True,
                )
                image_pages += int(bool(result.success and result.mau))
            finally:
                try:
                    page_image.unlink()
                except OSError:
                    pass

    return {
        "kind": "pdf",
        "path": str(path),
        "pages_seen": len(pages),
        "text_chunks_stored": text_chunks,
        "page_images_stored": image_pages,
    }


def ingest_image(mem: Any, path: Path, args: argparse.Namespace) -> dict[str, Any]:
    session_id = f"legal_image_{path.stem}_{sha256_file(path)[:10]}"
    tags = ["legal_multimodal", "legal_image", "vision_on_demand", path.stem]
    caption = (
        f"Legal image or scanned document named {path.name}. "
        "Use the raw image when visual evidence or visible document text matters."
    )
    result = mem.add_image_on_demand_caption_only(
        str(path),
        caption_text=caption,
        session_id=session_id,
        tags=tags,
        force=True,
    )
    return {
        "kind": "image",
        "path": str(path),
        "stored": bool(result.success and result.mau),
        "error": result.error,
    }


def ingest_audio(mem: Any, path: Path, args: argparse.Namespace) -> dict[str, Any]:
    session_id = f"legal_audio_{path.stem}_{sha256_file(path)[:10]}"
    result = mem.add_audio(
        str(path),
        session_id=session_id,
        tags=["legal_multimodal", "legal_audio", path.stem],
        force=True,
    )
    return {
        "kind": "audio",
        "path": str(path),
        "stored": bool(result.success and result.mau),
        "error": result.error,
    }


def ingest_video(mem: Any, path: Path, args: argparse.Namespace) -> dict[str, Any]:
    session_id = f"legal_video_{path.stem}_{sha256_file(path)[:10]}"
    result = mem.add_video(
        str(path),
        session_id=session_id,
        tags=["legal_multimodal", "legal_video", path.stem],
        max_frames=args.max_video_frames,
    )
    return {
        "kind": "video",
        "path": str(path),
        "stored": bool(result.success and result.mau),
        "error": result.error,
    }


def ingest_path(mem: Any, path: Path, args: argparse.Namespace) -> dict[str, Any]:
    suffix = path.suffix.lower()
    if suffix in PDF_EXTS:
        return ingest_pdf(mem, path, args)
    if suffix in IMAGE_EXTS:
        return ingest_image(mem, path, args)
    if suffix in AUDIO_EXTS:
        return ingest_audio(mem, path, args)
    if suffix in VIDEO_EXTS:
        return ingest_video(mem, path, args)
    if suffix in TEXT_EXTS:
        return ingest_text_file(mem, path, args)
    return {"kind": "unsupported", "path": str(path), "stored": False}


def command_ingest(args: argparse.Namespace) -> int:
    load_env()
    mem = make_omni_memory(args.data_dir)
    records = []
    for file_path in iter_files(args.paths):
        record = ingest_path(mem, file_path, args)
        append_manifest(record, args.manifest)
        records.append(record)
        print(json.dumps(record, ensure_ascii=False))
    if hasattr(mem, "close"):
        mem.close()
    print(f"Ingested {len(records)} files. Manifest: {args.manifest}")
    return 0


def command_ask(args: argparse.Namespace) -> int:
    load_env()
    mem = make_omni_memory(args.data_dir)
    answer = mem.answer(
        args.question,
        top_k=args.top_k,
        include_sources=True,
        include_on_demand_images=True,
    )
    if hasattr(mem, "close"):
        mem.close()
    if not args.full_json:
        for item in answer.get("retrieval_result", {}).get("items", []):
            raw = item.get("raw_content")
            if isinstance(raw, dict) and raw.get("base64"):
                raw["base64"] = f"<{len(raw['base64'])} base64 chars hidden>"
    print(json.dumps(answer, indent=2, ensure_ascii=False))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Ingest/query legal multimodal evidence using SimpleMem omni mode."
    )
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)

    sub = parser.add_subparsers(dest="command", required=True)

    ingest = sub.add_parser("ingest", help="Ingest PDFs/images/audio/video/text.")
    ingest.add_argument("paths", nargs="+", type=Path)
    ingest.add_argument("--chunk-chars", type=int, default=3500)
    ingest.add_argument("--max-pages", type=int, default=None)
    ingest.add_argument("--render-pdf-pages", action="store_true")
    ingest.add_argument("--pdf-dpi", type=int, default=144)
    ingest.add_argument("--max-video-frames", type=int, default=20)
    ingest.set_defaults(func=command_ingest)

    ask = sub.add_parser("ask", help="Ask the legal multimodal memory.")
    ask.add_argument("question")
    ask.add_argument("--top-k", type=int, default=8)
    ask.add_argument("--full-json", action="store_true", help="Include raw base64 image payloads.")
    ask.set_defaults(func=command_ask)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
