# Changelog

## [0.3.0] - unreleased

First release with the Android app (same version, same release as the Windows installer).

- **Android app**: the full AIRAG on your phone, with a layout that fits phone screens, Obsidian vaults and any folder as library sources, light defaults to save battery and data, and updates from GitHub Releases (asks for the "install apps" permission when needed)
- **Share with my phone**: use the Ollama models on your PC from the phone app over your home Wi-Fi, protected by a pairing code
- **My library**: your own folder (any drive) for saved articles and files; always searched with *My library* ticked; add files by copying or moving them
- **Save** articles as Markdown with their sources (optionally with pictures and the interactive explainer), **Save page** on every source for a light text copy, and a **Saved articles** list that opens them without the AI
- **Search again** on any search, also using the sources it found before (the old search stays in history); failed searches are kept so they can be retried
- **Write an article** from a results page now uses the sources already found instead of searching again
- **Date range filter** before and after searching, with past week/month/year shortcuts; pages outside the range are left out
- **Translate with AI** for articles and results, with *Show original*
- **Check & repair** in Settings: checks program files, settings, the library index and saved searches, fixes them, or reinstalls the current version
- **Settings reorganized** with tooltips on every tab, a new **Defaults** tab (search mode, My library, pictures & explainer, time range, translation language, saving with pictures) and a new **System** tab (this device's hardware, updates, check & repair, storage, cache, backups and logs)
- **Update popup** when a new version is out (Update now / Later / Skip this version)
- **Microphone button** to speak your search (Android and browsers)
- **Hardware info** for your PC (processor, memory, graphics card and its memory) and phone; Ollama suggestions use your graphics memory
- **Backups**: export and import settings and history (API keys only if you choose)
- **Pictures & explainer** switch by the search bar: turn it off to save tokens; models that can see images pick the article pictures
- **Interactive explainer detail**: simple, medium or detailed
- **License** in plain words in Settings → About
- **Log viewer** (keys and codes hidden) and the local port in Settings
- Security: text from web pages and files that tries to instruct the AI is removed and flagged, data sent to the AI is fenced with random markers, secrets are redacted, links in AI text only point to real sources, the local API only accepts AIRAG's own page, and the library never reads AIRAG's own folders or likely secret files
- AIRAG now knows today's date and time, and prefers recent pages for news and "latest" questions
- Fewer AI calls and tokens per search (copies of the same article are read once, off-topic pages get a short read)
- Longer default article limit (8192 tokens), so long articles from reasoning models aren't cut off

Bug fixes:
- Summaries are written in the language of your question, not of the page
- DuckDuckGo searches that failed now retry and fall back to other ways of searching
- The interactive explainer no longer opens blank in some browsers
- On narrow screens the top bar, tooltips and the page width no longer overflow
- The *My library* tickbox is always visible
- After an update the app no longer keeps showing the previous version's screens
- The phone app uses your own time zone, and dates follow your device's format

## [0.2.0] - 2026-11-17

First public release.

- Windows installer with a choice between desktop window and browser tab + tray icon, optional headless browser download, start with Windows, and automatic updates from GitHub Releases
- Research agent: direct searches, related/indirect searches and gap-filling rounds; shows ranked results, writes a cited article, or suggests better searches
- Summarize button for articles, result lists and individual sources
- Interactive explainers (sandboxed simulations) for articles where they help
- Library ("Retrieve & Get"): search your own folders, Obsidian vaults, PDFs and documents
- Ollama: detection, one-click start, model picker with recommendations for your PC, one-click downloads
- Anthropic Claude, OpenAI, DeepSeek and OpenAI-compatible servers
- DuckDuckGo, Brave, Google Programmable Search and SearXNG
- 9 interface languages, answers in 20+ languages
- Themes with gray palettes and custom accent colours
- Customisable prompts, writing style and article length
- First-run setup and API key prompt
