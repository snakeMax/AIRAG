# Changelog

## [Unreleased] - Notes Mode ("Lookup Update")

- **Notes Mode**: a Research | Notes switch in the top bar. Obsidian-compatible vaults (create from Research, Writing, Worldbuilding, Personal or Empty, or link an existing Obsidian vault read-only), a folder tree with recent notes, a Markdown editor with Edit / Read, properties, [[links]] (missing notes can be created from the link) and #tags, saving by itself with the last 20 versions kept and no overwriting of notes changed elsewhere
- **Search notes**: every match, grouped by note with highlighted sections, with search words (tag:, type:, path:, prop:, linksto:, linkedfrom:, has:, modified:, created:, regex:, "exact", -word, OR) and a microphone; no AI
- **Linked from / Mentioned but not linked / Outline** beside each note, with one-tap *Link*
- **Voice note**: speak a note, then Save to Inbox as it is, or **Organize**: the AI tidies it and suggests a title, folder, type, tags and links, shown as an editable preview before anything is saved
- **Notes** in Models per task (Settings → AI)
- **Ask your notes**: a short answer from your vault with numbered citations that open the right heading, results in tiers (direct, related, closest), Research this (web + My library) and Collect into a note. Ask also writes a short article from your notes when you ask for one, and starts a Quick search or a full Research (with My library) when you ask to look something up online or research it
- Notes on phones: the microphone in the bottom bar is centred and larger
- **Main notes vault** (Settings → Library & storage → Notes vaults, and the first-start setup): AIRAG's own vault or an Obsidian vault; added Obsidian vaults can be edited straight away (optional read only); **Open in Obsidian** for vaults and notes
- **Add to notes** in Research: articles, quick answers, results pages and single sources go into a vault as raw data or auto-categorized (title, folder, type, tags and related links suggested; the text is kept)
- **Search words and tags**: a screen listing every search word with an example (tap to use it) and every tag in the vault with its count (tap to see its notes)
- **Help (?)** in the top bar: a short guide to Research or Notes, depending on where you are
- **Notes folder**: Documents\AIRAG Notes by default (system drive), changeable in Settings → Library & storage and in the first-start setup
- Phone: one screen at a time with a bottom bar (Notes, Search, Voice note, Graph and Ask coming next)

## [0.4.2] - 2026-11-24

- **Search with AIRAG** (Android): share text or a link from any app to AIRAG and it starts a search with it. Long text is put in the search box first so you can shorten it
- **Links in your question are read first**: put a web address in a search (typed or shared) and that page is read as a source before the search engine's results, with the usual checks (offline mode, blocked sites)
- **Quick search**: a short cited answer from 2-3 pages in seconds, with far fewer tokens than a full search. *Quick* next to the home search box (Shift+Enter; on phones a Quick and a Search button under the box). If nothing usable is found, the AI tries 3 simpler searches close to the question. Under a quick answer: *Add to this* (another quick question, added as a section) and *Research this properly* (a full search). In an article: *Sources → Quick search…*, which by default adds the answer to the article as a new section (the old text stays in Version history). Runs as its own task, so it doesn't wait behind a full search
- **Settings in 7 tabs**: General · Look & sound · AI · Searching · Library & storage · Tools & agents · System, each with titled sections and a jump list. *Search settings…* finds any setting by name or help text and jumps to it (the tab opens and the setting is highlighted)
- **Models per task** (Settings → AI, Claude API): pick Opus, Sonnet or Haiku per kind of work (research, quick search, follow-ups, rewrites, summaries, translation, tags, explainers, image analysis, small helpers); every task uses Sonnet 5.5 until changed; *Set all to…*, *Reset to Sonnet 5.5* and prices per million tokens. A running task keeps the model it started with
- **Text** (Settings → Look & sound): interface font, article font (including the bundled easy-reading font Atkinson Hyperlegible) and five text sizes, with a preview; applies at once
- **Live resource graphs** (Settings → System, off by default): a chip under the top bar and three graphs - processor (phones: battery and temperature), memory, AI tokens per minute - in your accent colour or plain grey
- **Snap panels**: the Answers panel and the Calculator card can be dragged by their title bar. On computers four snap areas light up and the one under the pointer shows where the box lands and that it resizes to fit; on phones (layout A, one column) a dashed slot shows the landing place while your finger is still down. Minimize turns a box into a pill in a tray; tap to bring it back. Positions are remembered
- Groundwork (nothing changes yet): agent types and limits for 0.5.0 "The Agentic Utilities Update" (`airag/agents`), editions for the later enterprise build (`airag/editions.py`), and settings sections for both
- Security: AIRAG never reads pages on this computer or your local network (router, NAS, 192.168.x.x...) unless you allow it in Settings → Searching, also after redirects and in the headless browser; other websites can't call any of AIRAG's local functions or show AIRAG inside a frame; on Android, links in articles only open web and mail links (no app or intent links), and AIRAG's WebViews have file access off
- For development: `tools/codemap.py` (CODEMAP.md) and `tools/review.py` (checks imports, routes, text keys and safety rules; part of the tests)

## [0.4.1] - 2026-11-19

- **Download summary**: a small Markdown file with only the summary and the sources' links, saved in My library/Summaries. On articles and in the Summarize panel (also for results and single sources); reuses an existing summary
- **Open with AIRAG**: Markdown and text files, saved articles (.airag.json) and exported web pages open as an article without the AI, with their sources. Windows: AIRAG is in the *Open with* list (never the default app); Android: open files from a file manager or share them to AIRAG; everywhere: *Open a file* in the Saved tab
- **Exported web pages** carry a data copy of the article, so AIRAG opens them again exactly
- **Saved articles you edit** (e.g. in Obsidian) are read from your edited .md when reopened
- **Read aloud: Resume carries on from the word where you paused** (it restarted the whole paragraph); text is read sentence by sentence
- **Selection menu on phones**: docked to the top or bottom edge away from your selection, two even rows of buttons with short labels, stays while you drag the selection handles, closes only when the selection is gone, and can't be selected itself (dragging onto it used to select the whole page)
- **Explainers no longer look up code on the web** unless your search is about programming (setting off by default); they can learn from JavaScript in your own My library instead
- **Safer explainers**: the no-network rules now apply before any of the AI's code runs; auto-redirects, outside links, frames and prefetches are removed; an explainer that tries to open a web page is stopped; loops that run longer than 2 seconds are stopped instead of freezing the app; on Android, frames inside the page can no longer open the browser, AIRAG's phone features (microphone, read aloud, volume, shared files) only answer AIRAG's own page, and a crashed page is recovered instead of closing the app
- **Data safety**: settings, History, pins and My library files are written so a crash can't leave them half-written; a damaged settings file is replaced by the last good copy instead of the defaults; features working on the same article at once (follow-ups, rewrites, explainers, translations, Locate more sources) no longer overwrite each other's changes; opened files no longer use the built-in History limit instead of yours
- **Budget stop covers all AI work** (follow-ups, rewrites, explainers, summaries, translations, image analysis), not only searches; work already running finishes
- **Fewer resources**: pressing a button twice no longer starts the same job twice; at most 30 tasks can wait; streamed text uses much less memory; a few small leaks fixed (PC-link connections, notification and lock-out lists, summary cache)
- **Adding files to My library** skips files that are already there and never overwrites a different file with the same name
- **Unsave and Saved articles window**: a saved article shows *Saved*, and its Export menu has **Unsave** (keeps it in History, with Undo). *Manage saved articles* (home page, Saved tab, article menu) unsaves several at once and has **Recently removed** for 30 days with Restore. Delete/unsave buttons in History lists are now visible on phones
- **Much better at finding information for medical and scientific questions**:
  - Bot-check pages ("Checking your browser", captchas) are recognised instead of being judged as empty pages; in tests up to 7 of 16 pages were bot checks from PubMed Central
  - Research papers on blocked sites (PubMed Central, PubMed, ScienceDirect, The Lancet, JAMA, ResearchGate, DOI links…) are read through Europe PMC: full text when open access, otherwise the abstract
  - Pages that can't be opened no longer use up the reading budget: others are read in their place; their search snippets are judged as low-trust sources
  - Sources are judged per part of the question (a page that answers the dosing part counts even if it says nothing about bradycardia), and evidence of the usual or opposite effect counts as an answer
  - Searches stay short; DuckDuckGo's "No results found" when it throttles is retried through other routes instead of losing the search
  - Slightly more pages read by default (8 per round / 20 in total; phone 5 / 14 over 3 rounds)
- **Guarded execution** (Settings → System, on by default): a running task keeps the settings it started with; small changes (how much to read) apply from its next step, the rest from the next task. Clearing the cache, the library index or History waits until running tasks finish or are cancelled. Deleting an article cancels its task first
- **More file types**: My library and Open with AIRAG read Word, PowerPoint (with speaker notes), Excel (every sheet as a table), OpenDocument, RTF, CSV, JSON and SQLite databases (read-only): text, tables and web links. Nothing in a file is run. Older .doc/.xls/.ppt files say to save them in the newer format
- **Save dialog**: tags (type them, or *Suggest tags* with the AI), which translations to keep, pictures and the explainer. Tags go in the Markdown file's properties, so Obsidian sees them too
- **Tags and language switcher** under an article's byline: edit tags any time (a saved copy is updated), tap a tag to see saved articles with it; switch between the original and its translations
- **Library searches read files whose tags match the question first**
- **Offline mode**: nothing is searched or read on the web; answers come from My library, your folders, pinned pages and History. Choose a local model (Ollama, the PC link, or a local server such as llama.cpp on the phone) or keep your current model with only local sources. An Offline chip shows it's on
- **Long messages at the bottom of the screen** are no longer squeezed into a circle
- **Article tools grouped**: Explainer and Listen stay, the rest are in *Export options*, *Rewrite* and *Sources* menus; on phones one row of four big buttons (Explainer, Listen, Export, More) with menus that slide up from the bottom
- **Regenerate article**: write the article again from the same sources, your way (typed or spoken instructions, quick choices, keep your edits, shorter or longer), or just a clearer version
- **Version history**: every change to an article keeps the previous version; Undo, Compare and Restore (last 20 kept, nothing is deleted)
- **All AI tools run as background jobs** (follow-ups, rewrites, translations, summaries, image questions, calculations): they show in the activity bar and on Android in the notification, and keep going when you leave the article
- **Selection menu stays open when you open the toolbar** on phones; it docks to the top edge instead
- **Reopened saved articles go back in History**, so the toolbar works on them (Settings → Library to turn off)

## [0.4.0] - 2026-11-18

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
- **Wikis**: Wikipedia (in your answer language) is searched next to the search engine and trusted by default; add any MediaWiki wiki (Fandom, PsychonautWiki, the Minecraft wiki...) in Settings → Search, with an "Ask AI to describe it" button
- **YouTube videos can be sources**: their title, description and (when YouTube allows) captions are read, shown with a video preview card. YouTube is no longer blocked by default
- **Marginalia**: a free independent search engine as an option in Settings → Search
- **Blocked and favourite sites**: both accept sites (all subdomains) or paths (that directory and below); favourites start with a higher trust score
- **Locate more sources on results pages** adds the new sources to the results (articles get a new section instead)
- **Settings → Tools**: one place to show or hide every tool button
- **Hover previews** (desktop): hovering a link in an article or a result shows the page's title, site, trust and summary
- **Conflicting sources**: the article goes with the clearly more trustworthy source and says why, or presents both when they're equally trustworthy
- **Explainers** look up code examples for similar simulations first (can be turned off in Research)
- **README**: a settings guide explaining every setting and button, with recommended setups
- **Fixed**: sound effects didn't play (wrong file address, and the phone app only allowed sound right after a tap); a sound's play button now turns into stop while it plays
- **Fixed**: the search spinner kept spinning after a search engine stopped answering and the Try again button showed
- **Research toolbar** on finished articles and results: Follow-up questions (typed or spoken) answered in a side panel with the article's source numbers and *Add to article*; Compare, Timeline and Fact-check; Rewrite with a side-by-side preview before anything changes; Calculate (exact maths with SymPy) with *Elaborate…*; Cite as APA, MLA or BibTeX. On phones it's a round menu button that opens a sheet
- **Selected text menu**: Ask about this, Fact-check, Rewrite, Calculate, Copy with source, and Voice (say what to do with the selection)
- **The AI can use tools** in follow-ups (calculator, date, searching the article's sources, web search, reading pages, read aloud, locate more sources). Settings → Tools sets which tools each kind of agent may use, saved straight away
- **Quality or saving**: five modes from Minimal to Maximum, per agent type (Medium by default), that set answer length, research rounds, pages read and tool calls
- **Analyze image**: the AI model looks at a picture or screenshot (formulas are solved, other pictures described). On Home (button, paste or drop), on pictures in articles (press and hold / right-click), and on Android by sharing a picture to AIRAG. Needs a model that can see pictures
- **Usage tab redesign**: switch between dollars and tokens, what's left of the budget, today's use, a daily chart, the month at this pace, and what local (Ollama) use would have cost on a paid model
- **Explainers can be data charts**: line or bar charts of numbers from the article and its sources (prices, stock values, measurements), each point labelled with its source
- **Selected text is remembered** (phones drop selections on the next tap): it stays marked and shows as "About …" above the question box, and every toolbar action uses it until cleared
- **Elaborate…** on every answer, and replaced paragraphs are listed in the Answers panel so you can see what changed and ask about it
- **Phone layout**: answers sit above the round button; the menu folds away while an answer comes in, and the answers shrink to make room when it's opened again
- **Microphone animation**: the mic button grows, bobs and glows in your accent colour (bright red with grey palettes) with a ring spinning around it while it listens
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
