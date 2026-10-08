"""Streaming APK rewriting and v2 signing with an optional platform RSA adapter."""
from __future__ import annotations

import copy
import hashlib
import shutil
import struct
import zipfile
from pathlib import Path
from typing import Callable

SIGNATURE_SUFFIXES = (".RSA", ".DSA", ".EC", ".SF", ".MF")
ALIGNMENT_EXTRA_ID = 0xD935
APK_SIG_BLOCK_MAGIC = b"APK Sig Block 42"
V2_BLOCK_ID = 0x7109871A
RSA_PKCS1_SHA256 = 0x0103
CHUNK = 1024 * 1024

# Game APKs are ~2 GiB; plain zip records are valid up to 4 GiB and the v2 format has no ZIP64.
zipfile.ZIP64_LIMIT = 0xFFFFFFFE


def _align(info: zipfile.ZipInfo, offset: int) -> None:
    info.extra = b""
    if info.compress_type == zipfile.ZIP_STORED:
        header = 30 + len(info.filename.encode("utf-8")) + 4
        pad = (-(offset + header)) % 4
        info.extra = struct.pack("<HH", ALIGNMENT_EXTRA_ID, pad) + b"\0" * pad


def rewrite_apk(source: Path, target: Path, replacements: dict[str, bytes], progress=None) -> None:
    """Copy an APK, replacing entries, dropping v1 signature files and 4-byte aligning stored data."""
    with zipfile.ZipFile(source) as src, zipfile.ZipFile(target, "w") as out:
        items = src.infolist()
        for index, item in enumerate(items):
            upper = item.filename.upper()
            if upper.startswith("META-INF/") and upper.endswith(SIGNATURE_SUFFIXES):
                continue
            info = copy.copy(item)
            data = replacements.get(item.filename)
            if data is not None:
                info.file_size = len(data)
            _align(info, out.fp.tell())
            with out.open(info, "w") as dst:
                if data is not None:
                    dst.write(data)
                else:
                    with src.open(item) as original:
                        shutil.copyfileobj(original, dst, CHUNK)
            if progress:
                progress(index + 1, len(items))


def _lp(data: bytes) -> bytes:
    return struct.pack("<I", len(data)) + data


def _find_eocd(f, size: int) -> int:
    tail_len = min(size, 0xFFFF + 22)
    f.seek(size - tail_len)
    tail = f.read(tail_len)
    pos = tail.rfind(b"PK\x05\x06")
    if pos < 0:
        raise ValueError("not a zip file")
    return size - tail_len + pos


def _chunk_digests(f, start: int, end: int, digests: list[bytes]) -> None:
    f.seek(start)
    remaining = end - start
    while remaining > 0:
        block = f.read(min(CHUNK, remaining))
        remaining -= len(block)
        digests.append(hashlib.sha256(b"\xa5" + struct.pack("<I", len(block)) + block).digest())


def sign_v2(source: Path, target: Path, key_der: bytes, cert_der: bytes, *,
            rsa_signer: Callable[[bytes], bytes] | None = None,
            public_key_der: bytes | None = None) -> None:
    """Write <target> = <source> plus an APK Signing Block holding a v2 RSA/SHA-256 signature."""
    if rsa_signer is None:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding

        key = serialization.load_der_private_key(key_der, password=None)
        public_key = key.public_key().public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        rsa_signer = lambda data: key.sign(data, padding.PKCS1v15(), hashes.SHA256())
    else:
        if not public_key_der:
            raise ValueError("A platform RSA adapter requires its DER public key")
        public_key = public_key_der
    size = source.stat().st_size
    with source.open("rb") as f:
        eocd_offset = _find_eocd(f, size)
        f.seek(eocd_offset)
        eocd = bytearray(f.read())
        cd_size, cd_offset = struct.unpack_from("<II", eocd, 12)
        contents_end = cd_offset
        if cd_offset >= 32:
            f.seek(cd_offset - 24)
            footer = f.read(24)
            if footer[8:] == APK_SIG_BLOCK_MAGIC:
                contents_end = cd_offset - (struct.unpack_from("<Q", footer, 0)[0] + 8)

        digests: list[bytes] = []
        _chunk_digests(f, 0, contents_end, digests)
        _chunk_digests(f, cd_offset, cd_offset + cd_size, digests)
        eocd_for_digest = bytearray(eocd)
        struct.pack_into("<I", eocd_for_digest, 16, contents_end)
        for i in range(0, len(eocd_for_digest), CHUNK):
            block = bytes(eocd_for_digest[i : i + CHUNK])
            digests.append(hashlib.sha256(b"\xa5" + struct.pack("<I", len(block)) + block).digest())
        top = hashlib.sha256(b"\x5a" + struct.pack("<I", len(digests)) + b"".join(digests)).digest()

        signed_data = (
            _lp(_lp(struct.pack("<I", RSA_PKCS1_SHA256) + _lp(top)))
            + _lp(_lp(cert_der))
            + _lp(b"")
        )
        signature = rsa_signer(signed_data)
        signer = _lp(signed_data) + _lp(_lp(struct.pack("<I", RSA_PKCS1_SHA256) + _lp(signature))) + _lp(public_key)
        value = _lp(_lp(signer))
        pairs = struct.pack("<QI", len(value) + 4, V2_BLOCK_ID) + value
        block_size = len(pairs) + 8 + len(APK_SIG_BLOCK_MAGIC)
        block = struct.pack("<Q", block_size) + pairs + struct.pack("<Q", block_size) + APK_SIG_BLOCK_MAGIC

        struct.pack_into("<I", eocd, 16, contents_end + len(block))
        with target.open("wb") as out:
            f.seek(0)
            remaining = contents_end
            while remaining > 0:
                data = f.read(min(CHUNK, remaining))
                out.write(data)
                remaining -= len(data)
            out.write(block)
            f.seek(cd_offset)
            out.write(f.read(cd_size))
            out.write(eocd)


def signed_with(apk: Path, cert_der: bytes) -> bool:
    """True when the APK's v1 signature file embeds <cert_der> (our re-signed builds carry v1 too)."""
    with zipfile.ZipFile(apk) as z:
        for name in z.namelist():
            upper = name.upper()
            if upper.startswith("META-INF/") and upper.endswith((".RSA", ".DSA", ".EC")):
                if cert_der in z.read(name):
                    return True
    # Builds signed by this tool have no v1 files; look for the certificate in the v2 block.
    with apk.open("rb") as f:
        size = apk.stat().st_size
        eocd_offset = _find_eocd(f, size)
        f.seek(eocd_offset + 16)
        cd_offset = struct.unpack("<I", f.read(4))[0]
        f.seek(max(0, cd_offset - 64 * 1024))
        return cert_der in f.read(min(cd_offset, 64 * 1024))
