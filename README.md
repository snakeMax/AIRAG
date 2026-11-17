<p align="center"><img src="assets/icon-512.png" width="120" alt="AIRAG"></p>

<h1 align="center">AIRAG</h1>
<p align="center"><b>AI Research Article Generation</b><br>A search engine that reads the pages for you, and writes the article when nobody else has.</p>
<p align="center"><sub>Built with the assistance of Claude Code.</sub></p>

---

You type a search like you would on Google. AIRAG searches the web (and optionally your own notes), reads the pages, rates every source for relevance and reliability, and then picks the most useful way to answer:

| What it finds | What you get |
|---|---|
| A page that answers the question directly and thoroughly | **Ranked results** with short summaries, key findings and reliability ratings |
| Only scattered bits (a figure mentioned in passing in a forum post, a case report, a study on a related topic) | **A new article** that pulls the pieces together, explains how they relate and cites every claim |
| Nothing usable | **Better searches** to try instead |

Other features:

- **Summarize** any article, result list or single source, focused on what you searched for.
- **Interactive explainers**: for articles where it helps (physics, statistics, how things work...), AIRAG can generate a small simulation you can play with. It runs sandboxed, with no network access.
- **Library ("Retrieve & Get")**: add your own folders (Obsidian vaults, PDFs, Word documents, notes) and tick *My library* to include them in searches. Indexed locally with SQLite full-text search.
- **Local or cloud AI**: Ollama (detected, started with one click, with a model picker and downloader), Anthropic Claude, OpenAI, DeepSeek, or any OpenAI-compatible server (LM Studio, vLLM, OpenRouter...).
- **Search engines**: DuckDuckGo (no key), Brave, Google Programmable Search, or your own SearXNG.
- **Desktop window or browser tab + tray icon**, chosen during install and switchable in Settings.
- **9 interface languages** (English, Norsk, Svenska, Dansk, Deutsch, Français, Español, 日本語, 简体中文); answers in 20+ languages.
- **Themes**: light/dark, four gray palettes and any accent colour.
- **Custom prompts**: writing style, length, your own instructions, or a fully replaced article prompt (safety rules always stay on).
- **Automatic updates** from GitHub Releases.

## Install (Windows 10/11)

1. Download **`AIRAG-Setup-x.y.z.exe`** from the [latest release](https://github.com/snakeMax/AIRAG/releases/latest).
2. Run it. No administrator rights needed. Pick *Desktop window* (default) or *Browser + tray icon*.
3. On first start, choose your AI:
   - **Local**: install [Ollama](https://ollama.com/download), then start it from AIRAG's setup screen and download a recommended model for your PC.
   - **Cloud**: paste an API key from [Anthropic](https://console.anthropic.com/settings/keys), [OpenAI](https://platform.openai.com/api-keys) or [DeepSeek](https://platform.deepseek.com/api_keys).

> **"Windows protected your PC"?** The installer isn't code-signed yet, so SmartScreen may warn you the first time. Click *More info → Run anyway*. You can verify the download against the `.sha256` file attached to each release.

A **portable zip** is attached to each release as well: unzip anywhere and run `AIRAG.exe`; settings are kept in a `data` folder next to it.

The desktop window uses Microsoft Edge WebView2, which is part of Windows 10/11. If it's missing, AIRAG falls back to browser mode automatically.

## Privacy

- Settings and history: `%APPDATA%\AIRAG`. Library index, optional browser and logs: `%LOCALAPPDATA%\AIRAG`.
- API keys are stored only in your own `settings.json` and are never shown in full again in the app.
- AIRAG talks to: the search engine you picked, the web pages it reads, and the AI provider you picked. Library files never leave your PC except for short excerpts sent to your AI model (none at all if you use Ollama).
- Uninstalling asks whether to delete your data as well.

## Run from source

```bash
git clone https://github.com/snakeMax/AIRAG.git
cd AIRAG
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python -m airag                   # --mode desktop | browser | server, --port N
```

Or just run `run.bat` / `run.sh`. Source and installed versions share the same data folders.

## Build and release

```bash
build.bat                          # local build: dist/AIRAG-Setup-x.y.z.exe + portable zip (needs Inno Setup 6)
python tools/release.py 0.3.0      # bump version, tag, push -> GitHub Actions builds and publishes
```

The release workflow (`.github/workflows/release.yml`) runs the tests, builds the app with PyInstaller, packages it with Inno Setup, and attaches the installer, portable zip and checksums to a GitHub release. Installed copies notice the new version on their next start and offer a one-click update.

## Project layout

```
airag/
  __main__.py        command line (also the packaged app's entry point)
  desktop.py         window / tray launcher, single instance, free port, restart
  main.py            HTTP API
  pipeline.py        the research agent: plan -> search rounds -> results / article / suggestions
  prompts.py         every prompt the agent uses
  config.py          settings and their schema (the Settings UI is generated from it)
  llm/               AI providers (ollama, anthropic, openai-compatible)
  search/            search backends (duckduckgo, brave, google_cse, searxng)
  fetch.py           page reading (HTTP, headless browser, PDF)
  library.py         local library index (SQLite FTS5)
  summarize.py       Summarize button
  interactive.py     interactive explainers
  ollama_manager.py  find/start Ollama, list and download models
  browser_install.py optional Playwright/Chromium download
  updater.py         GitHub release check and self-update
  paths.py           where files are stored
web/                 the interface (plain ES modules, no build step) and translations
packaging/           PyInstaller spec and Inno Setup script
tools/               build, release and secret-scan scripts
tests/               pytest suite with a fake AI and search engine
```

## Extending

- **AI provider**: subclass `LLMProvider` in `airag/llm/`, decorate it with `@register`, import it in `airag/llm/__init__.py`. Its `fields` show up in Settings automatically.
- **Search backend**: same pattern in `airag/search/`.
- **Translation**: copy `web/i18n/en.json` to `<code>.json`, translate the values, set `ui=True` for the language in `airag/languages.py`. Missing keys fall back to English.
- **Behaviour**: prompts are in `prompts.py`; thresholds and limits are in Settings → Research; each pipeline stage is a method on `Research`.
- **Try the UI without an AI**: `python -m tests.mock` starts AIRAG on port 8799 with a fake model and search engine.

## Disclaimer

Articles and summaries are written by AI from web pages and your own files. They can contain mistakes: check the cited sources before relying on anything important. AIRAG doesn't give medical, legal or financial advice.

## License

[MIT](LICENSE) © snakeMax
