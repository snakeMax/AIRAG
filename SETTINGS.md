# AIRAG settings guide

Every setting and button in AIRAG, grouped by what it does (not by which Settings tab it's on). Each entry says what it's for and what changing it does. **Tokens** means AI usage: money with paid AI providers, time with local models.

Everything works with the defaults. If you only change one thing, pick the AI model (see [AI model](#ai-model)).

**Contents:**
[Searching](#searching) ·
[Article and result tools](#article-and-result-tools) ·
[Interactive explainers](#interactive-explainers) ·
[Research toolbar](#research-toolbar) ·
[What the AI may use (tools)](#what-the-ai-may-use-tools) ·
[Analyze image](#analyze-image) ·
[Pinned articles and sources](#pinned-articles-and-sources) ·
[AI model](#ai-model) ·
[Usage and budget](#usage-and-budget) ·
[Search engine and wikis](#search-engine-and-wikis) ·
[Blocked and favourite sites](#blocked-and-favourite-sites) ·
[How hard each search works](#how-hard-each-search-works) ·
[Reading pages and videos](#reading-pages-and-videos) ·
[My library (your own files)](#my-library-your-own-files) ·
[Writing style and instructions](#writing-style-and-instructions) ·
[Look: theme and colours](#look-theme-and-colours) ·
[Sound effects](#sound-effects) ·
[Speech: microphone and read aloud](#speech-microphone-and-read-aloud) ·
[Saving and exporting](#saving-and-exporting) ·
[App, updates and maintenance](#app-updates-and-maintenance) ·
[Background work and notifications](#background-work-and-notifications) ·
[Recommended setups](#recommended-setups)

**Where things are in Settings (0.4.2):** seven tabs, each split into titled sections with a jump list at the top: **General** (General, Defaults, About) · **Look & sound** · **AI** (AI model, Usage, Prompts) · **Searching** (Search, Research) · **Library & storage** · **Tools & agents** · **System**. *Search settings…* at the top of Settings finds any setting by its name or help text and jumps to it. Old links such as "Settings → Research" now open the matching section.

*Developer settings (coming with the autonomous agent in 0.5) will get one group of their own at the end of this guide, with a subsection per setting.*

---

## Searching
The controls under the search box. Each can be changed for one search; the defaults are set in **Settings → General → Defaults**.

### Quick (home page) and Quick search… (article → Sources)
A short cited answer (about 80-200 words) from 2-3 pages, in a few seconds and with far fewer tokens than a full search: no AI planning step, one round of 1-2 searches, a lower relevance bar. **Shift+Enter** in the home search box runs a quick search; on phones the Quick and Search buttons sit under the box. If nothing usable is found, the AI writes **3 simpler searches** close to your question and tries once more under the same quick rules. Under a quick answer, **Add to this** asks a short follow-up (added as a new section) and **Research this properly** starts a full search. In an article, *Sources → Quick search…* asks a short question about it; **Update the article with the results** (on by default) adds the answer as a new section with its sources, and the old text stays in Version history. Untick it to get a separate quick answer in History instead. Quick searches run as their own kind of task, so they don't wait behind a full search.

### Links in your question
Web addresses you paste into a question are read first (with the usual checks for blocked and bot-check pages), then the search continues as normal.

### Search with AIRAG (share text on Android)
Share text from another app to AIRAG: short text starts a search straight away; longer text is put in the search box so you can edit it first. Shared pictures open *Analyze image* (describe it or pull out the text).

### Auto / Article / Results (search mode)
- **Auto:** writes an article when the answer is spread over several pages. When one page answers the question directly, it shows ranked results instead.
- **Article:** always writes an article.
- **Results:** never writes one; you get ranked, summarized pages.

Results is the fastest and uses the fewest tokens.

### My library
Also searches the folders you added in [My library](#my-library-your-own-files). Only files that are relevant enough are read and listed.

### Pictures & explainer
Finds pictures for the article, and checks whether an [interactive explainer](#interactive-explainers) would help. Turn it off to save tokens and time. The Interactive button can still check later, when you click it.

### Time range (Any time / last week / month / year / custom dates)
Only uses sources from that period. Some search engines can't filter by date; their results are filtered afterwards using each page's date.

### Microphone
Speak your search instead of typing. See [Speech](#speech-microphone-and-read-aloud).

### Cancel search, queue and history
- **Cancel search:** stops a running search.
- **Leaving the page:** doesn't stop the search; it keeps going in the background.
- **Starting another search:** it waits in a queue until the first one finishes.
- **History:** running and queued searches show at the top as *In progress*, each with a cancel button.

---

## Article and result tools
Buttons on articles, result pages and individual sources. Hide the ones you don't use in **Settings → Tools & agents**; all are shown by default.

### Summarize
A short summary of the article, the result list or one source, focused on your question. Uses a few tokens.

### Search results
Shows the ranked list of pages behind an article.

### Locate more sources
Searches new angles for sources AIRAG hasn't used yet.
- **On an article:** adds a *What more sources add* section that cites only the new sources. The article itself isn't rewritten.
- **On a results page:** adds the new sources to the results.

Uses about as many tokens as a short search.

### Save
Opens the Save dialog: tags, translations to keep, pictures and the explainer. See [Saving and exporting](#saving-and-exporting).

### Tags and language switcher (under the byline)
- **Tags:** shown under the article's byline once it's finished. *Edit tags* (or *Add tags*) changes them; for a saved article the saved Markdown file is updated too. Tap a tag to see the saved articles that have it (Saved tab in History). Free; only *Suggest tags* uses tokens.
- **Language switcher:** appears when the article has been translated. *Original* is always first; tap a language to read that translation. Follow-ups and the toolbar still use the original.

### Copy as Markdown
Copies the article and its source list, ready to paste anywhere. Free.

### Translate with AI
Translates the article or results into the language you pick; *Show original* switches back. Uses tokens roughly equal to the article's length.

### Listen
Reads the article aloud. See [Speech](#speech-microphone-and-read-aloud). Free.

### Pin article
Keeps the article at the top of the home page. See [Pinned articles and sources](#pinned-articles-and-sources).

### Export web page
Makes one HTML file of the article. See [Saving and exporting](#saving-and-exporting).

### Download summary
Saves a small file with just the summary and the sources' links. See [Saving and exporting](#saving-and-exporting).

### How the article tools are grouped
- **Computer:** *Explainer* and *Listen* are buttons of their own. *Export options* (Export web page, Copy as Markdown, Download summary, Save), *Rewrite* (Regenerate article, Version history, Translate, Summarize) and *Sources* (Locate more sources, Search results, Search again) open small menus. *Pin* stays a button.
- **Phone:** one row of four big buttons: *Explainer*, *Listen*, *Export* and *More*. Menus open as a sheet from the bottom of the screen; tap outside or ✕ to close.
- A group whose buttons you've all hidden (Settings → Tools & agents) disappears.

### Regenerate article
Writes the whole article again **from the same sources** (no new search). Type or say what should be different, or tap a quick choice (Simpler, Shorter, More detail…). *Skip, just improve it* writes a clearer version without instructions. Uses about as many tokens as writing the article once, and runs in the background like a search.
- **More options → Keep my edits** (on by default): paragraphs you rewrote and answers you added stay as they are.
- **More options → Length:** same, shorter or longer.

### Version history
Every change to an article (regenerating, rewriting a paragraph, adding an answer, Locate more sources) keeps the previous version. *Undo last change* steps back one version; *Restore* jumps to any version; *Compare* shows a version next to the current article. Undo and Restore never delete anything. The last 20 versions per article are kept; they're deleted with the article. Free.

### On sources: Summarize, Save page, Pin
- **Summarize:** sums up that one page.
- **Save page:** keeps a light copy of it in My library.
- **Pin:** pins it (see [Pinned articles and sources](#pinned-articles-and-sources)).

### Hover previews (computer only)
Hover over a citation number like [3], a link in the article, a source or a result title. A preview shows the page's title, site, trust score and summary.

---

## Interactive explainers
Small simulations or games that explain the topic, built by the AI for articles where they help.

### Interactive button
- **Opening:** builds the explainer, or opens it if it's already built.
- **In the background:** building keeps going when you close the window. The button shows a spinner while it builds, and clicking it again shows the one being built. *Cancel* stops it.

### How explainers are kept safe
Explainers are small programs written by the AI, so they run locked away from everything else:
- **Sandboxed:** an explainer can't see AIRAG's page, your settings, keys, history or files, and can't use cookies, storage, pop-ups, alerts, downloads, the camera or the microphone.
- **Offline:** it can't load anything from the internet or AIRAG. If one tries to open a web page, it's stopped and a note says so.
- **Can't freeze the app:** a part that keeps running for more than 2 seconds is stopped (the explainer shows a short note), and on phones a crash of the page is recovered instead of closing the app.
- **Phone:** AIRAG's own phone features (speech, read aloud, volume, shared files) only answer AIRAG's own page, never an explainer.
- **Files from elsewhere:** explainers aren't loaded from opened files outside your My library.

### Data charts
When the article or its sources give related numbers (prices or stock values over time, figures for different groups or years), the explainer can be an interactive line or bar chart of that data. Each point shows its source number. Only numbers from the sources are plotted.

### Explainer detail (Settings → AI → Prompts)
**Simple**, **medium** (default) or **detailed**. Detailed makes richer simulations but uses more tokens.

### Learn from code in My library (Settings → Searching → Research)
On (default): JavaScript in your own My library files that matches the explainer is used as a reference. Nothing is fetched from the web.

### Look up code examples on the web (Settings → Searching → Research)
Off (default). When on, it's still only used when your search itself is about programming. Code from the web can hide instructions aimed at the AI or contain mistakes, so normal explainers never fetch it.

---

## Research toolbar
Tools for a finished article or results page. On a computer it's a small bar at the bottom of the page; on a phone, tap the round button with three lines (they turn upright while the menu is open). The phone menu starts with the question box.

### Follow-up
Opens a box to ask about the article; tap the microphone to speak instead.
- **Where answers go:** the Answers panel beside the article, cited with the article's source numbers. On phones it sits above the round button; the menu folds away while an answer comes in, and when you open the menu again the answers shrink to make room instead of being covered. The list button (with the number of answers) reopens the panel.
- **Elaborate…:** under every answer, asks the AI to explain it in more depth and connect it to the article and its sources.
- **Add to article:** adds an answer to the article as a new section.
- **Questions that don't fit the article:** the AI doesn't search for them. It answers briefly only if it already knows, to save tokens.
- **Tools:** the AI may use the tools allowed for the standard agent (see [What the AI may use](#what-the-ai-may-use-tools)), for example the calculator for maths. The tools it used show as small labels above the answer.

### Compare / Timeline / Fact-check
Run on the whole article, or on the text you selected. Results go to the Follow-ups panel.
- **Compare:** the main options or viewpoints side by side.
- **Timeline:** the events in date order.
- **Fact-check:** checks claims against the sources (and the web, if Web search is allowed).

### Rewrite
Select a paragraph, then Rewrite. Say how it should change (or speak it), and the new version appears **next to the old one**. Nothing changes until you press *Replace in article*; *Copy* takes the new text without changing the article. A replaced paragraph is listed in the Answers panel (old text quoted above the new), where *Elaborate…* explains it.

### Calculate
Select a formula or sum. The AI turns it into plain maths and the calculator solves it exactly; the result stays in a small card until you close it. *Elaborate…* explains how the answer was found and how it relates to the article and its sources. Selecting text in the result card does the same.

### Cite
Copies all sources as **APA**, **MLA** or **BibTeX**, or downloads them (a .bib file for BibTeX).

### Selected text: Ask about this, Fact-check, Rewrite, Calculate, Copy with source, Voice
Selecting text in an article (title and subheading included) shows a small menu (below the selection on phones, so it doesn't cover the phone's own Copy bar).
- **The selected text is remembered:** phones drop a selection on the next tap, so AIRAG keeps the text marked and shows it above the question box ("About …"). Every toolbar action uses it until you press ✕ next to it, select something else, or tap elsewhere in the article.
- **Copy with source:** copies the quote with its sources in your citation style.
- **Calculate:** only appears when the selection looks like maths.
- **Voice (microphone):** say what to do with the selected text. A question becomes a follow-up; "fact-check this" runs a fact-check, and so on.

### Citation style (Settings → General → Defaults)
APA (default), MLA or BibTeX. Used by Cite and Copy with source.

### Analyze image (press and hold, or right-click)
On a picture or drawing in an article, choose *Analyze image*. The answer appears in the Follow-ups panel. Needs an AI model that can see pictures (see [Analyze image](#analyze-image)).

---

## What the AI may use (tools)
**Settings → Tools & agents**, at the top. Tools are things the AI can call while it answers, like the calculator.

### Agent
Pick which kind of agent you're changing. Each has its own set, and AIRAG remembers your last pick. Opens on *Autonomous* until you pick another.
- **Standard:** answers follow-ups and toolbar actions. It can't ask for more tools or setting changes; if a tool is off, it works the answer out in text.
- **Autonomous (from 0.5):** the research agent coming in 0.5. It may ask you once per research session to allow a tool for itself or its sub-agents.
- **Sub-agents (from 0.5):** helpers the autonomous agent starts for parts of a task.

### Tool switches
Saved the moment you change them (no Save button needed).

| Tool | What it does | On by default for |
|---|---|---|
| Calculator | Exact maths, equations, algebra and statistics. No AI tokens | all |
| Date and time | Today's date and the time | all |
| Search this article's sources | Looks through the pages already read, including ones the article didn't cite | all |
| Web search | New searches for fact-checks and follow-ups. *Uses tokens* | all |
| Read a web page | Reads a page found by web search. *Uses tokens* | all |
| Read aloud | Speaks text with your device's voice | all |
| Locate more sources | Same as the button. *Uses tokens* | standard, autonomous |
| Copy to clipboard | Copies an exact quote or result | autonomous |
| Pin article | Pins the article to Home | autonomous |

---

## Analyze image
Lets the AI model look at a picture or screenshot: formulas are written out and solved, other pictures are described.
- **Computer:** the *Analyze image* button on Home, or paste (Ctrl+V) or drop a picture on Home. The button only shows when the selected model can see pictures.
- **Phone:** share a picture or screenshot from any app and choose *Analyze with AIRAG*.
- **Ask a question (optional):** type or speak what you want to know.
- **Models that can see pictures:** Claude, OpenAI (GPT-4o and newer) and vision models through OpenRouter. Ollama and DeepSeek can't. If the model can't, AIRAG says so and suggests an image-to-text or maths-scanner app instead.

---

## Pinned articles and sources

### Pin article
Pinned articles appear at the top of the home page, and history never deletes them automatically.

### Pin source
Saves a copy of a web page and lists it under *Pinned sources* on the home page until you unpin it.

### Open pinned sources as (Settings → General → Defaults)
- **Saved page** (default): the copy saved when you pinned it.
- **AI version:** a short version written by the AI, focused on your search. Uses a few tokens each time.

### Use pinned sources in searches (Settings → Searching → Research)
New searches first read pinned pages that match the question, from the saved copy (no download). They can be cited like any other source. On by default.

---

## AI model
**Settings → AI → AI model.** This has the biggest effect on quality, speed and cost.

### Provider
- **Anthropic Claude, OpenAI, DeepSeek:** need an API key from that company. Strong quality, and you pay per use.
- **OpenRouter:** one key for hundreds of models. The default model `openrouter/auto` picks the best one for each request.
- **Ollama (local):** runs models on your own computer. Free and private, but needs a capable PC; see the hardware recommendations in Settings → System.
- **My PC (Ollama):** on the phone, uses the Ollama running on your computer over your home Wi-Fi.
- **OpenAI-compatible server:** any server that speaks the OpenAI API (LM Studio, vLLM, …).

### Model
Bigger models write better articles and use more tokens; smaller ones are faster and cheaper. *Load models* lists what your key or server offers. *Test* checks that it works.

### Models per task (Settings → AI)
Shown when Claude (Anthropic API) is your AI service. Each kind of work has its own model picker: Research & writing, Quick search, Follow-ups & toolbar, Rewrite & regenerate, Summaries, Translation, Tags, Explainers, Image analysis, Notes and Small helpers. **Every task uses Sonnet 5.5** until you change it ("Main model" = the model chosen above). *Set all to…* changes every task at once; *Reset to Sonnet 5.5* puts them all back. The line under the list shows the price per million tokens (in / out) for Opus, Sonnet and Haiku. Cheaper models such as Haiku work well for tags and small helpers; Image analysis needs a model that can see pictures. A running task keeps the model it started with; the change applies from the next task. Offline mode's local model always wins. Other AI services use their main model for everything (for now).

### Temperature
How varied the wording is. The default 0.3 keeps articles factual; higher values are more creative but less precise.

### API keys
Stored only on your device and never shown to the AI.

---

## Usage and budget
**Settings → AI → Usage.**

### This month
The total at the top, with a bar for the budget, what's left, and a small chart of each day.
- **$ / Tokens switch:** shows the numbers in dollars or in tokens. In tokens, *left* is an estimate of how many tokens the rest of the budget buys at your average price.
- **Other numbers:** today, number of AI calls, average tokens per call, the month at this pace, the most used model, and free local tokens.
- **Local models (Ollama):** counted in tokens only. When you've also used a paid model this month, a line shows what the local use would have cost on the cheapest paid model you used.

Tokens and cost per AI model are listed below.
- **Where the counts come from:** exact numbers when the provider reports them, otherwise estimated (marked *partly estimated*).
- **Prices:** from OpenRouter's public price list, updated daily, with built-in prices as a backup.
- **Local models:** count tokens only, at $0.

### Quality or saving (one per agent)
Five modes: **Minimal**, **Saver**, **Medium** (default for all), **Detailed** and **Maximum**. Set separately for Standard, Autonomous and Sub-agents; saved straight away.

| Mode | Answers | Research rounds and pages read | Tool calls per answer |
|---|---|---|---|
| Minimal | very short, plain | about a third | 1 |
| Saver | short | about two thirds | 2 |
| Medium | normal | as set in [How hard each search works](#how-hard-each-search-works) | 4 |
| Detailed | longer, more cross-checking | about a third more | 6 |
| Maximum | most thorough | about two thirds more | 8 |

The standard mode also applies to normal searches (rounds and pages read are scaled from your research settings).

### Monthly budget ($)
Shown as a bar; default $5. 0 means no budget.

### Tell the AI when the budget is nearly used
At 70% of the budget, the AI is asked to search less and write shorter answers. On by default.

### Stop new searches when the budget is used up
A hard stop: new searches are refused until you raise the budget or it's a new month. Off by default.

### Update prices / Reset this month
- **Update prices:** fetches the latest price list.
- **Reset this month:** clears this month's numbers.

---

## Search engine and wikis
**Settings → Searching → Search.**

### Web search
- **DuckDuckGo** (default): free, no key.
- **Brave**, **Google (Programmable Search)**, **SearXNG** (your own or a public instance): give more or different results, and most need a key.
- **Marginalia:** a free independent engine that favours text-heavy, non-commercial pages. The shared *public* key is rate-limited.

### Image search
Where pictures for articles come from. *None* turns pictures off entirely.

### Region / Safe search
- **Region:** *auto* follows your answer language. You can also enter a region code like `no-no`, `us-en` or `wt-wt` (worldwide).
- **Safe search:** filters adult results.

### Also search wikis / Wiki pages per search
Searches Wikipedia, in your answer language, alongside the search engine and reads the top matching pages (2 by default). Wikipedia starts with a trust score of 7/10.

### Wikis list
Add any wiki built on MediaWiki (Fandom wikis, PsychonautWiki, the Minecraft wiki, …) by its address; AIRAG checks it works. For each wiki you can:
- switch it on or off;
- write what it's good for (*Ask AI to describe it* fills this in);
- set how much it's trusted (1-10).

---

## Blocked and favourite sites
**Settings → Searching → Research.** Both lists are comma-separated, and use the same rules:
- `example.com` covers the whole site and all its subdomains (`news.example.com`).
- `example.com/forum` covers only that directory and everything below it (`example.com/forum/thread/1`), not the rest of the site.

### Blocked sites
Never read. By default: TikTok, Instagram, Facebook, X/Twitter and Pinterest, which can't be read as text. YouTube was removed from this list in 0.4, because videos can now be read.

### Favourite sites
Pages from these start with a higher trust score (+2), so they're more likely to be used and cited.

---

## How hard each search works
**Settings → Searching → Research.** Higher numbers mean better coverage, more tokens and more time.

### Max search rounds (default 3)
- **Round 1:** direct searches.
- **Round 2:** related and indirect searches.
- **Round 3 onwards:** searches that fill gaps in what was found.

### Results per query / Pages read per round / Max pages read in total
- **Results per query:** how many search results are considered for each search.
- **Pages read per round:** how many of them are opened and read in each round (default 8; phone 5). Pages that can't be opened (the site blocks programs, shows a bot check, or fails) don't count: the next results are read in their place, up to two extra tries per round. Other pages from a site that just blocked AIRAG are tried last.
- **Max pages read in total:** a hard limit for the whole search (default 20; phone 14 over 3 rounds). Only pages that were actually read count.
- New in 0.4.1: if you never changed these, the new defaults are used.

Reading is the main token cost.

### Parallel AI calls (default 3)
How many pages are judged at the same time. Use 1 for small local models.

### Text per page sent to AI
How much of each page the AI reads, only the most relevant passages. More text gives more detail and uses more tokens.

### Direct-hit relevance / coverage thresholds
In Auto mode, a page this relevant and complete makes AIRAG show results instead of writing an article.

### Min findings to write an article / Stop searching after N findings
- **Min findings to write an article:** with fewer facts found than this, AIRAG suggests better searches instead of writing an article.
- **Stop searching after N findings:** stops early once it has enough facts.

### Max article length (tokens) / Max sources per article
Upper limits for the article. Reasoning models count their thinking towards the length, so keep it generous (default 8192).

### Max images
How many pictures an article can show.

---

## Reading pages and videos
**Settings → Searching → Research → Page reader.**

### Page reader
- **auto:** fast download first, and a full browser for pages that need JavaScript (on PC with the optional browser installed; the phone app uses its own built-in browser).
- **http:** download only.
- **browser:** always the full browser.

### Page timeout / Pages read in parallel
How long to wait for each page, and how many are downloaded at once.

### Read YouTube videos (on) / YouTube retries (1)
A YouTube video's title, channel, description and, when YouTube allows it, its captions are read so the video can be used as a source. Videos show a preview card in the source list. *Retries* sets how often to try again when YouTube doesn't answer. If YouTube changes its pages, AIRAG says so separately from ordinary errors.

### Blocked pages, bot checks and research papers (automatic)
- **Bot checks** ("Checking your browser", Cloudflare "Just a moment…", captchas, "Access denied") are recognised and treated as pages that couldn't be read; they are never sent to the AI as if they were the page (no tokens wasted). On PC with the optional browser installed, and on the phone, the page is tried once more in a real browser first.
- **Research papers** that a site won't show to a program (PubMed Central, PubMed, journal sites such as ScienceDirect, The Lancet, JAMA, AHA journals, ResearchGate, DOI links…) are read through **Europe PMC**, the free public database of biomedical papers: the full text when the paper is open access, otherwise its abstract. The source list says "full text via Europe PMC" or "abstract only".
- **Other blocked pages:** their search-result descriptions are judged together in one small AI call. Useful ones are used as low-trust sources marked "search snippet only".
- **Searches** are kept short (long ones are cut to their first words and retried), a few run at a time, and when DuckDuckGo throttles AIRAG (it answers "No results found" even for ordinary searches) the plain DuckDuckGo page and then Mojeek are used instead.

### Read pages on my local network (off)
Links to this computer (127.0.0.1, localhost) or to your local network (router, NAS, printers, 192.168.x.x and similar) are never read, so nothing on them can reach the AI, whether the link is in a search result, typed in your question or shared from another app. Redirects to such addresses are stopped too, and only http and https links are read. Turn this on only if you want AIRAG to read your own intranet pages.

### User agent
How AIRAG identifies itself to websites. Only change this if a site you need refuses to load.

---

## My library (your own files)
**Settings → Library & storage.** AIRAG can only read the file types listed here, inside the folders you picked, nothing else.

### Offline mode
Nothing is searched or read on the web. Answers come only from My library, your library folders, pinned pages and earlier articles in History (these are marked "Your earlier article (AI-written)"). Turn it on with the **Offline** chip next to the search options on the home page, or here under *Offline mode*. Turning it on asks who writes the answers:
- **A local model:** nothing leaves your devices. Offered for what's set up under *AI model*: Ollama on this computer (it starts only when you press *Turn on*), Ollama on your computer through the PC link (phone), or an OpenAI-compatible server running on this device, for example llama.cpp's server on a phone (base URL `http://127.0.0.1:…/v1` with a model name).
- **Keep your current model, local sources only:** your usual model writes, but it only gets passages from your own files. The question and those passages are still sent to that AI service, and the dialog says so.

While it's on: the Offline chip shows by the search box (tap it to turn off), the *My library* tickbox is always on, web searches, page reading, wikis, YouTube, pictures for saved or exported pages, the automatic update check and the price-list update are all skipped. *Locate more sources* looks again in your own files instead of the web.

### Folders
The folders to search when *My library* is ticked. Your **personal folder** (where saved articles go) is always included.

### Also search the web when My library is ticked
Off: answers only from your own files.

### Reopened saved articles go back in History
On (default): opening a saved article puts it back in History if it had dropped out, so follow-ups and the other toolbar tools work on it.

### File types
Comma-separated extensions AIRAG may read. AIRAG can read: text and Markdown, PDF, Word (`.docx`), PowerPoint (`.pptx`, with speaker notes), Excel (`.xlsx`, every sheet as a table), OpenDocument (`.odt`, `.ods`, `.odp`), RTF, web pages, CSV/TSV, JSON (lists of records become tables) and SQLite databases (`.db`, `.sqlite`). Only text, tables and web links are taken; nothing in a file is ever run (no macros; formulas show their last saved value, or the formula itself), and databases are opened read-only and only listed and read, never queried with anything from the file. Older `.doc`, `.xls` and `.ppt` files can't be read; save them in the newer format. New in 0.4.1: if you never changed this list, the new types are added for you.

### Tags in My library
Markdown files with `tags:` in their properties (the way Obsidian writes them) are read first when a question mentions one of their tags.

### Skip files larger than (MB)
Large files take longer to index.

### Library files read per search / Minimum relevance
- **Library files read per search:** how many matching files are read.
- **Minimum relevance:** files the AI rates below this (1-10, default 4) for the question are left out and not listed.

### Default reliability of your own files
How much your notes are trusted to start with (default 6/10). The AI still judges each file.

---

## Writing style and instructions
**Settings → AI → Prompts.**

### Writing style / Article length
- **Writing style:** a balanced, simple or technical tone.
- **Article length:** *auto* follows the question, from short for simple facts to long for complex topics.

### Your instructions
Added to the article, summary and explainer prompts. For example: "Always use metric units", "Prefer peer-reviewed sources", "Explain like I'm a nurse".

### Search instructions
Added to the search planner. For example: "Include Norwegian sources", "Avoid Reddit".

### Article prompt (advanced)
Replaces the main article instructions. Safety rules and the answer language are always added. Leave it empty for the default.

---

## Look: theme and colours
**Settings → Look & sound.** Changes apply right away.

### Theme
System, light or dark.

### Colour palette
The overall colour family of backgrounds and surfaces.

### Accent colour
The colour of buttons and highlights; pick one or choose your own. *Reset* goes back to the default look.

---

### Text: interface font, article font, text size (Settings → Look & sound)
**Interface font**: System default (Inter), Serif, Rounded, Monospace, or Easy reading (Atkinson Hyperlegible, bundled with AIRAG so it works offline). **Article font**: Serif (Charter, the default), Same as interface, or Easy reading. **Text size**: five steps from Smaller to Larger (Normal is the middle); it changes articles and most text, and the preview shows the result. Like the colours, these apply at once. On phones, Android's own text size is added on top.

## Sound effects
**Settings → Look & sound → Customize audio.** Nothing here takes effect until you press **Save**; Cancel leaves everything as it was, including your phone's volume.

### Play sound effects
Turns all sound effects on or off.

### Master volume
- **On the phone:** this is the phone's media (music note) volume, so changing it here changes it on the phone too.
- **On the PC:** AIRAG's own volume for its sounds.

### Individual sounds
Separate sounds for:
- the microphone starting to listen;
- the microphone stopping;
- a search finishing;
- an explainer finishing;
- a task failing or being stopped.

Each has a volume slider that plays the sound when you let go of it, and a play/stop button. **Choose a file** uses your own clip (MP3, OGG, WAV, M4A, AAC, OPUS, FLAC or WEBM, up to 3 MB); **Use built-in** goes back to the default.

### Reset to defaults
Restores all volumes and built-in sounds, once you press Save.

---

## Speech: microphone and read aloud

### Microphone (search box)
Speak your search. On the phone it uses Android's speech recognition; on computers it uses the browser's (the desktop window may not offer it).

### Search as soon as you stop speaking (Settings → General → Defaults)
The search starts by itself when you stop talking. Turn it off to check or edit the text first. On by default.

### Read aloud: Voice (Settings → Look & sound)
*Female* or *Male* picks the best matching voice for the article's language, or you can choose a specific voice installed on your device. Install more voices in your phone's or computer's text-to-speech settings.

### Read aloud: Speed and Test
- **Speed:** 0.5× to 2×.
- **Test:** plays a sample with the chosen voice.

On articles, *Listen*, *Pause*, *Resume* and *Stop* control the reading.

---

## Notes

### Research | Notes (top bar)
Switches between searching the web (Research) and your notes (Notes). Both keep running in the background; unsaved typing in a note is saved when you switch.

### Vaults
A vault is a folder of Markdown notes (Obsidian-compatible). **+** next to the vault picker: *Create a vault* (name, what it's for, and how it starts: Research, Writing, Worldbuilding (no folders, make your own), Personal or Empty), or *Link an Obsidian vault* you already have. AIRAG reads a linked vault where it is; changes there need your approval (that arrives in a later test), and its `.obsidian` settings are never touched. AIRAG's own index for a vault lives in a hidden `.airag` folder inside it (for linked vaults: in AIRAG's own data folder).

### New note, Edit / Read, saving
*New note* asks for a name and opens it ready to write. **Edit** shows the Markdown (properties between the `---` lines, `[[Note name]]` links, `#tags`); **Read** shows it formatted with a properties table, and links you can tap. A link to a note that doesn't exist offers to create it. Notes save by themselves a moment after you stop typing (Ctrl+S saves at once). If the note changed in another app since you opened it, AIRAG doesn't overwrite it and asks you to reload. The last 20 versions of each note are kept.

### Linked from, Mentioned but not linked, Outline (right side; below the note on phones)
Notes that link to this one; notes that mention its name without a link (*Link* turns the first mention into a link); the note's headings; and links to notes that don't exist yet.

### Search notes (with microphone)
Lists **every** match, grouped by note, with every matching section and the words highlighted. No AI. Search words: `"exact phrase"`, `-leave out`, `OR`, `tag:status/draft`, `type:claim`, `path:Notes/`, `prop:year>1800` (or `prop:status=done`), `linksto:"Note"`, `linkedfrom:"Note"`, `has:image`, `modified:>2026-11-01`, `created:<2026-01-01`, `regex:pattern`, `case:yes`. The microphone fills the box and searches when you stop speaking.

### Search words and tags (tag button next to the Notes search box)
Two screens. **Search words** lists every search word with an example and what it does; tap one to put it in the search box, then change the example. **Your tags** lists every tag in the vault (nested tags indented) with how many notes use it; tap one to see those notes.

### Voice note
Speak (or type) a note, then pick one of two buttons:
- **Save to Inbox** (no AI): your words as they are, saved in the vault's Inbox (or its top folder) as "Voice note" with the date and time, then opened so you can edit or move it.
- **Organize**: the AI tidies the wording (keeping every fact you said, adding none) and suggests a title, folder, type, tags and links to notes you already have. You get **Check the note** with everything editable; nothing is saved until you press **Save note**. *Keep what I said at the bottom of the note* (on by default) adds your exact words under "What I said". **Back** returns to your words. It runs as a background job with the AI model set for **Notes** (Settings → AI → Models per task): you can close the dialog, and the preview opens when it's done (or the next time you press Voice note in that vault). Only folders and types that exist in the vault are accepted, and links only to notes that exist. The AI sees your words plus the vault's folder names, note types, most used tags and the titles and first lines of up to 25 notes that share words with what you said.

### Notes folder (Settings → Library & storage, and the first-start setup)
Where your notes vaults are kept. Default: **Documents\AIRAG Notes** on your system drive (C: on Windows; Documents/AIRAG Notes on Android). *Change…* picks another folder (for example on another drive); *Use the default* goes back. Changing it doesn't move vaults you already have, and switching back finds them again. The first-start setup shows the same choice.

## Help

### ? (top bar)
A short guide to the things that aren't obvious. In Research it covers search modes, Quick, the chips under the search box, selecting text, the toolbar, the Sources menu, floating panels, saving and pins, pictures and sharing from other apps. In Notes it covers vaults, links, properties, tags, search words, linked from and mentions, saving and voice notes.

## Saving and exporting

### Save (articles)
Saves a Markdown file to *My library → Articles*, plus a small `.airag.json` copy so it opens in AIRAG again. Saved articles appear under *Saved* in History, with their tags. The Save dialog has:
- **Tags:** type one and press Enter or a comma; × removes it. They go in the Markdown file's properties (`tags: [airag, …]`; `airag` is always added). *Suggest tags* asks the AI for 3-6 (a few hundred tokens, runs in the background); tap a suggestion to add it.
- **Translations to keep:** shown when the article has translations; ticked ones are kept in the AIRAG copy and appear in the language switcher when you open it again.
- **Include pictures and the interactive explainer:** see below.
Saving again updates the same file.
- **Editing the .md:** you can change the saved Markdown file in any editor (Obsidian, Notepad...). Next time you open the article in AIRAG, it's read from your edited file, and a note says so. Keep the "Sources" list at the bottom as it is, so the source numbers still work.

### Unsave and Saved articles
- **Saved state:** a saved article shows *Saved* under its byline, and in *Export options* the Save item reads *Saved · Save again to update it*, with **Unsave** right under it.
- **Unsave** takes the article out of *My library → Articles* (its `.md` and AIRAG copy) but keeps it in History, so it opens like any other search. A message offers **Undo**.
- **Manage saved articles** (*Export options* in an article, *Manage* next to *Saved articles* on the home page, or the top of the *Saved* tab in History): tick several to unsave them at once, or use the bin icon on one.
- **Recently removed** (in the same window): unsaved articles are kept for 30 days in AIRAG's private app folder, outside My library (so they aren't searched or synced). *Restore* puts the article back exactly as it was, with its tags and translations; × deletes that copy for good (the article stays in History). At most 50 are kept.
- On phones, the delete and unsave buttons in History lists are always shown (they used to appear only when a mouse hovered over them).

### Save articles with pictures and the explainer (Settings → General → Defaults)
Also keeps pictures and the interactive explainer in the saved copy, so they work offline. This makes larger files.

### Export web page
One HTML file in *My library → Exports* that opens in any browser, offline, without AIRAG; good for sending to someone. Before exporting it asks whether to include:
- a short summary;
- the interactive explainer;
- pictures.

If the summary or explainer doesn't exist yet, it's made first, which uses tokens.

The exported page also carries a hidden data copy of the article (plain data, it never runs), so AIRAG can open the page again exactly.

### Download summary
A small Markdown file in *My library → Summaries* with only the summary and the sources' links. On articles (next to Export web page) and in the Summarize panel (also for search results and single sources). An existing summary is reused; if there isn't one yet, it's made first, which uses tokens.

### Open with AIRAG
Opens a file as an article, **without the AI** (no tokens). The article goes into History, so the toolbar works on it.
- **What it opens:** Markdown and text files (`.md`, `.txt`), saved articles (`.airag.json`), web pages exported from AIRAG (`.html`), and (new in 0.4.1) Word, PowerPoint, Excel, OpenDocument, PDF, RTF, CSV, JSON and SQLite files, shown as text with real tables; web links found in the file become its sources. Other web pages open as their readable text. Up to 20 MB.
- **Computer:** right-click a file → *Open with* → AIRAG (the installer adds AIRAG to that list but never makes it the default app). Or use *Open a file* at the top of *Saved* in History. The portable zip version has only the *Open a file* button.
- **Phone:** open the file in a file manager and pick *Open in AIRAG*, or share the file to AIRAG.
- **Safety:** an interactive explainer is only loaded from files in your own My library; from anywhere else it's left out, and links that aren't web addresses are removed.

### Backup / import (Settings → System)
Exports your settings and history to one file, and imports them again. API keys are only included if you tick that option.

---

## App, updates and maintenance

### Language and answer language (Settings → General)
- **Language:** the app's own language.
- **Answer language:** *Same as my question* (default) writes in the language you searched in; you can also pick the app's language or a fixed language.

### Window mode (PC)
How AIRAG runs on your PC: in its own **desktop window**, or as a **browser tab with a tray icon**.

### Guarded execution (Settings → System → Maintenance)
On by default. Protects tasks that are running (searches, explainers, toolbar answers, regenerating…):
- **Settings you change while a task runs:** the task keeps the settings it started with, so switching the AI model, search engine, language or offline mode can't break it halfway. Small settings that only change *how much* it does (results per search, pages per round, rounds, pictures, sources in the article, blocked/favourite sites, page timeout, library files read) are picked up at its next step: lowering the number of results doesn't cut short the search it's doing, only the next ones. Everything else applies from the next task. After saving, a note says when your change applies.
- **Clearing the cache, the library index or History** waits while a task is running: you're told to try again when it has finished or to cancel it first.
- A settings file that's damaged or half-written while a task runs never stops the task; it carries on with the settings it has.

Off: tasks read the settings file directly, as before 0.4.1, and clearing is always allowed (a task that was using cleared pages just reads them again; clearing History cancels running tasks first). Deleting one article from History always cancels its task first.

### Live resource graphs / Graph colours (Settings → System)
Off by default. When on, a small chip under the top bar shows the processor (phones: battery and temperature), AIRAG's memory and the number of running tasks; tap it for three graphs: processor or battery, memory (AIRAG, and the whole computer as a dashed line), and AI tokens per minute over the last 10 minutes. It only measures, and only while AIRAG is open and visible. **Graph colours**: Accent (your accent colour, the default) or Plain (grey, following light or dark mode).

### Check for updates when AIRAG starts / Check for updates / Check & repair
- **Check for updates when AIRAG starts:** shows a popup when a new version is out.
- **Check & repair** (Settings → System): finds and fixes broken or missing app files.

### Searches kept in history
Every finished search (article, results page, or "nothing reliable found") is kept as one small file in AIRAG's own app folder, not in My library: on Windows `%APPDATA%\AIRAG\history`, on the phone inside the app's private storage. Up to this many are kept (default 300 on PC, 100 on the phone); when there are more, the oldest are deleted automatically. Pinned articles are never deleted this way. Each file holds the article, its sources and their notes, follow-up answers, translations, tags and the explainer, so reopening it needs no AI. Earlier versions of an article (Version history) are kept next to it and deleted with it. Saving an article additionally puts a copy in My library; unsaving removes only that copy.

### Preferred port (PC)
The local address AIRAG uses on your computer; a free one is picked if it's busy.

### Clear cache / Logs / Hardware (Settings → System)
- **Clear cache:** fixes a page that looks outdated after an update.
- **Logs:** helps when reporting a bug.
- **Hardware:** shows your device and recommends local models that fit it.

---

## Floating boxes and snap panels

### Drag, snap, minimize
The Answers panel and the Calculator card (and later the explainer window) are floating boxes with a grip on their title bar, a **minimize** button and an **X**.
- **Computer:** drag a box by its title bar and four snap areas light up (left and right column, top and bottom half). The one under the pointer is highlighted and says the box will snap there and resize to fit. One box in a column fills it; two share it. Dropping on a taken area swaps the boxes. The article makes room on that side.
- **Phone (layout A):** boxes sit in one column above the menu button. While your finger is still down, a dashed "will snap here" slot moves between the other boxes, so you see where the box lands before you let go.
- **Minimize** turns a box into a pill in the tray (bottom left; on phones beside the menu button) showing its name and the start of its text, like *Answers: "Yes: crossings…"*. Tap the pill to bring the box back with everything in it. Where you put each box is remembered.

## Background work and notifications

### Searches and explainers keep running
- **Leaving the page:** the work keeps going.
- **On the phone:** a notification with AIRAG's icon and a **Cancel** button keeps it going even after you close the app. Expand the notification to see everything running or queued.
- **On the PC:** closing the window while something runs hides the window until the work is done.

### Finished and failed notifications
A notification tells you when a search or explainer is done (tap to open it), or why it stopped.

### Background permission (phone)
The first time, AIRAG asks to show notifications and to be allowed to run in the background without battery restrictions. Without this, Android may pause a search when you leave the app.

### Activity bar and History dot
- **Activity bar:** a slim bar under the top bar shows what's running; tap it to open, or ✕ to cancel.
- **History dot:** pulses while something runs, and stays on when something finished that you haven't opened yet.

---

## Recommended setups

| Goal | Change these |
|---|---|
| **Cheapest** | Mode *Results*; Pictures & explainer off; a small model (Claude Haiku, `openrouter/auto`); Research → Max pages read in total 8-10; Usage → stop at budget. |
| **Best quality** | Mode *Auto*; a strong model; Research → Max search rounds 3-4 and Max pages read 20+; Wikis on; add Favourite sites for your field. |
| **Offline / private** | AI model → Ollama; tick *My library*; Library → *Also search the web* off. |
| **Phone** | Keep the defaults; allow background running when asked so searches finish while the app is closed. |
