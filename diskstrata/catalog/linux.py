"""Linux locations. Path templates use the variables from platforms.linux.path_vars()."""
from __future__ import annotations

# (base folder template, only match names starting with ".")
AGENT_BASES = [
    ("{home}", True),
    ("{config}", False),
    ("{cache}", False),
    ("{data}", False),
    ("{state}", False),
    ("{home}/.vscode/extensions", False),
    ("{config}/Code/User/globalStorage", False),
    ("{home}/.cursor/extensions", False),
    ("{config}/Cursor/User/globalStorage", False),
    ("{home}/.kiro/extensions", False),
    ("{home}/.npm-global/lib/node_modules", False),
    ("/opt", False),
]

_CACHE = "Cache; regenerated on demand."
_TRASH = "Move to Trash is not deletion: empty the Trash from your file manager."

# (category, label, path template, advice). Advice is text only.
HOTSPOTS = [
    ("Temp", "User cache folder", "{cache}", "Per-app caches; most regenerate. Review before clearing."),
    ("Temp", "Trash", "{data}/Trash", _TRASH),
    ("Temp", "Thumbnail cache", "{cache}/thumbnails", "Regenerated automatically."),
    ("Temp", "Temp files", "/tmp", "Cleared at reboot on most systems."),
    ("Temp", "Persistent temp files", "/var/tmp", "Survives reboots; old files can usually go."),
    ("Temp", "Crash reports", "/var/crash", "Not needed unless debugging."),
    ("Temp", "Core dumps", "/var/lib/systemd/coredump", "`coredumpctl` to inspect; safe to clear."),
    ("Python", "pip cache", "{cache}/pip", "`pip cache purge`."),
    ("Python", "uv cache", "{cache}/uv", "`uv cache prune` or `uv cache clean`."),
    ("Python", "uv-managed Pythons", "{data}/uv/python", "`uv python list`."),
    ("Python", "uv tools", "{data}/uv/tools", "Tools installed with `uv tool install`."),
    ("Python", "pipx venvs", "{data}/pipx/venvs", "Tools installed with pipx."),
    ("Python", "Poetry cache", "{cache}/pypoetry", "`poetry cache clear --all PyPI`."),
    ("Python", "Conda installation", "{home}/miniconda3", "Miniconda install incl. envs; `conda clean --all`."),
    ("Python", "Conda installation", "{home}/anaconda3", "Anaconda install incl. envs; `conda clean --all`."),
    ("Python", "Hugging Face cache", "{cache}/huggingface", "Models/datasets; `hf cache scan` to review."),
    ("Python", "PyTorch hub cache", "{cache}/torch", "Downloaded weights; re-downloaded on demand."),
    ("Python", "Triton kernel cache", "{home}/.triton", "Compiled kernels; regenerated."),
    ("JS/Dev", "npm cache", "{home}/.npm", "`npm cache verify` / `npm cache clean --force`."),
    ("JS/Dev", "Yarn cache", "{cache}/yarn", "`yarn cache clean`."),
    ("JS/Dev", "pnpm store", "{data}/pnpm/store", "`pnpm store prune`."),
    ("JS/Dev", "Bun install cache", "{home}/.bun/install/cache", "`bun pm cache rm`."),
    ("JS/Dev", "Playwright browsers", "{cache}/ms-playwright", "Downloaded browsers; old versions linger."),
    ("JS/Dev", "Puppeteer browsers", "{cache}/puppeteer", "Downloaded Chrome builds."),
    ("JS/Dev", "Gradle caches", "{home}/.gradle/caches", _CACHE),
    ("JS/Dev", "Maven repository", "{home}/.m2/repository", "Re-downloaded on demand."),
    ("JS/Dev", "NuGet packages", "{home}/.nuget/packages", "`dotnet nuget locals all --clear`."),
    ("JS/Dev", "Cargo registry", "{home}/.cargo/registry", "Re-downloaded on demand."),
    ("JS/Dev", "Rust toolchains", "{home}/.rustup/toolchains", "`rustup toolchain list`."),
    ("JS/Dev", "Go module cache", "{home}/go/pkg/mod", "`go clean -modcache`."),
    ("JS/Dev", "Android SDK", "{home}/Android/Sdk", "Remove unused images via SDK Manager."),
    ("JS/Dev", "Android emulators (AVD)", "{home}/.android/avd", "Delete unused AVDs in Device Manager."),
    ("JS/Dev", "VS Code extensions", "{home}/.vscode/extensions", "Old extension versions may linger."),
    ("JS/Dev", "VS Code workspaceStorage", "{config}/Code/User/workspaceStorage", "Per-folder state; grows forever."),
    ("JS/Dev", "VS Code cache", "{config}/Code/Cache", _CACHE),
    ("JS/Dev", "JetBrains caches", "{cache}/JetBrains", "IDE caches/indexes; old IDE versions linger."),
    ("JS/Dev", "Docker CLI config", "{home}/.docker", "Docker contexts/buildx state."),
    ("Browser", "Chrome profile", "{config}/google-chrome", "Clear cache in Chrome settings."),
    ("Browser", "Chromium profile", "{config}/chromium", "Clear cache in Chromium settings."),
    ("Browser", "Brave profile", "{config}/BraveSoftware", "Clear cache in Brave settings."),
    ("Browser", "Firefox profiles", "{home}/.mozilla/firefox", "Cache lives under ~/.cache/mozilla."),
    ("Apps", "Slack data", "{config}/Slack", "Cache, Service Worker, IndexedDB."),
    ("Apps", "Discord data", "{config}/discord", "Cache folders regenerate."),
    ("Apps", "Telegram data", "{data}/TelegramDesktop", "Downloaded media cache."),
    ("Apps", "Spotify cache", "{cache}/spotify", "Set the cache size in Spotify."),
    ("Apps", "Steam library", "{data}/Steam", "Installed games; uninstall inside Steam."),
    ("Apps", "Flatpak apps (user)", "{data}/flatpak", "`flatpak uninstall --unused`."),
    ("VMs", "Docker data", "/var/lib/docker", "`docker system df`, then prune inside Docker."),
    ("VMs", "Podman / rootless containers", "{data}/containers", "`podman system df`."),
    ("VMs", "libvirt disk images", "/var/lib/libvirt/images", "KVM/QEMU VM disks."),
    ("VMs", "GNOME Boxes", "{data}/gnome-boxes", "VM disks."),
    ("VMs", "VirtualBox VMs", "{home}/VirtualBox VMs", "VirtualBox VM disks."),
]

# (label, path template, advice). Text only.
SYSTEM_ITEMS = [
    ("Package cache (apt)", "/var/cache/apt/archives", "`sudo apt clean` removes downloaded .deb files."),
    ("Package cache (dnf)", "/var/cache/dnf", "`sudo dnf clean all`."),
    ("Package cache (pacman)", "/var/cache/pacman/pkg", "`paccache -r` keeps the last 3 versions."),
    ("Systemd journal", "/var/log/journal", "`sudo journalctl --vacuum-size=500M`."),
    ("System logs", "/var/log", "Rotated logs; `logrotate` manages them."),
    ("Snap packages", "/var/lib/snapd", "Old revisions linger: `snap list --all`."),
    ("Flatpak apps (system)", "/var/lib/flatpak", "`flatpak uninstall --unused`."),
    ("Docker data", "/var/lib/docker", "`docker system df`, then prune inside Docker."),
    ("Swap file", "/swapfile", "Virtual memory; resize via your distro's swap settings."),
    ("Boot files / old kernels", "/boot", "Remove old kernels with your package manager, not by hand."),
    ("Crash reports", "/var/crash", "Safe to clear."),
    ("Core dumps", "/var/lib/systemd/coredump", "Safe to clear."),
    ("Mail spool", "/var/mail", "Local mail."),
    ("Optional software", "/opt", "Third-party installs."),
    ("Installed software", "/usr", "Core OS and packages. Leave it."),
]

# SYSTEM_ITEMS labels that are leftovers the OS itself can clean ("quick wins")
STALE = {"Package cache (apt)", "Package cache (dnf)", "Package cache (pacman)",
         "Systemd journal", "Crash reports", "Core dumps"}
