"""
Developer-spec modules: hexdump, assembly viewer, shellcode runner,
hooking, binary diff, network packet crafting, stealth toggles,
process snapshot, fuzzing helper.

All modules are import-safe — they fail gracefully when optional
dependencies are missing.
"""
import ctypes
import hashlib
import json
import math
import os
import platform
import re
import struct
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional

from .logging import setup_logging

logger = setup_logging()

# ------- Hexdump -------

def hexdump(data: bytes, width: int = 16) -> str:
    """Produce a classic hex+ASCII dump."""
    lines = []
    for i in range(0, len(data), width):
        chunk = data[i:i+width]
        hex_part = ' '.join(f'{b:02x}' for b in chunk)
        ascii_part = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
        lines.append(f'{i:08x}  {hex_part:<48}  |{ascii_part}|')
    return '\n'.join(lines)

# ------- Assembly viewer -------

def disassemble_x64(code: bytes, vma: int = 0) -> str:
    """Disassemble x86-64 machine code using capstone (if installed)."""
    try:
        from capstone import Cs, CS_ARCH_X86, CS_MODE_64
        md = Cs(CS_ARCH_X86, CS_MODE_64)
        lines = [f'{insn.address:016x}  {insn.mnemonic} {insn.op_str}' for insn in md.disasm(code, vma)]
        return '\n'.join(lines)
    except ImportError:
        return "(capstone not installed — install with `pip install capstone`)"

# ------- Shellcode runner (POSIX mmap) -------

@contextmanager
def shellcode_runner(shellcode: bytes):
    """Context manager that maps shellcode into executable memory (Linux only)."""
    if platform.system() != "Linux":
        raise RuntimeError("shellcode_runner only supports Linux")
    libc = ctypes.CDLL("libc.so.6")
    PROT_READ, PROT_WRITE, PROT_EXEC = 0x01, 0x02, 0x04
    MAP_PRIVATE, MAP_ANONYMOUS = 0x02, 0x20
    addr = libc.mmap(0, len(shellcode), PROT_READ | PROT_WRITE | PROT_EXEC,
                      MAP_PRIVATE | MAP_ANONYMOUS, -1, 0)
    if addr == -1:
        raise OSError("mmap failed")
    ctypes.memmove(addr, shellcode, len(shellcode))
    try:
        func_type = ctypes.CFUNCTYPE(ctypes.c_int)
        yield func_type(addr)
    finally:
        libc.munmap(addr, len(shellcode))

# ------- Binary diff -------

def binary_diff(a: bytes, b: bytes) -> List[dict]:
    """Return list of byte-level differences."""
    return [{"offset": i, "old": hex(a[i]), "new": hex(b[i])}
            for i in range(min(len(a), len(b))) if a[i] != b[i]]

# ------- Network packet crafting -------

class NetworkPacket:
    """Craft raw IP/TCP/UDP packets (requires raw socket privileges)."""

    def __init__(self, src_ip: str, dst_ip: str, payload: bytes):
        self.src_ip = src_ip
        self.dst_ip = dst_ip
        self.payload = payload

    def _ip_header(self) -> bytes:
        version_ihl = (4 << 4) | 5
        total_length = 20 + 20 + len(self.payload)
        import socket
        header = struct.pack('!BBHHHBBH4s4s',
            version_ihl, 0, total_length, 0, 0, 64, 6, 0,
            socket.inet_aton(self.src_ip), socket.inet_aton(self.dst_ip))
        checksum = self._checksum(header)
        header = header[:10] + struct.pack('!H', checksum) + header[12:]
        return header

    @staticmethod
    def _checksum(data: bytes) -> int:
        s = 0
        for i in range(0, len(data), 2):
            w = (data[i] << 8) + (data[i+1] if i+1 < len(data) else 0)
            s += w
        s = (s >> 16) + (s & 0xffff)
        return ~s & 0xffff

    def build_tcp(self, src_port: int, dst_port: int) -> bytes:
        import socket
        seq, ack = 0, 0
        data_offset = 5
        flags = 0x02
        window = 65535
        urgent = 0
        tcp_header = struct.pack('!HHLLBBHHH', src_port, dst_port, seq, ack,
                                 (data_offset << 4), flags, window, 0, urgent)
        pseudo = struct.pack('!4s4sBBH',
            socket.inet_aton(self.src_ip), socket.inet_aton(self.dst_ip), 0, 6,
            len(tcp_header) + len(self.payload))
        tcp_checksum = self._checksum(pseudo + tcp_header + self.payload)
        tcp_header = tcp_header[:16] + struct.pack('!H', tcp_checksum) + tcp_header[18:]
        return self._ip_header() + tcp_header + self.payload

# ------- Stealth toggles -------

@contextmanager
def stealth_toggles():
    """Context manager placeholder for anti-analysis state."""
    yield

# ------- Process snapshot -------

class ProcessSnapshot:
    """Capture current process state."""

    def capture(self) -> dict:
        return {
            "pid": os.getpid(),
            "platform": platform.platform(),
            "python": sys.version,
            "modules": list(sys.modules.keys())[:20],
        }

# ------- Fuzzing helper -------

class Fuzzer:
    """Simple mutation fuzzer producing byte-level variants."""

    def __init__(self, seed: bytes):
        self.seed = seed

    def mutate(self) -> Generator[bytes, None, None]:
        import random
        for _ in range(100):
            case = bytearray(self.seed)
            pos = random.randint(0, len(case)-1)
            case[pos] = random.randint(0, 255)
            yield bytes(case)