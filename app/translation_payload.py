"""The Windows patcher's translation payload: build it, publish it as a checkpoint, apply it to the phone.

`TranslationPayload` is mixed into `patcher_core.Patcher`, its methods moved there verbatim. They use the
patcher's `run_owner`, `language`, `normal_apk`, `remove`, `keep`, `work` and `_active_build`, and its
`log`, `step`, `done`, `event`, `control_boundary`, `_transaction`, `_read_delta` and `_delta_info`.
`patcher_core` re-exports `build_patch`.
"""
from __future__ import annotations

import os
from pathlib import Path

import languages
import pristine_delta
from device_transaction import _publish, _durable_copy
from patch_summary import count_translated, count_untranslated_graphics, count_untranslated_text
from pristine_layer import LAYER, PENDING_DELTA
from qts_builder import find_builder_dir
from run_artifacts import file_identity, read_record, tree_manifest
from ui_strings import BUNDLE, PatchError
from windows_checkpoints import Checkpoints, owned_attempt

def build_patch(*args: object, **kwargs: object) -> dict:
    """Load the translation engine only for a fresh staging operation."""
    from build_device_patch import build_patch as build
    return build(*args, **kwargs)


class TranslationPayload:
    def build_translation(self, session: Path) -> tuple[dict, Path | None]:
        self.step("translate", "1-3 minutes")
        self._active_build = owned_attempt(self.run_owner, session, "build")
        staged = self._active_build / "payload"
        # The prime layer half the game's text lives in is inside the APK, and the append pass is what
        # carries it into a downloaded package. That needs the APK, not the package builder: the builder
        # is only for laying a package out whole, which no package asks for. Only a source run finds
        # resources/qtsvfs; the exe does not bundle it, and still translates everything the catalog covers.
        builder_dir = find_builder_dir([BUNDLE / "qtsvfs"])
        catalog = languages.catalog_dir(BUNDLE, self.language.code)
        summary = build_patch(session / "game", catalog, self._active_build / "scratch", staged,
                              apk=self.normal_apk, builder_dir=builder_dir,
                              log=self._build_progress)
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

    def _build_progress(self, line: object) -> None:
        self.control_boundary()
        self.log("  " + str(line))
        self.event("working", "build_translation", detail=str(line))

    def _publish_payload(self, session: Path, summary: dict, staged: Path | None,
                         restored: list[str], identity: dict | None) -> Path:
        """Finish restored outputs/delta before publishing a separate build receipt."""
        attempt = self._active_build
        root = attempt / "committed"
        root.mkdir()
        outputs = root / "payload"
        outputs.mkdir()
        names = pristine_delta.package_files(staged) if staged else []
        # Move only finished payload files inside this owned attempt. Scratch is
        # deliberately outside the immutable receipt's exact artifact set.
        for name in names:
            target = outputs / name
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staged / name, target)
        delta = (pristine_delta.make(session / LAYER, outputs, info=self._delta_info(), fingerprint=True)
                 if names else pristine_delta.Delta((), self._delta_info()))
        if not self.remove:
            pristine_delta.write(delta, root / PENDING_DELTA)
        deletions = []
        for name in restored:
            if name in names:
                continue
            source = session / LAYER / name
            if source.exists():
                _durable_copy(source, outputs / name)
            else:
                original = file_identity(session / "recovery" / "packages" / name)
                candidates = [self._read_delta(pristine_delta.DELTA_NAME), self._read_delta(PENDING_DELTA)]
                if not any((entry := saved.entry(name)) is not None and entry.created
                           and original == {"size": entry.staged_size, "sha256": entry.staged_sha256}
                           for saved in candidates if saved is not None):
                    self.log(f"  {name}: removing it is not proven by a saved delta")
                    raise PatchError("error_files_changed")
                deletions.append(name)
        original = Checkpoints(self.run_owner, session).snapshot()["files"]
        expected = dict(original)
        payload = tree_manifest(outputs)
        for name, item in payload.items():
            expected["packages/" + name] = item
        for name in deletions:
            expected.pop("packages/" + name)
        if expected != original:
            expected = {name: item for name, item in expected.items() if not name.startswith("Watchdog/")}
        _publish(root / "deletions.json", {"schema": 1, "paths": sorted(deletions)})
        _publish(root / "expected-layer.json", {"schema": 1, "files": expected})
        _publish(root / "device_patch_summary.json", summary)
        if identity is not None and (self.remove or bool(delta.files)):
            Checkpoints(self.run_owner, session).publish_build(root, identity, remove=self.remove)
        else:
            # No complete producer or no translated entries: verified fresh apply
            # remains available, but this is explicitly not a reusable STAGED receipt.
            _publish(root / "fresh-only.json", {"schema": 1, "reusable": False})
        return root

    def _apply_checkpoint(self, session: Path, root: Path) -> None:
        """Consumer-boundary validation also covers fresh-only ordinary processing."""
        payload = root / "payload"
        files = {name: payload / name for name in tree_manifest(payload)}
        deletions = read_record(root / "deletions.json")
        if (set(deletions) != {"schema", "paths"} or deletions["schema"] != 1
                or not isinstance(deletions["paths"], list)
                or len(set(deletions["paths"])) != len(deletions["paths"])):
            raise PatchError("error_run_state", detail="Malformed deletion plan")
        from run_artifacts import relative_path
        for name in deletions["paths"]:
            relative_path(name)
            if name in files:
                raise PatchError("error_run_state", detail="Contradictory output plan")
            files[name] = None
        material = session / "delta-material"
        material.mkdir(exist_ok=True)
        if self.remove:
            pending = material / PENDING_DELTA
            pristine_delta.write(pristine_delta.Delta((), self._delta_info()), pending)
        else:
            pending = root / PENDING_DELTA
        delta = pristine_delta.read(pending)
        record = material / pristine_delta.STAGED_HASHES_NAME
        old_record = self.keep / pristine_delta.STAGED_HASHES_NAME
        if old_record.exists():
            _durable_copy(old_record, record)
        pristine_delta.record_staged_hashes(record, delta.staged_hashes)
        result_binding = material / "result-binding.json"
        _publish(result_binding, {"schema": 1, "summary": file_identity(root / "device_patch_summary.json"),
                 "receipt": file_identity(root / "build-receipt.json") if (root / "build-receipt.json").exists() else None,
                 "root": root.relative_to(session).as_posix()})
        metadata = {"pending-delta.bin": pending, "new-hashes.json": record, "result-binding.json": result_binding}
        for name, role in ((pristine_delta.DELTA_NAME, "old-delta.bin"), (PENDING_DELTA, "old-pending.bin"),
                           (pristine_delta.STAGED_HASHES_NAME, "old-hashes.json")):
            if (self.keep / name).exists():
                metadata[role] = self.keep / name
        tx = self._transaction()
        previous_cycles = []
        for key, child in self.run_owner.record["children"].items():
            if not key.startswith("retired_"):
                continue
            old = self.work / "sessions" / child / "file-transaction.json"
            if old.exists():
                saved = read_record(old)
                if saved.get("run_id") != self.run_owner.run_id or saved.get("phase") != "rolled_back":
                    raise PatchError("error_run_state", detail="Retired file action is unresolved")
                previous_cycles.append(saved["cycle"])
        tx.prepare(files, metadata, remove_delta=not bool(delta.files),
                   initial_cycle=max(previous_cycles) + 1 if previous_cycles else 0)
        self.file_transaction = tx
        expected = read_record(root / "expected-layer.json")
        if expected != {"schema": 1, "files": tx.record["expected"]}:
            raise PatchError("error_run_state", detail="Complete output manifest differs")
        tx.apply()
        self.done("install")
