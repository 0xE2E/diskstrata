"""macOS locations. Path templates use the variables from platforms.macos.path_vars()."""
from __future__ import annotations

# (base folder template, only match names starting with ".")
AGENT_BASES = [
    ("{home}", True),
    ("{home}/.config", False),
    ("{home}/.cache", False),
    ("{home}/.local/share", False),
    ("{support}", False),
    ("{caches}", False),
    ("{home}/.vscode/extensions", False),
    ("{support}/Code/User/globalStorage", False),
    ("{home}/.cursor/extensions", False),
    ("{support}/Cursor/User/globalStorage", False),
    ("{home}/.kiro/extensions", False),
    ("/Applications", False),
]

_CACHE = "Cache; regenerated on demand."

# (category, label, path template, advice). Advice is text only.
HOTSPOTS = [
    ("Temp", "User caches", "{caches}", "Per-app caches; most regenerate. Review before clearing."),
    ("Temp", "Trash", "{home}/.Trash", "Empty the Trash from Finder."),
    ("Temp", "User logs", "{lib}/Logs", "Logs and diagnostic reports."),
    ("Python", "pip cache", "{caches}/pip", "`pip cache purge`."),
    ("Python", "uv cache", "{home}/.cache/uv", "`uv cache prune` or `uv cache clean`."),
    ("Python", "uv-managed Pythons", "{support}/uv/python", "`uv python list`."),
    ("Python", "pipx venvs", "{home}/.local/pipx/venvs", "Tools installed with pipx."),
    ("Python", "Conda installation", "{home}/miniconda3", "Miniconda install incl. envs; `conda clean --all`."),
    ("Python", "Hugging Face cache", "{home}/.cache/huggingface", "Models/datasets; `hf cache scan` to review."),
    ("Python", "PyTorch hub cache", "{home}/.cache/torch", "Downloaded weights; re-downloaded on demand."),
    ("JS/Dev", "npm cache", "{home}/.npm", "`npm cache verify` / `npm cache clean --force`."),
    ("JS/Dev", "Yarn cache", "{caches}/Yarn", "`yarn cache clean`."),
    ("JS/Dev", "pnpm store", "{lib}/pnpm/store", "`pnpm store prune`."),
    ("JS/Dev", "Homebrew downloads", "{caches}/Homebrew", "`brew cleanup -s`."),
    ("JS/Dev", "Homebrew (Apple Silicon)", "/opt/homebrew", "`brew list`; `brew autoremove`."),
    ("JS/Dev", "Homebrew (Intel)", "/usr/local/Cellar", "`brew list`; `brew autoremove`."),
    ("JS/Dev", "CocoaPods cache", "{caches}/CocoaPods", "`pod cache clean --all`."),
    ("JS/Dev", "Xcode DerivedData", "{lib}/Developer/Xcode/DerivedData", "Build products; Xcode rebuilds them."),
    ("JS/Dev", "Xcode Archives", "{lib}/Developer/Xcode/Archives", "App archives; review before removing."),
    ("JS/Dev", "iOS device support", "{lib}/Developer/Xcode/iOS DeviceSupport", "Debug symbols per iOS version; old ones can go."),
    ("JS/Dev", "iOS Simulators", "{lib}/Developer/CoreSimulator", "`xcrun simctl delete unavailable`."),
    ("JS/Dev", "Xcode", "/Applications/Xcode.app", "Remove old Xcode versions you no longer use."),
    ("JS/Dev", "Gradle caches", "{home}/.gradle/caches", _CACHE),
    ("JS/Dev", "Maven repository", "{home}/.m2/repository", "Re-downloaded on demand."),
    ("JS/Dev", "Cargo registry", "{home}/.cargo/registry", "Re-downloaded on demand."),
    ("JS/Dev", "Rust toolchains", "{home}/.rustup/toolchains", "`rustup toolchain list`."),
    ("JS/Dev", "Go module cache", "{home}/go/pkg/mod", "`go clean -modcache`."),
    ("JS/Dev", "Android SDK", "{lib}/Android/sdk", "Remove unused images via SDK Manager."),
    ("JS/Dev", "Android emulators (AVD)", "{home}/.android/avd", "Delete unused AVDs in Device Manager."),
    ("JS/Dev", "VS Code extensions", "{home}/.vscode/extensions", "Old extension versions may linger."),
    ("JS/Dev", "VS Code workspaceStorage", "{support}/Code/User/workspaceStorage", "Per-folder state; grows forever."),
    ("JS/Dev", "JetBrains caches", "{caches}/JetBrains", "IDE caches/indexes; old IDE versions linger."),
    ("JS/Dev", "Docker Desktop data", "{lib}/Containers/com.docker.docker", "Prune inside Docker; the disk image only grows."),
    ("Browser", "Chrome profile", "{support}/Google/Chrome", "Clear cache in Chrome settings."),
    ("Browser", "Edge profile", "{support}/Microsoft Edge", "Clear cache in Edge settings."),
    ("Browser", "Brave profile", "{support}/BraveSoftware", "Clear cache in Brave settings."),
    ("Browser", "Firefox profiles", "{support}/Firefox/Profiles", "Cache lives under Caches/Firefox."),
    ("Apps", "Mail data and attachments", "{lib}/Mail", "Mail > Settings to limit downloads."),
    ("Apps", "Messages attachments", "{lib}/Messages", "Review attachments in Messages."),
    ("Apps", "iPhone / iPad backups", "{support}/MobileSync/Backup", "Manage in Finder > device > Manage Backups."),
    ("Apps", "Photos library", "{home}/Pictures/Photos Library.photoslibrary", "Managed by Photos; do not edit inside."),
    ("Apps", "Music library", "{home}/Music/Music", "Managed by Music."),
    ("Apps", "iCloud Drive (local copies)", "{lib}/Mobile Documents", "System Settings > Apple ID > iCloud to optimise storage."),
    ("Apps", "Slack data", "{support}/Slack", "Cache, Service Worker, IndexedDB."),
    ("Apps", "Discord data", "{support}/discord", "Cache folders regenerate."),
    ("Apps", "Spotify cache", "{caches}/com.spotify.client", "Set the cache size in Spotify."),
    ("Apps", "Zoom data", "{support}/zoom.us", "Recordings may live in Documents/Zoom."),
    ("VMs", "Parallels VMs", "{home}/Parallels", "VM disks."),
    ("VMs", "VMware Fusion VMs", "{home}/Virtual Machines.localized", "VM disks."),
    ("VMs", "UTM VMs", "{lib}/Containers/com.utmapp.UTM", "VM disks."),
    ("VMs", "VirtualBox VMs", "{home}/VirtualBox VMs", "VM disks."),
]

# (label, path template, advice). Text only.
SYSTEM_ITEMS = [
    ("System caches", "/Library/Caches", "Shared app caches; managed by macOS and apps."),
    ("Temporary items", "/private/var/folders", "Per-user temp and cache; cleared at reboot."),
    ("System logs", "/private/var/log", "Rotated automatically."),
    ("Software updates", "/Library/Updates", "Downloaded updates; installed or removed by macOS."),
    ("Virtual memory (swap)", "/private/var/vm", "Managed by macOS. Leave it."),
    ("Command Line Tools", "/Library/Developer/CommandLineTools", "`xcode-select --install` to reinstall; remove if Xcode is installed."),
    ("Shared app data", "/Library/Application Support", "Per-app data for all users."),
    ("Spotlight index", "/.Spotlight-V100", "If huge: `sudo mdutil -E /` to rebuild."),
    ("Applications", "/Applications", "Installed apps; drag to Trash to remove."),
    ("Other users", "/Users", "Home folders of all accounts."),
]

# SYSTEM_ITEMS labels that are leftovers the OS itself can clean ("quick wins")
STALE = {"System caches", "Temporary items", "Software updates"}
