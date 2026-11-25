"""HOK ACE Language Patcher: English or Indonesian translation for a USB-connected Android phone or the PC game.

The window has two targets: *Phone over USB* drives `patcher_core`, *PC game on this computer* drives
`pc_edition`, whose jobs run in a child process (`--pc-job`) that this window polls.
"""
from __future__ import annotations

import ctypes
import json
import tkinter
import tkinter.filedialog as filedialog
import queue
import subprocess
import sys
import threading
import time
import traceback
from pathlib import Path
from typing import Callable

import customtkinter as ctk
from PIL import Image

from patcher_core import (BUNDLE, MIN_FREE_BYTES, SETTINGS, STEPS, Adb, PatchError, Patcher, build_patch,
                          count_translated, count_untranslated_graphics, count_untranslated_text, free_space,
                          holds_delta, languages, load_language, load_work_dir, save_language, save_work_dir,
                          set_interface_language, ui_text)
from patcher_core import NOTHING_TO_RECOVER, discover_pending_runs
import pc_edition  # noqa: E402 - after patcher_core, which puts tools/ and the runtime on sys.path

APP_TITLE = "HOK ACE Language Patcher"
VERSION_FILE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1])) / "VERSION"
APP_VERSION = VERSION_FILE.read_text(encoding="utf-8").strip()
FONTS = BUNDLE / "fonts"

# DESIGN.md tokens, from resources/ui/theme.json.
THEME = json.loads((BUNDLE / "ui" / "theme.json").read_text(encoding="utf-8"))
COLORS = THEME["colors"]
# Tk uses opaque surfaces, with the dark end of the atmospheric gradient as the page.
PAGE = COLORS["page-top"]
SURFACE = COLORS["surface"]
SUBTLE = COLORS["surface-subtle"]
SUCCESS = COLORS["success"]
SUCCESS_SURFACE = COLORS["success-surface"]
WARNING_SURFACE = COLORS["warning-surface"]
CARD = COLORS["card-solid"]
CARD_EDGE = COLORS["card-edge"]
INK = COLORS["ink"]
MUTED = COLORS["text-muted"]
PANEL_TOP = COLORS["panel-top"]
PANEL_BOTTOM = COLORS["panel-bottom"]
ON_PANEL = COLORS["on-panel"]
ON_PANEL_MUTED = COLORS["on-panel-muted"]
CONFIRM_RIGHT = COLORS["confirm-right"]
WARNING = COLORS["warning"]
ERROR = COLORS["error"]
ERROR_SURFACE = COLORS["error-surface"]
DISABLED_FILL = COLORS["disabled-fill"]
DISABLED_TEXT = COLORS["disabled-text"]
RADIUS = int(THEME["rounded"]["card"].removesuffix("px"))
BUTTON_RADIUS = int(THEME["rounded"]["button"].removesuffix("px"))
SPACE = {name: int(value.removesuffix("px")) for name, value in THEME["spacing"].items()}

CARD_PAD = SPACE["lg"]
WRAP = 360
BUTTON_HEIGHT = 44
LOG_HEIGHT = 170
PC_GEOMETRY = "1040x660"
PC_TWO_COLUMNS = 740

# Tk family names and weights as GDI exposes the bundled faces.
TK_FONTS = {
    ("Commissioner", 400): ("Commissioner", "normal"),
    ("Commissioner", 600): ("Commissioner SemiBold", "normal"),
    ("Ace Heading", 700): ("Ace Heading", "bold"),
    ("Barlow Condensed", 800): ("Barlow Condensed ExtraBold", "normal"),
    ("Fragment Mono", 400): ("Fragment Mono", "normal"),
}
FONT_FILES = {
    ("Commissioner", 400): "Commissioner-Regular.ttf",
    ("Commissioner", 600): "Commissioner-SemiBold.ttf",
    ("Ace Heading", 700): "AceHeading-Bold.ttf",
    ("Barlow Condensed", 800): "BarlowCondensed-ExtraBold.ttf",
    ("Fragment Mono", 400): "FragmentMono-Regular.ttf",
}
FR_PRIVATE = 0x10

# The two targets of the target choice, and the settings key that remembers the last one.
PHONE, PC = "phone", "pc"
TARGET_KEY = "target"
# How often the window polls a PC job's child and tails its log, in ms.
PC_TICK = 500
# A failed job these keys name left the game as it was, so no Check follows it.
PC_NO_FOLLOW_UP = ("pc_close_game", "pc_game_folder_invalid", "pc_catalog_missing")


def load_target() -> str:
    """The target the window last showed; the phone when none was saved."""
    try:
        value = json.loads(SETTINGS.read_text(encoding="utf-8")).get(TARGET_KEY)
    except (OSError, ValueError, AttributeError):
        return PHONE
    return value if value in (PHONE, PC) else PHONE


def save_target(target: str) -> None:
    try:
        data = json.loads(SETTINGS.read_text(encoding="utf-8"))
        data = data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        data = {}
    try:
        SETTINGS.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS.write_text(json.dumps({**data, TARGET_KEY: target}), encoding="utf-8")
    except OSError:
        pass  # the choice still applies for this session


def _elapsed(seconds: float) -> str:
    """Seconds as m:ss, or h:mm:ss from an hour."""
    minutes, secs = divmod(int(seconds), 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def _type(kind: str) -> tuple[tuple[str, int], int, float]:
    """The (family, weight) key, pixel size and letter spacing (em) of a DESIGN.md type step."""
    spec = THEME["typography"][kind]
    spacing = float(spec.get("letterSpacing", "0em").removesuffix("em"))
    return (spec["fontFamily"], int(spec["fontWeight"])), int(spec["fontSize"].removesuffix("px")), spacing


def _font(kind: str) -> ctk.CTkFont:
    key, size, _ = _type(kind)
    family, weight = TK_FONTS[key]
    return ctk.CTkFont(family=family, size=size, weight=weight)


def load_fonts() -> None:
    """Make the bundled fonts available to this process only; nothing is installed."""
    for path in sorted(FONTS.glob("*.ttf")):
        try:
            ctypes.windll.gdi32.AddFontResourceExW(str(path), FR_PRIVATE, 0)
        except (AttributeError, OSError):
            pass  # Tk falls back to the system font


def _size(count: int) -> str:
    """A measured byte count as the player reads it: MB below 1 GB, then GB with one decimal."""
    if count < 1024**3:
        return f"{count / 1024**2:.0f} MB"
    return f"{count / 1024**3:.1f} GB"


def _rgb(color: str) -> tuple[int, int, int]:
    return int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)


def _mix(color: str, over: str, alpha: float) -> str:
    """<color> at <alpha> over <over>, as #RRGGBB."""
    a, b = _rgb(color), _rgb(over)
    return "#" + "".join(f"{round(x * alpha + y * (1 - alpha)):02X}" for x, y in zip(a, b))


# (fill, hover, text, edge) of each button role in DESIGN.md's colour roles.
BUTTONS = {
    "primary": (PANEL_BOTTOM, PANEL_TOP, ON_PANEL, PANEL_BOTTOM),
    "secondary": (SURFACE, SUBTLE, INK, COLORS["outline"]),
    "danger": (ERROR, _mix(ERROR, PANEL_BOTTOM, 0.85), ON_PANEL, ERROR),
}


def _make_button(master: ctk.CTkBaseClass, role: str, command: Callable[[], None], height: int = BUTTON_HEIGHT,
                 **options) -> ctk.CTkButton:
    button = ctk.CTkButton(master, height=height, corner_radius=BUTTON_RADIUS, border_width=2, font=_font("button"),
                           text_color_disabled=DISABLED_TEXT, command=command, **options)
    _style_button(button, role, True)

    def activate(_event: tkinter.Event) -> str:
        if button.cget("state") == "normal":
            button.invoke()
        return "break"

    def focus(event: tkinter.Event) -> None:
        if button.cget("state") != "normal":
            return
        fill = button.cget("fg_color")
        current_role = next(name for name, colors in BUTTONS.items() if colors[0] == fill)
        edge = BUTTONS[current_role][3]
        indicator = PANEL_TOP if current_role == "secondary" else CONFIRM_RIGHT
        button.configure(border_color=indicator if event.type == tkinter.EventType.FocusIn else edge)

    for key in ("<space>", "<Return>"):
        tkinter.Misc.bind(button, key, activate)
    for event in ("<FocusIn>", "<FocusOut>"):
        tkinter.Misc.bind(button, event, focus)
    return button


def _style_button(button: ctk.CTkButton, role: str, enabled: bool) -> None:
    """Enable or disable <button>; a disabled one takes the disabled colours, never only a dimmer look."""
    fill, hover, text, edge = BUTTONS[role]
    if enabled:
        button.configure(state="normal", fg_color=fill, hover_color=hover, text_color=text, border_color=edge)
    else:
        button.configure(state="disabled", fg_color=DISABLED_FILL, border_color=DISABLED_FILL)
    tkinter.Frame.configure(button, takefocus=int(enabled))
    if enabled and button.focus_get() == button:
        button.configure(border_color=PANEL_TOP if role == "secondary" else CONFIRM_RIGHT)


class Dialog(ctk.CTkToplevel):
    """Light confirmation surface with a clearly marked destructive action when needed."""

    WIDTH = 468

    def __init__(self, master, title: str, message: str, confirm: bool, danger: bool, confirm_label: str | None):
        super().__init__(master, fg_color=CARD)
        self.title(title)
        self.resizable(False, False)
        self.result = False
        self.transient(master)
        for content, style, color in ((title, "heading", INK), (message, "body", MUTED)):
            ctk.CTkLabel(self, text=content, font=_font(style), text_color=color, anchor="w",
                         justify="left", wraplength=self.WIDTH - 2 * SPACE["xl"]).pack(
                fill="x", padx=SPACE["xl"], pady=(SPACE["md"], 0))
        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.pack(fill="x", padx=SPACE["xl"], pady=SPACE["xl"])
        label = confirm_label or ui_text("continue" if confirm else "ok")
        if confirm:
            cancel = _make_button(buttons, "secondary", self.destroy, text=ui_text("cancel"), width=110)
            cancel.pack(side="left")
        accept = _make_button(buttons, "danger" if danger else "primary", self._ok, text=label, width=140)
        accept.pack(side="right")
        self.bind("<Escape>", lambda _event: self.destroy())
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.after(50, self._center)

    def _center(self) -> None:
        self.update_idletasks()
        master = self.master
        x = master.winfo_rootx() + (master.winfo_width() - self.winfo_width()) // 2
        y = master.winfo_rooty() + (master.winfo_height() - self.winfo_height()) // 3
        self.geometry(f"+{x}+{y}")
        self.grab_set()
        self.focus_force()

    def _ok(self) -> None:
        self.result = True
        self.destroy()

    @classmethod
    def show(cls, master, title: str, message: str, confirm: bool = False, danger: bool = False,
             confirm_label: str | None = None) -> bool:
        dialog = cls(master, title, message, confirm, danger, confirm_label)
        master.wait_window(dialog)
        return dialog.result


class App(ctk.CTk):
    def __init__(self) -> None:
        super().__init__(fg_color=PAGE)
        self.title(APP_TITLE)
        self.geometry(PC_GEOMETRY)
        self.minsize(560, 520)
        icon = BUNDLE / "icon.ico"
        if icon.exists():
            self.iconbitmap(str(icon))
        self.messages: queue.Queue = queue.Queue()
        self.busy = False
        self.worker_thread: threading.Thread | None = None
        self.control_threads: list[threading.Thread] = []
        self.patcher: Patcher | None = None
        self.closing = False
        self.stopping = False
        self.stop_saved = False
        self.pending_stop = False
        self.pending_work = False
        # The durable runs discovery found (`discover_pending_runs`): the attention state's one action reads them.
        self.pending_runs: list[dict] = []
        self.run_state: dict = {}
        self.step_detail = ""
        self.ui_cancel = threading.Event()
        self.removing = False
        self.work_dir = load_work_dir()
        self.language = load_language()
        set_interface_language(self.language)
        # Every text that follows the interface language, redrawn at once when it changes.
        self.texts: list[tuple[ctk.CTkBaseClass, Callable[[], str]]] = []
        # The step running (index into STEPS) and the last result, which ② draws itself from.
        self.step_index: int | None = None
        self.result: tuple[str, object] | None = None
        self.connected = False
        self.usb_status: str | None = None
        self.usb_probe: threading.Thread | None = None
        self.blocker = ""
        # The PC target: the game root, the running child job, Check's last state and the last job's result.
        self.target = load_target()
        self.pc_game: Path | None = None
        self.pc_job = None
        self.pc_action = ""
        self.pc_answer: Path | None = None
        self.pc_log_offset = 0
        self.pc_started = 0.0
        self.pc_follow_up = False
        self.pc_state: str | None = None
        self.pc_language: str | None = None
        self.pc_version: str | None = None
        self.pc_recoverable = False
        self.pc_result: tuple[str, float] | None = None
        self.pc_error: PatchError | None = None
        self.pc_opened = False

        self.page = page = ctk.CTkScrollableFrame(self, fg_color=PAGE, corner_radius=0,
                                                  scrollbar_button_color=CARD_EDGE,
                                                  scrollbar_button_hover_color=DISABLED_TEXT)
        page.pack(fill="both", expand=True)
        page.columnconfigure(0, weight=1)
        self.column = ctk.CTkFrame(page, fg_color="transparent")
        self.column.grid(row=0, column=0, sticky="ew", padx=SPACE["md"],
                         pady=(SPACE["md"], SPACE["section"]))
        self.column.columnconfigure(0, weight=1)
        self._build_header()
        self._build_start()
        self._build_pc()
        self._build_error()
        self._build_log()
        self.device_label.configure(text=ui_text("device_not_connected"))
        self.show_work_dir()
        self.show_target()
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.after(100, self.pump)
        self.after(150, self.discover_saved_work)
        self.after(200, self.poll_usb)

    # ---------- layout ----------
    def bind_text(self, widget: ctk.CTkBaseClass, text: Callable[[], str]) -> ctk.CTkBaseClass:
        widget.configure(text=text())
        self.texts.append((widget, text))
        return widget

    def card(self, row: int, fill: str = CARD, edge: str = CARD_EDGE) -> ctk.CTkFrame:
        card = ctk.CTkFrame(self.column, fg_color=fill, corner_radius=RADIUS, border_width=1, border_color=edge)
        card.grid(row=row, column=0, sticky="ew", pady=(SPACE["md"], 0))
        card.columnconfigure(0, weight=1)
        return card

    def label(self, master: ctk.CTkBaseClass, kind: str, color: str = INK, **options) -> ctk.CTkLabel:
        return ctk.CTkLabel(master, text_color=color, font=_font(kind), anchor="w", justify="left",
                            **{"text": "", "wraplength": WRAP, "height": 16, **options})

    def place(self, widget: ctk.CTkBaseClass, row: int, top: int = 0, bottom: int = 0, **options) -> None:
        widget.grid(row=row, column=0, sticky="ew", padx=CARD_PAD, pady=(top, bottom), **options)

    def _workspace_button(self, master, role: str, command: Callable[[], None], height: int = 36,
                          **options) -> ctk.CTkButton:
        button = _make_button(master, role, command, height=height, **options)
        tkinter.Misc.bind(button, "<FocusIn>", lambda _event: self._reveal_button(button), add="+")
        return button

    def _reveal_button(self, button: ctk.CTkButton) -> None:
        canvas = self.page._parent_canvas
        top = button.winfo_rooty() - canvas.winfo_rooty()
        bottom = top + button.winfo_height()
        height = canvas.winfo_height()
        if top < 0 or bottom > height:
            content = canvas.bbox("all")
            if content:
                offset = top if top < 0 else bottom - height
                canvas.yview_moveto((canvas.canvasy(0) + offset - content[1]) / (content[3] - content[1]))

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self.column, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", pady=(0, SPACE["xs"]))
        header.columnconfigure(0, weight=1)
        self.label(header, "title", ON_PANEL, text=APP_TITLE, wraplength=320).grid(
            row=0, column=0, sticky="w")
        caption = self.label(header, "label", COLORS["accent-gold"])
        self.bind_text(caption, lambda: f"{ui_text('community_patcher')} · {ui_text('windows_edition')} · v{APP_VERSION}")
        caption.grid(row=1, column=0, sticky="w")
        targets = ctk.CTkFrame(header, fg_color="transparent")
        targets.grid(row=0, column=1, rowspan=2, sticky="e")
        self.targets = {}
        for index, (target, key) in enumerate(((PC, "target_pc_short"), (PHONE, "target_android_short"))):
            button = self._workspace_button(targets, "secondary", lambda target=target: self.choose_target(target),
                                     width=68 if target == PC else 118)
            self.bind_text(button, lambda key=key: ui_text(key))
            button.grid(row=0, column=index, padx=(SPACE["xs"], 0))
            self.targets[target] = button
        self.target_note = self.bind_text(self.label(header, "body", ON_PANEL_MUTED), lambda: ui_text("target_locked"))
        self.target_note.grid(row=2, column=0, columnspan=2, sticky="w", pady=(SPACE["xs"], 0))

    def _workspace(self) -> tuple[ctk.CTkFrame, ctk.CTkFrame, ctk.CTkFrame]:
        """Status and setup are separate surfaces, stacked in narrower windows."""
        workspace = ctk.CTkFrame(self.column, fg_color="transparent")
        workspace.grid(row=3, column=0, sticky="ew", pady=(SPACE["md"], 0))
        workspace.columnconfigure(0, weight=3, uniform="workspace")
        workspace.columnconfigure(1, weight=2, uniform="workspace")
        patch, settings = (
            ctk.CTkFrame(workspace, fg_color=CARD, corner_radius=RADIUS, border_width=1, border_color=CARD_EDGE)
            for _ in range(2)
        )
        patch.grid(row=0, column=0, columnspan=2, sticky="nsew")
        settings.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(SPACE["md"], 0))
        patch.columnconfigure(0, weight=1)
        settings.columnconfigure(0, weight=1)

        def reflow(event: tkinter.Event) -> None:
            wide = workspace._reverse_widget_scaling(event.width) >= PC_TWO_COLUMNS
            patch.grid_configure(columnspan=1 if wide else 2, padx=(0, SPACE["xs"]) if wide else 0)
            settings.grid_configure(row=0 if wide else 1, column=int(wide), columnspan=1 if wide else 2,
                                    padx=(SPACE["xs"], 0) if wide else 0, pady=0 if wide else (SPACE["md"], 0))

        tkinter.Misc.bind(workspace, "<Configure>", reflow, add="+")
        return workspace, patch, settings

    @staticmethod
    def _wrap_to(panel: ctk.CTkFrame, labels: tuple[ctk.CTkLabel, ...], padding: int = 2 * CARD_PAD) -> None:
        def wrap(event: tkinter.Event) -> None:
            width = max(1, panel._reverse_widget_scaling(event.width) - padding)
            for label in labels:
                label.configure(wraplength=width)

        tkinter.Misc.bind(panel, "<Configure>", wrap, add="+")

    def _status_label(self, parent: ctk.CTkFrame) -> ctk.CTkLabel:
        label = self.label(parent, "label", corner_radius=BUTTON_RADIUS, padx=SPACE["sm"], pady=SPACE["xxs"])
        label.grid(row=0, column=0, sticky="w", padx=CARD_PAD, pady=(CARD_PAD, 0))
        return label

    def _build_pc(self) -> None:
        """Keep patch status and actions beside the installation settings."""
        self.pc_card, patch, settings = self._workspace()
        self.pc_state_label = self._status_label(patch)

        self.pc_heading = self.label(patch, "heading")
        self.place(self.pc_heading, 1, top=SPACE["md"])
        self.pc_detail = self.label(patch, "body", MUTED)
        self.place(self.pc_detail, 2, top=SPACE["xs"])

        self.pc_actions = actions = ctk.CTkFrame(patch, fg_color="transparent")
        patch.rowconfigure(4, weight=1)
        self.place(actions, 5, top=SPACE["md"], bottom=CARD_PAD)
        self.pc_install_button = self._workspace_button(actions, "primary", lambda: self.run_pc("install"), width=138)
        self.pc_install_button.grid(row=0, column=0, sticky="w")
        self.pc_check_button = self._workspace_button(actions, "secondary", lambda: self.run_pc("status"), width=76)
        self.bind_text(self.pc_check_button, lambda: ui_text("pc_check"))
        self.pc_check_button.grid(row=0, column=1, padx=SPACE["xs"])
        self.pc_remove_button = self._workspace_button(actions, "secondary", self.confirm_pc_remove, width=148)
        self.bind_text(self.pc_remove_button, lambda: ui_text("remove_translation"))
        self.pc_remove_button.grid(row=0, column=2, sticky="w")

        self.pc_checklist = self.bind_text(self.label(patch, "body", MUTED), lambda: ui_text("pc_setup_tip"))
        self.place(self.pc_checklist, 3, top=SPACE["sm"])

        self.pc_progress_view = progress = ctk.CTkFrame(patch, fg_color="transparent")
        progress.columnconfigure(0, weight=1)
        self.pc_progress = ctk.CTkProgressBar(progress, mode="indeterminate", progress_color=INK,
                                              fg_color=DISABLED_FILL, height=6, corner_radius=3)
        self.pc_progress.grid(row=0, column=0, sticky="ew")
        self.pc_elapsed_line = self.label(progress, "button")
        self.pc_elapsed_line.grid(row=1, column=0, sticky="ew", pady=(SPACE["xs"], 0))
        self.pc_operation_line = self.label(progress, "body", MUTED)
        self.pc_operation_line.grid(row=2, column=0, sticky="ew")
        self.place(progress, 5, top=SPACE["md"], bottom=CARD_PAD)

        self.place(self.bind_text(self.label(settings, "heading"), lambda: ui_text("pc_setup")), 0, top=CARD_PAD)
        self.pc_game_label, self.pc_game_button = self._folder_field(
            settings, 1, "pc_game_folder_label", "pc_choose_folder", self.choose_game)
        self.pc_folder_label, self.pc_folder_button = self._folder_field(
            settings, 2, "pc_working_folder_label", "change_folder", self.choose_folder)
        self.pc_space_label = self.label(settings, "body", MUTED)
        self.place(self.pc_space_label, 3, top=SPACE["xxs"])
        self.pc_choices = self._language_field(settings, 4)
        self._wrap_to(patch, (self.pc_heading, self.pc_detail, self.pc_operation_line, self.pc_checklist))
        self._wrap_to(settings, (self.pc_space_label,))
        self.pc_card.grid_remove()

    def _folder_field(self, setup: ctk.CTkFrame, row: int, field_key: str, button_key: str,
                      choose: Callable[[], None]) -> tuple[ctk.CTkLabel, ctk.CTkButton]:
        field = ctk.CTkFrame(setup, fg_color="transparent")
        self.place(field, row, top=SPACE["sm"])
        field.columnconfigure(0, weight=1)
        self.bind_text(self.label(field, "label", MUTED, wraplength=140), lambda: ui_text(field_key)).grid(
            row=0, column=0, sticky="ew")
        button = self._workspace_button(field, "secondary", choose, width=112)
        self.bind_text(button, lambda: ui_text(button_key))
        button.grid(row=0, column=1, sticky="e", padx=(SPACE["xs"], 0))
        path = self.label(field, "body", fg_color=SURFACE, corner_radius=BUTTON_RADIUS,
                          padx=SPACE["xs"], pady=SPACE["xs"], wraplength=230)
        path.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(SPACE["xxs"], 0))
        self._wrap_to(field, (path,), padding=2 * SPACE["xs"])
        return path, button

    def _language_field(self, settings: ctk.CTkFrame, row: int, *, bottom: int = CARD_PAD) -> dict[str, ctk.CTkButton]:
        field = ctk.CTkFrame(settings, fg_color="transparent")
        self.place(field, row, top=SPACE["sm"], bottom=bottom)
        self.bind_text(self.label(field, "label", MUTED), lambda: ui_text("language")).grid(
            row=0, column=0, columnspan=2, sticky="ew")
        choices = {}
        for column, (code, language) in enumerate(languages.LANGUAGES.items()):
            field.columnconfigure(column, weight=1)
            button = self._workspace_button(field, "secondary", lambda code=code: self.choose_language(code),
                                     text=language.name, width=64)
            button.grid(row=1, column=column, sticky="ew",
                        padx=(SPACE["xs"] if column else 0, 0), pady=(SPACE["xxs"], 0))
            choices[code] = button
        return choices

    def _build_start(self) -> None:
        """Pair live patch status with USB, workspace and translation settings."""
        self.start_card, card, setup = self._workspace()
        card.rowconfigure(8, weight=1)
        self.stage = self._status_label(card)
        self.place(self.bind_text(self.label(setup, "heading"), lambda: ui_text("pc_setup")), 0, top=CARD_PAD)
        self.place(self.bind_text(self.label(setup, "label", MUTED), lambda: ui_text("device_label")), 1,
                   top=SPACE["sm"])
        self.device_label = self.label(setup, "body")
        self.place(self.device_label, 2, top=SPACE["xxs"])
        self.folder_label, self.folder_button = self._folder_field(
            setup, 3, "pc_working_folder_label", "change_folder", self.choose_folder)
        self.space_label = self.label(setup, "body", MUTED)
        self.place(self.space_label, 4, top=SPACE["xxs"])
        self.choices = self._language_field(setup, 5, bottom=0)
        self.language_note = self.label(setup, "body", MUTED)
        self.place(self.language_note, 6, bottom=CARD_PAD)
        self.remove_button = self._workspace_button(card, "secondary", self.confirm_remove)
        self.bind_text(self.remove_button, lambda: ui_text("remove_translation"))
        self.place(self.remove_button, 11, bottom=CARD_PAD)
        self._wrap_to(setup, (self.device_label, self.space_label, self.language_note))

        self.heading = self.label(card, "heading")
        self.place(self.heading, 4, top=SPACE["md"])
        self.detail = self.label(card, "body", MUTED)
        self.place(self.detail, 5, top=SPACE["xxs"])
        self.result_items = ctk.CTkFrame(card, fg_color="transparent")
        self.result_items.columnconfigure(0, weight=1)
        self.place(self.result_items, 6, top=SPACE["xs"])
        self.result_note = self.label(card, "body", color=WARNING, fg_color=WARNING_SURFACE,
                                      corner_radius=BUTTON_RADIUS, padx=SPACE["sm"], pady=SPACE["xs"])
        self.place(self.result_note, 7, top=SPACE["xs"])

        # One primary button: Start, or the one recovery action while saved work is unresolved.
        self.usb_actions = ctk.CTkFrame(card, fg_color="transparent")
        self.usb_actions.columnconfigure(0, weight=1)
        self.place(self.usb_actions, 9, top=SPACE["md"], bottom=CARD_PAD)
        self.button = self._workspace_button(self.usb_actions, "primary", self.main_action, height=BUTTON_HEIGHT)
        self.button.grid(row=0, column=0, sticky="ew")
        self.recovery_save = self._workspace_button(self.usb_actions, "secondary", self.save_log,
                                                    height=BUTTON_HEIGHT, width=164)
        self.bind_text(self.recovery_save, lambda: ui_text("save_log_for_help"))
        self.recovery_save.grid(row=0, column=1, padx=(SPACE["xs"], 0))
        # Running: the bar and "Step N of M · <step>" take the button's place.
        self.progress_view = ctk.CTkFrame(card, fg_color="transparent")
        self.progress_view.columnconfigure(0, weight=1)
        self.progress = ctk.CTkProgressBar(self.progress_view, mode="determinate", progress_color=INK,
                                           fg_color=DISABLED_FILL, height=8, corner_radius=4)
        self.progress.grid(row=0, column=0, sticky="ew")
        self.step_line = self.label(self.progress_view, "button")
        self.step_line.grid(row=1, column=0, sticky="ew", pady=(SPACE["xs"], 0))
        self.operation_line = self.label(self.progress_view, "body", color=MUTED, wraplength=WRAP)
        self.operation_line.grid(row=2, column=0, sticky="ew", pady=(SPACE["xs"], 0))
        self.stop_button = self._workspace_button(self.progress_view, "secondary", self.stop_safely,
                                                  text=ui_text("stop_safely"))
        self.stop_button.grid(row=3, column=0, sticky="ew", pady=(SPACE["md"], 0))
        self.place(self.progress_view, 10, top=SPACE["md"], bottom=CARD_PAD)
        self._wrap_to(card, (self.heading, self.detail, self.step_line, self.operation_line))
        self._wrap_to(card, (self.result_note,), padding=2 * (CARD_PAD + SPACE["sm"]))

    def _build_error(self) -> None:
        """The error card, directly under ②: the cause and Save log for help."""
        self.error_card = self.card(4, ERROR_SURFACE, ERROR)
        self.place(self.bind_text(self.label(self.error_card, "heading"), lambda: ui_text("error_details")), 0,
                   top=CARD_PAD)
        self.error_text = self.label(self.error_card, "body")
        self.place(self.error_text, 1, top=SPACE["xxs"])
        self._wrap_to(self.error_card, (self.error_text,))
        self.error_save = self._workspace_button(self.error_card, "secondary", self.save_log)
        self.place(self.bind_text(self.error_save, lambda: ui_text("save_log_for_help")), 2,
                   top=SPACE["md"], bottom=CARD_PAD)
        self.error_card.grid_remove()

    def _build_log(self) -> None:
        card = self.card(5)
        header = ctk.CTkFrame(card, fg_color="transparent")
        self.place(header, 0, top=CARD_PAD)
        header.columnconfigure(0, weight=1)
        self.bind_text(self.label(header, "heading"), lambda: ui_text("patching_activity")).grid(
            row=0, column=0, sticky="w")
        self.save_log_button = self._workspace_button(header, "secondary", self.save_log, width=146)
        self.bind_text(self.save_log_button, lambda: ui_text("save_log_for_help"))
        self.save_log_button.grid(row=0, column=1, sticky="e")
        self.log_view = ctk.CTkTextbox(card, fg_color=SURFACE, text_color=INK, corner_radius=BUTTON_RADIUS,
                                      border_width=0, height=LOG_HEIGHT, font=_font("log"), wrap="word")
        self.place(self.log_view, 1, top=SPACE["xs"], bottom=CARD_PAD)
        self.log_view.configure(state="disabled")
        self.log_view.bind("<MouseWheel>", self._scroll_log)

    def _scroll_log(self, event: tkinter.Event) -> str:
        """Scroll the log inside its own panel; the page scrolls only outside it."""
        self.log_view.yview("scroll", -3 * (event.delta // 120), "units")
        return "break"

    # ---------- ① Language ----------
    def show_language_card(self) -> None:
        """The note and Remove translation, from whether this folder keeps the phone's pristine delta."""
        held = self.target == PHONE and holds_delta(self.work_dir)
        note = "language_note_no_clear" if held else "language_note_clear_first"
        # Saved unfinished work keeps its language until it finishes or Stop safely resolves it.
        self.language_note.configure(text=ui_text("choices_locked") if self.pending_work and not self.busy
                                     else ui_text(note))
        if held:
            self.remove_button.grid()
        else:
            self.remove_button.grid_remove()
        # A run reads the language once at its start, so the choices and Remove translation lock while it runs.
        locked = self.busy or self.pending_work or self.pc_busy
        _style_button(self.folder_button, "secondary", not locked)
        for choices in (self.choices, self.pc_choices):
            for code, button in choices.items():
                chosen = code == self.language
                _style_button(button, "primary" if chosen else "secondary", not locked)
                if locked and chosen:
                    button.configure(border_color=DISABLED_TEXT)
        _style_button(self.remove_button, "secondary", not locked)
        self.show_target_card()  # the target choice locks with the language choices

    def choose_language(self, code: str) -> None:
        if self.busy or self.pc_busy or code == self.language:
            return
        if self.busy or not self.settings_available():
            return
        self.language = code
        if self.target == PC and self.pc_result and self.pc_result[0] in ("added", "removed"):
            self.pc_result = None
        save_language(code)
        set_interface_language(code)
        self.retext()

    def retext(self) -> None:
        """Redraw every text in the interface language."""
        for widget, text in self.texts:
            widget.configure(text=text())
        if not self.busy:
            self.show_usb_device()
        self.show_work_dir()
        self.show_language_card()
        self.show_start()

    # ---------- ② Start ----------
    def show_work_dir(self) -> None:
        path = str(self.work_dir)
        self.folder_label.configure(text=path)
        free = free_space(self.work_dir)
        gigabytes = f"{(free or 0) / 1024**3:.1f}"
        if free is None:
            self.blocker = ui_text("drive_not_available")
        elif free < MIN_FREE_BYTES:
            self.blocker = ui_text("drive_free_not_enough", free=gigabytes)
        else:
            self.blocker = ""
        self.space_label.configure(text=self.blocker or ui_text("drive_free", free=gigabytes),
                                   text_color=ERROR if self.blocker else MUTED)
        self.pc_folder_label.configure(text=path)
        self.pc_space_label.configure(text=self.space_label.cget("text"), text_color=ERROR if self.blocker else MUTED)

    def show_start(self) -> None:
        """Rewrite ② in place from the run state (spec, User-visible states): Working, Continuing, Stopping
        safely, Restoring, Waiting for you, Verified complete or Recovery needs attention."""
        if self.target == PC:
            self.show_pc()
            return
        kind, value = self.result or ("idle", None)
        items: list[str] = []
        note = ""
        action = ""
        self.error_card.grid_remove()
        tone = SUBTLE
        foreground = INK
        if self.busy:
            stage = ui_text("02_working")
            state = self.run_state.get("state")
            if self.closing:
                heading = ui_text("closing_safely")
            elif self.stopping:
                heading = ui_text("stopping_safely") if self.stop_saved else ui_text("saving_stop_request")
            elif state == "restoring":
                heading = ui_text("restoring_your_game")
            elif state == "waiting":
                heading = ui_text("waiting_for_you")
            elif state == "continuing":
                heading = ui_text("continuing_saved_work")
            else:
                heading = ui_text("working_on_your_game")
            detail = ui_text("close_continuation_note") if self.closing else ui_text("usb_running_hint")
        elif self.pending_work and kind not in ("added", "removed"):
            # Recovery needs attention: the main button becomes the one required recovery action, never a fresh
            # patch; Save log for help stays on the error card as the secondary action.
            tone, foreground = WARNING_SURFACE, WARNING
            stage, heading = ui_text("02_needs_attention"), ui_text("recovery_needs_attention")
            action, detail = self.recovery_action()
            if kind == "failed":
                self.error_text.configure(text=value.shown() if value else ui_text("unexpected_error"))
                self.error_card.grid()
        elif kind == "cancelled":
            # A resolved Stop returns to safe idle; it never claims the requested translation completed.
            stage, heading, detail = ui_text("02_ready_to_play"), ui_text("work_stopped"), ui_text("stopped_safely_note")
        elif kind == "added":
            tone, foreground = SUCCESS_SURFACE, SUCCESS
            stage, heading, detail = ui_text("02_done"), ui_text("translation_added"), ""
            text, images, dropped, skipped = value
            items = ui_text("applied_counts", text_tables=text, applied_textures=images, skipped_tables=dropped,
                            skipped_textures=skipped).split("\n")
            note = ui_text("result_open_game")
        elif kind == "removed":
            tone, foreground = SUCCESS_SURFACE, SUCCESS
            stage, heading, detail = ui_text("02_done"), ui_text("translation_removed"), ui_text("reads_chinese_again")
            items = [ui_text("original_files_restored", count=value)] if value else [ui_text("already_untranslated")]
            note = ui_text("removed_login_note")
        elif kind == "failed":
            tone, foreground = WARNING_SURFACE, WARNING
            stage, heading, detail = ui_text("02_needs_attention"), ui_text("work_stopped"), ui_text("failed_status")
            self.error_text.configure(text=value.shown() if value else ui_text("unexpected_error"))
            self.error_card.grid()
        else:
            stage = "" if self.connected else ui_text("usb_waiting")
            heading = ui_text("usb_ready_heading") if self.connected else ui_text("usb_waiting_heading")
            detail = self.blocker or (ui_text("usb_ready_hint") if self.connected else ui_text("usb_waiting_hint"))
        self.stage.configure(text=stage.partition("/")[2].strip() if "/" in stage else stage,
                             fg_color=tone, text_color=foreground)
        self._show(self.stage, bool(stage))
        self.heading.configure(text=heading)
        self.detail.configure(text=detail)
        self._show(self.detail, bool(detail))
        recovery_export = self.pending_work and not self.busy
        self._show(self.recovery_save, recovery_export)
        self._show(self.error_save, not recovery_export)
        self.error_text.grid_configure(pady=(SPACE["xxs"], CARD_PAD if recovery_export else 0))
        self._show(self.save_log_button, not recovery_export and self.error_card.winfo_manager() == "")
        for row in self.result_items.winfo_children():
            row.destroy()
        for row, item in enumerate(items):
            self._count_row(row, item)
        self._show(self.result_items, bool(items))
        self.result_note.configure(text=note)
        self._show(self.result_note, bool(note))
        self._show(self.usb_actions, not self.busy)
        self._show(self.progress_view, self.busy)
        if self.busy:
            self.show_step()
        else:
            again = {"added": ui_text("run_again"), "removed": ui_text("run_again"), "failed": ui_text("try_again")}
            self.button.configure(text=action or again.get(kind) or ui_text("start"))
            ready = not self.blocker and (self.usb_status is None or self.connected)
            _style_button(self.button, "primary", self.pending_work or ready)

    def recovery_action(self) -> tuple[str, str]:
        """The attention state's (button label, instruction), from the saved run and the core's next action."""
        record = (self.pending_runs[0].get("record") or {}) if len(self.pending_runs) == 1 else {}
        authorized = len(self.pending_runs) == 1 and self.pending_runs[0].get("kind") == "authorized"
        next_action = self.patcher.outcome.get("next_action") if self.patcher is not None else None
        if not authorized:
            return ui_text("check_saved_work"), ui_text("attention_check_saved_work")
        if self.pending_stop or record.get("stop_requested"):
            return ui_text("finish_stopping_safely"), ui_text("attention_stop_saved")
        if next_action == "restore_normal":
            return ui_text("restore_game_app"), ui_text("attention_restore_normal")
        return ui_text("continue_saved_work"), ui_text("attention_saved_action")

    def _count_row(self, row: int, item: str) -> None:
        """'Label: value' with the value at the end, so five-digit counts line up."""
        label, _, value = item.rpartition(": ")
        line = ctk.CTkFrame(self.result_items, fg_color=SURFACE, corner_radius=BUTTON_RADIUS)
        line.grid(row=row, column=0, sticky="ew", pady=(0, SPACE["xxs"]))
        line.columnconfigure(0, weight=1)
        ctk.CTkLabel(line, text=label or value, text_color=INK, font=_font("body"), anchor="w").grid(
            row=0, column=0, sticky="w", padx=SPACE["sm"])
        if label:
            ctk.CTkLabel(line, text=value, text_color=INK, font=_font("button"), anchor="e").grid(
                row=0, column=1, sticky="e", padx=SPACE["sm"])

    @staticmethod
    def _show(widget: ctk.CTkBaseClass, visible: bool) -> None:
        if visible:
            widget.grid()
        else:
            widget.grid_remove()

    def show_step(self) -> None:
        index = self.step_index or 0
        # Spelled out key by key so check_ui_strings.py sees every step string.
        names = {"device": ui_text("step_device"), "apk": ui_text("step_apk"), "access": ui_text("step_access"),
                 "pull": ui_text("step_pull"), "translate": ui_text("step_translate"),
                 "install": ui_text("step_install"), "restore": ui_text("step_restore")}
        self.step_line.configure(text=ui_text("progress_step", n=index + 1, total=len(STEPS),
                                              step=names[STEPS[index][0]]))

    def poll_usb(self) -> None:
        """Read ADB transport status off the UI thread while the USB workspace is idle."""
        if not self.closing and self.target == PHONE and not self.busy and not (
                self.usb_probe is not None and self.usb_probe.is_alive()):
            self.usb_probe = threading.Thread(target=self._read_usb_status, args=(self.work_dir,), daemon=True)
            self.usb_probe.start()
        if not self.closing:
            self.after(2000, self.poll_usb)

    def _read_usb_status(self, work: Path) -> None:
        try:
            rows = Adb(work).run("devices").splitlines()[1:]
        except (OSError, PatchError, subprocess.TimeoutExpired):
            self.messages.put(("usb-status", (work, None)))
            return
        states = [parts[1] for row in rows if len(parts := row.split()) >= 2]
        status = states[0] if len(states) == 1 else "multiple" if states else "missing"
        self.messages.put(("usb-status", (work, status)))

    def show_usb_device(self) -> None:
        if self.usb_status == "device":
            text = ui_text("usb_connected")
        elif self.usb_status == "unauthorized":
            text = ui_text("device_allow_usb_debugging")
        elif self.usb_status == "multiple":
            text = ui_text("device_one_phone_only")
        else:
            text = ui_text("device_not_connected")
        self.device_label.configure(text=text, text_color=SUCCESS if self.connected else MUTED)

    # ---------- the target choice ----------
    @property
    def pc_busy(self) -> bool:
        return self.pc_job is not None

    def show_target_card(self) -> None:
        """Mark the chosen target; the choice locks while either target works or saved phone work waits."""
        locked = self.busy or self.pc_busy or self.pending_work
        for target, button in self.targets.items():
            chosen = target == self.target
            _style_button(button, "primary" if chosen else "secondary", not locked)
            if locked and chosen:
                button.configure(border_color=DISABLED_TEXT)
        self._show(self.target_note, self.pending_work and not self.busy)

    def show_target(self) -> None:
        """Switch workspaces within the shared Windows shell."""
        pc = self.target == PC
        self._show(self.start_card, not pc)
        self._show(self.pc_card, pc)
        self.page._parent_canvas.yview_moveto(0.0)
        if self.target == PHONE:
            self.error_card.grid_remove()
        self.show_language_card()
        self.show_start()

    def choose_target(self, target: str) -> None:
        if target == self.target or self.busy or self.pc_busy or self.pending_work or self.closing:
            return
        self.target = target
        save_target(target)
        self.show_target()
        if target == PC:
            self.open_pc()

    def _force_phone(self) -> None:
        """Saved phone work comes first (DESIGN.md, ② Start): show the phone target before it."""
        if self.target != PHONE:
            self.target = PHONE
            self.show_target()

    # ---------- the PC target ----------
    def open_pc(self) -> None:
        """Find the game (the remembered folder, then the launcher's records) and run Check on it."""
        self.pc_opened = True
        try:
            games = pc_edition.find_games(SETTINGS)
        except (PatchError, OSError, ValueError) as error:
            self.log(f"PC edition: finding the game failed: {error}")
            games = []
        if games and self.pc_game is None:
            self.pc_game = games[0]
        self.show_start()
        if self.pc_game is not None:
            self.run_pc("status")

    def choose_game(self) -> None:
        if self.pc_busy:
            return
        start = self.pc_game if self.pc_game is not None and self.pc_game.exists() else Path.home()
        chosen = filedialog.askdirectory(parent=self, title=ui_text("pc_choose_folder_title"), initialdir=str(start))
        if not chosen:
            return
        self.set_game(Path(chosen))

    def set_game(self, folder: Path) -> None:
        """Take a picked folder as the game once `pc_edition.resolve` accepts it, remember it, then Check."""
        try:
            root = pc_edition.resolve(folder)
        except PatchError as error:
            self.pc_result, self.pc_error = ("failed", 0.0), error
            self.log(f"\nFAILED: {error}")
            self.show_start()
            return
        try:
            pc_edition.remember_game(SETTINGS, root)
        except OSError as error:
            self.log(f"PC edition: the game folder was not saved: {error}")
        self.pc_game, self.pc_state, self.pc_language, self.pc_version = root, None, None, None
        self.pc_recoverable = False
        self.pc_result = self.pc_error = None
        self.run_pc("status")

    def confirm_pc_remove(self) -> None:
        # A plain dialog: Remove translation puts the saved originals back and deletes no game data.
        if Dialog.show(self, ui_text("remove_the_translation_question"), ui_text("pc_remove_confirmation"),
                       confirm=True, confirm_label=ui_text("remove_the_translation")):
            self.run_pc("restore")

    def run_pc(self, action: str, follow_up: bool = False) -> None:
        """Start one PC job in its child process; `pc_tick` follows it until it answers."""
        if self.pc_busy or self.busy or self.closing or self.pc_game is None:
            return
        if not follow_up:
            self.pc_result = self.pc_error = None
        self.pc_action, self.pc_follow_up = action, follow_up
        answer = self.work_dir / "pc" / "jobs" / f"{action}.json"
        try:
            answer.parent.mkdir(parents=True, exist_ok=True)
            self.pc_job = pc_edition.start_job(action, self.pc_game, self.work_dir, answer, self.language)
        except OSError as error:
            self.pc_job = None
            self.pc_result, self.pc_error = ("failed", 0.0), PatchError("pc_engine_failed", detail=error)
            self.show_start()
            return
        self.pc_answer, self.pc_log_offset, self.pc_started = answer, 0, time.monotonic()
        self.log(f"\nPC edition: {action} on {self.pc_game} (working folder {self.work_dir})")
        self.pc_operation_line.configure(text="")
        self.pc_progress.start()
        self.show_language_card()
        self.show_start()
        self.after(PC_TICK, self.pc_tick)

    def _tail_pc_log(self) -> None:
        """Copy the child's new log lines into the log; its last line goes under the bar."""
        try:
            with (self.pc_answer.parent / (self.pc_answer.name + ".log")).open("rb") as handle:
                handle.seek(self.pc_log_offset)
                chunk = handle.read()
        except OSError:
            return
        end = chunk.rfind(b"\n") + 1  # a line still being written waits for the next tick
        if not end:
            return
        self.pc_log_offset += end
        lines = [line for line in chunk[:end].decode("utf-8", "replace").splitlines() if line.strip()]
        for line in lines:
            self.log("  " + line)
        if lines:
            last = lines[-1].strip()
            self.pc_operation_line.configure(text=last if len(last) <= 110 else last[:109] + "…")

    def pc_tick(self) -> None:
        if self.pc_job is None:
            return
        self._tail_pc_log()
        self.pc_elapsed_line.configure(text=ui_text("pc_elapsed", elapsed=_elapsed(time.monotonic() - self.pc_started)))
        if self.pc_job.poll() is None:
            self.after(PC_TICK, self.pc_tick)
            return
        self._tail_pc_log()
        self.pc_job = None
        self.pc_progress.stop()
        self.finish_pc()

    def finish_pc(self) -> None:
        """Read the child's answer, then run Check after Install and Remove translation."""
        action, seconds = self.pc_action, time.monotonic() - self.pc_started
        error = None
        self.show_work_dir()  # the job used the working folder's space
        try:
            answer = pc_edition.read_answer(self.pc_answer)
        except PatchError as failure:
            error = failure
            self.log(f"\nFAILED: {failure}")
        if action == "status":
            if error is None:
                self.pc_state, self.pc_language = answer.get("state"), answer.get("language")
                self.pc_version = answer.get("version")
                self.pc_recoverable = bool(answer.get("recoverable"))
                self.log(f"\nCHECKED: {self.pc_state}" + (f" ({self.pc_language})" if self.pc_language else ""))
            else:
                self.pc_state = self.pc_language = self.pc_version = None
                self.pc_recoverable = False
                # A follow-up Check never hides the job's own error.
                if not (self.pc_follow_up and self.pc_error is not None):
                    self.pc_error = error
                if not self.pc_follow_up or (self.pc_result or ("",))[0] != "failed":
                    self.pc_result = ("failed", seconds)
        else:
            if error is None:
                self.pc_result = ("added" if action == "install" else "removed", seconds)
                self.log(f"\nSUCCESS: {action} finished in {_elapsed(seconds)}")
            else:
                self.pc_result, self.pc_error = ("failed", seconds), error
            if error is None or error.keys[:1] and error.keys[0] not in PC_NO_FOLLOW_UP:
                self.pc_state = None
                self.run_pc("status", follow_up=True)
                return
        self.show_language_card()
        self.show_start()

    def _pc_view(self) -> tuple[str, str]:
        """Heading and next step for the current PC state."""
        if self.pc_busy:
            heading = {"install": "pc_installing", "restore": "pc_removing"}.get(self.pc_action, "pc_checking")
            return ui_text(heading), ui_text("pc_busy_note")
        kind, seconds = self.pc_result or ("", 0.0)
        finished = ui_text("pc_finished_in", elapsed=_elapsed(seconds))
        if kind == "added":
            return ui_text("translation_added"), f"{ui_text('pc_result_added')} {finished}"
        if kind == "removed":
            return ui_text("translation_removed"), f"{ui_text('reads_chinese_again')} {finished}"
        if kind == "failed":
            return ui_text("work_stopped"), ui_text("pc_failed_status")
        if self.pc_game is None:
            return ui_text("pc_heading_no_game"), ui_text("pc_detail_no_game")
        state = self.pc_state
        if state == pc_edition.INSTALLED:
            if self.pc_language != self.language:
                name = languages.get(self.language).name
                return ui_text("pc_switch"), ui_text("pc_switch_detail", language=name)
            if self.pc_version != APP_VERSION:
                return ui_text("pc_update_available"), ui_text("pc_update_detail")
            return ui_text("pc_heading_installed"), ui_text("pc_detail_installed")
        if state == pc_edition.REPLACED:
            return ui_text("pc_heading_replaced"), ui_text("pc_detail_replaced")
        if state == pc_edition.PARTLY:
            if self.pc_recoverable:
                return ui_text("pc_heading_partly"), ui_text("pc_resume_detail")
            return ui_text("pc_heading_partly"), ui_text("pc_detail_partly")
        if state == pc_edition.FOREIGN:
            advice = f"{ui_text('pc_foreign_install')} {ui_text('pc_repair_advice')}"
            return ui_text("pc_heading_foreign"), advice
        if state == pc_edition.NOT_INSTALLED:
            return ui_text("pc_install_translation"), self.blocker or ui_text("pc_detail_not_installed")
        return ui_text("pc_install_translation"), self.blocker or ui_text("pc_detail_unknown")

    def _pc_state_line(self) -> tuple[str, str]:
        """Check's state as the status row reads it, with its dot colour."""
        if self.pc_busy:
            return ui_text("pc_state_checking") if self.pc_action == "status" else ui_text("pc_state_working"), MUTED
        state = self.pc_state
        if state == pc_edition.INSTALLED:
            name = languages.get(self.pc_language).name if self.pc_language in languages.LANGUAGES else ""
            return ui_text("pc_state_installed", language=name).rstrip(": "), SUCCESS
        lines = {pc_edition.NOT_INSTALLED: (ui_text("pc_state_not_installed"), DISABLED_TEXT),
                 pc_edition.REPLACED: (ui_text("pc_state_replaced_by_update"), WARNING),
                 pc_edition.PARTLY: (ui_text("pc_state_partly_installed"), WARNING),
                 pc_edition.FOREIGN: (ui_text("pc_state_foreign"), WARNING)}
        return lines.get(state, (ui_text("pc_state_unknown"), DISABLED_TEXT))

    def show_pc(self) -> None:
        """Rewrite the PC card in place: running, a job's result, or Check's state with its next step."""
        heading, detail = self._pc_view()
        self.pc_heading.configure(text=heading)
        self.pc_detail.configure(text=detail)
        game = str(self.pc_game) if self.pc_game is not None else ui_text("pc_no_game_found")
        self.pc_game_label.configure(text=game)
        text, color = self._pc_state_line()
        attention_heading = color == WARNING and self.pc_result is None
        self.pc_heading.configure(text_color=WARNING if attention_heading else INK)
        fill = SUCCESS_SURFACE if color == SUCCESS else WARNING_SURFACE if color == WARNING else SUBTLE
        self.pc_state_label.configure(text=text, text_color=color, fg_color=fill)
        self._show(self.pc_state_label, not attention_heading)
        busy = self.pc_busy
        self._show(self.pc_checklist, not busy and self.pc_state in (None, pc_edition.NOT_INSTALLED, pc_edition.REPLACED)
                   and self.pc_game is not None and self.pc_result is None)
        self._show(self.pc_actions, not busy)
        self._show(self.pc_progress_view, busy)
        ready = not busy and self.pc_game is not None
        state = self.pc_state
        install_text = ui_text("pc_install")
        if state == pc_edition.REPLACED:
            install_text = ui_text("pc_reapply")
        elif state == pc_edition.PARTLY and self.pc_recoverable:
            install_text = ui_text("pc_resume")
        elif state == pc_edition.INSTALLED:
            if self.pc_language != self.language:
                install_text = ui_text("pc_switch")
            elif self.pc_version != APP_VERSION:
                install_text = ui_text("pc_update_translation")
            else:
                install_text = ui_text("pc_reapply")
        self.pc_install_button.configure(text=install_text)
        _style_button(self.pc_install_button, "primary",
                      ready and not self.blocker and state != pc_edition.FOREIGN
                      and (state != pc_edition.PARTLY or self.pc_recoverable))
        _style_button(self.pc_check_button, "secondary", ready)
        _style_button(self.pc_remove_button, "secondary", ready and state == pc_edition.INSTALLED)
        _style_button(self.pc_game_button, "secondary", not busy)
        _style_button(self.pc_folder_button, "secondary", not busy)
        if busy:
            self.pc_elapsed_line.configure(
                text=ui_text("pc_elapsed", elapsed=_elapsed(time.monotonic() - self.pc_started)))
        if self.pc_error is not None and not busy:
            self.error_text.configure(text=self.pc_error.shown())
            self.error_card.grid()
        else:
            self.error_card.grid_remove()
        self._show(self.error_save, True)
        self.error_text.grid_configure(pady=(SPACE["xxs"], 0))
        self._show(self.save_log_button, busy or self.pc_error is None)

    # ---------- working folder ----------
    def settings_available(self) -> bool:
        """Use the durable registry, even when another working folder was selected."""
        try:
            pending = discover_pending_runs(self.work_dir)
            if pending:
                raise PatchError("error_run_pending", detail=pending[0]["root"])
        except PatchError as error:
            self._force_phone()
            self.finish("failed", error)
            return False
        return True

    def choose_folder(self) -> None:
        if self.busy or self.pc_busy or not self.settings_available():
            return
        chosen = filedialog.askdirectory(parent=self, title=ui_text("choose_folder_title"),
                                         initialdir=str(self.work_dir if self.work_dir.exists() else self.work_dir.parent))
        if not chosen:
            return
        path = Path(chosen)
        # Keep the data in its own subfolder so the user's folder is never cluttered or cleaned up.
        if path.name != "HOK ACE Patcher Data":
            path = path / "HOK ACE Patcher Data"
        self.work_dir = path
        save_work_dir(path)
        self.show_work_dir()
        self.show_language_card()
        self.show_start()
        if self.target == PC and self.pc_game is not None:
            # The receipts live in the working folder, so Check reads the game against the new one.
            self.pc_state = self.pc_language = self.pc_version = None
            self.pc_recoverable = False
            self.run_pc("status")

    def save_log(self) -> None:
        chosen = filedialog.asksaveasfilename(parent=self, title=ui_text("save_log_for_help"),
                                              defaultextension=".txt", initialfile="hok-ace-patcher-log.txt",
                                              filetypes=[("*.txt", "*.txt")])
        if not chosen:
            return
        try:
            Path(chosen).write_text(self.log_view.get("1.0", "end"), encoding="utf-8")
        except OSError as error:
            self.log(str(error))
            return
        self.log(ui_text("log_saved", path=chosen))

    # ---------- thread-safe UI interface used by Patcher ----------
    def log(self, line: str) -> None:
        self.messages.put(("log", line))

    def set_step(self, key: str, state: str, detail: str = "") -> None:
        self.messages.put(("step", (key, state, detail)))

    def set_device(self, text: str, connected: bool) -> None:
        self.messages.put(("device", (text, connected)))

    def run_event(self, event: dict) -> None:
        self.messages.put(("event", dict(event)))

    def _cancel_dialogs(self) -> None:
        self.ui_cancel.set()
        for child in self.winfo_children():
            if isinstance(child, Dialog):
                child.destroy()

    def _wait_ended(self) -> PatchError:
        """Why a UI wait ended early: Stop safely, or Close keeping the action for the next open."""
        if self.stopping:
            return PatchError("error_cancelled")
        return PatchError("error_close_preserved")

    def _on_ui(self, func):
        done = threading.Event()
        box = {}

        def call():
            try:
                if not self.ui_cancel.is_set():
                    box["value"] = func()
            except Exception as error:
                box["error"] = error
            finally:
                done.set()

        self.messages.put(("call", call))
        while not done.wait(0.1):
            if self.ui_cancel.is_set():
                self.patcher.control_boundary()
                raise self._wait_ended()
        if self.ui_cancel.is_set():
            self.patcher.control_boundary()
            raise self._wait_ended()
        if "error" in box:
            raise box["error"]
        return box.get("value", False)

    def ask(self, title: str, message: str, danger: bool = True) -> bool:
        # Only first setup's data-loss consent asks; it is never a routine patch confirmation.
        self.run_event({"state": "waiting", "next_action": "setup_consent", "detail": ui_text("waiting_setup_consent")})
        return self._on_ui(lambda: Dialog.show(self, title, message, confirm=True, danger=danger))

    def wait_user(self, title: str, message: str) -> None:
        # An actual download wait: its one action names what it confirms.
        self.run_event({"state": "waiting", "next_action": "downloads_finished",
                        "detail": ui_text("waiting_downloads_detail")})
        self._on_ui(lambda: Dialog.show(self, title, message, confirm_label=ui_text("downloads_finished")))

    # ---------- event loop ----------
    def pump(self) -> None:
        try:
            while True:
                kind, value = self.messages.get_nowait()
                if kind == "log":
                    self.log_view.configure(state="normal")
                    self.log_view.insert("end", value + "\n")
                    self.log_view.see("end")
                    self.log_view.configure(state="disabled")
                elif kind == "step":
                    key, state, self.step_detail = value
                    self.operation_line.configure(text=self.step_detail)
                    index = [step for step, _ in STEPS].index(key)
                    if state == "active":
                        self.step_index = index
                        self.progress.configure(mode="indeterminate")
                        self.progress.start()
                        self.show_step()
                    elif state in ("done", "skipped"):
                        self.progress.stop()
                        self.progress.configure(mode="determinate")
                        self.progress.set((index + 1) / len(STEPS))
                elif kind == "device":
                    text, connected = value
                    self.connected = connected
                    self.device_label.configure(text=text)
                elif kind == "usb-status":
                    work, status = value
                    if (self.target == PHONE and not self.busy and work == self.work_dir
                            and (status != self.usb_status or self.connected != (status == "device"))):
                        self.usb_status = status
                        self.connected = status == "device"
                        self.show_usb_device()
                        self.show_start()
                elif kind == "event":
                    self.run_state = value
                    done, total = value.get("bytes_done"), value.get("bytes_total")
                    detail = value.get("detail") or self.step_detail
                    if isinstance(done, int) and isinstance(total, int) and total > 0:
                        self.progress.stop()
                        self.progress.configure(mode="determinate")
                        self.progress.set(min(1, done / total))
                        detail = ui_text("progress_bytes", done=_size(done), total=_size(total))
                    elif isinstance(value.get("items_done"), int) and value.get("items_total", 0) > 0:
                        self.progress.stop()
                        self.progress.configure(mode="determinate")
                        self.progress.set(value["items_done"] / value["items_total"])
                        detail = ui_text("progress_items", done=value["items_done"], total=value["items_total"])
                    elif self.busy:
                        if isinstance(done, int):
                            detail = ui_text("progress_bytes_read", done=_size(done))
                        self.progress.configure(mode="indeterminate")
                        self.progress.start()
                    if value.get("next_action") == "connect_saved_phone":
                        detail = ui_text("connect_saved_phone")
                    elif value.get("reason") == "transient_retry":
                        detail = ui_text("retrying_saved_action")
                    self.operation_line.configure(text=detail)
                    self.show_start()
                elif kind == "control":
                    if isinstance(value, Exception):
                        self.closing = False
                        self.log(str(value))
                        self.operation_line.configure(text=ui_text("control_save_failed"))
                    elif value:
                        self.stop_saved = self.stopping
                        self.stop_button.configure(text=ui_text("stopping_safely") if self.stopping else ui_text("closing_safely"))
                        self.operation_line.configure(text=ui_text("waiting_operation_boundary"))
                    self.show_start()
                elif kind == "call":
                    value()
                elif kind == "done":
                    self.finish(*value)
        except queue.Empty:
            pass
        if self.closing and not self.busy and not any(t.is_alive() for t in self.control_threads):
            if self.worker_thread is None or not self.worker_thread.is_alive():
                self.destroy()
                return
        self.after(100, self.pump)

    def confirm_remove(self) -> None:
        # A plain dialog: removing writes the original files back and deletes no game data.
        if Dialog.show(self, ui_text("remove_the_translation_question"), ui_text("remove_confirmation"),
                       confirm=True, confirm_label=ui_text("remove_the_translation")):
            self.start(remove=True)

    def discover_saved_work(self) -> None:
        """Startup dispatch requires a durable intent; no pending run means idle."""
        if self.busy or self.closing:
            return
        try:
            pending = discover_pending_runs(self.work_dir)
            self.pending_runs = pending
            self.pending_work = bool(pending)
            if pending:
                self._force_phone()
            if len(pending) == 1 and pending[0]["kind"] == "authorized":
                saved = pending[0]["record"]
                self.work_dir = Path(pending[0]["root"])
                self.language = saved["language"]
                set_interface_language(self.language)
                self.retext()
                self.start(remove=saved["action"] == "remove", automatic=True)
            elif pending:
                self.finish("failed", PatchError("error_run_pending", detail=pending[0]["root"]))
            elif self.target == PC and not self.pc_opened:
                self.open_pc()
        except PatchError as error:
            self.pending_work = True
            self._force_phone()
            self.finish("failed", error)

    def main_action(self) -> None:
        """② Start's primary button: the recovery action while saved work is unresolved, otherwise Start."""
        if self.pending_work:
            self.recover()
        else:
            self.start()

    def recover(self) -> None:
        """Dispatch the saved action's recovery or continuation; never a fresh patch while recovery is unresolved."""
        if self.busy or self.closing:
            return
        try:
            pending = discover_pending_runs(self.work_dir)
        except PatchError as error:
            self.finish("failed", error)
            return
        self.pending_runs, self.pending_work = pending, bool(pending)
        if not pending:
            # Resolved since the screen was drawn: back to safe idle; Start stays the player's own choice.
            self.result = None
            self.show_language_card()
            self.show_start()
            return
        record = pending[0].get("record") or {}
        # Core re-reads the record under its locks and never falls through to a fresh patch.
        self.start(remove=record.get("action") == "remove", recovery_only=True)

    def start(self, remove: bool = False, *, automatic: bool = False, recovery_only: bool = False) -> None:
        if self.busy or self.closing or self.worker_thread is not None and self.worker_thread.is_alive():
            return
        self.removing = remove
        self.busy = True
        self.stopping = self.pending_stop
        self.stop_saved = False
        self.ui_cancel.clear()
        self.run_state = {}
        self.result = None
        self.step_index = 0
        self.progress.set(0)
        self.patcher = Patcher(self, self.work_dir, self.language, remove=remove,
                               retry=self.pending_work and not automatic, recovery_only=recovery_only)
        if self.pending_stop:
            self.patcher.queue_control(stop=True)
        _style_button(self.stop_button, "secondary", not self.pending_stop)
        self.stop_button.configure(text=ui_text("saving_stop_request") if self.pending_stop else ui_text("stop_safely"))
        self.show_language_card()
        self.show_start()
        self.worker_thread = threading.Thread(target=self.worker, name="patch-worker", daemon=False)
        self.worker_thread.start()

    def worker(self) -> None:
        patcher = self.patcher
        try:
            summary = patcher.run()
            if summary.get(NOTHING_TO_RECOVER):
                self.messages.put(("done", (NOTHING_TO_RECOVER, None)))
                return
            if patcher.outcome.get("state") != "verified_complete":
                raise PatchError("error_run_state", detail="Missing verified completion")
            if patcher.remove:
                self.messages.put(("done", ("removed", len(summary.get("removed", [])))))
                return
            text, images = count_translated(summary)
            counts = (text, images, count_untranslated_text(summary), count_untranslated_graphics(summary))
            self.messages.put(("done", ("added", counts)))
        except PatchError as error:
            kind = "cancelled" if error.keys == ("error_cancelled",) and patcher.outcome.get("state") == "cancelled" else "failed"
            self.messages.put(("done", (kind, error)))
        except Exception:
            self.messages.put(("log", traceback.format_exc()))
            self.messages.put(("done", ("failed", None)))

    def finish(self, kind: str, value: object) -> None:
        self.busy = False
        self.progress.stop()
        self.result = (kind, value)
        if kind in {"cancelled", "added", "removed"}:
            self.pending_stop = False
        if kind == NOTHING_TO_RECOVER:
            # Resolved before the claim: no game file was touched; back to idle with one line saying so.
            self.result = None
            self.log(ui_text("nothing_left_to_recover_click"))
        elif kind == "failed":
            self.log(f"\nFAILED: {value or 'unexpected error'}")
        elif kind == "cancelled":
            self.log("\nSTOPPED: consistency verified")
        elif kind == "added":
            self.log("\nSUCCESS: {} text tables and {} images applied, {} text tables and {} images skipped"
                     .format(*value))
        else:
            self.log(f"\nSUCCESS: translation removed, {value} original game files restored")
        try:
            self.pending_runs = discover_pending_runs(self.work_dir)
            self.pending_work = bool(self.pending_runs)
        except PatchError:
            self.pending_runs = []
            self.pending_work = True
        if not self.pending_work and self.patcher is not None and self.patcher.run_owner is None:
            # Stop before selecting/authorizing a phone dispatched no game mutation.
            self.pending_stop = False
        self.show_work_dir()
        self.show_language_card()
        self.show_start()

    def _request_control(self, *, stop: bool = False, close: bool = False) -> None:
        patcher = self.patcher
        patcher.queue_control(stop=stop, close=close)
        def save():
            try:
                durable = patcher.request_control(stop=stop, close=close)
                self.messages.put(("control", durable))
            except Exception as error:
                self.messages.put(("control", error))
        thread = threading.Thread(target=save, name="patch-control", daemon=False)
        self.control_threads.append(thread)
        thread.start()

    def stop_safely(self) -> None:
        if not self.busy or self.stopping or self.closing:
            return
        self.stopping = True
        self.pending_stop = True
        _style_button(self.stop_button, "secondary", False)
        self.stop_button.configure(text=ui_text("saving_stop_request"))
        self._request_control(stop=True)
        self._cancel_dialogs()

    def close(self) -> None:
        if self.pc_busy:
            # A PC job cannot stop part-way and its answer is read here: the player waits for it.
            Dialog.show(self, ui_text("pc_close_wait_title"), ui_text("pc_close_wait"))
            return
        if self.closing:
            return
        self.closing = True
        if self.busy:
            _style_button(self.stop_button, "secondary", False)
            self._request_control(close=True)
            self._cancel_dialogs()
            self.show_start()
        elif not any(t.is_alive() for t in self.control_threads):
            self.destroy()


class LogStream:
    """File-like sink so print() inside the translation runtime works in a windowed exe."""

    def __init__(self, app: App):
        self.app = app

    def write(self, text: str) -> int:
        for line in text.rstrip().splitlines():
            self.app.log("  " + line)
        return len(text)

    def flush(self) -> None:
        pass


def selftest(game: Path, out: Path, language: str = languages.DEFAULT_LANGUAGE) -> None:
    """Headless check of the frozen translation runtime: <exe> --selftest <game> <out> [language]."""
    with (out.parent / (out.name + ".log")).open("w", encoding="utf-8") as log_file:
        sys.stdout = sys.stderr = log_file
        try:
            summary = build_patch(game, languages.catalog_dir(BUNDLE, language), out / "build", out / "staged")
            (out / "selftest.json").write_text(json.dumps(
                {"ok": True, "packages": [(p["package_id"], p["stage_report"]["replacement_count"])
                                          for p in summary["packages"]]}))
        except Exception:
            traceback.print_exc()


# The runtime modules a run imports; the runtime ships as data, so PyInstaller never sees their imports.
SMOKE_RUNTIME_MODULES = ("wxq_patch.adaptive", "wxq_patch.qtsvfs", "wxq_patch.unity_package_installer")


def smoketest(out: Path) -> None:
    """Headless check of the frozen exe that needs no game dump: <exe> --smoketest <out>.

    It imports the pipeline and the runtime modules a run loads, reads every language's catalog, and runs
    each codec once on a tiny input, so a module or data file the build left out (``HIDDEN_IMPORTS``, the
    ``--collect-all`` codecs) fails here rather than on a user's first texture. It writes
    ``<out>/smoketest.json`` with ``ok`` and one line per check; a failure's traceback goes to ``<out>.log``.
    """
    import gzip
    import importlib
    import io

    out.mkdir(parents=True, exist_ok=True)
    passed: list[str] = []
    with (out.parent / (out.name + ".log")).open("w", encoding="utf-8") as log_file:
        sys.stdout = sys.stderr = log_file
        try:
            for name in ("build_device_patch", *SMOKE_RUNTIME_MODULES):
                importlib.import_module(name)
                passed.append(f"import {name}")
            for code in languages.LANGUAGES:
                with gzip.open(languages.catalog_dir(BUNDLE, code) / "catalog.json.gz", "rt", encoding="utf-8") as handle:
                    json.load(handle)
                passed.append(f"catalog {code}")
            import catalog_supplement
            assert catalog_supplement.TEXTS and catalog_supplement.LEADERBOARDS
            passed.append("catalog supplement")

            import lz4.block
            import ooz  # noqa: F401 - only decompress exists; the import loads the native module
            import zstandard
            from pypinyin import lazy_pinyin
            import mobile_graphics

            sample = bytes(range(256)) * 4
            assert lz4.block.decompress(lz4.block.compress(sample)) == sample
            assert zstandard.ZstdDecompressor().decompress(zstandard.ZstdCompressor().compress(sample)) == sample
            assert lazy_pinyin("王者") == ["wang", "zhe"]
            block = bytes((200, 100, 50, 255)) * 16
            decoded = mobile_graphics.decode_astc(mobile_graphics.encode_astc(block, 4, 4, 4, 4), 4, 4, 4, 4)
            assert max(abs(a - b) for a, b in zip(decoded, block)) <= 8
            png = io.BytesIO()
            Image.new("RGBA", (4, 4), (200, 100, 50, 255)).save(png, "PNG")
            passed += ["lz4", "ooz", "zstandard", "pypinyin", "astc round trip", "png"]

            # The PC edition: its three modules, the engine attributes its hooks replace, and one BC7
            # block through the native encoder (etcpak) and the decoder.
            for name in ("engine_hooks", "pc_catalog", "pc_edition"):
                importlib.import_module(name)
                passed.append(f"import {name}")
            import bc7_mode6
            import engine_hooks
            import etcpak  # noqa: F401 - bc7_mode6 imports it only when it encodes; fail here, not there

            missing = engine_hooks.check()
            assert not missing, f"runtime lacks {missing}"
            passed.append("engine hook attributes")
            pixels = [(200, 100, 50, 255)] * 16
            decoded = mobile_graphics.decode_pc(bc7_mode6.encode_block(pixels), 4, 4, "bc7")
            assert max(abs(a - b) for a, b in zip(decoded, bytes(c for p in pixels for c in p))) <= 8
            passed.append("bc7 round trip")
            ok = True
        except Exception:  # noqa: BLE001 - the report records the failure; CI reads ``ok``
            traceback.print_exc()
            ok = False
    (out / "smoketest.json").write_text(json.dumps({"ok": ok, "passed": passed}, indent=1), encoding="utf-8")


def main() -> None:
    if len(sys.argv) in (4, 5) and sys.argv[1] == "--selftest":
        selftest(Path(sys.argv[2]), Path(sys.argv[3]), *sys.argv[4:])
        return
    if len(sys.argv) == 3 and sys.argv[1] == "--smoketest":
        smoketest(Path(sys.argv[2]))
        return
    if len(sys.argv) in (7, 9) and sys.argv[1] == "--pc-job":
        import pc_edition  # a PC job's child: <action> <game> <work> <answer.json> <language> [--cycle-asset <hash>]

        sys.exit(pc_edition.job(*sys.argv[2:]))
    if len(sys.argv) in (4, 6) and sys.argv[1] == "--pc-selftest":
        import pc_edition

        cycle = frozenset()
        if len(sys.argv) == 6:
            import extra_text

            if sys.argv[4] != "--cycle-asset":
                sys.exit(f"unknown option {sys.argv[4]!r}; expected --cycle-asset <hash>")
            cycle = frozenset(extra_text.resolve_candidates(sys.argv[5]))
        pc_edition.selftest(Path(sys.argv[2]), Path(sys.argv[3]), cycle)
        return
    try:
        # Own taskbar identity so Windows shows our icon instead of the Python one.
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("HOKAce.EnglishPatcher")
    except Exception:  # noqa: BLE001 - the taskbar icon is cosmetic and never stops the app
        pass
    load_fonts()
    ctk.set_appearance_mode("light")
    app = App()
    sys.stdout = sys.stderr = LogStream(app)
    app.mainloop()


if __name__ == "__main__":
    main()
