"""HOK ACE Language Patcher: English or Indonesian translation for a USB-connected Android phone."""
from __future__ import annotations

import ctypes
import json
import tkinter
import tkinter.filedialog as filedialog
import queue
import sys
import threading
import traceback
from pathlib import Path
from typing import Callable

import customtkinter as ctk
from PIL import Image, ImageDraw, ImageFont

from patcher_core import (BUNDLE, MIN_FREE_BYTES, STEPS, Adb, PatchError, Patcher, build_patch, count_translated,
                          count_untranslated_graphics, count_untranslated_text, free_space, holds_delta,
                          languages, load_language, load_work_dir, save_language, save_work_dir,
                          set_interface_language, ui_text)

APP_TITLE = "HOK ACE Language Patcher"
VERSION_FILE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1])) / "VERSION"
APP_VERSION = VERSION_FILE.read_text(encoding="utf-8").strip()
FONTS = BUNDLE / "fonts"

# DESIGN.md tokens, from resources/ui/theme.json.
THEME = json.loads((BUNDLE / "ui" / "theme.json").read_text(encoding="utf-8"))
COLORS = THEME["colors"]
# Windows fallback (DESIGN.md): no transparency, so a flat page and solid cards with a light edge.
PAGE = COLORS["page-top"]
CARD = COLORS["card-solid"]
CARD_EDGE = "#E4E3F2"
INK = COLORS["ink"]
MUTED = COLORS["text-muted"]
PANEL_TOP = COLORS["panel-top"]
PANEL_BOTTOM = COLORS["panel-bottom"]
ON_PANEL = COLORS["on-panel"]
ON_PANEL_MUTED = COLORS["on-panel-muted"]
CONFIRM_LEFT = COLORS["confirm-left"]
CONFIRM_RIGHT = COLORS["confirm-right"]
WARNING = COLORS["warning"]
ERROR = COLORS["error"]
ERROR_SURFACE = COLORS["error-surface"]
DISABLED_FILL = COLORS["disabled-fill"]
DISABLED_TEXT = COLORS["disabled-text"]
RADIUS = int(THEME["rounded"]["card"].removesuffix("px"))
SPACE = {name: int(value.removesuffix("px")) for name, value in THEME["spacing"].items()}

# One centred column, at most 720 px wide (DESIGN.md, Layout).
COLUMN = 720
CARD_PAD = SPACE["lg"]
WRAP = COLUMN - 2 * CARD_PAD - 4
BUTTON_HEIGHT = 44
LOG_HEIGHT = 220
# Images are drawn at twice their size so they stay sharp up to 200 % display scaling.
IMAGE_SCALE = 2

# The Tk family and weight of each Barlow file, as GDI names them once loaded.
TK_FONTS = {
    ("Barlow", 400): ("Barlow", "normal"),
    ("Barlow", 500): ("Barlow Medium", "normal"),
    ("Barlow", 600): ("Barlow SemiBold", "normal"),
    ("Barlow", 700): ("Barlow", "bold"),
    ("Barlow Condensed", 800): ("Barlow Condensed ExtraBold", "normal"),
}
FONT_FILES = {
    ("Barlow", 400): "Barlow-Regular.ttf",
    ("Barlow", 500): "Barlow-Medium.ttf",
    ("Barlow", 600): "Barlow-SemiBold.ttf",
    ("Barlow", 700): "Barlow-Bold.ttf",
    ("Barlow Condensed", 800): "BarlowCondensed-ExtraBold.ttf",
}
FR_PRIVATE = 0x10


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
    """Make the bundled Barlow files available to this process only; nothing is installed."""
    for path in sorted(FONTS.glob("*.ttf")):
        try:
            ctypes.windll.gdi32.AddFontResourceExW(str(path), FR_PRIVATE, 0)
        except (AttributeError, OSError):
            pass  # Tk falls back to the system font


def _rgb(color: str) -> tuple[int, int, int]:
    return int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)


def _mix(color: str, over: str, alpha: float) -> str:
    """<color> at <alpha> over <over>, as #RRGGBB."""
    a, b = _rgb(color), _rgb(over)
    return "#" + "".join(f"{round(x * alpha + y * (1 - alpha)):02X}" for x, y in zip(a, b))


# (fill, hover, text, edge) of each button role in DESIGN.md's colour roles.
BUTTONS = {
    "primary": (PANEL_BOTTOM, PANEL_TOP, ON_PANEL, PANEL_BOTTOM),
    "secondary": (CARD, PAGE, INK, _mix(INK, CARD, 0.3)),
    "confirm": (CONFIRM_RIGHT, CONFIRM_LEFT, INK, CONFIRM_RIGHT),
    "danger": (ERROR, _mix(ERROR, PANEL_BOTTOM, 0.85), ON_PANEL, ERROR),
    "panel-secondary": (CARD, PAGE, INK, CARD),
}


def _make_button(master: ctk.CTkBaseClass, role: str, command: Callable[[], None], height: int = BUTTON_HEIGHT,
                 **options) -> ctk.CTkButton:
    button = ctk.CTkButton(master, height=height, corner_radius=RADIUS, border_width=1, font=_font("button"),
                           text_color_disabled=DISABLED_TEXT, command=command, **options)
    _style_button(button, role, True)
    return button


def _style_button(button: ctk.CTkButton, role: str, enabled: bool) -> None:
    """Enable or disable <button>; a disabled one takes the disabled colours, never only a dimmer look."""
    fill, hover, text, edge = BUTTONS[role]
    if enabled:
        button.configure(state="normal", fg_color=fill, hover_color=hover, text_color=text, border_color=edge)
    else:
        button.configure(state="disabled", fg_color=DISABLED_FILL, border_color=DISABLED_FILL)


# ---------- locally drawn panels (DESIGN.md: the gradients appear only in the hero and dialog images) ----------
def _pil_font(kind: str) -> tuple[ImageFont.FreeTypeFont, float]:
    key, size, spacing = _type(kind)
    try:
        return ImageFont.truetype(str(FONTS / FONT_FILES[key]), size * IMAGE_SCALE), spacing * size * IMAGE_SCALE
    except OSError:
        return ImageFont.load_default(size * IMAGE_SCALE), spacing * size * IMAGE_SCALE


def _text_width(text: str, face: ImageFont.FreeTypeFont, tracking: float) -> float:
    return face.getlength(text) + tracking * max(len(text) - 1, 0)


def _wrap(text: str, face: ImageFont.FreeTypeFont, width: float, tracking: float = 0.0) -> list[str]:
    lines = []
    for paragraph in text.split("\n"):
        line = ""
        for word in paragraph.split(" "):
            candidate = f"{line} {word}" if line else word
            if line and _text_width(candidate, face, tracking) > width:
                lines.append(line)
                line = word
            else:
                line = candidate
        lines.append(line)
    return lines


class _Panel:
    """Lines of text laid out top to bottom on the panel gradient, measured before they are drawn."""

    def __init__(self, width: int, pad: int) -> None:
        self.width, self.pad = width, pad
        self.items: list[tuple[str, ImageFont.FreeTypeFont, float, str, float]] = []
        self.height = pad * IMAGE_SCALE

    def add(self, text: str, kind: str, color: str, gap: int = 0, line_height: float = 1.3) -> None:
        face, tracking = _pil_font(kind)
        self.height += gap * IMAGE_SCALE
        for line in _wrap(text, face, (self.width - 2 * self.pad) * IMAGE_SCALE, tracking):
            self.items.append((line, face, tracking, color, self.height))
            self.height += round(face.size * line_height)

    def draw(self, bands: bool, corner: str | None) -> ctk.CTkImage:
        width, height = self.width * IMAGE_SCALE, self.height + self.pad * IMAGE_SCALE
        image = Image.new("RGB", (width, height))
        top, bottom = _rgb(PANEL_TOP), _rgb(PANEL_BOTTOM)
        draw = ImageDraw.Draw(image, "RGBA")
        for y in range(height):
            t = y / max(height - 1, 1)
            draw.line([(0, y), (width, y)], fill=tuple(round(a + (b - a) * t) for a, b in zip(top, bottom)))
        if bands:
            # The Android hero's bands: oversized and to the right, so the title's left edge stays calm.
            draw.polygon([(width * 0.73, 0), (width, 0), (width * 0.66, height), (width * 0.38, height)],
                         fill=(255, 255, 255, 22))
            for index in range(4):
                x = index * width / 4
                draw.line([(x, height), (x + width * 0.28, height * 0.55)], fill=(255, 255, 255, 26),
                          width=IMAGE_SCALE)
        x0 = self.pad * IMAGE_SCALE
        for text, face, tracking, color, y in self.items:
            if tracking:
                x = x0
                for char in text:
                    draw.text((x, y), char, font=face, fill=color)
                    x += face.getlength(char) + tracking
            else:
                draw.text((x0, y), text, font=face, fill=color)
        if corner:
            mask = Image.new("L", image.size, 0)
            ImageDraw.Draw(mask).rounded_rectangle([0, 0, width - 1, height - 1], RADIUS * IMAGE_SCALE, fill=255)
            image = Image.composite(image, Image.new("RGB", image.size, corner), mask)
        return ctk.CTkImage(light_image=image, size=(self.width, height // IMAGE_SCALE))


def _hero_image() -> ctk.CTkImage:
    """The hero: eyebrow, title and the one line on the partial translation and Scan to login."""
    panel = _Panel(COLUMN, SPACE["lg"])
    panel.add(ui_text("community_patcher_hok_ace"), "label", ON_PANEL_MUTED)
    panel.add(APP_TITLE, "title", ON_PANEL, gap=SPACE["xxs"], line_height=1.1)
    panel.add(ui_text("some_game_text_will_stay_chinese_use"), "body", ON_PANEL, gap=SPACE["xxs"])
    return panel.draw(bands=True, corner=PAGE)


class Dialog(ctk.CTkToplevel):
    """Modal message box on a deep-indigo panel, returning True/False (DESIGN.md, Dialogs)."""

    WIDTH = 468

    def __init__(self, master, title: str, message: str, confirm: bool, danger: bool, confirm_label: str | None):
        super().__init__(master, fg_color=PANEL_BOTTOM)
        self.title(title)
        self.resizable(False, False)
        self.result = False
        self.transient(master)
        panel = _Panel(self.WIDTH, SPACE["xl"])
        panel.add(title, "heading", ON_PANEL)
        panel.add(message, "body", ON_PANEL_MUTED, gap=SPACE["xs"])
        ctk.CTkLabel(self, image=panel.draw(bands=False, corner=None), text="").pack(fill="x")
        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.pack(fill="x", padx=SPACE["xl"], pady=(0, SPACE["xl"]))
        label = confirm_label or ui_text("continue" if confirm else "ok")
        _make_button(buttons, "danger" if danger else "confirm", self._ok, text=label, width=140).pack(side="right")
        if confirm:
            _make_button(buttons, "panel-secondary", self.destroy, text=ui_text("cancel"), width=110).pack(side="left")
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
        self.geometry("820x900")
        self.minsize(COLUMN + 2 * SPACE["md"] + 40, 560)
        icon = BUNDLE / "icon.ico"
        if icon.exists():
            self.iconbitmap(str(icon))
        self.messages: queue.Queue = queue.Queue()
        self.busy = False
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
        self.blocker = ""

        self.page = page = ctk.CTkScrollableFrame(self, fg_color=PAGE, corner_radius=0,
                                                  scrollbar_button_color=CARD_EDGE,
                                                  scrollbar_button_hover_color=DISABLED_TEXT)
        page.pack(fill="both", expand=True)
        page.columnconfigure(0, weight=1)
        self.column = ctk.CTkFrame(page, fg_color="transparent")
        self.column.grid(row=0, column=0, pady=(SPACE["md"], SPACE["section"]))
        self.column.columnconfigure(0, weight=1)
        self.hero = ctk.CTkLabel(self.column, text="", image=_hero_image())
        self.hero.grid(row=0, column=0, sticky="ew")
        self._build_language()
        self._build_start()
        self._build_error()
        self._build_log()
        footer = ctk.CTkLabel(self.column, text_color=MUTED, font=_font("body"))
        footer.grid(row=5, column=0, pady=(SPACE["md"], 0))
        self.bind_text(footer, lambda: f"{ui_text('patcher_version')}: {APP_VERSION}")
        self.device_label.configure(text=ui_text("device_not_connected"))
        self.show_work_dir()
        self.show_language_card()
        self.show_start()
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.after(100, self.pump)

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
        return ctk.CTkLabel(master, text="", text_color=color, font=_font(kind), anchor="w", justify="left",
                            **{"wraplength": WRAP, **options})

    def place(self, widget: ctk.CTkBaseClass, row: int, top: int = 0, bottom: int = 0, **options) -> None:
        widget.grid(row=row, column=0, sticky="ew", padx=CARD_PAD, pady=(top, bottom), **options)

    def _build_language(self) -> None:
        """① Language: the title, the language note, the two choices, then Remove translation."""
        card = self.card(1)
        self.place(self.bind_text(self.label(card, "label", MUTED), lambda: ui_text("01_your_translation")), 0,
                   top=CARD_PAD)
        self.place(self.bind_text(self.label(card, "heading"), lambda: ui_text("language")), 1, top=SPACE["xxs"])
        self.language_note = self.label(card, "body", MUTED)
        self.place(self.language_note, 2, top=SPACE["xxs"])
        choices = ctk.CTkFrame(card, fg_color="transparent")
        self.place(choices, 3, top=SPACE["sm"])
        self.choices: dict[str, ctk.CTkButton] = {}
        for column, (code, item) in enumerate(languages.LANGUAGES.items()):
            choices.columnconfigure(column, weight=1, uniform="choice")
            button = _make_button(choices, "secondary", lambda code=code: self.choose_language(code), text=item.name)
            button.grid(row=0, column=column, sticky="ew", padx=(0 if column == 0 else SPACE["xs"], 0))
            self.choices[code] = button
        self.remove_button = _make_button(card, "secondary", self.confirm_remove)
        self.bind_text(self.remove_button, lambda: ui_text("remove_translation"))
        self.place(self.remove_button, 4, top=SPACE["sm"])
        # Closes the card whether or not Remove translation shows.
        ctk.CTkFrame(card, fg_color="transparent", width=1, height=CARD_PAD).grid(row=5, column=0)

    def _build_start(self) -> None:
        """② Start: the checklist, device and working folder, then the state and its one primary button."""
        card = self.card(2)
        self.stage = self.label(card, "label", MUTED)
        self.place(self.stage, 0, top=CARD_PAD)

        self.checklist = ctk.CTkFrame(card, fg_color="transparent")
        self.checklist.columnconfigure(0, weight=1)
        self.bind_text(self.label(self.checklist, "button"), lambda: ui_text("before_you_start")).grid(
            row=0, column=0, sticky="ew")
        self.bind_text(self.label(self.checklist, "body", MUTED), lambda: ui_text("before_you_start_tips")).grid(
            row=1, column=0, sticky="ew", pady=(SPACE["xxs"], 0))
        self.place(self.checklist, 1, top=SPACE["sm"])

        device = ctk.CTkFrame(card, fg_color="transparent")
        device.columnconfigure(1, weight=1)
        self.bind_text(self.label(device, "label", MUTED), lambda: ui_text("device_label")).grid(
            row=0, column=0, columnspan=2, sticky="ew")
        self.device_dot = ctk.CTkLabel(device, text="●", text_color=DISABLED_TEXT, font=_font("body"), width=18)
        self.device_dot.grid(row=1, column=0, sticky="nw")
        self.device_label = self.label(device, "body", wraplength=WRAP - 24)
        self.device_label.grid(row=1, column=1, sticky="ew", padx=(SPACE["xxs"], 0))
        self.place(device, 2, top=SPACE["md"])

        folder = ctk.CTkFrame(card, fg_color="transparent")
        folder.columnconfigure(0, weight=1)
        self.bind_text(self.label(folder, "label", MUTED), lambda: ui_text("working_folder_label")).grid(
            row=0, column=0, sticky="ew")
        self.folder_label = self.label(folder, "body", wraplength=WRAP - 140)
        self.folder_label.grid(row=1, column=0, sticky="ew")
        self.space_label = self.label(folder, "body", MUTED, wraplength=WRAP - 140)
        self.space_label.grid(row=2, column=0, sticky="ew")
        self.folder_button = _make_button(folder, "secondary", self.choose_folder, width=120)
        self.bind_text(self.folder_button, lambda: ui_text("change_folder"))
        self.folder_button.grid(row=1, column=1, rowspan=2, sticky="e", padx=(SPACE["sm"], 0))
        self.place(folder, 3, top=SPACE["md"])

        self.heading = self.label(card, "heading")
        self.place(self.heading, 4, top=SPACE["xl"])
        self.detail = self.label(card, "body", MUTED)
        self.place(self.detail, 5, top=SPACE["xxs"])
        self.result_items = ctk.CTkFrame(card, fg_color="transparent")
        self.result_items.columnconfigure(0, weight=1)
        self.place(self.result_items, 6, top=SPACE["xs"])
        self.result_note = self.label(card, "body")
        self.place(self.result_note, 7, top=SPACE["xs"])

        self.button = _make_button(card, "primary", self.start)
        self.place(self.button, 8, top=SPACE["md"], bottom=CARD_PAD)
        # Running: the bar and "Step N of M · <step>" take the button's place.
        self.progress_view = ctk.CTkFrame(card, fg_color="transparent")
        self.progress_view.columnconfigure(0, weight=1)
        self.progress = ctk.CTkProgressBar(self.progress_view, mode="determinate", progress_color=INK,
                                           fg_color=DISABLED_FILL, height=8, corner_radius=4)
        self.progress.grid(row=0, column=0, sticky="ew")
        self.step_line = self.label(self.progress_view, "button")
        self.step_line.grid(row=1, column=0, sticky="ew", pady=(SPACE["xs"], 0))
        self.place(self.progress_view, 9, top=SPACE["md"], bottom=CARD_PAD)

    def _build_error(self) -> None:
        """The error card, directly under ②: the cause and Save log for help."""
        self.error_card = self.card(3, ERROR_SURFACE, ERROR)
        self.place(self.bind_text(self.label(self.error_card, "heading"), lambda: ui_text("error_details")), 0,
                   top=CARD_PAD)
        self.error_text = self.label(self.error_card, "body")
        self.place(self.error_text, 1, top=SPACE["xxs"])
        save = _make_button(self.error_card, "secondary", self.save_log)
        self.place(self.bind_text(save, lambda: ui_text("save_log_for_help")), 2, top=SPACE["md"], bottom=CARD_PAD)
        self.error_card.grid_remove()

    def _build_log(self) -> None:
        card = self.card(4)
        self.place(self.bind_text(self.label(card, "heading"), lambda: ui_text("patching_activity")), 0, top=CARD_PAD)
        _, size, _ = _type("log")
        self.log_view = ctk.CTkTextbox(card, fg_color=PAGE, text_color=INK, corner_radius=RADIUS, border_width=0,
                                   height=LOG_HEIGHT, font=ctk.CTkFont(family="Consolas", size=size), wrap="word")
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
        held = holds_delta(self.work_dir)
        self.language_note.configure(text=ui_text("language_note_no_clear" if held else "language_note_clear_first"))
        if held:
            self.remove_button.grid()
        else:
            self.remove_button.grid_remove()
        # A run reads the language once at its start, so the choices and Remove translation lock while it runs.
        for code, button in self.choices.items():
            chosen = code == self.language
            _style_button(button, "primary" if chosen else "secondary", not self.busy)
            if self.busy and chosen:
                button.configure(border_color=DISABLED_TEXT)
        _style_button(self.remove_button, "secondary", not self.busy)

    def choose_language(self, code: str) -> None:
        if self.busy or code == self.language:
            return
        self.language = code
        save_language(code)
        set_interface_language(code)
        self.retext()

    def retext(self) -> None:
        """Redraw every text in the interface language."""
        for widget, text in self.texts:
            widget.configure(text=text())
        self.hero.configure(image=_hero_image())
        if not self.connected:
            self.device_label.configure(text=ui_text("device_not_connected"))
        self.show_work_dir()
        self.show_language_card()
        self.show_start()

    # ---------- ② Start ----------
    def show_work_dir(self) -> None:
        path = str(self.work_dir)
        self.folder_label.configure(text=path if len(path) <= 70 else "…" + path[-69:])
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

    def show_start(self) -> None:
        """Rewrite ② in place for the current state: idle, running, a result or failed."""
        kind, value = self.result or ("idle", None)
        items: list[str] = []
        note = ""
        self.error_card.grid_remove()
        if self.busy:
            stage, heading, detail = ui_text("02_working"), ui_text("working_on_your_game"), ""
        elif kind == "added":
            stage, heading, detail = ui_text("02_done"), ui_text("translation_added"), ""
            text, images, dropped, skipped = value
            items = ui_text("applied_counts", text_tables=text, applied_textures=images, skipped_tables=dropped,
                            skipped_textures=skipped).split("\n")
            note = ui_text("result_open_game")
        elif kind == "removed":
            stage, heading, detail = ui_text("02_done"), ui_text("translation_removed"), ui_text("reads_chinese_again")
            items = [ui_text("original_files_restored", count=value)] if value else [ui_text("already_untranslated")]
            note = ui_text("removed_login_note")
        elif kind == "failed":
            stage, heading, detail = ui_text("02_needs_attention"), ui_text("work_stopped"), ui_text("failed_status")
            self.error_text.configure(text=value or ui_text("unexpected_error"))
            self.error_card.grid()
        else:
            stage, heading = ui_text("02_ready_to_play"), ui_text("ready_when_you_are")
            detail = self.blocker or ui_text("ready_connect_phone")
        self.stage.configure(text=stage)
        self.heading.configure(text=heading)
        self.detail.configure(text=detail)
        self._show(self.detail, bool(detail))
        self._show(self.checklist, kind in ("idle", "failed") and not self.busy)
        for row in self.result_items.winfo_children():
            row.destroy()
        for row, item in enumerate(items):
            self._count_row(row, item)
        self._show(self.result_items, bool(items))
        self.result_note.configure(text=note)
        self._show(self.result_note, bool(note))
        self._show(self.button, not self.busy)
        self._show(self.progress_view, self.busy)
        if self.busy:
            self.show_step()
        else:
            again = {"added": ui_text("run_again"), "removed": ui_text("run_again"), "failed": ui_text("try_again")}
            self.button.configure(text=again.get(kind) or ui_text("start"))

    def _count_row(self, row: int, item: str) -> None:
        """'Label: value' with the value at the end, so five-digit counts line up."""
        label, _, value = item.rpartition(": ")
        line = ctk.CTkFrame(self.result_items, fg_color="transparent")
        line.grid(row=row, column=0, sticky="ew")
        line.columnconfigure(0, weight=1)
        ctk.CTkLabel(line, text=label or value, text_color=INK, font=_font("body"), anchor="w").grid(
            row=0, column=0, sticky="w")
        if label:
            ctk.CTkLabel(line, text=value, text_color=INK, font=_font("button"), anchor="e").grid(
                row=0, column=1, sticky="e")

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

    # ---------- working folder ----------
    def choose_folder(self) -> None:
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

    def _on_ui(self, func):
        done = threading.Event()
        box = {}

        def call():
            box["value"] = func()
            done.set()

        self.messages.put(("call", call))
        done.wait()
        return box["value"]

    def ask(self, title: str, message: str, danger: bool = True) -> bool:
        return self._on_ui(lambda: Dialog.show(self, title, message, confirm=True, danger=danger))

    def wait_user(self, title: str, message: str) -> None:
        self._on_ui(lambda: Dialog.show(self, title, message))

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
                    key, state, _ = value
                    index = [step for step, _ in STEPS].index(key)
                    if state == "active":
                        self.step_index = index
                        self.progress.set(index / len(STEPS))
                        self.show_step()
                    elif state in ("done", "skipped"):
                        self.progress.set((index + 1) / len(STEPS))
                elif kind == "device":
                    text, connected = value
                    self.connected = connected
                    self.device_label.configure(text=text)
                    self.device_dot.configure(text_color=INK if connected else WARNING)
                elif kind == "call":
                    value()
                elif kind == "done":
                    self.finish(*value)
        except queue.Empty:
            pass
        self.after(100, self.pump)

    def confirm_remove(self) -> None:
        # A plain dialog: removing writes the original files back and deletes no game data.
        if Dialog.show(self, ui_text("remove_the_translation_question"), ui_text("remove_confirmation"),
                       confirm=True, confirm_label=ui_text("remove_the_translation")):
            self.start(remove=True)

    def start(self, remove: bool = False) -> None:
        self.removing = remove
        self.busy = True
        self.result = None
        self.step_index = 0
        self.progress.set(0)
        _style_button(self.folder_button, "secondary", False)
        self.show_language_card()
        self.show_start()
        threading.Thread(target=self.worker, daemon=True).start()

    def worker(self) -> None:
        try:
            summary = Patcher(self, self.work_dir, self.language, remove=self.removing).run()
            if self.removing:
                self.messages.put(("done", ("removed", len(summary.get("removed", [])))))
                return
            text, images = count_translated(summary)
            counts = (text, images, count_untranslated_text(summary), count_untranslated_graphics(summary))
            self.messages.put(("done", ("added", counts)))
        except PatchError as error:
            self.messages.put(("done", ("failed", str(error))))
        except Exception:
            self.messages.put(("log", traceback.format_exc()))
            self.messages.put(("done", ("failed", None)))

    def finish(self, kind: str, value: object) -> None:
        self.busy = False
        self.result = (kind, value)
        if kind == "failed":
            self.log("\nFAILED: " + (value or "unexpected error"))
        elif kind == "added":
            self.log("\nSUCCESS: {} text tables and {} images applied, {} text tables and {} images skipped"
                     .format(*value))
        else:
            self.log(f"\nSUCCESS: translation removed, {value} original game files restored")
        _style_button(self.folder_button, "secondary", True)
        self.show_work_dir()
        self.show_language_card()
        self.show_start()

    def close(self) -> None:
        if self.busy and not Dialog.show(self, ui_text("close_while_busy_title"), ui_text("close_while_busy"),
                                         confirm=True, danger=True):
            return
        Adb.kill_server(self.work_dir)
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


def main() -> None:
    if len(sys.argv) in (4, 5) and sys.argv[1] == "--selftest":
        selftest(Path(sys.argv[2]), Path(sys.argv[3]), *sys.argv[4:])
        return
    try:
        # Own taskbar identity so Windows shows our icon instead of the Python one.
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("HOKAce.EnglishPatcher")
    except Exception:
        pass
    load_fonts()
    ctk.set_appearance_mode("light")
    app = App()
    sys.stdout = sys.stderr = LogStream(app)
    app.mainloop()


if __name__ == "__main__":
    main()
