# Running The Application

This guide starts the Legal AI Ask AI app locally.

## 1. Open The Project Folder

```bash
cd "Legal AI Implementation"
```

If you are inside the parent SimpleMem repository, the path is usually:

```bash
cd "SimpleMem/Legal AI Implementation"
```

## 2. Create A Python Environment

```bash
python -m venv .venv
source .venv/bin/activate
```

## 3. Install Dependencies

Install this app's support dependencies:

```bash
pip install -r requirements.txt
```

Install SimpleMem from the parent or local SimpleMem clone:

```bash
pip install -e ..
```

If your SimpleMem clone is somewhere else, point `pip install -e` to that path.

## 4. Configure Models

Create a local environment file from the example:

```bash
cp .env.example .env
```

Set these values in `.env`:

```bash
OPENROUTER_API_KEY=your_openrouter_key
ASK_AI_MODEL=anthropic/claude-sonnet-4.5
EMBEDDING_MODEL=qwen/qwen3-embedding-0.6b
```

The app uses OpenRouter-compatible chat and embedding endpoints by default.

## 5. Start The App

```bash
python case_browser_app.py --port 8088
```

You should see:

```text
Legal AI Ask AI running at http://127.0.0.1:8088
```

## 6. Open The Browser

Go to:

[http://127.0.0.1:8088/](http://127.0.0.1:8088/)

## 7. Quick Smoke Test

Ask a general legal question, for example:

```text
Under U.S. law, when can a startup treat someone as an independent contractor instead of an employee?
```

You can also upload a legal document and ask questions about it. Uploaded files
become the local source layer for answers.

## Common Issues

### Port Already In Use

Use another port:

```bash
python case_browser_app.py --port 8090
```

Then open:

[http://127.0.0.1:8090/](http://127.0.0.1:8090/)

### Missing API Key

If Ask AI says OpenRouter is not configured, check that `.env` exists and has:

```bash
OPENROUTER_API_KEY=your_openrouter_key
```

Then restart the app.

### SimpleMem Not Installed

If SimpleMem imports fail, install the parent package:

```bash
pip install -e ..
```

The app has local fallback memory, but native SimpleMem features need the
SimpleMem package available in the Python environment.
