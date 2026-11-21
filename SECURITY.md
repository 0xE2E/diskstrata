# Security policy

DiskStrata runs a small web server on `127.0.0.1` and, only when you ask, restarts itself with
administrator or root rights. Reports of vulnerabilities in either are taken seriously.

## Reporting

Please use GitHub's private vulnerability reporting
(Security tab > "Report a vulnerability") instead of a public issue.
Include the version (`diskstrata --version`), your OS, and steps to reproduce.

## Scope

In scope: the local server (token, Host-header and CSP handling), report generation (anything that lets
file names or paths inject script into a report), the elevation hand-off, and any case where a scan could
modify, delete or upload data.

Out of scope: attacks that already require code execution as your user, and the contents of your own
reports being visible to other accounts that can read your data folder.

## Design guarantees you can check in the code

- Scanning only calls `os.scandir` / `stat`. Nothing writes outside the DiskStrata data folder.
- The only network socket is the listener on `127.0.0.1`. There is no outbound traffic.
- Actions that change state require a per-run random token and a loopback `Host` header.
- Report data is embedded with `<` escaped, and pages are served with a restrictive Content-Security-Policy.
