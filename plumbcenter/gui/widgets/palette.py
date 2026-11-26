"""Command palette (Ctrl+K): type to filter, Up/Down to move, Enter to run, Esc to close."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional, Sequence

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout, QWidget


@dataclass(frozen=True)
class Command:
    title: str
    run: Callable[[], None]
    hint: str = ""                  # e.g. "Go to", "Theme", shown dimmed after the title
    keywords: str = ""              # extra searchable text


def fuzzy_score(query: str, text: str) -> Optional[int]:
    """Lower is better; None when `query` is not a subsequence of `text`. Substring beats scattered."""
    q, t = query.lower().strip(), text.lower()
    if not q:
        return 0
    idx = t.find(q)
    if idx >= 0:
        return idx                                   # contiguous match: earlier is better
    pos, gaps = -1, 0
    for ch in q:
        nxt = t.find(ch, pos + 1)
        if nxt < 0:
            return None
        gaps += nxt - pos - 1 if pos >= 0 else nxt
        pos = nxt
    return 1000 + gaps


def filter_commands(commands: Sequence[Command], query: str) -> List[Command]:
    scored = []
    for i, c in enumerate(commands):
        s = fuzzy_score(query, c.title)
        if s is None:                                # fall back to hint/keywords, ranked below title hits
            extra = fuzzy_score(query, f"{c.hint} {c.keywords}")
            s = None if extra is None else 5000 + extra
        if s is not None:
            scored.append((s, i, c))
    scored.sort(key=lambda x: (x[0], x[1]))
    return [c for _, _, c in scored]


class CommandPalette(QDialog):
    def __init__(self, commands: Sequence[Command], parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._commands = list(commands)
        self._shown: List[Command] = []
        self.setWindowTitle("Command palette")
        self.setModal(True)
        self.setMinimumWidth(520)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(8)
        self.input = QLineEdit(self)
        self.input.setAccessibleName("Command search")
        self.input.setPlaceholderText("Type a command...")
        self.input.setClearButtonEnabled(True)
        self.input.textChanged.connect(self._refilter)
        self.input.installEventFilter(self)
        lay.addWidget(self.input)
        self.list = QListWidget(self)
        self.list.setAccessibleName("Commands")
        self.list.itemActivated.connect(lambda _i: self.run_current())
        self.list.itemClicked.connect(lambda _i: self.run_current())
        lay.addWidget(self.list)
        self._refilter("")

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if obj is self.input and event.type() == event.Type.KeyPress:
            key = event.key()
            if key in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                step = 1 if key == Qt.Key.Key_Down else -1
                n = self.list.count()
                if n:
                    self.list.setCurrentRow((self.list.currentRow() + step) % n)
                return True
        return super().eventFilter(obj, event)

    def _refilter(self, query: str) -> None:
        self._shown = filter_commands(self._commands, query)
        self.list.clear()
        for c in self._shown:
            label = f"{c.title}    ·  {c.hint}" if c.hint else c.title
            self.list.addItem(QListWidgetItem(label))
        if self._shown:
            self.list.setCurrentRow(0)

    def visible_titles(self) -> List[str]:
        return [c.title for c in self._shown]

    def run_current(self) -> None:
        row = self.list.currentRow()
        if not 0 <= row < len(self._shown):
            return
        cmd = self._shown[row]
        self.accept()
        cmd.run()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.run_current()
            return
        super().keyPressEvent(event)
