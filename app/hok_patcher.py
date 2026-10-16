"""HOK ACE Language Patcher: English or Indonesian translation for a USB-connected Android phone."""
from __future__ import annotations

import ctypes
import tkinter.filedialog as filedialog
import queue
import sys
import threading
import traceback
from pathlib import Path

import customtkinter as ctk
from PIL import Image

from patcher_core import (BUNDLE, MIN_FREE_BYTES, STEPS, Adb, PatchError, Patcher, build_patch, count_translated,
                          count_untranslated_graphics, count_untranslated_text, free_space, languages,
                          load_language, load_work_dir, save_language, save_work_dir)

APP_TITLE = "HOK ACE Language Patcher"
APP_VERSION = "1.1"

# Palette
BG = "#0f1117"
SURFACE = "#171a23"
SURFACE_2 = "#1f2330"
BORDER = "#2a2f3d"
TEXT = "#e8eaf0"
MUTED = "#8b91a3"
ACCENT = "#7c5cff"
ACCENT_HOVER = "#6a4cf0"
GOLD = "#f6c453"
SUCCESS = "#3ecf8e"
DANGER = "#ff5c6c"

STATE_STYLE = {
    "pending": ("○", MUTED),
    "active": ("●", ACCENT),
    "done": ("✓", SUCCESS),
    "skipped": ("–", MUTED),
    "error": ("✕", DANGER),
}


class StepRow(ctk.CTkFrame):
    def __init__(self, master, index: int, label: str):
        super().__init__(master, fg_color="transparent")
        self.badge = ctk.CTkLabel(self, text=str(index), width=28, height=28, corner_radius=14,
                                  fg_color=SURFACE_2, text_color=MUTED, font=ctk.CTkFont(size=12, weight="bold"))
        self.badge.grid(row=0, column=0, rowspan=2, padx=(0, 12), pady=4)
        self.title = ctk.CTkLabel(self, text=label, text_color=TEXT, anchor="w", font=ctk.CTkFont(size=13, weight="bold"))
        self.title.grid(row=0, column=1, sticky="w")
        self.detail = ctk.CTkLabel(self, text="", text_color=MUTED, anchor="w", font=ctk.CTkFont(size=11), height=14)
        self.detail.grid(row=1, column=1, sticky="w")
        self.index = index
        self.columnconfigure(1, weight=1)

    def set(self, state: str, detail: str = "") -> None:
        symbol, color = STATE_STYLE[state]
        text = str(self.index) if state == "pending" else symbol
        self.badge.configure(text=text, fg_color=color if state in ("active", "done", "error") else SURFACE_2,
                             text_color="#0f1117" if state in ("done",) else (TEXT if state != "pending" else MUTED))
        self.title.configure(text_color=TEXT if state != "pending" else MUTED)
        if detail or state == "pending":
            self.detail.configure(text=detail)


class Dialog(ctk.CTkToplevel):
    """Themed modal message box returning True/False."""

    def __init__(self, master, title: str, message: str, confirm: bool, danger: bool = False):
        super().__init__(master, fg_color=SURFACE)
        self.title(title)
        self.resizable(False, False)
        self.result = False
        self.transient(master)
        ctk.CTkLabel(self, text=title, font=ctk.CTkFont(size=16, weight="bold"), text_color=TEXT).pack(
            anchor="w", padx=24, pady=(22, 8))
        ctk.CTkLabel(self, text=message, wraplength=420, justify="left", text_color=MUTED,
                     font=ctk.CTkFont(size=13)).pack(anchor="w", padx=24)
        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.pack(fill="x", padx=24, pady=22)
        ok_color = DANGER if danger else ACCENT
        ctk.CTkButton(buttons, text="Continue" if confirm else "OK", fg_color=ok_color, hover_color=ACCENT_HOVER,
                      width=120, height=36, corner_radius=10, command=self._ok).pack(side="right")
        if confirm:
            ctk.CTkButton(buttons, text="Cancel", fg_color=SURFACE_2, hover_color=BORDER, width=100, height=36,
                          corner_radius=10, command=self.destroy).pack(side="right", padx=(0, 10))
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
    def show(cls, master, title: str, message: str, confirm: bool = False, danger: bool = False) -> bool:
        dialog = cls(master, title, message, confirm, danger)
        master.wait_window(dialog)
        return dialog.result


class App(ctk.CTk):
    def __init__(self) -> None:
        super().__init__(fg_color=BG)
        self.title(APP_TITLE)
        self.geometry("960x660")
        self.minsize(860, 600)
        icon = BUNDLE / "icon.ico"
        if icon.exists():
            self.iconbitmap(str(icon))
        self.messages: queue.Queue = queue.Queue()
        self.busy = False
        self.rows: dict[str, StepRow] = {}
        self.work_dir = load_work_dir()
        self.language = load_language()

        self.columnconfigure(0, weight=0, minsize=320)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)
        self._build_header()
        self._build_sidebar()
        self._build_main()
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.after(100, self.pump)

    # ---------- layout ----------
    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color=SURFACE, corner_radius=0, height=84)
        header.grid(row=0, column=0, columnspan=2, sticky="ew")
        header.columnconfigure(1, weight=1)
        png = BUNDLE / "icon.png"
        if png.exists():
            image = ctk.CTkImage(Image.open(png), size=(52, 52))
            ctk.CTkLabel(header, image=image, text="").grid(row=0, column=0, rowspan=2, padx=(24, 14), pady=16)
        ctk.CTkLabel(header, text=APP_TITLE, text_color=TEXT,
                     font=ctk.CTkFont(size=20, weight="bold")).grid(row=0, column=1, sticky="sw", pady=(18, 0))
        ctk.CTkLabel(header, text="English or Indonesian translation for 王者万象棋 (Android) · no root required",
                     text_color=MUTED, font=ctk.CTkFont(size=12)).grid(row=1, column=1, sticky="nw", pady=(0, 16))
        ctk.CTkLabel(header, text=f"v{APP_VERSION}", text_color=GOLD, fg_color=SURFACE_2, corner_radius=8,
                     width=52, height=26, font=ctk.CTkFont(size=12, weight="bold")).grid(
            row=0, column=2, rowspan=2, padx=24)

    def _build_sidebar(self) -> None:
        side = ctk.CTkFrame(self, fg_color="transparent")
        side.grid(row=1, column=0, sticky="nsew", padx=(20, 10), pady=20)
        side.rowconfigure(1, weight=1)

        device = ctk.CTkFrame(side, fg_color=SURFACE, corner_radius=14, border_width=1, border_color=BORDER)
        device.grid(row=0, column=0, sticky="ew")
        device.columnconfigure(1, weight=1)
        self.device_dot = ctk.CTkLabel(device, text="●", text_color=MUTED, font=ctk.CTkFont(size=18))
        self.device_dot.grid(row=0, column=0, rowspan=2, padx=(16, 10), pady=14)
        ctk.CTkLabel(device, text="DEVICE", text_color=MUTED, font=ctk.CTkFont(size=10, weight="bold")).grid(
            row=0, column=1, sticky="sw", pady=(12, 0))
        self.device_label = ctk.CTkLabel(device, text="Not connected", text_color=TEXT, anchor="w",
                                         wraplength=230, justify="left", font=ctk.CTkFont(size=13))
        self.device_label.grid(row=1, column=1, sticky="nw", pady=(0, 12), padx=(0, 12))

        steps = ctk.CTkFrame(side, fg_color=SURFACE, corner_radius=14, border_width=1, border_color=BORDER)
        steps.grid(row=1, column=0, sticky="nsew", pady=(14, 0))
        ctk.CTkLabel(steps, text="PROGRESS", text_color=MUTED, font=ctk.CTkFont(size=10, weight="bold")).pack(
            anchor="w", padx=18, pady=(14, 4))
        for index, (key, label) in enumerate(STEPS, 1):
            row = StepRow(steps, index, label)
            row.pack(fill="x", padx=18, pady=2)
            self.rows[key] = row

    def _build_main(self) -> None:
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.grid(row=1, column=1, sticky="nsew", padx=(10, 20), pady=20)
        main.columnconfigure(0, weight=1)
        main.rowconfigure(4, weight=1)

        guide = ctk.CTkFrame(main, fg_color=SURFACE, corner_radius=14, border_width=1, border_color=BORDER)
        guide.grid(row=0, column=0, sticky="ew")
        guide.columnconfigure(0, weight=1)
        ctk.CTkLabel(guide, text="Before you start", text_color=TEXT, font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=18, pady=(14, 4))
        tips = ("1.  Enable USB debugging on the phone, connect the USB cable and tap 'Allow'.\n"
                "2.  Open the game once until the data download finishes (login screen), then close it.\n"
                "3.  If Google Play Protect asks, tap 'More details' → 'Install anyway'.")
        ctk.CTkLabel(guide, text=tips, justify="left", text_color=MUTED, font=ctk.CTkFont(size=12)).grid(
            row=1, column=0, sticky="w", padx=18, pady=(0, 14))

        folder = ctk.CTkFrame(main, fg_color=SURFACE, corner_radius=14, border_width=1, border_color=BORDER)
        folder.grid(row=1, column=0, sticky="ew", pady=(14, 0))
        folder.columnconfigure(0, weight=1)
        ctk.CTkLabel(folder, text="WORKING FOLDER  ·  temporary game data, about 8 GB", text_color=MUTED,
                     font=ctk.CTkFont(size=10, weight="bold")).grid(row=0, column=0, sticky="w", padx=18, pady=(12, 2))
        self.folder_label = ctk.CTkLabel(folder, text="", text_color=TEXT, anchor="w", font=ctk.CTkFont(size=12))
        self.folder_label.grid(row=1, column=0, sticky="ew", padx=18)
        self.space_label = ctk.CTkLabel(folder, text="", text_color=MUTED, anchor="w", font=ctk.CTkFont(size=11))
        self.space_label.grid(row=2, column=0, sticky="w", padx=18, pady=(0, 12))
        self.folder_button = ctk.CTkButton(folder, text="Change…", width=110, height=34, corner_radius=10,
                                           fg_color=SURFACE_2, hover_color=BORDER, command=self.choose_folder)
        self.folder_button.grid(row=0, column=1, rowspan=3, padx=18)
        self.show_work_dir()

        language = ctk.CTkFrame(main, fg_color=SURFACE, corner_radius=14, border_width=1, border_color=BORDER)
        language.grid(row=2, column=0, sticky="ew", pady=(14, 0))
        language.columnconfigure(0, weight=1)
        ctk.CTkLabel(language, text="LANGUAGE  ·  the translation installed into the game", text_color=MUTED,
                     font=ctk.CTkFont(size=10, weight="bold")).grid(row=0, column=0, sticky="sw", padx=18, pady=(12, 0))
        # Measured: a pass over an already-English install changes no table, only the re-drawn textures.
        ctk.CTkLabel(language, text="To switch a phone that is already translated, clear the game's data and "
                                    "let it download again first.", text_color=MUTED, anchor="w", wraplength=330,
                     justify="left", font=ctk.CTkFont(size=11)).grid(row=1, column=0, sticky="nw", padx=18,
                                                                      pady=(0, 12))
        names = {item.name: code for code, item in languages.LANGUAGES.items()}
        self.language_picker = ctk.CTkSegmentedButton(
            language, values=list(names), selected_color=ACCENT, selected_hover_color=ACCENT_HOVER,
            unselected_color=SURFACE_2, unselected_hover_color=BORDER, height=32, corner_radius=10,
            command=lambda name: self.choose_language(names[name]))
        self.language_picker.set(languages.get(self.language).name)
        self.language_picker.grid(row=0, column=1, rowspan=2, padx=18, pady=10)

        action = ctk.CTkFrame(main, fg_color="transparent")
        action.grid(row=3, column=0, sticky="ew", pady=14)
        action.columnconfigure(1, weight=1)
        self.button = ctk.CTkButton(action, text="Start Patch", fg_color=ACCENT, hover_color=ACCENT_HOVER,
                                    height=46, width=180, corner_radius=12,
                                    font=ctk.CTkFont(size=15, weight="bold"), command=self.start)
        self.button.grid(row=0, column=0, rowspan=2)
        self.status = ctk.CTkLabel(action, text="Ready. Connect your phone and click Start Patch.", text_color=TEXT,
                                   anchor="w", font=ctk.CTkFont(size=13))
        self.status.grid(row=0, column=1, sticky="ew", padx=(16, 0))
        self.progress = ctk.CTkProgressBar(action, mode="determinate", progress_color=ACCENT, fg_color=SURFACE_2,
                                           height=6, corner_radius=3)
        self.progress.grid(row=1, column=1, sticky="ew", padx=(16, 0), pady=(8, 0))
        self.progress.set(0)

        log_card = ctk.CTkFrame(main, fg_color=SURFACE, corner_radius=14, border_width=1, border_color=BORDER)
        log_card.grid(row=4, column=0, sticky="nsew")
        log_card.rowconfigure(1, weight=1)
        log_card.columnconfigure(0, weight=1)
        ctk.CTkLabel(log_card, text="LOG", text_color=MUTED, font=ctk.CTkFont(size=10, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=18, pady=(12, 4))
        self.text = ctk.CTkTextbox(log_card, fg_color=BG, text_color="#c6cad6", corner_radius=10, border_width=0,
                                   font=ctk.CTkFont(family="Consolas", size=12), wrap="word")
        self.text.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        self.text.configure(state="disabled")

    # ---------- working folder ----------
    def show_work_dir(self) -> None:
        path = str(self.work_dir)
        self.folder_label.configure(text=path if len(path) <= 70 else "…" + path[-69:])
        free = free_space(self.work_dir)
        if free is None:
            self.space_label.configure(text="Drive not available", text_color=DANGER)
        else:
            enough = free >= MIN_FREE_BYTES
            self.space_label.configure(
                text=f"{free / 1024**3:.1f} GB free on this drive" + ("" if enough else " — not enough, choose another drive"),
                text_color=MUTED if enough else DANGER)

    def choose_folder(self) -> None:
        chosen = filedialog.askdirectory(parent=self, title="Choose a folder for the temporary game data",
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

    def choose_language(self, code: str) -> None:
        self.language = code
        save_language(code)

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

    def ask(self, title: str, message: str) -> bool:
        return self._on_ui(lambda: Dialog.show(self, title, message, confirm=True, danger=True))

    def wait_user(self, title: str, message: str) -> None:
        self._on_ui(lambda: Dialog.show(self, title, message))

    # ---------- event loop ----------
    def pump(self) -> None:
        try:
            while True:
                kind, value = self.messages.get_nowait()
                if kind == "log":
                    self.text.configure(state="normal")
                    self.text.insert("end", value + "\n")
                    self.text.see("end")
                    self.text.configure(state="disabled")
                elif kind == "step":
                    key, state, detail = value
                    self.rows[key].set(state, detail)
                    if state == "active":
                        self.status.configure(text=f"{dict(STEPS)[key]}{' — ' + detail if detail else ''}")
                elif kind == "device":
                    text, connected = value
                    self.device_label.configure(text=text)
                    self.device_dot.configure(text_color=SUCCESS if connected else GOLD)
                elif kind == "call":
                    value()
                elif kind == "done":
                    self.finish(*value)
        except queue.Empty:
            pass
        self.after(100, self.pump)

    def start(self) -> None:
        self.busy = True
        for row in self.rows.values():
            row.set("pending")
        self.button.configure(state="disabled", text="Running…")
        self.folder_button.configure(state="disabled")
        self.language_picker.configure(state="disabled")
        self.progress.configure(mode="indeterminate")
        self.progress.start()
        threading.Thread(target=self.worker, daemon=True).start()

    def worker(self) -> None:
        try:
            summary = Patcher(self, self.work_dir, self.language).run()
            text, images = count_translated(summary)
            dropped_text = count_untranslated_text(summary)
            skipped = count_untranslated_graphics(summary)
            if text or images:
                detail = f"{text} text tables and {images} images translated. "
            elif dropped_text:
                detail = "Nothing new to install. "
            else:
                detail = "The translation was already installed. "
            if dropped_text:
                detail += (f"{dropped_text} text table{'s' if dropped_text != 1 else ''} could not be "
                           "applied and stay in Chinese. ")
            if skipped:
                detail += (f"{skipped} image{'s' if skipped != 1 else ''} could not be translated "
                           "and stay in Chinese. ")
            self.messages.put(("done", (True, detail + "Open the game on your phone.\n\nLogin: use 'Scan to login' "
                                        "(the direct WeChat/QQ buttons do not work). With one phone: screenshot the QR code, "
                                        "open WeChat in split screen and scan it from the gallery.")))
        except PatchError as error:
            self.messages.put(("done", (False, str(error))))
        except Exception:
            self.messages.put(("log", traceback.format_exc()))
            self.messages.put(("done", (False, "An unexpected error occurred. See the log in this window.")))

    def finish(self, ok: bool, message: str) -> None:
        self.busy = False
        self.progress.stop()
        self.progress.configure(mode="determinate")
        self.progress.set(1 if ok else 0)
        self.button.configure(state="normal", text="Run Again" if ok else "Try Again")
        self.folder_button.configure(state="normal")
        self.language_picker.configure(state="normal")
        self.show_work_dir()
        self.status.configure(text="Done! Translation installed." if ok else "Failed. See the log for details.",
                              text_color=SUCCESS if ok else DANGER)
        self.log(("\nSUCCESS: " if ok else "\nFAILED: ") + message)
        Dialog.show(self, "Done" if ok else "Failed", message)
        self.status.configure(text_color=TEXT)

    def close(self) -> None:
        if self.busy and not Dialog.show(
            self, "Patch in progress",
            "Closing now can leave the game unable to start until the patcher is run again.\n\nClose anyway?",
            confirm=True, danger=True,
        ):
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
    import json

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
    ctk.set_appearance_mode("dark")
    app = App()
    sys.stdout = sys.stderr = LogStream(app)
    app.mainloop()


if __name__ == "__main__":
    main()
