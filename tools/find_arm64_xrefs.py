from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vendor", type=Path, required=True)
    parser.add_argument("library", type=Path)
    parser.add_argument("addresses", nargs="+", type=lambda value: int(value, 0))
    args = parser.parse_args()
    sys.path.insert(0, str(args.vendor.resolve()))

    from capstone import CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN, Cs
    from capstone.arm64 import ARM64_OP_IMM, ARM64_OP_REG

    data = args.library.read_bytes()
    md = Cs(CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN)
    md.detail = True
    instructions = list(md.disasm(data[0x33E20 : 0x33E20 + 0x3111D4], 0x33E20))
    wanted = set(args.addresses)
    for index, instruction in enumerate(instructions):
        if instruction.mnemonic != "adrp" or len(instruction.operands) != 2:
            continue
        destination, page = instruction.operands
        if destination.type != ARM64_OP_REG or page.type != ARM64_OP_IMM:
            continue
        for candidate in instructions[index + 1 : index + 9]:
            if candidate.address - instruction.address > 32:
                break
            if candidate.mnemonic != "add" or len(candidate.operands) < 3:
                continue
            output, source, immediate = candidate.operands[:3]
            if (
                output.type == ARM64_OP_REG
                and source.type == ARM64_OP_REG
                and immediate.type == ARM64_OP_IMM
                and source.reg == destination.reg
            ):
                address = page.imm + immediate.imm
                if address in wanted:
                    print(
                        f"target={address:#x} adrp={instruction.address:#x} "
                        f"add={candidate.address:#x} reg={md.reg_name(output.reg)}"
                    )


if __name__ == "__main__":
    main()
