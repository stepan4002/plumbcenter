"""Design tokens and QSS stylesheet generator for PlumbCenter (dark & light themes).

Single token table drives both themes so visual hierarchy, spacing, radii,
and Plumbnote brand accent (#79ccf3) stay consistent across every widget.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict


BRAND_ACCENT = "#79ccf3"


@dataclass(frozen=True)
class ThemeTokens:
    name: str
    # Surfaces
    bg_window: str
    bg_sidebar: str
    bg_surface: str
    bg_surface_alt: str
    bg_surface_hover: str
    bg_input: str
    bg_input_focus: str
    bg_code: str
    # Borders
    border_subtle: str
    border_default: str
    border_strong: str
    # Text
    text_primary: str
    text_secondary: str
    text_muted: str
    text_on_accent: str
    # Brand & accent
    accent: str
    accent_hover: str
    accent_pressed: str
    accent_soft: str
    accent_border: str
    # Semantic
    success: str
    success_soft: str
    warning: str
    warning_soft: str
    danger: str
    danger_soft: str
    info: str
    info_soft: str
    # Neutral badge
    neutral: str
    neutral_soft: str
    # Scrollbar
    scroll_handle: str
    scroll_handle_hover: str


DARK_TOKENS = ThemeTokens(
    name="dark",
    bg_window="#0f1117",
    bg_sidebar="#141821",
    bg_surface="#181d28",
    bg_surface_alt="#1d2432",
    bg_surface_hover="#232b3c",
    bg_input="#121620",
    bg_input_focus="#161b28",
    bg_code="#0b0e14",
    border_subtle="#222a3a",
    border_default="#2b3549",
    border_strong="#3b4863",
    text_primary="#f1f5f9",
    text_secondary="#cbd5e1",
    text_muted="#8b9ab0",
    text_on_accent="#09131c",
    accent="#79ccf3",
    accent_hover="#93d7f6",
    accent_pressed="#5bbce9",
    accent_soft="#162b38",
    accent_border="#2c5f78",
    success="#34d399",
    success_soft="#112b24",
    warning="#fbbf24",
    warning_soft="#2d2410",
    danger="#f87171",
    danger_soft="#311619",
    info="#79ccf3",
    info_soft="#162b38",
    neutral="#94a3b8",
    neutral_soft="#222a38",
    scroll_handle="#2f3a4f",
    scroll_handle_hover="#41506c",
)

LIGHT_TOKENS = ThemeTokens(
    name="light",
    bg_window="#f4f7fb",
    bg_sidebar="#eaf0f7",
    bg_surface="#ffffff",
    bg_surface_alt="#f8fafd",
    bg_surface_hover="#eef4fb",
    bg_input="#ffffff",
    bg_input_focus="#ffffff",
    bg_code="#f1f5f9",
    border_subtle="#e2e8f0",
    border_default="#cbd5e1",
    border_strong="#94a3b8",
    text_primary="#0f172a",
    text_secondary="#334155",
    text_muted="#64748b",
    text_on_accent="#ffffff",
    accent="#1686b8",
    accent_hover="#1174a1",
    accent_pressed="#0d6087",
    accent_soft="#e1f4fd",
    accent_border="#79ccf3",
    success="#059669",
    success_soft="#d1fae5",
    warning="#b45309",
    warning_soft="#fef3c7",
    danger="#dc2626",
    danger_soft="#fee2e2",
    info="#0284c7",
    info_soft="#e0f2fe",
    neutral="#475569",
    neutral_soft="#e2e8f0",
    scroll_handle="#cbd5e1",
    scroll_handle_hover="#94a3b8",
)

THEMES: Dict[str, ThemeTokens] = {
    "dark": DARK_TOKENS,
    "light": LIGHT_TOKENS,
}


def get_tokens(theme_name: str = "dark") -> ThemeTokens:
    """Return the token table for 'dark' or 'light' (defaults to dark)."""
    return THEMES.get((theme_name or "dark").lower(), DARK_TOKENS)


def build_stylesheet(theme_name: str = "dark") -> str:
    """Generate the complete application QSS from the theme token table."""
    t = get_tokens(theme_name)
    return f"""
/* === Global Base === */
QWidget {{
    color: {t.text_primary};
    font-family: "Segoe UI", "Inter", "SF Pro Text", "Helvetica Neue", Arial, sans-serif;
    font-size: 13px;
    selection-background-color: {t.accent};
    selection-color: {t.text_on_accent};
}}

QMainWindow, QDialog {{
    background-color: {t.bg_window};
}}

QWidget#centralRoot {{
    background-color: {t.bg_window};
}}

/* === Sidebar (Creative-Cloud style) === */
QFrame#sidebar {{
    background-color: {t.bg_sidebar};
    border-right: 1px solid {t.border_subtle};
}}

QLabel#brandTitle {{
    font-size: 16px;
    font-weight: 700;
    color: {t.text_primary};
    letter-spacing: -0.2px;
}}

QLabel#brandSubtitle {{
    font-size: 11px;
    color: {t.text_muted};
}}

QPushButton[navItem="true"] {{
    background-color: transparent;
    color: {t.text_secondary};
    border: 1px solid transparent;
    border-radius: 8px;
    padding: 9px 12px;
    text-align: left;
    font-size: 13px;
    font-weight: 500;
}}

QPushButton[navItem="true"]:hover {{
    background-color: {t.bg_surface_hover};
    color: {t.text_primary};
}}

QPushButton[navItem="true"][active="true"] {{
    background-color: {t.accent_soft};
    color: {t.accent};
    border: 1px solid {t.accent_border};
    font-weight: 600;
}}

QFrame#sidebarDivider {{
    background-color: {t.border_subtle};
    max-height: 1px;
    min-height: 1px;
}}

/* === Page Headers & Typography === */
QLabel[role="pageTitle"] {{
    font-size: 22px;
    font-weight: 700;
    color: {t.text_primary};
    letter-spacing: -0.3px;
}}

QLabel[role="pageSubtitle"] {{
    font-size: 13px;
    color: {t.text_muted};
}}

QLabel[role="sectionTitle"] {{
    font-size: 15px;
    font-weight: 600;
    color: {t.text_primary};
}}

QLabel[role="muted"] {{
    font-size: 12px;
    color: {t.text_muted};
}}

QLabel[role="cardTitle"] {{
    font-size: 15px;
    font-weight: 700;
    color: {t.text_primary};
}}

QLabel[role="cardBody"] {{
    font-size: 12px;
    color: {t.text_secondary};
}}

QLabel[role="mono"] {{
    font-family: "Cascadia Code", "Consolas", "JetBrains Mono", monospace;
    font-size: 12px;
    color: {t.text_secondary};
}}

/* === Cards & Panels === */
QFrame[card="true"] {{
    background-color: {t.bg_surface};
    border: 1px solid {t.border_subtle};
    border-radius: 12px;
}}

QFrame[card="true"]:hover {{
    border: 1px solid {t.border_strong};
}}

QFrame[panel="true"] {{
    background-color: {t.bg_surface};
    border: 1px solid {t.border_subtle};
    border-radius: 10px;
}}

QFrame[subpanel="true"] {{
    background-color: {t.bg_surface_alt};
    border: 1px solid {t.border_subtle};
    border-radius: 8px;
}}

/* === Buttons === */
QPushButton {{
    background-color: {t.bg_surface_alt};
    color: {t.text_primary};
    border: 1px solid {t.border_default};
    border-radius: 7px;
    padding: 6px 12px;
    font-weight: 500;
    min-height: 20px;
}}

QPushButton:hover {{
    background-color: {t.bg_surface_hover};
    border-color: {t.border_strong};
}}

QPushButton:pressed {{
    background-color: {t.bg_input};
}}

QPushButton:disabled {{
    color: {t.text_muted};
    background-color: {t.bg_surface_alt};
    border-color: {t.border_subtle};
}}

QPushButton[variant="primary"] {{
    background-color: {t.accent};
    color: {t.text_on_accent};
    border: 1px solid {t.accent};
    font-weight: 600;
}}

QPushButton[variant="primary"]:hover {{
    background-color: {t.accent_hover};
    border-color: {t.accent_hover};
}}

QPushButton[variant="primary"]:pressed {{
    background-color: {t.accent_pressed};
    border-color: {t.accent_pressed};
}}

QPushButton[variant="primary"]:disabled {{
    background-color: {t.neutral_soft};
    color: {t.text_muted};
    border-color: {t.border_subtle};
}}

QPushButton[variant="danger"] {{
    background-color: {t.danger_soft};
    color: {t.danger};
    border: 1px solid {t.danger};
    font-weight: 600;
}}

QPushButton[variant="danger"]:hover {{
    background-color: {t.danger};
    color: #ffffff;
}}

QPushButton[variant="ghost"] {{
    background-color: transparent;
    color: {t.text_secondary};
    border: 1px solid transparent;
    padding: 5px 9px;
}}

QPushButton[variant="ghost"]:hover {{
    background-color: {t.bg_surface_hover};
    color: {t.text_primary};
}}

QPushButton[size="sm"] {{
    padding: 4px 9px;
    font-size: 12px;
    min-height: 16px;
    border-radius: 6px;
}}

/* === Inputs === */
QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QTextEdit {{
    background-color: {t.bg_input};
    color: {t.text_primary};
    border: 1px solid {t.border_default};
    border-radius: 7px;
    padding: 5px 10px;
    min-height: 20px;
}}

QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus {{
    background-color: {t.bg_input_focus};
    border: 1px solid {t.accent};
}}

QLineEdit:disabled, QComboBox:disabled {{
    background-color: {t.bg_surface_alt};
    color: {t.text_muted};
    border-color: {t.border_subtle};
}}

QComboBox::drop-down {{
    border: none;
    width: 24px;
}}

QComboBox QAbstractItemView {{
    background-color: {t.bg_surface};
    color: {t.text_primary};
    border: 1px solid {t.border_default};
    selection-background-color: {t.accent_soft};
    selection-color: {t.accent};
    outline: none;
}}

QCheckBox {{
    spacing: 8px;
    color: {t.text_primary};
}}

QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 1px solid {t.border_strong};
    background-color: {t.bg_input};
}}

QCheckBox::indicator:checked {{
    background-color: {t.accent};
    border-color: {t.accent};
}}

/* === Badges === */
QLabel[badge="true"] {{
    border-radius: 9px;
    padding: 2px 8px;
    font-size: 11px;
    font-weight: 600;
}}

QLabel[badgeTone="success"] {{
    background-color: {t.success_soft};
    color: {t.success};
    border: 1px solid {t.success};
}}

QLabel[badgeTone="warning"] {{
    background-color: {t.warning_soft};
    color: {t.warning};
    border: 1px solid {t.warning};
}}

QLabel[badgeTone="danger"] {{
    background-color: {t.danger_soft};
    color: {t.danger};
    border: 1px solid {t.danger};
}}

QLabel[badgeTone="info"] {{
    background-color: {t.info_soft};
    color: {t.info};
    border: 1px solid {t.accent_border};
}}

QLabel[badgeTone="neutral"] {{
    background-color: {t.neutral_soft};
    color: {t.neutral};
    border: 1px solid {t.border_default};
}}

/* === Scroll Areas & Scrollbars === */
QScrollArea {{
    background-color: transparent;
    border: none;
}}

QScrollArea > QWidget > QWidget {{
    background-color: transparent;
}}

QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px;
}}

QScrollBar::handle:vertical {{
    background: {t.scroll_handle};
    border-radius: 4px;
    min-height: 28px;
}}

QScrollBar::handle:vertical:hover {{
    background: {t.scroll_handle_hover};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: none;
    height: 0px;
}}

QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 2px;
}}

QScrollBar::handle:horizontal {{
    background: {t.scroll_handle};
    border-radius: 4px;
    min-width: 28px;
}}

QScrollBar::handle:horizontal:hover {{
    background: {t.scroll_handle_hover};
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal,
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    background: none;
    width: 0px;
}}

/* === Tables & Log View === */
QTableWidget {{
    background-color: {t.bg_surface};
    alternate-background-color: {t.bg_surface_alt};
    gridline-color: {t.border_subtle};
    border: 1px solid {t.border_subtle};
    border-radius: 8px;
    outline: none;
}}

QHeaderView::section {{
    background-color: {t.bg_surface_alt};
    color: {t.text_muted};
    border: none;
    border-bottom: 1px solid {t.border_subtle};
    padding: 7px 10px;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
}}

QPlainTextEdit#logOutput {{
    background-color: {t.bg_code};
    color: {t.text_primary};
    border: 1px solid {t.border_subtle};
    border-radius: 8px;
    font-family: "Cascadia Code", "Consolas", "JetBrains Mono", monospace;
    font-size: 12px;
    padding: 8px;
}}

/* === Toast === */
QFrame[toast="true"] {{
    background-color: {t.bg_surface};
    border: 1px solid {t.border_strong};
    border-radius: 10px;
}}

QFrame[toastTone="success"] {{
    border-left: 4px solid {t.success};
}}

QFrame[toastTone="warning"] {{
    border-left: 4px solid {t.warning};
}}

QFrame[toastTone="danger"] {{
    border-left: 4px solid {t.danger};
}}

QFrame[toastTone="info"] {{
    border-left: 4px solid {t.accent};
}}

/* === Status Bar & Tooltips === */
QFrame#statusBar {{
    background-color: {t.bg_sidebar};
    border-top: 1px solid {t.border_subtle};
}}

QToolTip {{
    background-color: {t.bg_surface};
    color: {t.text_primary};
    border: 1px solid {t.border_strong};
    border-radius: 6px;
    padding: 5px 8px;
    font-size: 12px;
}}

QProgressBar {{
    background-color: {t.bg_input};
    border: 1px solid {t.border_subtle};
    border-radius: 4px;
    max-height: 6px;
    text-align: center;
}}

QProgressBar::chunk {{
    background-color: {t.accent};
    border-radius: 3px;
}}
"""
