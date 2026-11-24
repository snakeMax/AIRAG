<p align="center"><img src="assets/icon-512.png" width="120" alt="AIRAG"></p>

<h1 align="center">AIRAG</h1>
<p align="center"><b>AI Research Article Generation</b><br>An open-source agentic research harness for intelligence gathering: it searches the web and your own files, weighs every source, and turns scattered information into one cited, readable article, with local models through Ollama or the AI services you already use, without burning through your tokens.</p>
<p align="center"><sub>Built with the assistance of Claude Code.</sub></p>

> **Quick install (Windows 10/11)**
> 1. Download **`AIRAG-Setup-x.y.z.exe`** from the [latest release](https://github.com/snakeMax/AIRAG/releases/latest).
> 2. Run it and follow the steps. No admin rights needed; you can pick any install folder.
> 3. If Windows warns you, see [Windows Defender / SmartScreen warnings](#windows-defender--smartscreen-warnings) below.
>
> **Android:** download **`AIRAG-x.y.z.apk`** from the same release on your phone and open it (see [Install (Android)](#install-android)).

---

You type a search like you would on Google. AIRAG searches the web (and optionally your own notes), reads the pages, rates every source for relevance and reliability, and then picks the most useful way to answer:

| What it finds | What you get |
|---|---|
| A page that answers the question directly and thoroughly | **Ranked results** with short summaries, key findings and reliability ratings |
| Only scattered bits (a figure mentioned in passing in a forum post, a case report, a study on a related topic) | **A new article** that pulls the pieces together, explains how they relate and cites every claim |
| Nothing usable | **Better searches** to try instead |

## Features

- **Answers, not just links**: shows the best pages when one answers your question, writes a cited article when the answer is scattered across many pages, or suggests better searches when nothing useful turns up.
- **Source ratings**: every source gets a relevance, coverage and reliability rating, with the key findings quoted.
- **Quick search**: a short cited answer from a few pages in seconds; on an article it can add the answer as a new section.
- **Summarize** any article, result list or single source, focused on what you searched for.
- **Interactive explainers**: for articles where it helps (physics, statistics, how things work...), AIRAG can generate a small simulation you can play with. It runs sandboxed, with no network access.
- **Library ("Retrieve & Get")**: add your own folders (Obsidian vaults, PDFs, Word documents, notes) and tick *My library* to include them in searches. Indexed locally.
- **My library and saving**: save articles as Markdown with their sources (optionally with pictures and the interactive explainer), save light text copies of source pages, and reopen saved articles without the AI.
- **Background searches**: searches keep going when you leave the page, queue up behind each other, and can be cancelled from the page or from History.
- **Search again, date ranges and translation**: rerun a search building on what it found before, limit results to a period of time, and translate articles or results with AI.
- **Android app**, and **Share with my phone** to use your PC's Ollama models from the phone over your home Wi-Fi.
- **Check & repair** and a **log viewer** in Settings for when something goes wrong.
- **Local or cloud AI**: Ollama (with a model picker and downloader), Anthropic Claude, OpenAI, DeepSeek, or any OpenAI-compatible server (LM Studio, vLLM, OpenRouter...).
- **Search engines**: DuckDuckGo (no key needed), Brave, Google Programmable Search, or your own SearXNG.
- **Desktop window or browser tab + tray icon**, chosen during install and switchable in Settings.
- **9 interface languages** (English, Norsk, Svenska, Dansk, Deutsch, Français, Español, 日本語, 简体中文); answers in 20+ languages.
- **Themes and text**: light/dark, four gray palettes, any accent colour, interface and article fonts (including an easy-reading font) and five text sizes.
- **Models per task** (Claude): a cheaper or stronger model for each kind of work.
- **Snap panels**: drag the Answers panel and Calculator into place; minimize them to a tray.
- **Custom prompts**: writing style, length, your own instructions, or a fully replaced article prompt (safety rules always stay on).
- **Automatic updates** from GitHub Releases, on Windows and Android.

## Settings guide

Everything works out of the box. **[SETTINGS.md](SETTINGS.md)** explains every setting and button, grouped by what it does (searching, tools, AI model, usage and budget, search engine and wikis, blocked and favourite sites, how hard each search works, reading pages and videos, My library, writing style, look, sound, speech, saving and exporting, app and updates, background work), with what each change costs and recommended setups:

| Goal | Change these |
|---|---|
| **Cheapest** | Mode *Results*, Pictures & explainer off, a small model (Claude Haiku, `openrouter/auto`), fewer pages read. |
| **Best quality** | Mode *Auto*, a strong model, more search rounds and pages, wikis on, favourite sites for your field. |
| **Offline / private** | Ollama on your PC, *My library* ticked, *Also search the web* off. |
| **Phone** | The defaults; allow background running when asked. |

## Updates

Newest first. Full technical details are in [CHANGELOG.md](CHANGELOG.md).

### 0.4.2 (24 Nov 2026)
Quick search: a short answer with sources in seconds, for far fewer tokens (Quick button or Shift+Enter; from an article it can add the answer as a new section). Settings are now 7 tabs with sections and a search box. Pick a Claude model per kind of work, choose the interface and article font (including an easy-reading font) and the text size, and turn on live graphs of processor, memory and AI use. The Answers panel and Calculator can be dragged, snapped into place and minimized. Share text or a link to AIRAG on Android to search it, and links in your question are read first.
Safety: AIRAG never reads pages on your own computer or home network unless you allow it, other websites can't use AIRAG or show it in a frame, and phone links only open web and mail links.

### 0.4.1 (19 Nov 2026)
Much better at finding information, especially for medical and scientific questions: bot-check pages are recognised, research papers on blocked sites are read through Europe PMC, unreadable pages are replaced by others, and sources count when they answer any part of your question. Open Word, PowerPoint, Excel, OpenDocument, RTF, CSV, JSON and SQLite files, or any saved article or exported page, without the AI. Article tools are grouped into menus; Regenerate an article your way with version history (Undo, Compare, Restore). A Save dialog with tags (and Suggest tags) and translations to keep, a language switcher, Unsave with a Saved articles window and Recently removed. Offline mode answers from your own files, with a local model or your usual one. Guarded execution keeps running tasks safe while you change settings, and every AI tool runs in the background.
Fixes: read aloud resumes where you paused, the selection menu on phones stays put and docks away from your text, safer interactive explainers, delete buttons are visible on phones, and long messages no longer squeeze into a circle.

### 0.4.0 (18 Nov 2026)
A research toolbar on every article: ask follow-up questions (typed or spoken) with answers in a side panel, compare, timeline, fact-check, rewrite a paragraph with a side-by-side preview, calculate formulas exactly, and cite sources as APA, MLA or BibTeX. Select any text for quick actions, and the AI can use tools like a calculator and web search while it answers. Analyze pictures and screenshots with vision models (share them to AIRAG on Android). A Usage tab with budget, dollars or tokens, and Quality-or-saving modes. Searches and explainers keep running in the background with notifications, plus sound effects, read aloud, pinned articles and sources, exporting to a web page, Wikipedia and your own wikis, YouTube videos as sources, and explainers that can chart the data in an article.
Fixes: sound effects play on all devices, the search spinner stops when a search engine stops answering, and selected text is kept on phones.

### 0.3.0 (18 Nov 2026)
The Android app, My library with saving and reopening articles, background searches with a queue and Cancel, Search again, date ranges, translation with AI, sharing your PC's Ollama with your phone, a microphone button, an update popup, backups, hardware info and Check & repair. Settings got Defaults and System tabs. Better protection against web pages that try to trick the AI, and fewer AI calls per search.
Fixes: summaries now use your search language, DuckDuckGo failures retry, the interactive explainer no longer opens blank, phone screens no longer overflow, and the app no longer shows old screens after updating.

### 0.2.0 (17 Nov 2026)
First public release: Windows installer, research agent with results/articles/suggestions, summaries, interactive explainers, local library, Ollama and cloud AI support, 9 languages, themes and automatic updates.

## Install (Windows 10/11)

1. Download **`AIRAG-Setup-x.y.z.exe`** from the [latest release](https://github.com/snakeMax/AIRAG/releases/latest).
2. Run it. No administrator rights needed. Pick *Desktop window* (default) or *Browser + tray icon*.
3. On first start, choose your AI:
   - **Local**: install [Ollama](https://ollama.com/download), then start it from AIRAG's setup screen and download a recommended model for your PC.
   - **Cloud**: paste an API key from [Anthropic](https://console.anthropic.com/settings/keys), [OpenAI](https://platform.openai.com/api-keys) or [DeepSeek](https://platform.deepseek.com/api_keys).

## Install (Android)

1. On your phone, open the [latest release](https://github.com/snakeMax/AIRAG/releases/latest) and download **`AIRAG-x.y.z.apk`**.
2. Open the file. Android asks you to allow your browser (or file app) to install apps; allow it once.
3. Open AIRAG and add an API key, or connect to your PC's Ollama: on the PC open *Settings → AI model → Share with my phone*, then on the phone pick *My PC (Ollama)* and paste the address and pairing code. This works on the same Wi-Fi network.

Updates: AIRAG checks GitHub when it starts and offers new versions; Android asks you to confirm the install.

### Windows Defender / SmartScreen warnings

AIRAG is a new, open-source app without a paid code-signing certificate, so Windows may be cautious about it:

- **"Windows protected your PC" (SmartScreen):** click **More info → Run anyway**. This appears because the installer is new and unsigned, not because anything was found in it.
- **Defender quarantines or blocks the file:** apps packaged with PyInstaller are sometimes falsely flagged. Open *Windows Security → Virus & threat protection → Protection history*, select the AIRAG item and choose **Allow** / **Restore**. Please also [report the false positive to Microsoft](https://www.microsoft.com/wdsi/filesubmission) so it gets fixed for everyone.
- **Want to be sure the file is genuine?** Every release has a `.sha256` file. In PowerShell run `Get-FileHash .\AIRAG-Setup-x.y.z.exe` and compare the hash. All releases are built from this repository's source code by GitHub Actions, and you can see the build log for each one under the *Actions* tab.

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
python tools/release.py 0.3.0      # bump version and push -> GitHub Actions builds and publishes v0.3.0
```

When the version in `airag/__init__.py` changes on `main`, the release workflow (`.github/workflows/release.yml`) runs the tests, builds the app with PyInstaller, packages it with Inno Setup, and attaches the installer, portable zip and checksums to a GitHub release. Installed copies notice the new version on their next start and offer a one-click update.

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
