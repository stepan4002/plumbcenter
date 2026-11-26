# Shared providers contract

PlumbCenter writes `~/.plumbnote/providers.json` (override the folder with `PLUMBNOTE_HOME`).
Other Plumbnote apps only read it.

```json
{"version": 1,
 "providers": {"openai": {"enabled": true, "base_url": "https://api.openai.com/v1",
                          "default_model": "gpt-4.1-mini", "secret": "keyring"}},
 "defaults": {"plumbdoctor": "openai"}}
```

- `defaults[app_id]` is the provider an app should prefer; fall back to the first enabled provider.
- **The API key is never in this file.** Read it from the OS keyring: service `plumbnote`,
  username = the provider id (for example `openai`). On Windows without a usable keyring
  backend, PlumbCenter uses a per-user DPAPI file in the same folder.
- Apps must treat a missing or malformed file as "no providers configured".
- `version` is 1. Readers should ignore unknown fields.

Verified against the sibling checkouts: PlumbDoctor and PlumbStudio use keyring service
`plumbnote` and the same provider ids; PlumbGate reads names and models only; PlumbCode reads
the file in `plumbcode wizard`; PlumbScout has no integration yet.
