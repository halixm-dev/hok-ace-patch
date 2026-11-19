"""The Windows patcher's pristine layer: read the kept delta, rebuild or refuse, bootstrap a first one, Remove.

`PristineLayer` is mixed into `patcher_core.Patcher`, its methods moved there verbatim. They use the
patcher's `keep`, `work`, `language`, `data_version` and `replaced`, and its `log`, `skip`,
`preserve_recovery_snapshot` and `push_translation`. `patcher_core` re-exports `LAYER` and `PENDING_DELTA`.
"""
from __future__ import annotations

import json
import shutil
import tarfile
from datetime import datetime
from pathlib import Path

import pristine_delta
from ui_strings import PatchError


# The session's copy of the override layer, where build_patch reads it.
LAYER = Path("game") / "WXQ_Data" / "Package" / "builtin"
# The delta of an install being written; it becomes the delta once the last write succeeds.
PENDING_DELTA = "delta.pending.bin"


class PristineLayer:
    def _read_delta(self, name: str) -> pristine_delta.Delta | None:
        path = self.keep / name
        if not path.is_file():
            return None
        try:
            return pristine_delta.read(path)
        except pristine_delta.DeltaError as error:
            raise PatchError("error_delta_damaged", "clear_game_data", error=error) from error

    def restore_pristine(self, session: Path) -> list[str] | None:
        """Rebuild the pristine layer in the session's copy, before anything is built or written.

        Returns the files rebuilt from the pristine delta, or None when this patcher holds no delta for
        the phone and the layer may be the pristine one (`check_first_delta` decides after the build).
        Raises PatchError, with nothing written to the game data, when the layer can be neither.
        """
        self.preserve_recovery_snapshot(session)
        layer = session / LAYER
        delta = self._read_delta(pristine_delta.DELTA_NAME)
        pending = self._read_delta(PENDING_DELTA)
        if delta is None and pending is None:
            delta = self.bootstrap_delta(session)
        known = pristine_delta.load_staged_hashes(self.keep / pristine_delta.STAGED_HASHES_NAME)
        translated = pristine_delta.files_at(layer, known)  # read before the rebuild changes them
        Layer = pristine_delta.Layer
        if delta is None and pending is None:
            if pristine_delta.layer_verdict(translated, None).kind is Layer.NO_RECORD:
                self.log("  this phone holds files this patcher wrote, but no record of their original bytes")
                raise PatchError("error_cannot_rebuild", "clear_game_data")
            self.log("  no pristine delta for this phone: building from the files as pulled")
            return None
        report = pristine_delta.rebuild(layer, delta or pending, layer, fallback=pending if delta else None)
        verdict = pristine_delta.layer_verdict(translated, report)
        if verdict.kind is Layer.STALE:
            # Nothing this patcher wrote is left, as after clearing the game's data and downloading a
            # newer version: the delta describes a layer that is gone. The text signal decides instead.
            self.log(f"  the pristine delta no longer matches ({len(report.unmatched)} file(s) differ) and no "
                     f"file holds this patcher's translation: building from the files as pulled")
            return None
        if verdict.kind is Layer.MIXED:
            for name, state in sorted(report.unmatched.items()):
                self.log(f"  {name}: {state} since the last install")
            accepted, restorable, refused = pristine_delta.accept_replaced(layer, delta or pending, report,
                                                                           fallback=pending if delta else None)
            # Asset restore (ADR 0008) is the Android patcher's alone for now: here a restorable package
            # is refused like any other.
            refused = {**restorable, **refused}
            for package, reason in refused.items():
                self.log(f"  package {package} cannot be read as untranslated: {reason}")
            verdict = pristine_delta.layer_verdict(translated, report, refused)
            if verdict.kind is Layer.CHANGED:
                self.log(f"  cannot rebuild from the pristine delta: {len(report.unmatched)} file(s) changed")
                raise PatchError("error_files_changed", "clear_game_data")
            # The update's bytes stand as the new pristine; the text pass must still read them as such.
            self.replaced = accepted
            self.log(f"  {len(accepted)} file(s) the game update replaced hold none of this patcher's "
                     "translation: building from them as the update left them")
        if verdict.kind is Layer.UNCOVERED:
            self.log(f"  still translated after the rebuild: {', '.join(verdict.names)}")
            raise PatchError("error_uncovered_files", "clear_game_data")
        self.log(f"  rebuilt {len(report.rebuilt)} files from the pristine delta"
                 + (f" ({len(report.pristine)} already untranslated)" if report.pristine else ""))
        return report.rebuilt

    def check_first_delta(self, summary: dict) -> None:
        """Refuse a first install, or a build over files an update replaced, the text pass did not read as pristine."""
        reason = pristine_delta.text_not_pristine(summary)
        if reason:
            self.log(f"  not the pristine layer: {reason}")
            if self.replaced:
                raise PatchError("error_update_kept_translation", "clear_game_data")
            raise PatchError("error_translated_elsewhere", "clear_game_data", "use_other_patcher")

    def bootstrap_delta(self, session: Path) -> pristine_delta.Delta | None:
        """Make a first delta from a kept session, so a phone patched before deltas existed needs no clear.

        A kept session qualifies when the phone's files equal its staged output and its backup reads as
        pristine: no file at a staged hash this patcher recorded, and a text pass that read the pristine
        text. Tried once per run, newest session first.
        """
        layer = session / LAYER
        known = pristine_delta.load_staged_hashes(self.keep / pristine_delta.STAGED_HASHES_NAME)
        for old in sorted((self.work / "sessions").iterdir(), reverse=True):
            staged, backup = old / "staged", old / "device-backup.tar"
            if old == session or not (staged / "device_patch_summary.json").is_file() or not backup.is_file():
                continue
            names = pristine_delta.package_files(staged)
            if not names or not all((layer / name).is_file() and pristine_delta.sha256_file(layer / name)
                                    == pristine_delta.sha256_file(staged / name) for name in names):
                continue
            try:
                summary = json.loads((staged / "device_patch_summary.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if pristine_delta.text_not_pristine(summary):
                continue
            original = session / "bootstrap"
            shutil.rmtree(original, ignore_errors=True)
            wanted = {f"packages/{name}" for name in names}
            try:
                with tarfile.open(backup) as tar:
                    members = [m for m in tar.getmembers() if m.name in wanted and m.isfile()]
                    tar.extractall(original, members=members, filter="data")
                source = original / "packages"
                if len(members) != len(names) or pristine_delta.files_at(source, known):
                    continue
                delta = pristine_delta.make(source, staged, info={**self._delta_info(),
                                                                  "bootstrapped_from": old.name})
            except (OSError, tarfile.TarError):
                continue
            finally:
                shutil.rmtree(original, ignore_errors=True)
            pristine_delta.write(delta, self.keep / pristine_delta.DELTA_NAME)
            pristine_delta.record_staged_hashes(self.keep / pristine_delta.STAGED_HASHES_NAME,
                                                delta.staged_hashes)
            self.log(f"  made a pristine delta from the kept session {old.name}")
            return delta
        return None

    def write_back_pristine(self, session: Path, restored: list[str] | None) -> dict:
        """Remove translation: write every rebuilt pristine file back, with no new patch.

        Goes through the same push as an install, which then deletes the delta: the phone's files are
        pristine, and the next patch run is a first install that makes a fresh one. Refuses, before
        anything is written, when the layer cannot be rebuilt or this patcher has no record of a
        translation on it.
        """
        if restored is None:
            raise PatchError("error_no_record_to_remove", "use_other_patcher")
        self.skip("translate", "removing the translation")
        self.push_translation(session, None, restored)
        return {"packages": [], "removed": restored}

    def _delta_info(self) -> dict:
        return {"patcher": "windows", "language": self.language.code, "data_version": self.data_version,
                "made": datetime.now().isoformat(timespec="seconds")}
