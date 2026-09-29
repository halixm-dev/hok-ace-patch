from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path


PAGE = 0x1000


def align_down(value: int) -> int:
    return value & -PAGE


def align_up(value: int) -> int:
    return (value + PAGE - 1) & -PAGE


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vendor", type=Path, required=True)
    parser.add_argument("--library", type=Path, required=True)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--function", default="_ZN3oo216rrBigHash64_SIMDEPKvl")
    parser.add_argument("hashes", nargs="+")
    args = parser.parse_args()
    sys.path[:0] = [str(args.vendor.resolve()), str(args.runtime.resolve())]

    from elftools.elf.elffile import ELFFile
    from unicorn import Uc, UcError, UC_ARCH_ARM64, UC_HOOK_CODE, UC_MODE_ARM
    from unicorn.arm64_const import (
        UC_ARM64_REG_LR,
        UC_ARM64_REG_PC,
        UC_ARM64_REG_SP,
        UC_ARM64_REG_TPIDR_EL0,
        UC_ARM64_REG_X0,
        UC_ARM64_REG_X1,
        UC_ARM64_REG_X2,
    )
    from wxq_patch.qtsvfs import QtsPackage

    library_bytes = args.library.read_bytes()
    with args.library.open("rb") as stream:
        elf = ELFFile(stream)
        symbol = next(
            symbol
            for symbol in elf.get_section_by_name(".dynsym").iter_symbols()
            if symbol.name == args.function
        )
        segments = [segment for segment in elf.iter_segments() if segment["p_type"] == "PT_LOAD"]

    package = QtsPackage.from_flat_dir(args.package)
    for text_hash in args.hashes:
        file_hash = int(text_hash, 16)
        raw = package.extract(file_hash)
        emulator = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
        for segment in segments:
            start = align_down(segment["p_vaddr"])
            end = align_up(segment["p_vaddr"] + segment["p_memsz"])
            emulator.mem_map(start, end - start)
            file_start = segment["p_offset"]
            file_end = file_start + segment["p_filesz"]
            emulator.mem_write(segment["p_vaddr"], library_bytes[file_start:file_end])

        data_address = 0x10000000
        stack_address = 0x11000000
        stop_address = 0x12000000
        tls_address = 0x13000000
        memset_address = 0x14000000
        memcpy_address = 0x14001000
        emulator.mem_map(data_address, align_up(max(1, len(raw))))
        emulator.mem_write(data_address, raw)
        emulator.mem_map(stack_address, 0x100000)
        emulator.mem_map(stop_address, PAGE)
        emulator.mem_write(stop_address, struct.pack("<I", 0xD503201F))
        emulator.mem_map(tls_address, PAGE)
        emulator.mem_map(memset_address, PAGE * 2)
        emulator.mem_write(0x3F3578, struct.pack("<Q", memset_address))
        emulator.mem_write(0x3F34E8, struct.pack("<Q", memcpy_address))
        emulator.reg_write(UC_ARM64_REG_X0, data_address)
        emulator.reg_write(UC_ARM64_REG_X1, len(raw))
        emulator.reg_write(UC_ARM64_REG_SP, stack_address + 0xFF000)
        emulator.reg_write(UC_ARM64_REG_LR, stop_address)
        emulator.reg_write(UC_ARM64_REG_TPIDR_EL0, tls_address)
        trace: list[int] = []

        def on_code(uc, address, _size, _user):
            trace.append(address)
            if address == memset_address:
                destination = uc.reg_read(UC_ARM64_REG_X0)
                value = uc.reg_read(UC_ARM64_REG_X1) & 0xFF
                size = uc.reg_read(UC_ARM64_REG_X2)
                uc.mem_write(destination, bytes([value]) * size)
                uc.reg_write(UC_ARM64_REG_PC, uc.reg_read(UC_ARM64_REG_LR))
            elif address == memcpy_address:
                destination = uc.reg_read(UC_ARM64_REG_X0)
                source = uc.reg_read(UC_ARM64_REG_X1)
                size = uc.reg_read(UC_ARM64_REG_X2)
                uc.mem_write(destination, bytes(uc.mem_read(source, size)))
                uc.reg_write(UC_ARM64_REG_PC, uc.reg_read(UC_ARM64_REG_LR))

        emulator.hook_add(UC_HOOK_CODE, on_code)
        try:
            emulator.emu_start(symbol["st_value"], stop_address)
        except UcError:
            print(
                f"emulation stopped at PC={emulator.reg_read(UC_ARM64_REG_PC):X}; "
                f"trace={[f'{address:X}' for address in trace[-12:]]}"
            )
            raise
        result = emulator.reg_read(UC_ARM64_REG_X0)
        slot_hash = package.build_slot_map([file_hash])[file_hash][0].hash1

        def combine(left: int, right: int) -> int:
            emulator.reg_write(UC_ARM64_REG_X0, left)
            emulator.reg_write(UC_ARM64_REG_X1, right)
            emulator.reg_write(UC_ARM64_REG_LR, stop_address)
            emulator.emu_start(0x30BA5C, stop_address)
            return emulator.reg_read(UC_ARM64_REG_X0)

        candidates = {
            "hash,file": combine(result, file_hash),
            "file,hash": combine(file_hash, result),
            "hash,size": combine(result, len(raw)),
            "size,hash": combine(len(raw), result),
            "hash,slot": combine(result, slot_hash),
            "slot,hash": combine(slot_hash, result),
        }
        print(f"{file_hash:016X} {args.function}={result:016X}")
        for name, value in candidates.items():
            print(f"  combine({name})={value:016X}")


if __name__ == "__main__":
    main()
