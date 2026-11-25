"""Static registry of Plumbnote open-source apps (the single source of truth).

Pure data, no I/O. Every other module imports from here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple

GITHUB_OWNER = "stepan4002"


@dataclass(frozen=True)
class Action:
    """Something the hub can do with an installed app.

    kind "run":   short-lived command; hub waits and captures output.
    kind "serve": long-lived process; hub starts it detached and tracks its PID.
    argv placeholders: "{python}" -> sys.executable. Other executables (node,
    npm) are resolved with shutil.which by the runner. Never run via a shell.
    """

    name: str                       # e.g. "demo", "studio"
    label: str
    kind: str                       # "run" | "serve"
    argv: Tuple[str, ...]
    ok_exit_codes: Tuple[int, ...] = (0,)
    url_pattern: Optional[str] = None   # regex for the public URL shown in status/UI
    launch_pattern: Optional[str] = None  # regex for a private launch link (may hold a token); only used by `open`, never shown
    requires: Tuple[str, ...] = ()      # executables that must be on PATH


@dataclass(frozen=True)
class AppSpec:
    id: str
    name: str
    tagline: str
    stage: str                      # "released" | "preview" | "design"
    dir_names: Tuple[str, ...]      # candidate local directory names, first = clone target
    actions: Tuple[Action, ...] = ()
    version_file: Optional[str] = None  # JSON file with a "version" key, e.g. package.json

    @property
    def repo(self) -> str:
        return f"{GITHUB_OWNER}/{self.id}"

    @property
    def clone_url(self) -> str:
        return f"https://github.com/{self.repo}.git"

    @property
    def web_url(self) -> str:
        return f"https://github.com/{self.repo}"

    def action(self, name: str) -> Optional[Action]:
        return next((a for a in self.actions if a.name == name), None)


def _demo() -> Action:
    return Action("demo", "Run demo", "run", ("{python}", "demo/run.py"), requires=("python",))


REGISTRY: Tuple[AppSpec, ...] = (
    AppSpec(
        "plumbcheck", "PlumbCheck", "Local regression tests for what your AI agent does.",
        "released", ("plumbcheck", "plumcheck"), version_file="package.json",
        actions=(
            # The PlumbCheck demo exits 1 on purpose (it demonstrates caught regressions).
            Action("demo", "Run demo", "run", ("node", "bin/plumbcheck.js", "demo"),
                   ok_exit_codes=(0, 1), requires=("node",)),
            Action("studio", "Start Studio", "serve", ("node", "bin/plumbcheck.js", "studio"),
                   url_pattern=r"https?://(?:127\.0\.0\.1|localhost):\d+",
                   launch_pattern=r"https?://(?:127\.0\.0\.1|localhost):\d+/#auth=[0-9a-fA-F]+",
                   requires=("node",)),
        ),
    ),
    AppSpec("plumbcode", "PlumbCode", "Hand a coding task between AI subscriptions in one Git workspace.",
            "design", ("plumbcode",)),
    AppSpec("plumbdoctor", "PlumbDoctor", "Failure diagnosis for automation workflows.",
            "preview", ("plumbdoctor",), actions=(_demo(),)),
    AppSpec("plumbgate", "PlumbGate", "An approval policy for agent tool calls.",
            "preview", ("plumbgate",), actions=(_demo(),)),
    AppSpec("plumbscout", "PlumbScout", "Structured extraction and change detection.",
            "preview", ("plumbscout",), actions=(_demo(),)),
    AppSpec("plumbstudio", "PlumbStudio", "A draft and approval workflow for marketing teams.",
            "preview", ("plumbstudio",), actions=(_demo(),)),
    AppSpec("plumbbridge", "PlumbBridge", "OpenAPI operations as agent tools.",
            "preview", ("plumbbridge",), actions=(_demo(),)),
)


def get_app(app_id: str) -> Optional[AppSpec]:
    app_id = app_id.strip().lower()
    return next((a for a in REGISTRY if a.id == app_id), None)
