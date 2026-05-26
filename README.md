# Legal AI Implementation

A focused local Ask AI app for legal questions, document review, and
SimpleMem/EvolveMem memory workflows.

This repository is the legal application layer built alongside
[aiming-lab/SimpleMem](https://github.com/aiming-lab/SimpleMem). SimpleMem
provides the memory and evolution foundation; this project provides the local
browser UI, OpenRouter model integration, document ingestion, and legal Ask AI
workflow.

## Current Scope

- Ask AI browser interface.
- Automatic workflow detection for legal questions and uploaded documents.
- OpenRouter-compatible chat model support.
- OpenRouter-compatible embedding model support.
- User-uploaded document ingestion into Ask AI memory.
- Native SimpleMem text memory for clean conversation and matter memory.
- SimpleMem omni memory for PDFs, scans, images, audio, video, and text files.
- SimpleMem/EvolveMem `EvolutionEngine` background optimization over an in-app
  Ask AI legal benchmark.
- Imported legal workflow skills from
  [zubair-trabzada/ai-legal-claude](https://github.com/zubair-trabzada/ai-legal-claude).
- Source-aware answers that can cite retrieved user-uploaded material or clean
  memory entries.

## Main Files

| File | Purpose |
| --- | --- |
| `case_browser_app.py` | Local HTTP server and browser UI for Ask AI. |
| `ask_ai_engine.py` | Ask AI orchestration: model calls, embeddings, uploads, SimpleMem memory, and EvolveMem optimization. |
| `simplemem_memory.py` | SimpleMem text-memory adapter with a local fallback. |
| `legal_multimodal_memory.py` | SimpleMem omni-memory wrapper for multimodal evidence. |
| `ai_legal_claude_skills/` | Vendored legal skill prompts and supporting agent instructions from `ai-legal-claude`. |
| `docs/RUNNING.md` | Step-by-step local setup and run guide. |
| `requirements.txt` | Python dependencies used by this app layer. |
| `.env.example` | Example configuration keys for local setup. |

## Architecture

```text
User question or upload
        |
        v
Ask AI app
        |
        +--> OpenRouter chat model
        +--> OpenRouter embeddings
        +--> SimpleMem text memory
        +--> SimpleMem omni memory
        +--> ai-legal-claude workflow skills
        +--> EvolveMem optimization
        |
        v
Source-aware legal answer
```

## ai-legal-claude Integration

This app uses the legal workflow prompts from
[zubair-trabzada/ai-legal-claude](https://github.com/zubair-trabzada/ai-legal-claude)
as real local prompt assets. The upstream skill files are stored in
`ai_legal_claude_skills/`, and `ask_ai_engine.py` loads the matching `SKILL.md`
file for each Ask AI workflow.

Current mappings:

| Ask AI workflow | Imported skill |
| --- | --- |
| General Legal Question | `legal/SKILL.md` |
| Contract Review | `skills/legal-review/SKILL.md` plus supporting agent files |
| Clause Risk Analysis | `skills/legal-risks/SKILL.md` |
| Plain English Explanation | `skills/legal-plain/SKILL.md` |
| Compliance Check | `skills/legal-compliance/SKILL.md` |
| Negotiation Suggestions | `skills/legal-negotiate/SKILL.md` |
| Missing Protections | `skills/legal-missing/SKILL.md` |
| Document Summary | `skills/legal-review/SKILL.md` |

The app also recognizes `/legal ...` style prompts and loads the matching
vendored skill when available.

Users do not need to select a workflow manually. Ask AI detects the best
workflow from the question and available uploaded documents, then loads the
matching legal skill.

## Setup

For the full setup guide, see [docs/RUNNING.md](docs/RUNNING.md).

From this folder:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Install or expose the parent SimpleMem package so the app can use the native
SimpleMem and EvolveMem APIs.

## Run

For detailed troubleshooting and smoke-test steps, see
[docs/RUNNING.md](docs/RUNNING.md).

```bash
python case_browser_app.py --port 8088
```

Then open:

[http://127.0.0.1:8088/](http://127.0.0.1:8088/)

## Ask AI Flow

```text
user question
-> retrieve user-uploaded documents and clean SimpleMem memory
-> answer with the configured model
-> save useful interaction memory
-> run background retrieval improvement
```

The app is designed so uploaded documents become the local source layer, while
general legal questions can still be answered by the configured model and the
active legal workflow skills.
