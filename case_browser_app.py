#!/usr/bin/env python3
"""
Local Ask AI app for the Legal AI prototype.

Run:
    python3 "Legal AI Implementation/case_browser_app.py"

Then open:
    http://localhost:8088
"""

from __future__ import annotations

import json
import base64
import html
import re
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

from ask_ai_engine import ASK_AI_UPLOAD_DIR, AskAIEngine
from legal_multimodal_memory import ingest_path, make_omni_memory


APP_DIR = Path(__file__).resolve().parent
MULTIMODAL_DATA_DIR = APP_DIR / "legal_omni_memory_data"
MULTIMODAL_UPLOAD_DIR = APP_DIR / "legal_multimodal_uploads"
DEFAULT_PORT = 8088
ASK_AI: AskAIEngine | None = None
OMNI_MEMORY = None


HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
      <title>Legal AI Ask AI</title>
  <style>
    @import url("https://fonts.cdnfonts.com/css/cal-sans");

    :root {
      color-scheme: light;
      --bg: #f5f5f5;
      --panel: #ffffff;
      --panel-soft: #f8f8f8;
      --line: #dedede;
      --line-strong: #bdbdbd;
      --text: #171717;
      --muted: #6f6f6f;
      --muted-2: #929292;
      --accent: #111111;
      --accent-hover: #2b2b2b;
      --accent-soft: #eeeeee;
      --accent-line: #cfcfcf;
      --shadow: 0 1px 2px rgba(16, 24, 40, 0.05);
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 14px/1.5 "Cal Sans", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      letter-spacing: 0;
    }

    .app {
      min-height: 100vh;
      display: grid;
      grid-template-rows: 1fr;
    }

    body.chat-open .detail-inner {
      max-width: 980px;
    }

    main {
      display: grid;
      grid-template-columns: minmax(0, 1fr);
      gap: 0;
      min-height: 0;
      overflow: hidden;
      transition: grid-template-columns 220ms ease;
    }

    body.chat-open main {
      grid-template-columns: minmax(0, 1fr) minmax(380px, 440px);
    }

    aside {
      border-right: 1px solid var(--line);
      background: #fbfbfc;
      min-height: 0;
      display: grid;
      grid-template-rows: auto 1fr;
    }

    input {
      width: 100%;
      height: 38px;
      border: 1px solid var(--line-strong);
      border-radius: 6px;
      padding: 0 11px;
      background: #fff;
      color: var(--text);
      outline: none;
    }

    input:focus {
      border-color: var(--accent);
      box-shadow: 0 0 0 3px rgba(47, 95, 143, 0.12);
    }

    textarea {
      width: 100%;
      min-height: 82px;
      border: 1px solid var(--line-strong);
      border-radius: 6px;
      padding: 9px 11px;
      background: #fff;
      color: var(--text);
      outline: none;
      resize: vertical;
      font: inherit;
    }

    textarea:focus {
      border-color: var(--accent);
      box-shadow: 0 0 0 3px rgba(47, 95, 143, 0.12);
    }

    .detail {
      min-width: 0;
      overflow: auto;
      padding: 22px;
    }

    .detail-inner {
      max-width: 1120px;
      margin: 0 auto;
    }

    .title-row {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 20px;
      margin-bottom: 18px;
    }

    .title-actions {
      display: flex;
      gap: 8px;
      flex-shrink: 0;
    }

    .ask-ai-shell {
      display: grid;
      gap: 14px;
    }

    .ask-ai-shell.chat-style {
      min-height: calc(100vh - 86px);
      grid-template-rows: auto minmax(360px, 1fr) auto;
    }

    .ask-ai-topbar {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 10px;
      margin-bottom: 2px;
      flex-wrap: wrap;
    }

    .ask-ai-topbar-actions,
    .ask-ai-upload-inline,
    .ask-ai-composer-actions {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }

    .ask-ai-topbar select,
    .ask-ai-upload-inline input[type="file"] {
      height: 38px;
      border: 1px solid var(--line-strong);
      border-radius: 6px;
      background: #fff;
      color: var(--text);
      font: inherit;
      padding: 0 10px;
    }

    .auto-workflow-pill {
      min-height: 34px;
      display: inline-flex;
      align-items: center;
      border: 1px solid var(--line);
      border-radius: 999px;
      background: #fff;
      color: var(--muted);
      padding: 0 12px;
      font-size: 12px;
      font-weight: 650;
    }

    .ask-ai-upload-inline input[type="file"] {
      height: auto;
      max-width: 320px;
      border-style: dashed;
      background: #fafafa;
      padding: 8px 10px;
      font-size: 12px;
    }

    .ask-ai-messages {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      overflow: auto;
      padding: 18px;
    }

    .ask-ai-message {
      max-width: 860px;
      margin: 0 auto 18px;
    }

    .ask-ai-message:last-child {
      margin-bottom: 0;
    }

    .ask-ai-message.user {
      text-align: right;
    }

    .ask-ai-message.user .message-label {
      text-align: right;
    }

    .ask-ai-bubble {
      display: inline-block;
      max-width: 92%;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fafafa;
      padding: 12px 14px;
      text-align: left;
    }

    .ask-ai-message.user .ask-ai-bubble {
      border-color: var(--accent);
      background: var(--accent);
      color: #fff;
    }

    .ask-ai-message.user .message-content {
      color: #fff;
    }

    .ask-ai-composer {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      padding: 12px;
      display: grid;
      gap: 10px;
    }

    .ask-ai-composer textarea {
      min-height: 92px;
      border: 0;
      padding: 0;
      box-shadow: none;
      resize: vertical;
    }

    .ask-ai-composer textarea:focus {
      border-color: transparent;
      box-shadow: none;
    }

    .ask-ai-composer-actions {
      justify-content: space-between;
    }

    button.primary {
      height: 38px;
      border: 1px solid var(--accent);
      border-radius: 7px;
      background: var(--accent);
      color: #fff;
      padding: 0 13px;
      font-weight: 650;
      cursor: pointer;
    }

    button.primary:hover {
      background: var(--accent-hover);
    }

    button.secondary {
      height: 34px;
      border: 1px solid var(--line-strong);
      border-radius: 7px;
      background: #fff;
      color: var(--text);
      padding: 0 11px;
      font-weight: 620;
      cursor: pointer;
    }

    button.secondary:hover {
      background: #f3f4f6;
    }

    h1 {
      margin: 0 0 8px;
      font-size: 25px;
      line-height: 1.2;
      font-weight: 700;
      letter-spacing: 0;
    }

    .subtitle {
      color: var(--muted);
      margin: 0;
    }

    .grid {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
      margin-bottom: 18px;
    }

    .box {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      box-shadow: var(--shadow);
      padding: 13px;
      min-width: 0;
    }

    .box-label {
      color: var(--muted);
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      margin-bottom: 4px;
    }

    .box-value {
      font-weight: 620;
      overflow-wrap: anywhere;
    }

    .section {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: var(--panel);
      box-shadow: var(--shadow);
      margin-bottom: 14px;
      overflow: hidden;
    }

    .section-header {
      padding: 12px 14px;
      border-bottom: 1px solid var(--line);
      font-weight: 650;
      background: var(--panel-soft);
    }

    .section-body {
      padding: 14px;
    }

    .chips {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }

    .chip {
      border: 1px solid var(--line);
      background: #f7f7f7;
      border-radius: 999px;
      padding: 5px 9px;
      color: #333333;
      font-size: 12px;
    }

    .summary {
      margin: 0;
      color: #333333;
      white-space: pre-wrap;
    }

    .section-actions {
      display: flex;
      justify-content: flex-end;
      margin-top: 12px;
    }

    .evidence-grid {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
      gap: 14px;
    }

    .evidence-form {
      display: grid;
      gap: 9px;
      align-content: start;
    }

    .file-input {
      min-height: 76px;
      border: 1px dashed var(--line-strong);
      border-radius: 8px;
      background: #fafafa;
      padding: 13px;
      display: grid;
      gap: 8px;
    }

    .file-input input {
      height: auto;
      border: 0;
      padding: 0;
      box-shadow: none;
      background: transparent;
    }

    .check-row {
      display: flex;
      align-items: center;
      gap: 8px;
      color: var(--muted);
      font-size: 12px;
    }

    .check-row input {
      width: 15px;
      height: 15px;
      margin: 0;
    }

    .status-line {
      min-height: 20px;
      color: var(--muted);
      font-size: 12px;
    }

    .status-line.error {
      color: #111111;
    }

    .status-line.ok {
      color: #111111;
    }

    .evidence-answer {
      min-height: 164px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fafafa;
      padding: 11px;
      overflow: auto;
      color: #333333;
    }

    .chunk {
      border-top: 1px solid var(--line);
      padding: 13px 14px;
    }

    .chunk:first-child { border-top: 0; }

    .chunk-head {
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 5px;
      font-weight: 600;
    }

    .chunk-text {
      margin: 0;
      color: #333333;
    }

    .empty {
      color: var(--muted);
      padding: 24px;
      text-align: center;
    }

    .chat-drawer {
      display: none;
      min-height: 0;
      background: var(--panel);
      border-left: 1px solid var(--line);
      border-right: 0;
      box-shadow: -1px 0 0 rgba(16, 24, 40, 0.02);
      transform: translateX(24px);
      opacity: 0;
      transition: transform 220ms ease, opacity 220ms ease;
      grid-template-rows: auto 1fr auto;
      max-height: 100vh;
    }

    body.chat-open .chat-drawer {
      display: grid;
    }

    body.chat-open .chat-drawer.open {
      transform: translateX(0);
      opacity: 1;
    }

    .chat-head {
      padding: 14px;
      border-bottom: 1px solid var(--line);
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 12px;
      background: var(--panel-soft);
    }

    .chat-head strong {
      display: block;
      font-size: 14px;
      line-height: 1.2;
      margin-bottom: 3px;
    }

    .chat-head span {
      color: var(--muted);
      font-size: 12px;
    }

    .chat-actions {
      display: flex;
      align-items: center;
      gap: 8px;
      flex: 0 0 auto;
    }

    .chat-thread-select {
      width: 100%;
      height: 32px;
      margin-top: 8px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      color: var(--text);
      font: inherit;
      font-size: 12px;
      padding: 0 8px;
    }

    .chat-new {
      height: 32px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #fff;
      color: var(--text);
      cursor: pointer;
      font: inherit;
      font-size: 12px;
      padding: 0 10px;
    }

    .icon-button {
      width: 32px;
      height: 32px;
      border-radius: 6px;
      border: 1px solid var(--line);
      background: #fff;
      cursor: pointer;
      font-size: 18px;
      line-height: 1;
    }

    .chat-messages {
      overflow: auto;
      min-height: 0;
      padding: 14px;
      background: #fff;
      overscroll-behavior: contain;
      scroll-behavior: auto;
    }

    .message {
      border: 0;
      border-radius: 0;
      background: #fff;
      padding: 8px 0;
      margin-bottom: 12px;
      box-shadow: none;
    }

    .message.user {
      background: #fff;
    }

    .message.streaming {
      border-color: transparent;
    }

    .message-label {
      color: var(--muted);
      font-size: 11px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      margin-bottom: 4px;
    }

    .message p {
      margin: 0;
      white-space: pre-wrap;
    }

    .message-content {
      color: #26313d;
    }

    .message-content h2 {
      margin: 14px 0 7px;
      font-size: 17px;
      line-height: 1.25;
    }

    .message-content h3 {
      margin: 12px 0 6px;
      font-size: 15px;
      line-height: 1.25;
    }

    .message-content h2:first-child,
    .message-content h3:first-child {
      margin-top: 0;
    }

    .message-content p {
      margin: 0 0 9px;
      white-space: normal;
    }

    .message-content ul,
    .message-content ol {
      margin: 6px 0 10px 20px;
      padding: 0;
    }

    .message-content li {
      margin-bottom: 5px;
    }

    .message-content strong {
      font-weight: 700;
    }

    .message-content .table-scroll {
      width: 100%;
      overflow-x: auto;
      margin: 10px 0 12px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
    }

    .message-content table {
      width: 100%;
      min-width: 520px;
      border-collapse: collapse;
      font-size: 13px;
      line-height: 1.45;
    }

    .message-content th,
    .message-content td {
      padding: 9px 10px;
      border-bottom: 1px solid var(--line);
      border-right: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
    }

    .message-content th:last-child,
    .message-content td:last-child {
      border-right: 0;
    }

    .message-content tr:last-child td {
      border-bottom: 0;
    }

    .message-content th {
      background: var(--panel-soft);
      color: #222222;
      font-weight: 700;
    }

    .stage-block {
      border: 1px solid var(--line);
      border-radius: 8px;
      background: #fff;
      margin-top: 10px;
      overflow: hidden;
    }

    .stage-block:first-child {
      margin-top: 0;
    }

    .stage-title {
      padding: 8px 10px;
      border-bottom: 1px solid var(--line);
      background: var(--panel-soft);
      color: #333333;
      font-weight: 700;
      font-size: 12px;
    }

    .stage-title.active {
      background: var(--accent-soft);
      color: var(--accent);
    }

    .stage-body {
      padding: 10px;
    }

    .message-content .cursor {
      display: inline-block;
      width: 7px;
      height: 1em;
      margin-left: 2px;
      vertical-align: -2px;
      background: var(--accent);
      animation: blink 900ms steps(1) infinite;
    }

    .confidence-wait {
      display: inline-flex;
      align-items: center;
      gap: 7px;
      margin: 8px 0 12px;
      padding: 7px 9px;
      border: 1px solid var(--accent-line);
      border-radius: 7px;
      background: var(--accent-soft);
      color: var(--accent);
      font-size: 12px;
      font-weight: 650;
    }

    .confidence-dot {
      width: 6px;
      height: 6px;
      border-radius: 999px;
      background: var(--accent);
      animation: pulse 900ms ease-in-out infinite;
    }

    @keyframes pulse {
      50% { opacity: 0.35; transform: scale(0.75); }
    }

    .source-list {
      margin-top: 10px;
      display: grid;
      gap: 8px;
    }

    .source-card {
      border: 1px solid var(--line);
      border-radius: 7px;
      background: #fafafa;
      padding: 9px;
    }

    .source-title {
      font-weight: 700;
      margin-bottom: 3px;
    }

    .source-meta {
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 6px;
    }

    .source-quote {
      margin: 0;
      padding-left: 9px;
      border-left: 3px solid var(--accent-line);
      color: #333333;
    }

    .source-relevance {
      margin: 7px 0 8px;
      color: #333333;
    }

    .source-relevance strong {
      font-weight: 700;
    }

    @keyframes blink {
      50% { opacity: 0; }
    }

    .chat-form {
      border-top: 1px solid var(--line);
      padding: 12px;
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 8px;
      background: var(--panel);
    }

    .chat-form input {
      height: 40px;
    }

    @media (max-width: 900px) {
      main { grid-template-columns: 1fr; }
      body.chat-open main { grid-template-columns: 1fr; }
      aside {
        border-right: 0;
        border-bottom: 1px solid var(--line);
        max-height: 45vh;
      }
      .chat-drawer {
        max-height: 55vh;
        border-left: 0;
        border-top: 1px solid var(--line);
      }
      .grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .evidence-grid { grid-template-columns: 1fr; }
      .title-row { flex-direction: column; }
      .title-actions { width: 100%; }
      button.primary { width: 100%; }
    }

    @media (max-width: 560px) {
      .detail { padding: 14px; }
      .grid { grid-template-columns: 1fr; }
      h1 { font-size: 21px; }
    }
  </style>
</head>
<body>
  <div class="app">
    <main>
      <section class="detail">
        <div class="detail-inner" id="detail"></div>
      </section>

    </main>
  </div>

  <script>
    const state = {
      memory: { provider: "unknown", status: "unknown", error: "" },
      view: "ask-ai",
    };

    const detail = document.getElementById("detail");
    function isChatNearBottom() {
      const messages = document.getElementById("askAiMessages");
      if (!messages) return true;
      return messages.scrollHeight - messages.scrollTop - messages.clientHeight < 80;
    }

    function scrollChatToBottom() {
      const messages = document.getElementById("askAiMessages");
      if (messages) messages.scrollTop = messages.scrollHeight;
    }

    function escapeHtml(value) {
      return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
    }

    function renderInlineMarkdown(value) {
      return escapeHtml(value)
        .replace(/\\*\\*(.+?)\\*\\*/g, "<strong>$1</strong>")
        .replace(/`(.+?)`/g, "<code>$1</code>");
    }

    function splitMarkdownTableRow(line) {
      let value = String(line || "").trim();
      if (!value.includes("|")) return [];
      if (value.startsWith("|")) value = value.slice(1);
      if (value.endsWith("|")) value = value.slice(0, -1);
      return value.split("|").map(cell => cell.trim());
    }

    function isMarkdownTableRow(line) {
      const cells = splitMarkdownTableRow(line);
      return cells.length >= 2 && cells.some(cell => cell.length > 0);
    }

    function isMarkdownTableSeparator(line) {
      const cells = splitMarkdownTableRow(line);
      return cells.length >= 2 && cells.every(cell => /^:?-{3,}:?$/.test(cell.replace(/\\s+/g, "")));
    }

    function renderMarkdownTable(headers, rows) {
      const head = headers.map(cell => `<th>${renderInlineMarkdown(cell)}</th>`).join("");
      const body = rows.map(row => {
        const cells = headers.map((_, index) => `<td>${renderInlineMarkdown(row[index] || "")}</td>`).join("");
        return `<tr>${cells}</tr>`;
      }).join("");
      return `<div class="table-scroll"><table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
    }

    function renderMarkdown(value) {
      const lines = String(value || "").split("\\n");
      const html = [];
      let listType = null;
      let inSources = false;
      let pendingSource = null;

      function closeList() {
        if (listType) {
          html.push(`</${listType}>`);
          listType = null;
        }
      }

      function closeSourcesBlock() {
        if (inSources) {
          html.push("</div>");
          inSources = false;
        }
      }

      function closeSource() {
        if (pendingSource) {
          html.push(`
            <div class="source-card">
              <div class="source-title">${renderInlineMarkdown(pendingSource.title)}</div>
              <div class="source-meta">${renderInlineMarkdown(pendingSource.meta.join(" · "))}</div>
              ${pendingSource.kind ? `<div class="source-meta">${renderInlineMarkdown(pendingSource.kind)}</div>` : ""}
              ${pendingSource.url ? `<div class="source-meta">${renderInlineMarkdown(pendingSource.url)}</div>` : ""}
              ${pendingSource.relevance ? `<p class="source-relevance"><strong>Why relevant:</strong> ${renderInlineMarkdown(pendingSource.relevance)}</p>` : ""}
              ${pendingSource.quote ? `<p class="source-quote">${renderInlineMarkdown(pendingSource.quote)}</p>` : ""}
            </div>
          `);
          pendingSource = null;
        }
      }

      for (let index = 0; index < lines.length; index += 1) {
        const line = lines[index];
        if (
          !inSources
          && isMarkdownTableRow(line)
          && index + 1 < lines.length
          && isMarkdownTableSeparator(lines[index + 1])
        ) {
          closeList();
          closeSource();
          closeSourcesBlock();
          const headers = splitMarkdownTableRow(line);
          const rows = [];
          index += 2;
          while (
            index < lines.length
            && isMarkdownTableRow(lines[index])
            && !isMarkdownTableSeparator(lines[index])
          ) {
            rows.push(splitMarkdownTableRow(lines[index]));
            index += 1;
          }
          index -= 1;
          html.push(renderMarkdownTable(headers, rows));
          continue;
        }

        if (/^###\\s+/.test(line)) {
          closeList();
          closeSource();
          closeSourcesBlock();
          const heading = line.replace(/^###\\s+/, "");
          html.push(`<h3>${renderInlineMarkdown(heading)}</h3>`);
          if (heading === "Sources Used") {
            html.push('<div class="source-list">');
            inSources = true;
          }
        } else if (/^##\\s+/.test(line)) {
          closeList();
          closeSource();
          closeSourcesBlock();
          const heading = line.replace(/^##\\s+/, "");
          html.push(`<h2>${renderInlineMarkdown(heading)}</h2>`);
          if (heading === "Sources Used") {
            html.push('<div class="source-list">');
            inSources = true;
          }
        } else if (/^[-*]\\s+/.test(line)) {
          if (inSources) continue;
          if (listType !== "ul") {
            closeList();
            html.push("<ul>");
            listType = "ul";
          }
          html.push(`<li>${renderInlineMarkdown(line.replace(/^[-*]\\s+/, ""))}</li>`);
        } else if (/^\\d+\\.\\s+/.test(line)) {
          if (inSources) {
            closeSource();
            const sourceLine = line.replace(/^\\d+\\.\\s+/, "");
            const [titlePart, ...metaParts] = sourceLine.split(" · ");
            pendingSource = {
              title: titlePart,
              meta: metaParts,
              url: "",
              kind: "",
              relevance: "",
              quote: "",
            };
            continue;
          }
          if (listType !== "ol") {
            closeList();
            html.push("<ol>");
            listType = "ol";
          }
          html.push(`<li>${renderInlineMarkdown(line.replace(/^\\d+\\.\\s+/, ""))}</li>`);
        } else if (inSources && /^Type:\\s+/.test(line)) {
          if (pendingSource) pendingSource.kind = line;
        } else if (inSources && /^(URL|Source ID):\\s+/.test(line)) {
          if (pendingSource) pendingSource.url = line;
        } else if (inSources && /^Why relevant:\\s+/.test(line)) {
          if (pendingSource) pendingSource.relevance = line.replace(/^Why relevant:\\s+/, "");
        } else if (inSources && /^Quote:\\s+/.test(line)) {
          if (pendingSource) pendingSource.quote = line.replace(/^Quote:\\s+/, "").replace(/^"|"$/g, "");
        } else if (line.trim()) {
          closeList();
          if (inSources) {
            if (pendingSource) {
              pendingSource.quote = [pendingSource.quote, line].filter(Boolean).join(" ");
            }
          } else {
            html.push(`<p>${renderInlineMarkdown(line)}</p>`);
          }
        } else {
          closeList();
          if (inSources) closeSource();
        }
      }
      closeList();
      closeSource();
      if (inSources) html.push("</div>");
      return html.join("");
    }

    function streamMarkdownIntoTarget(content, text, options = {}) {
      const charsPerTick = options.charsPerTick || 8;
      const delay = options.delay || 42;
      const onDone = options.onDone || (() => {});
      const scrollContainer = options.scrollContainer || null;
      let index = 0;
      const step = () => {
        const shouldFollow = scrollContainer
          ? scrollContainer.scrollHeight - scrollContainer.scrollTop - scrollContainer.clientHeight < 80
          : isChatNearBottom();
        index = Math.min(text.length, index + charsPerTick);
        content.innerHTML = renderMarkdown(text.slice(0, index)) + (index < text.length ? '<span class="cursor"></span>' : "");
        if (shouldFollow) {
          if (scrollContainer) {
            scrollContainer.scrollTop = scrollContainer.scrollHeight;
          } else {
            scrollChatToBottom();
          }
        }
        if (index < text.length) {
          window.setTimeout(step, delay);
        } else {
          onDone();
        }
      };
      step();
    }

    function createStage(container, title, isActive = false, options = {}) {
      const scrollContainer = options.scrollContainer || null;
      const block = document.createElement("div");
      block.className = "stage-block";
      block.innerHTML = `
        <div class="stage-title ${isActive ? "active" : ""}">${escapeHtml(title)}</div>
        <div class="stage-body"></div>
      `;
      container.appendChild(block);
      if (scrollContainer) {
        scrollContainer.scrollTop = scrollContainer.scrollHeight;
      } else if (isChatNearBottom()) {
        scrollChatToBottom();
      }
      return {
        block,
        titleNode: block.querySelector(".stage-title"),
        bodyNode: block.querySelector(".stage-body"),
      };
    }

    function splitAnswerSections(text) {
      const matches = [...text.matchAll(/^#{2,3}\\s+(.+)$/gm)];
      if (!matches.length) return [{ title: "Answer", text }];
      return matches.map((match, index) => {
        const start = match.index;
        const end = index + 1 < matches.length ? matches[index + 1].index : text.length;
        return {
          title: match[1].trim(),
          text: text.slice(start, end).trim(),
        };
      });
    }

    function streamAnswerInStages(node, text, onDone = () => {}, options = {}) {
      const scrollContainer = options.scrollContainer || null;
      const content = node.querySelector(".message-content");
      const sections = splitAnswerSections(text);
      const reasoning = sections.find(section => section.title === "Reasoning Process");
      const confidence = sections.find(section => section.title === "Confidence Check");
      const autoResearch = sections.find(section => section.title === "AutoResearch Reasoning");
      const remaining = sections.filter(section => !["Reasoning Process", "Confidence Check", "AutoResearch Reasoning"].includes(section.title));

      const withoutSectionHeading = section => section.text.replace(/^#{2,3}\\s+.+\\n?/, "").trim();

      if (!reasoning || !remaining.length) {
        streamMarkdownIntoTarget(node.querySelector(".message-content"), text, { scrollContainer, onDone });
        return;
      }

      node.classList.add("streaming");
      content.innerHTML = "";

      const reasoningStage = createStage(content, "1. Reasoning Process", true, { scrollContainer });
      streamMarkdownIntoTarget(reasoningStage.bodyNode, withoutSectionHeading(reasoning), {
        charsPerTick: 7,
        delay: 48,
        scrollContainer,
        onDone: () => {
          reasoningStage.titleNode.classList.remove("active");
          const confidenceStage = createStage(content, autoResearch ? "2. AutoResearch Reasoning" : "2. Confidence Check", true, { scrollContainer });
          const confidenceText = confidence
            ? withoutSectionHeading(confidence)
            : autoResearch
              ? withoutSectionHeading(autoResearch)
            : "### Confidence Check\\nThe retrieved sources have been checked. Showing the answer now.";
          streamMarkdownIntoTarget(confidenceStage.bodyNode, confidenceText, {
            charsPerTick: 7,
            delay: 48,
            scrollContainer,
            onDone: () => {
              confidenceStage.titleNode.classList.remove("active");
              const waitingStage = createStage(content, "3. Answer", true, { scrollContainer });
              waitingStage.bodyNode.innerHTML = '<div class="confidence-wait"><span class="confidence-dot"></span> Preparing answer...</div>';
              if (scrollContainer) scrollContainer.scrollTop = scrollContainer.scrollHeight;
              window.setTimeout(() => {
                streamMarkdownIntoTarget(waitingStage.bodyNode, remaining.map(withoutSectionHeading).join("\\n\\n"), {
                  charsPerTick: 8,
                  delay: 44,
                  scrollContainer,
                  onDone: () => {
                    waitingStage.titleNode.classList.remove("active");
                    node.classList.remove("streaming");
                    onDone();
                  },
                });
              }, 700);
            },
          });
        },
      });
    }

    function sourceList(sources) {
      if (!sources || !sources.length) return "";
      return "\\n\\n### Sources Used\\n" + sources.map((source, index) => {
        const section = source.section_number ? `section ${source.section_number}` : "section not available";
        const heading = source.section_heading ? ` - ${source.section_heading}` : "";
        const score = typeof source.score === "number" ? ` · score ${source.score}` : "";
        const identifierLabel = /^https?:\\/\\//i.test(source.identifier || "") ? "URL" : "Source ID";
        const identifier = source.identifier ? `\\n${identifierLabel}: ${source.identifier}` : "";
        const kind = source.kind ? `\\nType: ${source.kind}` : "";
        const relevance = source.relevance ? `\\nWhy relevant: ${source.relevance}` : "";
        const quote = source.quote ? `\\nQuote: \"${source.quote}\"` : "";
        return `${index + 1}. ${source.title}, ${section}${heading}${score}${kind}${identifier}${relevance}${quote}`;
      }).join("\\n\\n");
    }

    function renderWorkspaceTabs() {
      return "";
    }

    function wireWorkspaceTabs() {
    }

    function renderDetail() {
      renderAskAI();
    }

    function fileToBase64(file) {
      return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => {
          const value = String(reader.result || "");
          resolve(value.includes(",") ? value.split(",")[1] : value);
        };
        reader.onerror = () => reject(reader.error || new Error("Could not read file"));
        reader.readAsDataURL(file);
      });
    }

    function renderAskAI() {
      detail.innerHTML = `
        ${renderWorkspaceTabs()}
        <div class="ask-ai-shell chat-style">
          <div class="ask-ai-topbar">
            <div>
              <h1>Ask AI</h1>
            </div>
            <div class="ask-ai-topbar-actions">
              <span class="auto-workflow-pill" id="askAiWorkflow">Auto workflow</span>
            </div>
          </div>

          <div class="ask-ai-messages" id="askAiMessages">
            <div class="ask-ai-message assistant">
              <div class="message-label">Ask AI</div>
              <div class="ask-ai-bubble message-content">What can I help you with?</div>
            </div>
          </div>

          <div class="ask-ai-composer">
            <textarea id="askAiQuestion" placeholder="Message Ask AI..."></textarea>
            <div class="ask-ai-composer-actions">
              <div class="ask-ai-upload-inline">
                <input id="askAiFile" type="file" accept=".pdf,.txt,.md,.json,.xml,.html,.htm,.csv,.png,.jpg,.jpeg,.webp,.bmp,.tif,.tiff,.mp3,.wav,.m4a,.aac,.flac,.ogg,.mp4,.mov,.mkv,.avi,.webm" />
                <button class="secondary" id="askAiUpload" type="button">Upload To Memory</button>
              </div>
              <button class="primary" id="askAiSubmit" type="button">Send</button>
            </div>
            <div class="status-line" id="askAiStatus">Ready.</div>
          </div>
        </div>
      `;
      wireWorkspaceTabs();
      wireAskAIControls();
    }

    function setAskAIStatus(message, kind = "") {
      const status = document.getElementById("askAiStatus");
      if (!status) return;
      status.className = `status-line ${kind}`;
      status.textContent = message;
    }

    function appendAskAIMessage(role, markdown) {
      const messages = document.getElementById("askAiMessages");
      if (!messages) return null;
      const node = document.createElement("div");
      node.className = `ask-ai-message ${role === "user" ? "user" : "assistant"}`;
      node.innerHTML = `
        <div class="message-label">${role === "user" ? "You" : "Ask AI"}</div>
        <div class="ask-ai-bubble message-content">${role === "user" ? escapeHtml(markdown) : renderMarkdown(markdown)}</div>
      `;
      messages.appendChild(node);
      messages.scrollTop = messages.scrollHeight;
      return node;
    }

    function updateAskAIMessage(node, markdown) {
      if (!node) return;
      const content = node.querySelector(".message-content");
      if (!content) return;
      content.innerHTML = renderMarkdown(markdown);
      const messages = document.getElementById("askAiMessages");
      if (messages) messages.scrollTop = messages.scrollHeight;
    }

    function streamAskAIMessage(node, markdown, onDone = () => {}) {
      if (!node) return;
      const messages = document.getElementById("askAiMessages");
      streamAnswerInStages(node, markdown, onDone, {
        scrollContainer: messages,
      });
    }

    function wireAskAIControls() {
      const askButton = document.getElementById("askAiSubmit");
      const uploadButton = document.getElementById("askAiUpload");
      const questionInput = document.getElementById("askAiQuestion");
      const workflowNode = document.getElementById("askAiWorkflow");
      const fileInput = document.getElementById("askAiFile");

      questionInput.addEventListener("keydown", event => {
        if (event.key === "Enter" && !event.shiftKey) {
          event.preventDefault();
          askButton.click();
        }
      });

      askButton.addEventListener("click", async () => {
        const question = questionInput.value.trim();
        if (!question) {
          setAskAIStatus("Ask AI needs a question first.", "error");
          return;
        }
        appendAskAIMessage("user", question);
        questionInput.value = "";
        const pending = appendAskAIMessage("assistant", "### Working\\nThinking with the selected model...");
        if (workflowNode) workflowNode.textContent = "Detecting workflow...";
        setAskAIStatus("Detecting the best legal workflow...");
        try {
          const response = await fetch("/api/ask-ai", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ question }),
          });
          const payload = await response.json();
          if (!response.ok || payload.error) throw new Error(payload.error || "Ask AI failed");
          if (workflowNode) workflowNode.textContent = payload.workflow_label ? `Auto: ${payload.workflow_label}` : "Auto workflow";
          const finalAnswer = `${payload.answer || "No answer returned."}${sourceList(payload.sources)}`;
          streamAskAIMessage(pending, finalAnswer, () => {
            const workflow = payload.workflow_label ? ` Detected: ${payload.workflow_label}.` : "";
            setAskAIStatus(`Answered with ${payload.model}; embeddings: ${payload.embedding_model}.${workflow}${autoImproveNote(payload.auto_improve)}`, "ok");
          });
        } catch (error) {
          if (workflowNode) workflowNode.textContent = "Auto workflow";
          updateAskAIMessage(pending, `### Request Failed\\n${error.message}`);
          setAskAIStatus(error.message, "error");
        }
      });

      uploadButton.addEventListener("click", async () => {
        const file = fileInput.files && fileInput.files[0];
        if (!file) {
          setAskAIStatus("Choose a file to upload first.", "error");
          return;
        }
        setAskAIStatus(`Uploading ${file.name} into Ask AI memory...`);
        try {
          const contentBase64 = await fileToBase64(file);
          const response = await fetch("/api/ask-ai/upload", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ filename: file.name, content_base64: contentBase64 }),
          });
          const payload = await response.json();
          if (!response.ok || payload.error) throw new Error(payload.error || "Upload failed");
          const chunks = payload.record.chunk_count || 0;
          const omni = payload.record.omni ? " SimpleMem omni memory updated." : "";
          const textNote = payload.record.text_index_error ? " Text retrieval index skipped." : "";
          setAskAIStatus(`Uploaded ${payload.record.filename}: ${chunks} retrieval chunks.${omni}${textNote}${autoImproveNote(payload.record.auto_improve)}`, "ok");
        } catch (error) {
          setAskAIStatus(error.message, "error");
        }
      });

    }

    function autoImproveNote(status) {
      if (!status || status.enabled === false) return "";
      if (status.status === "running") return " Auto-improve is running in the background.";
      if (status.last_completed_at && status.last_ok === true) return " Auto-improve config is active.";
      return "";
    }

    function render() {
      renderDetail();
    }

    async function init() {
      const memoryResponse = await fetch("/api/ask-ai/status");
      state.memory = memoryResponse.ok ? await memoryResponse.json() : state.memory;
      render();
    }

    init().catch(error => {
      detail.innerHTML = `<div class="empty">Could not load Ask AI: ${escapeHtml(error.message)}</div>`;
    });
  </script>
</body>
</html>
"""


class AskAIHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/ask-ai":
            self.handle_ask_ai()
            return
        if parsed.path == "/api/ask-ai/upload":
            self.handle_ask_ai_upload()
            return
        if parsed.path == "/api/ask-ai/autoresearch":
            self.handle_ask_ai_autoresearch()
            return
        if parsed.path == "/api/multimodal/ingest":
            self.handle_multimodal_ingest()
            return
        if parsed.path == "/api/multimodal/ask":
            self.handle_multimodal_ask()
            return
        self.send_json({"error": "Not found"}, status=404)

    def read_json_body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def handle_ask_ai(self) -> None:
        try:
            payload = self.read_json_body()
            question = str(payload.get("question", "")).strip()
            mode = str(payload.get("mode", "auto")).strip()
            if not question:
                self.send_json({"error": "Question is required"}, status=400)
                return
            self.send_json(get_ask_ai().ask(question, mode))
        except Exception as error:
            self.send_json({"error": str(error)}, status=500)

    def handle_ask_ai_upload(self) -> None:
        try:
            payload = self.read_json_body()
            filename = str(payload.get("filename", "ask-ai-upload.txt"))
            content_base64 = str(payload.get("content_base64", ""))
            if not content_base64:
                self.send_json({"error": "File content is required"}, status=400)
                return
            ASK_AI_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
            upload_path = unique_upload_path(ASK_AI_UPLOAD_DIR, filename)
            upload_path.write_bytes(base64.b64decode(content_base64))
            record: dict[str, object]
            try:
                record = get_ask_ai().ingest_file(upload_path)
            except Exception as text_error:
                record = {
                    "filename": upload_path.name,
                    "path": str(upload_path),
                    "chunk_count": 0,
                    "text_index_error": str(text_error),
                }
            try:
                args = SimpleNamespace(
                    chunk_chars=3500,
                    max_pages=None,
                    render_pdf_pages=True,
                    pdf_dpi=144,
                    max_video_frames=20,
                )
                record["omni"] = ingest_path(get_omni_memory(), upload_path, args)
            except Exception as omni_error:
                record["omni_error"] = str(omni_error)
            self.send_json({"ok": True, "record": record})
        except Exception as error:
            self.send_json({"error": str(error)}, status=500)

    def handle_ask_ai_autoresearch(self) -> None:
        try:
            self.send_json(get_ask_ai().run_autoresearch())
        except Exception as error:
            self.send_json({"error": str(error)}, status=500)

    def handle_multimodal_ingest(self) -> None:
        try:
            payload = self.read_json_body()
            filename = Path(str(payload.get("filename", "upload.bin"))).name
            content_base64 = str(payload.get("content_base64", ""))
            if not content_base64:
                self.send_json({"error": "File content is required"}, status=400)
                return
            MULTIMODAL_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
            upload_path = MULTIMODAL_UPLOAD_DIR / filename
            upload_path.write_bytes(base64.b64decode(content_base64))
            args = SimpleNamespace(
                chunk_chars=3500,
                max_pages=None,
                render_pdf_pages=bool(payload.get("render_pdf_pages", True)),
                pdf_dpi=144,
                max_video_frames=20,
            )
            record = ingest_path(get_omni_memory(), upload_path, args)
            self.send_json({"ok": True, "record": record})
        except Exception as error:
            self.send_json({"error": str(error)}, status=500)

    def handle_multimodal_ask(self) -> None:
        try:
            payload = self.read_json_body()
            question = str(payload.get("question", "")).strip()
            if not question:
                self.send_json({"error": "Question is required"}, status=400)
                return
            answer = get_omni_memory().answer(
                question,
                top_k=int(payload.get("top_k", 8)),
                include_sources=True,
                include_on_demand_images=True,
            )
            strip_base64(answer)
            self.send_json(answer)
        except Exception as error:
            self.send_json({"error": str(error)}, status=500)

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/":
            self.send_bytes(HTML.encode("utf-8"), "text/html; charset=utf-8")
            return

        if parsed.path == "/api/ask-ai/status":
            ask_ai = get_ask_ai()
            self.send_json(
                {
                    "model": ask_ai.chat_model,
                    "embedding_model": ask_ai.embedding_model,
                    "documents": len(ask_ai.documents),
                    "memory": ask_ai.memory.status_payload(),
                    "auto_improve": ask_ai.auto_improve_status(),
                }
            )
            return

        if parsed.path == "/api/ask-ai/simplemem/status":
            self.send_json(get_ask_ai().simplemem_status())
            return

        if parsed.path == "/api/multimodal/status":
            self.send_json({"provider": "simplemem-omni", "status": "configured"})
            return

        self.send_json({"error": "Not found"}, status=404)

    def send_json(self, payload: object, status: int = 200) -> None:
        self.send_bytes(json.dumps(payload).encode("utf-8"), "application/json; charset=utf-8", status)

    def send_bytes(self, payload: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: object) -> None:
        print(f"{self.address_string()} - {format % args}")


def get_omni_memory():
    global OMNI_MEMORY
    if OMNI_MEMORY is None:
        OMNI_MEMORY = make_omni_memory(MULTIMODAL_DATA_DIR)
    return OMNI_MEMORY


def get_ask_ai() -> AskAIEngine:
    global ASK_AI
    if ASK_AI is None:
        ASK_AI = AskAIEngine([])
    return ASK_AI


def strip_base64(answer: object) -> None:
    if not isinstance(answer, dict):
        return
    for item in answer.get("retrieval_result", {}).get("items", []):
        raw = item.get("raw_content")
        if isinstance(raw, dict) and raw.get("base64"):
            raw["base64"] = f"<{len(raw['base64'])} base64 chars hidden>"


def safe_filename(filename: str) -> str:
    original = Path(filename).name
    suffix = Path(original).suffix.lower() or ".txt"
    stem = Path(original).stem
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip("-._")
    return f"{stem or 'upload'}{suffix}"


def unique_upload_path(directory: Path, filename: str) -> Path:
    cleaned = safe_filename(filename)
    candidate = directory / cleaned
    if not candidate.exists():
        return candidate
    stem = candidate.stem
    suffix = candidate.suffix
    index = 2
    while True:
        candidate = directory / f"{stem}-{index}{suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def main() -> int:
    global ASK_AI
    import argparse

    parser = argparse.ArgumentParser(description="Run the Legal AI Ask AI app.")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()

    ASK_AI = AskAIEngine([])

    server = ThreadingHTTPServer(("127.0.0.1", args.port), AskAIHandler)
    print(f"Legal AI Ask AI running at http://127.0.0.1:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
