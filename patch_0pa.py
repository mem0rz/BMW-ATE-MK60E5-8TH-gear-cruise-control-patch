#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from dataclasses import dataclass

@dataclass
class Patch:
    addr: int
    old: bytes
    new: bytes
    name: str

PATCHES = [
    Patch(0x0C5EF2, bytes.fromhex("A9 0B"), bytes.fromhex("A9 0C"), "DTC202A gate A90B->A90C"),
    Patch(0x0C5EFE, bytes.fromhex("B9 0B"), bytes.fromhex("B9 0C"), "DTC202A gate B90B->B90C"),
    Patch(0x0DA856, bytes.fromhex("B7 0C"), bytes.fromhex("B7 0B"), "Cruise swap B70C->B70B"),
    Patch(0x0DA874, bytes.fromhex("B7 0B"), bytes.fromhex("B7 0C"), "Cruise swap B70B->B70C"),
]

def parse_hex_record(line: str):
    # returns (ll, addr16, rectype, data_bytes, checksum_byte)
    line = line.strip()
    if not line.startswith(":"):
        return None
    raw = bytes.fromhex(line[1:])
    if len(raw) < 5:
        raise ValueError("short record")
    ll = raw[0]
    addr16 = (raw[1] << 8) | raw[2]
    rectype = raw[3]
    data = raw[4:4+ll]
    cks = raw[4+ll]
    # verify checksum
    s = sum(raw[:-1]) & 0xFF
    calc = ((-s) & 0xFF)
    if calc != cks:
        raise ValueError(f"bad checksum: got {cks:02X} expect {calc:02X}")
    return ll, addr16, rectype, bytearray(data), cks

def build_hex_record(ll, addr16, rectype, data: bytes):
    raw = bytearray()
    raw.append(ll & 0xFF)
    raw.append((addr16 >> 8) & 0xFF)
    raw.append(addr16 & 0xFF)
    raw.append(rectype & 0xFF)
    raw.extend(data)
    cks = ((-sum(raw)) & 0xFF)
    raw.append(cks)
    return ":" + raw.hex().upper()

def main(inp, outp):
    patches = {p.addr: p for p in PATCHES}
    applied = {p.addr: False for p in PATCHES}

    base = 0  # absolute base from type 02/04
    out_lines = []

    with open(inp, "r", encoding="ascii", errors="ignore") as f:
        for line in f:
            if not line.startswith(":"):
                out_lines.append(line.rstrip("\n"))
                continue

            rec = parse_hex_record(line)
            if rec is None:
                out_lines.append(line.rstrip("\n"))
                continue

            ll, addr16, rectype, data, _cks = rec

            if rectype == 0x00:
                abs_addr = base + addr16
                # apply patches that fall into this record
                for p in PATCHES:
                    a = p.addr
                    if abs_addr <= a < abs_addr + ll:
                        off = a - abs_addr
                        old = bytes(data[off:off+len(p.old)])
                        if old != p.old:
                            raise RuntimeError(
                                f"[{p.name}] addr=0x{a:X} expected {p.old.hex()} got {old.hex()} "
                                f"(record @0x{abs_addr:X})"
                            )
                        data[off:off+len(p.new)] = p.new
                        applied[a] = True

                newline = build_hex_record(ll, addr16, rectype, bytes(data))
                out_lines.append(newline)

            elif rectype == 0x04:
                # extended linear address: base = (data<<16)
                if ll != 2:
                    raise ValueError("bad type04 len")
                base = ((data[0] << 8) | data[1]) << 16
                out_lines.append(line.strip())

            elif rectype == 0x02:
                # extended segment address: base = (data<<4)
                if ll != 2:
                    raise ValueError("bad type02 len")
                base = ((data[0] << 8) | data[1]) << 4
                out_lines.append(line.strip())

            else:
                # keep as-is
                out_lines.append(line.strip())

    # verify all patches applied
    missing = [p for p in PATCHES if not applied[p.addr]]
    if missing:
        for p in missing:
            print("NOT APPLIED:", p.name, f"addr=0x{p.addr:X}", file=sys.stderr)
        raise RuntimeError("some patches were not applied (address not present in 0pa?)")

    with open(outp, "w", encoding="ascii") as f:
        for l in out_lines:
            f.write(l + "\n")

    print("OK. Patched and rewrote Intel HEX checksums.")
    for p in PATCHES:
        print(f"  {p.name}: addr=0x{p.addr:X} {p.old.hex()} -> {p.new.hex()}")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: patch_0pa.py in.0pa out.0pa")
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])