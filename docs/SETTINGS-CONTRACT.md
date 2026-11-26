# Shared settings contract

File: `settings.json` in `PLUMBNOTE_HOME` (default `~/.plumbnote`), next to `providers.json`.

```json
{ "version": 1, "theme": "dark" }
```

| Key | Values | Owner |
| --- | --- | --- |
| `version` | `1` | PlumbCenter |
| `theme` | `"dark"` or `"light"` | any Plumbnote desktop app |

Rules for every app that reads or writes the file:

1. Write atomically (temp file, then rename) and **keep keys you do not own**.
2. Never put secrets in it.
3. Ignore a missing, unreadable, or invalid file; fall back to your own saved setting.
4. To follow theme changes live, watch the file's modification time (PlumbCenter polls once a second)
   and re-read it only when it changes. Apply the theme without writing it back.
5. Namespace any app-specific keys under your app id (for example `"plumbstudio": {...}`).

PlumbCenter writes `theme` when you switch Dark/Light and adopts a different value written by another app.
It does not know which sibling apps implement this contract; until a sibling reads `settings.json`
it keeps its own theme.
