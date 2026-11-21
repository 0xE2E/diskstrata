# Cross-platform support and public release

Status: accepted. Decided by the owner (0xE2E) on 2026-11-21.

## Goal

Anyone can download DiskStrata and, on Windows, Linux or macOS, see what is using their disk space,
with strong guarantees: read-only, local only, no dependencies, easy to audit. The owner keeps
control over commercial use.

## Decisions

| Topic | Choice | Why | Revisit when |
|---|---|---|---|
| Dependencies | Python standard library only | One thing to audit; `pipx install` just works | A needed capability has no stdlib route (for example reliable macOS volume names) |
| License | PolyForm Noncommercial 1.0.0 (text read from the upstream repository at tag 1.0.0) | Standard, reviewed text; permits personal and noncommercial-organisation use, everything else needs approval | The owner wants a dual-license commercial offer |
| Wording | "source-available", never "open source" | The OSI definition forbids field-of-use limits | The license changes |
| Name | DiskStrata | No exact-name collisions in a GitHub name search; "strata" describes the layered folder tree | A trademark conflict appears |
| Elevation | UAC (Windows), pkexec (Linux), osascript (macOS); the app restarts itself on the same port | No separate privileged helper; the user approves at the OS prompt | A native installer is built |
| Scan accounting | Allocated size and one count per hard link on Linux/macOS; logical size on Windows | Matches `df` (0.5 % on a real Ubuntu root); Windows `scandir` exposes no inode numbers | Windows gains cheap link information |
| Walking other filesystems | Never: every other mount point is pruned | Other volumes are scanned separately; avoids double counting | A user wants cross-mount totals |
| Local security | Session cookie from the launch link, loopback Host check, API token, nonce-only scripts | Other local accounts and other web pages cannot drive the server | The server is ever exposed beyond loopback (it should not be) |

## Considered and rejected

- **Walking more levels on the calling thread to balance the thread pool** (suggested in review).
  Measured on the same machine: depth 3 took 22-25 s against 4-5 s at depth 1 on Linux, and was
  slightly slower on Windows. Kept depth 1. Look again only with dynamic work splitting.
- **psutil for volume listing.** Not needed: Win32, `/proc/self/mounts` and `mount` cover it.

## Verified this session

- PolyForm Noncommercial 1.0.0 text: https://raw.githubusercontent.com/polyformproject/polyform-licenses/1.0.0/PolyForm-Noncommercial-1.0.0.md
- Windows `DirEntry.stat()` exposes `st_reparse_tag` (junction tag 0xA0000003); name-surrogate bit 0x20000000.
- Linux: scan of an Ubuntu 24.04 root filesystem: 57.2 GB found, `df` reports 57.5 GB used.

## Not verified (known limits)

- macOS has no hardware test: covered by GitHub-hosted macOS runners only.
- The UAC / polkit / osascript prompts themselves cannot be automated. The hand-off around them
  (secret file, announce flag, same-port take-over, cookie continuity) is tested on Windows and Linux.
- OneDrive Files-On-Demand folders are walked because only name-surrogate reparse points are skipped;
  there was no OneDrive on the development machine to confirm.
