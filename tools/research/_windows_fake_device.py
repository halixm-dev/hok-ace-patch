"""Private offline transport: never invokes adb, shell, installers or a real device."""
from __future__ import annotations

from collections import Counter
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import tarfile
import tempfile
from typing import Callable

from patcher_core import PatchError, Adb, PACKAGE

OPERATIONS = ("journal_write", "upload", "temp_copy", "temp_hash", "rename", "acknowledgment",
              "read_back", "install_commit", "finalization", "live_copy", "sync", "delete", "directory")
FAILPOINTS = tuple(f"{when}_{operation}" for operation in OPERATIONS for when in ("before", "after"))


class Faults:
    """One-shot named cuts; counts include the call which loses its reply.

    Future coordinators can wrap journal/finalization calls with ``operation`` without
    production importing this research module. Mutation callbacks run between the hooks.
    """
    def __init__(self, cuts: dict[str, int] | None = None):
        self.cuts = dict(cuts or {})
        if set(self.cuts) - set(FAILPOINTS):
            raise ValueError("Unknown fixture failpoint")
        self.calls: Counter[str] = Counter()
        self.events: list[str] = []
        self.bytes: Counter[str] = Counter()

    def hit(self, name: str) -> None:
        if name not in FAILPOINTS:
            raise ValueError(name)
        self.calls[name] += 1
        self.events.append(name)
        if self.cuts.get(name) == self.calls[name]:
            raise PatchError("error_adb_failed", command=name, output="injected interruption")

    def operation(self, name: str, action: Callable[[], object]) -> object:
        self.hit(f"before_{name}")
        value = action()
        self.hit(f"after_{name}")
        return value


class FakeAdb:
    """Isolated phone layer, remote upload area and destination temps.

    ``phone`` is the explicit synthetic live root; uploaded bytes never change it until
    a shell copy/rename. Unknown commands refuse rather than silently simulating success.
    ``partial_live_copy`` models legacy cp truncation; atomic temp-copy cuts leave live intact.
    """
    def __init__(self, phone: Path, fail_after: int | None = None, *, garble: str | None = None,
                 truncate: bool = False, faults: Faults | None = None,
                 partial_live_copy: int | None = None, serial: str = "fixture-phone"):
        self.phone = phone.resolve()
        self.upload = self.phone.parent / (self.phone.name + "-uploads")
        self.upload.mkdir(parents=True, exist_ok=True)
        self.fail_after, self.garble, self.truncate = fail_after, garble, truncate
        self.pushed: list[str] = []
        self.tars: list[object] = []
        self.faults, self.partial_live_copy = faults or Faults(), partial_live_copy
        self.serial, self.installed = serial, b"access-apk"
        self.android_user = 0
        self.install_attempts = 0
        self.uninstall_attempts = 0
        self.exe = str(self.phone.parent / "fixture-adb.exe")
        self.install_reply = "Success"
        self.install_override: bytes | None = None
        self.commands: list[str] = []
        self.bound_operations: list[tuple[str, str]] = []
        self.watchdog = self.phone.parent / (self.phone.name + "-watchdog")
        self.partial_temp_copy: int | None = None
        self.require_debuggable_run_as = False
        # Production Adb.run/exec_out_to_file call the coordinator's control boundary
        # before every owned command; the fake keeps that seam.
        self.boundary: Callable[[], None] | None = None

    def _boundary(self) -> None:
        if self.boundary is not None:
            self.boundary()

    def bind(self, serial: str, android_user: int | None = None) -> None:
        if serial != self.serial or android_user is not None and android_user != self.android_user:
            raise PatchError("error_run_target", detail=serial)

    def assert_target(self) -> int:
        self.bound_operations.append((self.serial, "identity"))
        return self.android_user

    def _path(self, remote: str) -> Path:
        remote = remote.strip("'\"")
        if remote.startswith("/data/local/tmp/hokace/"):
            root, name = self.upload, remote.split("/hokace/", 1)[1]
        elif remote == "/data/local/tmp/hokace":
            return self.upload
        elif remote.startswith("files/QtsVFSCache/packages/"):
            root, name = self.phone, remote.split("packages/", 1)[1]
        elif remote == "files/QtsVFSCache/Watchdog":
            return self.watchdog
        elif remote.startswith("files/QtsVFSCache/Watchdog/"):
            root, name = self.watchdog, remote.split("Watchdog/", 1)[1]
        else:
            raise AssertionError(f"Unsupported fake path: {remote}")
        path = root / name
        if ".." in Path(name).parts or not path.resolve().is_relative_to(root.resolve()):
            raise AssertionError("Fixture path escape")
        return path

    def copy(self, source: Path, target: Path, *, temporary: bool = False) -> None:
        kind = "temp_copy" if temporary else "live_copy"
        def write() -> None:
            data = source.read_bytes()
            if not temporary and self.partial_live_copy is not None:
                data = data[:self.partial_live_copy]
            if temporary and self.partial_temp_copy is not None:
                data = data[:self.partial_temp_copy]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            self.faults.bytes[kind] += len(data)
            if not temporary and self.partial_live_copy is not None:
                raise PatchError("error_adb_failed", command="cp", output="interrupted live copy")
            if temporary and self.partial_temp_copy is not None:
                raise PatchError("error_adb_failed", command="cp", output="interrupted temp copy")
        self.faults.operation(kind, write)

    def rename(self, source: Path, target: Path) -> None:
        self.faults.operation("rename", lambda: source.replace(target))
        self.faults.operation("acknowledgment", lambda: None)

    def digest(self, path: Path, *, temporary: bool = False) -> str:
        def read() -> str:
            data = path.read_bytes()
            self.faults.bytes["hashed"] += len(data)
            return hashlib.sha256(data).hexdigest()
        return self.faults.operation("temp_hash" if temporary else "read_back", read)

    def shell(self, command: str, check: bool = True) -> str:
        self._boundary()
        self.bound_operations.append((self.serial, "shell"))
        self.commands.append(command)
        if command.startswith("# hok-file-upload "):
            marker, script = command.split("\n", 1)
            request = json.loads(marker.removeprefix("# hok-file-upload "))
            if request["operation"] != "upload_prepare" or "[ ! -L /data/local/tmp/hokace" not in script:
                raise AssertionError("Unsafe upload protocol")
            target = self._path(request["upload"])
            if target.exists() or target.is_symlink():
                raise AssertionError("Upload leaf already exists")
            target.parent.mkdir(parents=True, exist_ok=True)
            return ""
        if command.startswith("[ ! -L /data/local/tmp/hokace/") and "&& chmod 644 " in command:
            target = self._path(command.rsplit(" ", 1)[1])
            if not target.is_file() or target.is_symlink():
                raise AssertionError("Unsafe upload leaf")
            return ""
        if command.startswith("# hok-file-transaction "):
            if self.require_debuggable_run_as:
                identity = self.installed_identity()
                if identity is None or not identity["debuggable"]:
                    raise PatchError("error_adb_failed", command="run-as", output="package not debuggable")
            marker, script = command.split("\n", 1)
            if not script.startswith(f"run-as {PACKAGE} sh -c ") or "/system/bin/flock -x 9" not in script:
                raise AssertionError("Transaction lacks game-private lock")
            return self._transaction(json.loads(marker.removeprefix("# hok-file-transaction ")))
        if command == "am get-current-user":
            return str(self.android_user)
        if command == f"am force-stop {PACKAGE}":
            return ""
        if command == f"pm list packages --user 0 {PACKAGE}":
            return f"package:{PACKAGE}" if self.installed is not None else ""
        if command == "sha256sum '/data/app/fixture/base.apk'":
            if self.installed is None:
                raise PatchError("error_apk_identity", detail="APK absent")
            return hashlib.sha256(self.installed).hexdigest() + "  /data/app/fixture/base.apk"
        if command.endswith("packages/1/1.info"):
            path = self.phone / "1/1.info"
            return path.read_text() if path.is_file() else ""
        if command.startswith("run-as "):
            command = shlex.split(command)[-1]
        for part in command.split(" && "):
            tokens = shlex.split(part)
            if tokens[:2] == ["mkdir", "-p"]:
                self._path(tokens[2]).mkdir(parents=True, exist_ok=True)
            elif tokens[:2] == ["rm", "-rf"]:
                if tokens[2] == "files/QtsVFSCache/Watchdog/*":
                    continue
                target = self._path(tokens[2])
                if target == self.upload:
                    shutil.rmtree(target); target.mkdir()
                elif target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink(missing_ok=True)
            elif tokens[:2] == ["rm", "-f"]:
                self._path(tokens[2]).unlink(missing_ok=True)
            elif tokens[0] == "chmod":
                self._path(tokens[-1])
            elif tokens[0] == "cp":
                source, destination = tokens[-2:]
                target = self._path(destination.rstrip("/"))
                if source.endswith("/*"):
                    for path in sorted(self._path(source[:-2]).iterdir()):
                        self.copy(path, target / path.name)
                else:
                    self.copy(self._path(source), target, temporary=target.name.endswith(".tmp"))
            elif tokens[0] == "mv":
                self.rename(self._path(tokens[-2]), self._path(tokens[-1]))
            elif tokens[0] == "sha256sum":
                path = self._path(tokens[-1])
                return f"{self.digest(path, temporary=path.name.endswith('.tmp'))}  {tokens[-1]}\n"
            elif tokens[0] == "sync":
                self.faults.operation("sync", lambda: None)
            elif tokens[:2] == ["pm", "path"]:
                if tokens != ["pm", "path", PACKAGE]:
                    raise AssertionError(tokens)
                return "package:/data/app/fixture/base.apk" if self.installed is not None else ""
            else:
                raise AssertionError(f"Unsupported fake shell: {part}")
        return ""

    def exec_out(self, command: str) -> str:
        self._boundary()
        self.bound_operations.append((self.serial, "exec-out"))
        assert "sha256sum" in command, command
        if self.garble is not None:
            return self.garble
        return "".join(f"{self.digest(path)}  ./{path.relative_to(self.phone).as_posix()}\n"
                       for path in sorted(self.phone.rglob("*")) if path.is_file())

    @contextmanager
    def exec_out_stream(self, command: str):
        with tempfile.TemporaryDirectory() as folder:
            archive = Path(folder) / "wire.tar"
            self.exec_out_to_file(command, archive)
            with archive.open("rb") as stream:
                yield stream

    def exec_out_to_file(self, command: str, target: Path) -> None:
        self._boundary()
        self.bound_operations.append((self.serial, "exec-out-file"))
        if command.endswith(" -C files/QtsVFSCache Watchdog"):
            with tarfile.open(target, "w") as archive:
                archive.add(self.watchdog, arcname="Watchdog")
            self.tars.append("watchdog")
            return
        whole = command.endswith(" packages Watchdog")
        names = ([path.relative_to(self.phone).as_posix() for path in self.phone.rglob("*") if path.is_file()]
                 if whole else command.split(" -C files/QtsVFSCache/packages ", 1)[1].split())
        self.tars.append("whole" if whole else names)
        with tarfile.open(target, "w") as tar:
            for name in names:
                tar.add(self.phone / name, arcname=f"packages/{name}" if whole else name)
        if self.truncate and not whole:
            target.write_bytes(target.read_bytes()[:512])

    def run(self, *args: str, check: bool = True) -> str:
        self._boundary()
        self.bound_operations.append((self.serial, args[0]))
        if args[0] == "push":
            if self.fail_after is not None and len(self.pushed) >= self.fail_after:
                raise PatchError("error_adb_failed", command="push", output="cable pulled")
            def upload() -> None:
                target = self._path(args[2]); target.parent.mkdir(parents=True, exist_ok=True)
                data = Path(args[1]).read_bytes(); target.write_bytes(data)
                self.pushed.append(args[2].split("/hokace/", 1)[1]); self.faults.bytes["upload"] += len(data)
            self.faults.operation("upload", upload)
        elif args[0] == "uninstall":
            assert args == ("uninstall", PACKAGE), args
            self.uninstall_attempts += 1
            self.installed = None
        elif args[0] == "pull":
            assert len(args) == 3 and args[1] == "/data/app/fixture/base.apk", args
            if self.installed is None:
                raise PatchError("error_apk_identity", detail="APK absent")
            Path(args[2]).write_bytes(self.installed)
        elif args[0] == "install":
            assert len(args) == 3 and args[1] == "-r", args
            self.install(Path(args[2]))
            return self.install_reply
        elif args[0] == "devices":
            return f"List of devices attached\n{self.serial}\tdevice\n"
        elif args[0] != "start-server":
            raise AssertionError(f"Unsupported fake adb: {args}")
        return ""

    def install(self, apk: Path) -> None:
        self.install_attempts += 1
        def commit() -> None:
            self.installed = self.install_override if self.install_override is not None else apk.read_bytes()
            self.faults.bytes["install"] += len(self.installed)
        self.faults.operation("install_commit", commit)

    def installed_identity(self) -> dict | None:
        return Adb.installed_identity(self)

    def _transaction(self, request: dict) -> str:
        """Interpret the fixed transaction protocol; unknown operations refuse.

        This fake never executes the shell. Upload, temporary, live and Watchdog
        bytes remain separate physical paths. Every transport cut uses Faults.
        """
        from device_transaction import ShellTransport, _path
        from run_artifacts import file_identity
        operation, session = request["operation"], request["session"]
        if operation == "inventory":
            result = []
            for root, prefix in ((self.phone, "packages"), (self.watchdog, "Watchdog")):
                if not root.exists():
                    continue
                result.append("D " + prefix)
                for path in sorted(root.rglob("*")):
                    if path.is_symlink():
                        raise PatchError("error_run_state", detail="Fixture link")
                    name = prefix + "/" + path.relative_to(root).as_posix()
                    if path.is_dir():
                        result.append("D " + name)
                    else:
                        if path.name.startswith(f".hok-{session}-") and path.name.endswith(".tmp"):
                            continue
                        result.append(f"F {self.digest(path)} {path.stat().st_size} {name}")
            return "\n".join(result)
        name = request["name"]
        if operation == "directory":
            if name not in {"packages", "Watchdog"}:
                _path(name + "/placeholder")
            target = self.phone if name == "packages" else self._path("files/QtsVFSCache/" + name)
            self.faults.operation("directory", lambda: target.mkdir(parents=True, exist_ok=True))
            return ""
        _path(name)
        target = self._path("files/QtsVFSCache/" + name)
        temporary = self._path(ShellTransport._temp(session, name))
        if operation == "clear_temp":
            temporary.unlink(missing_ok=True)
            return ""
        if operation not in {"write", "remove"}:
            raise AssertionError(operation)
        actual = file_identity(target) if target.exists() else None
        if actual != request["before"]:
            raise PatchError("error_files_changed", detail=name)
        if operation == "remove":
            self.faults.operation("delete", lambda: target.unlink())
            self.faults.operation("sync", lambda: None)
            return ""
        self.copy(self._path(request["upload"]), temporary, temporary=True)
        if {"sha256": self.digest(temporary, temporary=True), "size": temporary.stat().st_size} != request["after"]:
            raise PatchError("error_files_changed", detail="temporary bytes differ")
        self.faults.operation("sync", lambda: None)
        self.rename(temporary, target)
        self.faults.operation("sync", lambda: None)
        if {"sha256": self.digest(target), "size": target.stat().st_size} != request["after"]:
            raise PatchError("error_files_changed", detail="live bytes differ")
        return ""
