"""Patch workflow: device detection, temporary data-access APK, translation build and install."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tarfile
import time
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Protocol

PACKAGE = "com.tencent.tmgp.osgame"
REMOTE_TMP = "/data/local/tmp/hokace"
MIN_FREE_BYTES = 8 * 1024**3
NO_WINDOW = 0x08000000 if os.name == "nt" else 0
# The name the game is listed under once patched. Writing it is cosmetic, so a manifest this cannot
# be written into is logged and the run continues.
APP_NAME = "Honor of Kings: ACE"

PROJECT = Path(__file__).resolve().parents[1]
BUNDLE = Path(getattr(sys, "_MEIPASS", PROJECT / "resources"))
if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(PROJECT / "tools"))  # the exe gets these via PyInstaller --paths
# Only the chosen working folder is remembered here (a few bytes); the ~8 GB of game data goes to
# whatever folder the user picks.
SETTINGS = Path(os.environ.get("APPDATA", Path.home())) / "HOKAceEnglishPatcher" / "settings.json"

# Translation runtime (compiled wxq_patch modules) ships as data; append so our stdlib wins.
sys.path.append(str(BUNDLE / "runtime"))

import apk_tools  # noqa: E402
from axml_label import set_label  # noqa: E402
from axml_set_debuggable import is_debuggable, patch as make_debuggable_manifest  # noqa: E402
from build_device_patch import build_patch  # noqa: E402
from qts_builder import find_builder_dir  # noqa: E402

PLAY_PROTECT_HINT = "If Google Play Protect shows a pop-up on the phone, tap 'More details' -> 'Install anyway'."

# (key, label) in display order; the UI renders these as a stepper.
STEPS = [
    ("device", "Connect phone"),
    ("apk", "Prepare game APK"),
    ("access", "Unlock data access"),
    ("pull", "Read language data"),
    ("translate", "Build translation"),
    ("install", "Install translation"),
    ("restore", "Restore game"),
]


def count_translated(summary: dict) -> tuple[int, int]:
    """(text tables, textures) written by build_patch.

    A rebuilt package holds both kinds and its `replacement_count` covers both, so it carries the
    texture share in `textures`; classifying it by mode alone would report package 1's tables as
    images, or package 1050016095's images as tables. A package the append pass added to carries the
    same split for the same reason.
    """
    text = images = 0
    for package in summary.get("packages", []):
        count = package["stage_report"]["replacement_count"]
        if package.get("mode") == "graphics":
            images += count
        elif package.get("mode") in ("rebuilt", "added-from-apk"):
            textures = package.get("textures", 0)
            images += textures
            text += count - textures
        else:
            text += count
    return text, images


def count_untranslated_graphics(summary: dict) -> int:
    """Textures the run found but could not translate, so they stay in Chinese.

    These live in build_patch's separate `graphics_skipped` list, not in `packages`: a package whose
    every texture was skipped writes no directory, and the installer pushes by directory. The append
    pass reports the textures it could not add the same way, in `append_skipped` — where a package that
    got some of its assets can also appear, naming the share that stays Chinese.
    """
    return (sum(entry.get("skipped_count", 0) for entry in summary.get("graphics_skipped", []))
            + sum(entry.get("textures", 0) for entry in summary.get("append_skipped", [])))


def count_untranslated_text(summary: dict) -> int:
    """Text tables the run translated but could not apply, so they stay in Chinese.

    These live in build_patch's `text_skipped` list. A package that loses tables can still have an
    output directory behind it — and one that loses all of them has none — so `packages` alone
    cannot say what did not make it. The append pass reports the tables it could not add in
    `append_skipped`; its entries count both kinds, so the tables are what is left after `textures`.
    That list carries the same two shapes, a package the pass could not add to at all and the refused
    share of one it did add to.
    """
    return (sum(entry.get("dropped_count", 0) for entry in summary.get("text_skipped", []))
            + sum(entry.get("assets", 0) - entry.get("textures", 0)
                  for entry in summary.get("append_skipped", [])))


class PatchError(Exception):
    """Expected failure with a message meant for the user."""


def default_work_dir() -> Path:
    """Folder next to the exe, so the data lands on whatever drive the user put the patcher on."""
    base = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
    return base / "HOK ACE Patcher Data"


def load_work_dir() -> Path:
    try:
        return Path(json.loads(SETTINGS.read_text(encoding="utf-8"))["work_dir"])
    except (OSError, ValueError, KeyError, TypeError):
        return default_work_dir()


def save_work_dir(path: Path) -> None:
    try:
        SETTINGS.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS.write_text(json.dumps({"work_dir": str(path)}), encoding="utf-8")
    except OSError:
        pass  # the choice still applies for this session


def free_space(path: Path) -> int | None:
    """Free bytes on the drive holding <path> (or its nearest existing parent)."""
    probe = path
    while not probe.exists() and probe.parent != probe:
        probe = probe.parent
    try:
        return shutil.disk_usage(probe).free
    except OSError:
        return None


def check_work_dir(path: Path) -> None:
    """Raise PatchError unless <path> is writable and has room for the game data."""
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write-test"
        probe.write_bytes(b"ok")
        probe.unlink()
    except OSError as error:
        raise PatchError(f"The working folder cannot be used:\n{path}\n{error}\n\nChoose another folder.") from error
    free = shutil.disk_usage(path).free
    if free < MIN_FREE_BYTES:
        raise PatchError(f"Not enough disk space in the working folder ({path}). At least 8 GB free is "
                         f"needed (currently {free / 1024**3:.1f} GB). Choose a folder on another drive.")


def apk_manifest(apk: Path) -> bytes:
    """The APK's binary AndroidManifest.xml."""
    with zipfile.ZipFile(apk) as archive:
        return archive.read("AndroidManifest.xml")


class Ui(Protocol):
    def log(self, line: str) -> None: ...
    def set_step(self, key: str, state: str, detail: str = "") -> None: ...
    def set_device(self, text: str, connected: bool) -> None: ...
    def ask(self, title: str, message: str) -> bool: ...
    def wait_user(self, title: str, message: str) -> None: ...


class Adb:
    def __init__(self, work: Path) -> None:
        target = work / "adb"
        target.mkdir(parents=True, exist_ok=True)
        # Run adb from a persistent folder so its background server never locks the PyInstaller temp dir.
        for item in (BUNDLE / "adb").iterdir():
            if not (target / item.name).exists() or (target / item.name).stat().st_size != item.stat().st_size:
                shutil.copy2(item, target / item.name)
        self.exe = str(target / "adb.exe")

    def run(self, *args: str, check: bool = True) -> str:
        result = subprocess.run([self.exe, *args], capture_output=True, text=True, encoding="utf-8",
                                errors="replace", creationflags=NO_WINDOW)
        output = (result.stdout + result.stderr).strip()
        if check and result.returncode != 0:
            raise PatchError(f"adb command failed: adb {' '.join(args)}\n{output}")
        return output

    def shell(self, command: str, check: bool = True) -> str:
        return self.run("shell", command, check=check)

    def exec_out_to_file(self, command: str, target: Path) -> None:
        with target.open("wb") as out:
            result = subprocess.run([self.exe, "exec-out", command], stdout=out, stderr=subprocess.PIPE,
                                    creationflags=NO_WINDOW)
        if result.returncode != 0:
            raise PatchError(f"Could not read data from the phone:\n{result.stderr.decode(errors='replace')}")

    def install(self, apk: Path) -> None:
        output = self.run("install", "-r", str(apk), check=False)
        if "Success" not in output:
            if "INSTALL_FAILED_VERIFICATION_FAILURE" in output:
                raise PatchError("Google Play Protect blocked the install. Try again and on the phone tap "
                                 "'More details' -> 'Install anyway'.")
            raise PatchError(f"APK install failed:\n{output}")

    @staticmethod
    def kill_server(work: Path) -> None:
        adb = work / "adb" / "adb.exe"
        if adb.exists():
            subprocess.run([str(adb), "kill-server"], creationflags=NO_WINDOW, capture_output=True)


class Patcher:
    def __init__(self, ui: Ui, work: Path):
        self.ui = ui
        self.work = work
        self.log = ui.log
        self.adb: Adb | None = None
        self.normal_apk: Path | None = None
        self.debuggable_installed = False
        self.current: str | None = None

    def run(self) -> dict:
        check_work_dir(self.work)
        self.log(f"Working folder: {self.work}")
        self.adb = Adb(self.work)
        self.wait_for_device()
        base_path = self.find_installed_apk()
        result = {"packages": []}
        try:
            self.prepare_normal_apk(base_path)
            debuggable = self.prepare_debuggable_apk()
            self.log(PLAY_PROTECT_HINT)
            self.log("Do NOT open the game until the patch has finished.")
            self.adb.shell(f"am force-stop {PACKAGE}", check=False)
            self.debuggable_installed = True
            self.adb.install(debuggable)
            self.done("access")
            session = self.pull_game_data()
            summary, staged = self.build_translation(session)
            result = summary
            if staged:
                self.push_translation(staged)
            else:
                self.skip("install", "nothing to change")
        except Exception:
            if self.current:
                self.ui.set_step(self.current, "error")
                self.current = None
            raise
        finally:
            if self.debuggable_installed:
                self.restore_normal_apk()
        return result

    # ---------- stepper helpers ----------
    def step(self, key: str, detail: str = "") -> None:
        if self.current and self.current != key:
            self.ui.set_step(self.current, "done")
        self.current = key
        self.ui.set_step(key, "active", detail)
        label = dict(STEPS)[key]
        self.log(f"\n== {label}{' - ' + detail if detail else ''}")

    def done(self, key: str, detail: str = "") -> None:
        self.ui.set_step(key, "done", detail)
        if self.current == key:
            self.current = None

    def skip(self, key: str, detail: str) -> None:
        self.ui.set_step(key, "skipped", detail)

    # ---------- workflow ----------
    def wait_for_device(self) -> None:
        self.step("device", "waiting for USB connection")
        self.adb.run("start-server", check=False)
        hinted = set()
        while True:
            lines = [l.split() for l in self.adb.run("devices").splitlines()[1:] if l.strip()]
            states = [parts[1] for parts in lines if len(parts) >= 2]
            if states.count("device") == 1 and len(states) == 1:
                brand = self.adb.shell("getprop ro.product.brand", check=False)
                model = self.adb.shell("getprop ro.product.model", check=False)
                release = self.adb.shell("getprop ro.build.version.release", check=False)
                name = f"{brand} {model}".strip()
                self.ui.set_device(f"{name}  ·  Android {release}", True)
                self.log(f"Phone detected: {name} (Android {release})")
                self.done("device", name)
                return
            if len(states) > 1:
                hint = "More than one phone/emulator is connected. Keep only one."
            elif "unauthorized" in states:
                hint = "On the phone, tap 'Allow' on the 'Allow USB debugging' prompt."
            else:
                hint = ("Connect the phone with a USB cable and enable USB debugging "
                        "(Settings > Developer options > USB debugging).")
            if hint not in hinted:
                self.log(hint)
                self.ui.set_device(hint, False)
                hinted.add(hint)
            time.sleep(2)

    def find_installed_apk(self) -> str:
        output = self.adb.shell(f"pm path {PACKAGE}", check=False)
        paths = [line[len("package:"):].strip() for line in output.splitlines() if line.startswith("package:")]
        if not paths:
            raise PatchError("HOK ACE (王者万象棋) is not installed on this phone. Install the game first.")
        if len(paths) > 1:
            raise PatchError("This game build is installed as split APKs, which the patcher does not support yet.")
        return paths[0]

    def manifest_to_install(self, manifest: bytes) -> bytes:
        """The manifest of the APK we install: no debug flag, and the game named in English.

        Only the first is load-bearing (the game dies during startup under a debuggable build) and only
        the second is optional: a manifest the rename cannot read keeps the game's own name rather than
        failing the run, because the translation is what the user is here for. Both are reported, so a
        run that did not rename the app says so.
        """
        if is_debuggable(manifest):
            self.log("The cached APK carries the debug flag; rebuilding it without it.")
            manifest = make_debuggable_manifest(manifest, debuggable=False)
        try:
            named = set_label(manifest, APP_NAME)
        except ValueError as error:
            self.log(f"  leaving the app name as it is: {error}")
            return manifest
        if named != manifest:
            self.log(f"  naming the app {APP_NAME!r}")
        return named

    def prepare_normal_apk(self, remote_path: str) -> None:
        self.step("apk", "copying the APK from the phone (~2 GB)")
        remote_size = int(self.adb.shell(f"stat -c %s '{remote_path}'").split()[0])
        local = self.work / "installed.apk"
        access = self.work / "access.apk"
        # A run interrupted between installing the access APK and restoring the game APK leaves our
        # own debuggable copy on the phone. It differs from the cached one by a byte, so the size test
        # below would pull it in and cache it as the game APK, and every later restore would install a
        # debug build. While the phone runs the access APK we built, the cache stays the source.
        needs_copy = not local.exists() or local.stat().st_size != remote_size
        if needs_copy and access.exists() and remote_size == access.stat().st_size:
            self.log("The phone is still running the temporary access APK; using the cached game APK.")
            needs_copy = False
        if needs_copy:
            partial = self.work / "installed.apk.part"
            self.adb.run("pull", remote_path, str(partial))
            partial.replace(local)
        else:
            self.log("APK already cached, skipping the copy.")
        # Whether the phone carries our signature is a property of the file the phone just gave us, so
        # it is read before any rebuild: a rebuilt APK always carries it, and asking afterwards would
        # answer yes for Tencent's own build too and skip the reinstall that build needs.
        cert = (BUNDLE / "key" / "cert.der").read_bytes()
        mine = apk_tools.signed_with(local, cert)
        manifest = apk_manifest(local)
        wanted = self.manifest_to_install(manifest)
        if wanted != manifest:
            # Only the manifest separates our build from the game's own APK, so rebuilding it here is
            # how a cached APK from an older version comes to carry the patch, and the run's last step
            # is what installs it. This is also what stops the work repeating: the next run reads the
            # rebuilt cache back and finds nothing left to write.
            clean = self.work / "normal-clean.apk"
            self.build_signed(local, clean, {"AndroidManifest.xml": wanted})
            clean.replace(local)
        if mine:
            self.log("The game uses the patcher-signed APK (signature matches).")
            self.normal_apk = local
            self.done("apk", "signature matches")
            return

        self.log("The game is the official Tencent build.")
        if not self.ui.ask(
            "Reinstall required",
            "The game on this phone uses the official Tencent signature, so it must be reinstalled "
            "with the patcher signature.\n\nThis DELETES the game data on the phone and the game will "
            "download its data again (~1.7 GB). Direct WeChat/QQ login will no longer work; use "
            "'Scan to login' instead.\n\nContinue?",
        ):
            raise PatchError("Cancelled by the user.")
        self.step("apk", "building the patcher-signed APK")
        resigned = self.work / "normal.apk"
        self.build_signed(local, resigned, {"AndroidManifest.xml": wanted})
        self.normal_apk = resigned
        self.step("apk", "reinstalling the game")
        self.adb.run("uninstall", PACKAGE, check=False)
        self.log(PLAY_PROTECT_HINT)
        self.adb.install(resigned)
        self.ui.wait_user(
            "Download game data",
            "Open the game on the phone, accept the policies and wait until the data download "
            "finishes and the login screen appears.\n\nThen CLOSE the game and click OK here.",
        )
        self.done("apk", "reinstalled")

    def build_signed(self, source: Path, target: Path, replacements: dict[str, bytes]) -> None:
        unsigned = target.with_suffix(".unsigned")
        last = [0.0]

        def progress(done, total):
            if time.time() - last[0] > 5:
                last[0] = time.time()
                self.log(f"  building APK {done * 100 // total}%")

        apk_tools.rewrite_apk(source, unsigned, replacements, progress)
        self.log("  signing APK...")
        apk_tools.sign_v2(unsigned, target, (BUNDLE / "key" / "key.pk8").read_bytes(),
                          (BUNDLE / "key" / "cert.der").read_bytes())
        unsigned.unlink()

    def prepare_debuggable_apk(self) -> Path:
        self.step("access", "preparing the temporary access APK")
        target = self.work / "access.apk"
        stamp = self.work / "access.apk.source"
        source_id = f"{self.normal_apk.stat().st_size}:{self.normal_apk.stat().st_mtime_ns}"
        if not (target.exists() and stamp.exists() and stamp.read_text() == source_id):
            manifest = make_debuggable_manifest(apk_manifest(self.normal_apk))
            self.build_signed(self.normal_apk, target, {"AndroidManifest.xml": manifest})
            stamp.write_text(source_id)
        self.ui.set_step("access", "active", "installing the access APK (check the phone for a pop-up)")
        return target

    def pull_game_data(self) -> Path:
        self.step("pull", "~2 GB")
        info = self.adb.shell(f"run-as {PACKAGE} cat files/QtsVFSCache/packages/1/1.info", check=False)
        if '"version"' not in info:
            raise PatchError("The game data has not been downloaded yet. Open the game, wait for the download to "
                             "reach the login screen, close the game, then run the patcher again.")
        self.log(f"Game data version: {info.strip()}")
        session = self.work / "sessions" / datetime.now().strftime("%Y%m%d-%H%M%S")
        session.mkdir(parents=True)
        backup = session / "device-backup.tar"
        self.adb.exec_out_to_file(f"run-as {PACKAGE} tar -cf - -C files/QtsVFSCache packages Watchdog", backup)
        game = session / "game" / "WXQ_Data" / "Package"
        game.mkdir(parents=True)
        with tarfile.open(backup) as tar:
            members = [m for m in tar.getmembers() if m.name.startswith("packages/") and m.isfile()]
            tar.extractall(game, members=members, filter="data")
        (game / "packages").rename(game / "builtin")
        self.prune_old_sessions(self.work, keep=session)
        self.done("pull", info.strip())
        return session

    def build_translation(self, session: Path) -> tuple[dict, Path | None]:
        self.step("translate", "1-3 minutes")
        staged = session / "staged"
        # The prime layer half the game's text lives in is inside the APK, and the append pass is what
        # carries it into a downloaded package. That needs the APK, not the package builder: the builder
        # is only for laying a package out whole, which no package asks for. A source checkout missing
        # resources/qtsvfs therefore still translates everything the catalog covers.
        builder_dir = find_builder_dir([BUNDLE / "qtsvfs"])
        summary = build_patch(session / "game", BUNDLE / "catalog", session / "build", staged,
                              apk=self.normal_apk, builder_dir=builder_dir,
                              log=lambda line: self.log("  " + str(line)))
        text, images = count_translated(summary)
        dropped_text = count_untranslated_text(summary)
        skipped = count_untranslated_graphics(summary)
        untranslated = []
        if dropped_text:
            untranslated.append(f"{dropped_text} text table{'s' if dropped_text != 1 else ''}")
        if skipped:
            untranslated.append(f"{skipped} image{'s' if skipped != 1 else ''}")
        if not summary["packages"]:
            self.log("Nothing new to translate (the game is probably already patched).")
        detail = f"{text} text tables, {images} images"
        if untranslated:
            detail += ", " + " and ".join(untranslated) + " left in Chinese"
        # "already installed" claims there is nothing to report, so a run that installs nothing and
        # still lost tables or images names them instead.
        self.done("translate", detail if (text or images or dropped_text or skipped) else "already installed")
        return summary, staged if summary["packages"] else None

    def push_translation(self, staged: Path) -> None:
        self.step("install")
        self.adb.shell(f"rm -rf {REMOTE_TMP} && mkdir -p {REMOTE_TMP}")
        for package_dir in sorted(p for p in staged.iterdir() if p.is_dir() and p.name.isdigit()):
            remote = f"{REMOTE_TMP}/{package_dir.name}"
            self.adb.shell(f"mkdir -p {remote}")
            for file in sorted(package_dir.glob("*.db")):
                self.adb.run("push", str(file), f"{remote}/{file.name}")
            self.adb.shell(f"chmod -R 755 {REMOTE_TMP}")
            self.adb.shell(f"run-as {PACKAGE} sh -c 'cp {remote}/* files/QtsVFSCache/packages/{package_dir.name}/'")
            self.log(f"  package {package_dir.name} installed")
        self.adb.shell(f"run-as {PACKAGE} sh -c 'rm -rf files/QtsVFSCache/Watchdog/*'")
        self.adb.shell(f"rm -rf {REMOTE_TMP}", check=False)
        self.done("install")

    def restore_normal_apk(self) -> None:
        self.step("restore", "check the phone for a Play Protect pop-up")
        self.log(PLAY_PROTECT_HINT)
        for attempt in range(3):
            try:
                self.adb.install(self.normal_apk)
                self.debuggable_installed = False
                self.done("restore")
                return
            except PatchError as error:
                self.log(str(error))
                if attempt < 2 and not self.ui.ask("Retry install?", "Installing the normal game APK failed. Try again?"):
                    break
        self.ui.set_step("restore", "error")
        self.current = None
        self.log(f"WARNING: the game still uses the temporary APK. Install this file manually: {self.normal_apk}")

    @staticmethod
    def prune_old_sessions(work: Path, keep: Path) -> None:
        sessions = sorted((work / "sessions").iterdir())
        for old in sessions[:-2]:
            if old != keep:
                shutil.rmtree(old, ignore_errors=True)
