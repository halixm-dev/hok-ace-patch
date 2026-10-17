"""Read Windows CPU-set topology for a local performance investigation."""
from __future__ import annotations

import argparse
import ctypes
import json
import struct
import winreg
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    query = kernel.GetSystemCpuSetInformation
    query.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(ctypes.c_ulong),
                      ctypes.c_void_p, ctypes.c_ulong]
    needed = ctypes.c_ulong()
    query(None, 0, ctypes.byref(needed), None, 0)
    if not needed.value:
        raise ctypes.WinError(ctypes.get_last_error())
    buffer = ctypes.create_string_buffer(needed.value)
    if not query(buffer, needed.value, ctypes.byref(needed), None, 0):
        raise ctypes.WinError(ctypes.get_last_error())
    raw, offset, rows = buffer.raw[:needed.value], 0, []
    while offset < len(raw):
        size, kind = struct.unpack_from("<II", raw, offset)
        assert size >= 8 and offset + size <= len(raw), "Invalid Windows CPU-set record"
        if kind == 0:
            assert size >= 32
            identifier, group, logical, core, cache, numa, efficiency, flags = struct.unpack_from(
                "<IH6B", raw, offset + 8)
            rows.append({"id": identifier, "group": group, "logical_processor": logical,
                         "core_index": core, "efficiency_class": efficiency, "flags": flags})
        offset += size
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                        r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as key:
        model = winreg.QueryValueEx(key, "ProcessorNameString")[0]
    result = {"model": model.strip(), "source": "Windows GetSystemCpuSetInformation", "cpu_sets": rows}
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
