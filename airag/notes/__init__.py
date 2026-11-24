"""Notes Mode ("Lookup Update"): Obsidian-compatible vaults with a fast, detailed index.

Modules
- pathguard: every path a note operation touches is resolved inside its vault (no escapes)
- parser:    Markdown note -> properties, sections (per heading), links, embeds, tags, gist
- store:     the Notes root folder, notes-index.json (vault list), vault templates, reading/writing notes
- index:     per-vault SQLite index (.airag/index.db): notes, sections, links, FTS5 full-text search
- search:    built-in search (every match, with operators) - no AI

Nothing here calls the AI; smart features (smart search, voice notes, smart editor) build on top later and
always have a manual twin. Linked Obsidian vaults are only read, and AIRAG never writes in `.obsidian/`.
"""
