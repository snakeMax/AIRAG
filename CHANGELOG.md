# Changelog

## [0.4.0] - unreleased

- **Usage tab**: tokens and cost per AI model this month, with a monthly budget bar (default $5). Exact token counts from Anthropic, OpenAI-compatible APIs and Ollama (estimated otherwise); prices from OpenRouter's public list, updated daily, with built-in prices as a fallback. Optional: tell the AI when 70% of the budget is used, and stop new searches when it's used up
- **OpenRouter**: new AI provider. One key for hundreds of models; the default `openrouter/auto` picks the best model for each request
- **Keeps working in the background**: on Android, a notification with a Cancel button keeps searches and explainers running after the app is closed, and a second notification opens the result when it's done (asks once to allow background running). On the PC, closing the window while something runs hides it until the work is done
- **Activity bar and dot**: a slim bar under the top bar shows what's running in the background (tap to open, ✕ to cancel), and a dot on the History button shows something is running or finished
- **Sound effects**: soft sounds when the microphone starts and stops, when a search or explainer finishes, and when something fails. Settings → Appearance → Customize audio: per-sound volume (plays a preview when you let go of the slider), your own clips (MP3, OGG, WAV, M4A and more), a master volume that on the phone is the phone's media volume, and Reset to defaults (only applied when you press Save)
- **Read aloud**: a Listen button on articles reads them with your device's voices (female or male, or pick a voice; adjustable speed), with pause and stop
- **Search when you stop speaking**: after using the microphone the search starts by itself (Settings → Defaults to turn off)
- **Export web page**: packs the article into one HTML file that opens in any browser, offline, without AIRAG (to send to someone). Choose whether to add a short summary, the interactive explainer and the pictures; parts that don't exist yet are made first
- **Pin articles** to the top of the home page; pinned articles are never removed from history automatically
- **Reading time and word count** under the article title; **Copy as Markdown** (article with its sources)
- **Library**: only library files that are relevant enough to the question are listed and used (adjustable in Settings → Library)
- **Notifications**: AIRAG's own icon in the status bar; expand the notification to see everything running or queued; a separate notification (with the reason) when a search or explainer fails
- **Locate more sources**: a button on articles that searches for new sources and adds a "What more sources add" section, without rewriting the article
- **Pin sources**: pin any web source to keep it until you unpin it. Pinned sources are listed on the home page and open as the saved page or an AI-written version (Settings → Defaults), and searches reuse them when they match the question (no download)
- **Choose which buttons are shown**: Settings → Appearance → Buttons shown (all on by default)
- **Fixed**: sound effects didn't play (wrong file address, and the phone app only allowed sound right after a tap); a sound's play button now turns into stop while it plays
- **Fixed**: the search spinner kept spinning after a search engine stopped answering and the Try again button showed
- **Explainers build in the background**: closing the explainer window doesn't stop it; the Interactive button shows a spinner, and clicking it again shows the one being built. Cancel button while building

## [0.3.0] - 2026-11-18

First release with the Android app (same version, same release as the Windows installer).

- **Android app**: the full AIRAG on your phone, with a layout that fits phone screens, Obsidian vaults and any folder as library sources, light defaults to save battery and data, and updates from GitHub Releases (asks for the "install apps" permission when needed)
- **Share with my phone**: use the Ollama models on your PC from the phone app over your home Wi-Fi, protected by a pairing code
- **Searches keep running in the background**: leave the page and come back, or start another search and it waits its turn. A *Cancel search* button stops one, and running or queued searches show at the top of History with cancel and delete buttons (on Android, fully closing the app can still stop a search until 0.4.0)
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
