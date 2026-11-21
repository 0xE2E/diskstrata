"""Cross-platform knowledge base: AI agent tools, file categories, folder meanings.

Pure data plus lookup; nothing here touches the disk.
Hint levels: safe (cache, regenerates) / review (your data: decide) /
keep (needed by the app) / unknown.
"""
from __future__ import annotations

import re

# --------------------------------------------------------------------------- #
# AI agents: (key, display name, regex on folder name). First match wins,
# so more specific patterns come first (Cline's extension id contains "claude").
# --------------------------------------------------------------------------- #
_AGENT_DEFS = [
    ("cline", "Cline / Roo Code", r"^\.?cline|claude-dev|roo-?cline|roo-code|rooveterinary"),
    ("claude", "Claude (Anthropic)", r"claude|anthropic"),
    ("codex", "Codex / OpenAI", r"codex|openai|chatgpt"),
    ("gemini", "Gemini / Antigravity", r"gemini|antigravity|geminicodeassist"),
    ("cursor", "Cursor", r"^\.?cursor|anysphere"),
    ("kiro", "Kiro", r"kiro"),
    ("opencode", "OpenCode", r"opencode"),
    ("copilot", "GitHub Copilot", r"copilot"),
    ("perplexity", "Perplexity", r"perplexity"),
    ("windsurf", "Windsurf / Codeium", r"windsurf|codeium"),
    ("continue", "Continue", r"^\.continue$|continue\.continue"),
    ("qoder", "Qoder", r"qoder"),
    ("lmstudio", "LM Studio", r"lm-?studio|lm studio"),
    ("ollama", "Ollama", r"ollama"),
    ("aider", "Aider", r"aider"),
    ("ml", "Hugging Face / ML caches", r"^huggingface$|^torch$|^\.triton$|unsloth"),
    ("misc", "Other AI agent tools", r"^\.agents$|cc-switch"),
]
AGENTS = [(k, n, re.compile(rx, re.IGNORECASE)) for k, n, rx in _AGENT_DEFS]

# --------------------------------------------------------------------------- #
# File categories for Documents / Downloads / Desktop ...
# --------------------------------------------------------------------------- #
_CATS = {
    "Video": "mp4 mkv mov avi wmv webm m4v flv mts m2ts 3gp",
    "Images": "jpg jpeg png gif bmp heic heif webp tif tiff raw cr2 cr3 nef arw dng psd ai svg ico",
    "Audio": "mp3 wav flac m4a aac ogg wma opus",
    "Archives": "zip rar 7z tar gz tgz bz2 xz zst cab",
    "Installers / disk images": "exe msi msix msixbundle appx appxbundle iso img vhd vhdx dmg apk",
    "Documents": "pdf doc docx xls xlsx xlsm ppt pptx txt md csv rtf odt ods odp epub one pst",
    "AI models": "safetensors gguf ckpt pt pth onnx bin h5 tflite",
    "Code / data": "py ipynb js ts json jsonl sql db sqlite sqlite3 parquet feather npy npz pkl log",
}
EXT_CAT = {"." + ext: cat for cat, exts in _CATS.items() for ext in exts.split()}

# --------------------------------------------------------------------------- #
# Folder meanings: agent-specific first, then generic, then prefix/suffix rules.
# --------------------------------------------------------------------------- #
_AGENT_INFO: dict[str, dict[str, tuple[str, str]]] = {
    "claude": {
        "projects": ("Claude Code session transcripts (.jsonl per session, grouped per project). "
                     "Used by --resume/--continue. Auto-pruned after `cleanupPeriodDays`.", "review"),
        "file-history": ("Claude Code file checkpoints (backups of edited files) for /rewind.", "safe"),
        "shell-snapshots": ("Snapshots of your shell environment per session.", "safe"),
        "todos": ("Per-session todo lists.", "safe"),
        "debug": ("Claude Code debug logs.", "safe"),
        "plugins": ("Installed plugins and marketplace clones.", "keep"),
        "statsig": ("Feature-flag cache.", "safe"),
        "ide": ("IDE connection lock files.", "safe"),
        "plans": ("Plan-mode plan files.", "review"),
        "session-env": ("Per-session environment data.", "safe"),
        "paste-cache": ("Cached pasted content.", "safe"),
        "image-cache": ("Cached images from sessions.", "safe"),
        "telemetry": ("Queued telemetry events.", "safe"),
        "local": ("Local Claude Code install (npm-local / native binary).", "keep"),
        "downloads": ("Downloaded Claude Code updates.", "safe"),
        "versions": ("Installed Claude Code versions; old ones may linger.", "review"),
        "skills": ("Your custom skills.", "keep"),
        "agents": ("Your custom subagents.", "keep"),
        "commands": ("Your custom slash commands.", "keep"),
        "hooks": ("Your hook scripts.", "keep"),
        "memory": ("Persistent memory files.", "keep"),
        "backups": ("Backups of the ~/.claude.json config.", "safe"),
        "tasks": ("Background task state/output.", "safe"),
        "teams": ("Agent-team state.", "review"),
        "vm_bundles": ("Claude Desktop VM images (sandbox for Cowork / Claude Code in the app). "
                       "Often several GB.", "review"),
        "claude-code": ("Claude Code binaries bundled by the desktop app (one per version).", "review"),
        "claude-code-vm": ("VM image used by Claude Code inside the desktop app.", "review"),
        "settings.json": ("Your Claude settings.", "keep"),
        ".claude.json": ("Claude Code main config + per-project history. Can grow large.", "review"),
    },
    "codex": {
        "sessions": ("Codex session rollouts (.jsonl transcripts by date).", "review"),
        "archived_sessions": ("Archived Codex sessions.", "review"),
        "log": ("Codex logs.", "safe"),
        "worktrees": ("Git worktrees Codex created for tasks.", "review"),
        "history.jsonl": ("Prompt history.", "review"),
        "cache": ("Codex cache.", "safe"),
        "tmp": ("Temporary files.", "safe"),
        "skills": ("Codex skills.", "keep"),
        "config.toml": ("Codex config.", "keep"),
    },
    "gemini": {
        "tmp": ("Gemini CLI per-project chat checkpoints, logs and shell history.", "review"),
        "antigravity": ("Antigravity agent data (brain / conversations / browser profile).", "review"),
        "brain": ("Antigravity per-conversation artifacts and plans.", "review"),
        "conversations": ("Saved agent conversations.", "review"),
        "history": ("Chat history.", "review"),
        "extensions": ("Gemini CLI extensions.", "keep"),
        "browser_recordings": ("Recordings from the agent browser.", "safe"),
        "settings.json": ("Gemini settings.", "keep"),
    },
    "ollama": {
        "models": ("Downloaded models (blobs + manifests). Remove with `ollama rm <model>`.", "review"),
        "blobs": ("Model weight blobs.", "review"),
        "manifests": ("Model manifests (map names to blobs).", "keep"),
    },
    "lmstudio": {
        "models": ("Downloaded models. Remove in LM Studio > My Models.", "review"),
        "hub": ("Model hub metadata/downloads.", "review"),
        "conversations": ("Saved chats.", "review"),
        "extensions": ("Runtimes / backends (llama.cpp, MLX...). Old versions linger.", "review"),
        ".internal": ("Internal app state.", "keep"),
    },
    "ml": {
        "hub": ("Downloaded models/datasets (one folder per repo).", "review"),
        "xet": ("Hugging Face Xet chunk cache.", "safe"),
        "datasets": ("Downloaded datasets.", "review"),
        "checkpoints": ("Downloaded model checkpoints.", "review"),
    },
    "copilot": {
        "session-state": ("Copilot CLI sessions.", "review"),
        "logs": ("Copilot logs.", "safe"),
        "pkg": ("Copilot CLI package versions.", "review"),
    },
}

_GENERIC_INFO: dict[str, tuple[str, str]] = {
    "cache": ("Cache.", "safe"),
    "caches": ("Caches.", "safe"),
    "code cache": ("Electron/Chromium compiled-JS cache.", "safe"),
    "gpucache": ("GPU shader cache.", "safe"),
    "dawncache": ("GPU (Dawn) shader cache.", "safe"),
    "dawngraphitecache": ("GPU (Dawn) shader cache.", "safe"),
    "dawnwebgpucache": ("GPU (Dawn) shader cache.", "safe"),
    "grshadercache": ("GPU shader cache.", "safe"),
    "shadercache": ("GPU shader cache.", "safe"),
    "service worker": ("Web service-worker cache (CacheStorage).", "safe"),
    "indexeddb": ("Web-app database (may hold chats/app state).", "review"),
    "local storage": ("Web-app local storage (settings, login).", "keep"),
    "session storage": ("Web-app session storage.", "keep"),
    "webstorage": ("Web storage quota data.", "safe"),
    "shared dictionary": ("Compression dictionary cache.", "safe"),
    "network": ("Cookies / network state (logins).", "keep"),
    "crashpad": ("Crash reports.", "safe"),
    "crashes": ("Crash reports.", "safe"),
    "sentry": ("Crash-reporting queue.", "safe"),
    "logs": ("Log files.", "safe"),
    "log": ("Log files.", "safe"),
    "blob_storage": ("Electron blob storage.", "safe"),
    "partitions": ("Electron per-partition storage (embedded web views, each with own caches).", "review"),
    "cacheddata": ("Compiled cache per app version; old versions pile up.", "safe"),
    "cachedextensionvsixs": ("Cached extension installers.", "safe"),
    "cachedextensions": ("Cached extension metadata.", "safe"),
    "cachedprofilesdata": ("Cached profile data.", "safe"),
    "cachedconfigurations": ("Cached configuration.", "safe"),
    "user": ("User settings + workspaceStorage + globalStorage.", "review"),
    "workspacestorage": ("Per-workspace extension state; grows with every folder opened.", "review"),
    "globalstorage": ("Extension global state (agent chat/task history often lives here).", "review"),
    "extensions": ("Installed extensions (old versions may linger).", "review"),
    "history": ("Local history (file or chat history).", "review"),
    "backups": ("Backups.", "review"),
    "node_modules": ("npm dependencies (reinstallable with npm install).", "safe"),
    ".venv": ("Python virtual environment (recreatable).", "safe"),
    "venv": ("Python virtual environment (recreatable).", "safe"),
    "models": ("Downloaded AI models - usually the biggest item.", "review"),
    "tmp": ("Temporary files.", "safe"),
    "temp": ("Temporary files.", "safe"),
    "sessions": ("Session transcripts/history.", "review"),
    "bin": ("Program binaries.", "keep"),
    "packages": ("Packages.", "review"),
    "versions": ("Installed versions (old ones may linger).", "review"),
    "updates": ("Downloaded updates.", "safe"),
    "update": ("Downloaded updates.", "safe"),
    "pending": ("Pending update downloads.", "safe"),
    "downloads": ("Downloaded files/updates.", "safe"),
    "localcache": ("Store-app cache (LocalCache).", "safe"),
    "localstate": ("Store-app data (LocalState).", "review"),
    "tempstate": ("Store-app temporary data.", "safe"),
    "roamingstate": ("Store-app roaming data.", "keep"),
    "ac": ("Store-app container data (INetCache, temp).", "safe"),
    "settings": ("Settings.", "keep"),
    "systemappdata": ("Store-app system data.", "keep"),
    "dictionaries": ("Spell-check dictionaries.", "keep"),
    "config": ("Configuration.", "keep"),
    ".config": ("Config for CLI tools (XDG style).", "keep"),
    ".cache": ("Cache for CLI tools (XDG style) - often large.", "review"),
    ".local": ("Local data/bin for CLI tools (XDG style).", "review"),
    ".bun": ("Bun runtime + install cache.", "review"),
    ".docker": ("Docker CLI config/buildx/contexts.", "keep"),
    ".android": ("Android SDK tools state + emulator images (avd).", "review"),
    ".gradle": ("Gradle caches/wrappers.", "safe"),
    ".m2": ("Maven repository.", "safe"),
    ".nuget": ("NuGet packages.", "safe"),
    ".cargo": ("Rust cargo registry/bin.", "review"),
    ".rustup": ("Rust toolchains.", "review"),
    ".vscode": ("VS Code extensions.", "review"),
    ".vscode-shared": ("Shared VS Code state.", "review"),
    ".ipython": ("IPython profiles/history.", "keep"),
    ".matplotlib": ("Matplotlib font cache.", "safe"),
    ".gnupg": ("GPG keys - keep!", "keep"),
    ".ssh": ("SSH keys - keep!", "keep"),
    ".triton": ("Triton kernel cache.", "safe"),
}


def describe(agent: str | None, name: str, is_file: bool) -> tuple[str, str]:
    """Return (meaning, hint) for a folder or file name."""
    lname = name.lower()
    info = _AGENT_INFO.get(agent or "", {}).get(lname) or _GENERIC_INFO.get(lname)
    if info:
        return info
    if lname.startswith("app-"):
        return ("Installed app version (Squirrel). Older app-* versions may be left over.", "review")
    if lname.endswith(("-updater", "updater")):
        return ("Updater: cached installers for app updates.", "safe")
    if lname.endswith((".log", ".old", ".bak", ".tmp", ".dmp")):
        return ("Log / backup / temp file.", "safe")
    if lname.endswith((".jsonl", ".json")):
        return ("Data / history file.", "review")
    if is_file:
        return ("File.", "unknown")
    return ("Unrecognised - inspect manually.", "unknown")

