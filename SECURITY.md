# Security Policy

## Supported versions

Security fixes go to the latest released version of PlumbCenter.

## Reporting a vulnerability

Please do not open a public issue for a security problem. Use GitHub's private reporting:
**Security → Report a vulnerability** on <https://github.com/stepan4002/plumbcenter/security/advisories/new>.

Include the version, what you did, and what you expected. Expect an acknowledgement within a few days.
Please give us a reasonable time to fix the issue before you disclose it.

## What PlumbCenter does with sensitive data

- **API keys** are stored in the OS keyring (DPAPI per-user file fallback on Windows). They are never
  written to `~/.plumbnote/providers.json`, logs, or test output.
- **Network use** is limited to: the provider connection test and health ping (sent only to the host of the
  provider's configured base URL; redirects to another host are refused), and the GitHub Releases check and
  asset download (HTTPS to GitHub hosts only; redirects off GitHub are refused).
- **Downloads are never run.** The updater saves a release asset to the hub's downloads folder and verifies
  its SHA-256 when GitHub or a `.sha256` file publishes one. You run it yourself.
- **No listener.** The hub opens no network port. Apps you start from it own their own ports.
- **Logs** of apps you start can contain private launch links. Treat the log viewer as sensitive.

## In scope

Key leakage, path traversal in install/update, command injection through the registry or app output,
unsafe handling of downloaded files, and anything that lets a remote host receive a key it should not.

## Out of scope

Vulnerabilities in the sibling Plumbnote apps themselves (report those in their own repositories),
and attacks that need an already-compromised user account or machine.
