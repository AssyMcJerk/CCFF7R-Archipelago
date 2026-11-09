"""Shop name hook: shows Archipelago info in the shop's buy list (v0.6.9).

The buy-list builder (exe+12B8EA0) fetches each stock item's display name with
    movzx ecx, word [rsi]  /  lea rdx, [rbp-19]  /  call GetItemName (exe+120E070)
GetItemName(id, FString* out) looks the item's text up and converts it with the message decoder
exe+120D900(msg, page, FString* out, float*). Only this call site is redirected, so the inventory, the sell list
and every other menu keep the real names.

The cave (unicorn-verified) reads the open shop's stock index from the widget in r13
([r13+318] + [r13+2E8]*4, low 12 bits) and searches its table for (shop, item id). On a hit it decodes our
own message into the row's FString; otherwise it tail-jumps to the original GetItemName.

Message format (decoder exe+120D900): u32 page count, then per page {u32 unit count, u32 byte offset}, then u32
units. A plain character is 0x80 | (UTF-16 code unit << 16).

Page layout (one 64 KiB RWX block within +-2 GB of the call site):
  0x0000  code
  0x00F0  u64 message decoder (exe+120D900)
  0x00F8  u64 original GetItemName (exe+120E070)
  0x0100  b"APSHOPNM"
  0x0108  u32 entry count
  0x010C  entries {u16 shop, u16 item id, u32 message offset from the page start}, up to MAX_ENTRIES
  0x0A00  messages
"""
import ctypes
import struct

from .cavehook import _k32

MAGIC = b"APSHOPNM"
SIG_PREFIX = bytes.fromhex("0fb70e488d55e7894503")   # movzx ecx,[rsi] / lea rdx,[rbp-19] / mov [rbp+3],eax
CAVE = bytes.fromhex(
    "53564883ec28498b85180300004d6385e8020000460fb704804181e0ff0f0000488d35e10000008b1e4883c60485db743f66443906"
    "753166394e02752b8b4604488d0db9ffffff4801c14989d031d24c8d4c242041c70100000000ff158f0000004883c4285e5bc34883"
    "c608ffcbebbd4883c4285e5bff257c000000")
PAGE_SIZE = 0x10000
MAX_ENTRIES = 0x100
MSG_START = 0xA00


def encode_message(text):
    units = [0x80 | (ord(c) & 0xFFFF) << 16 for c in text]
    return struct.pack("<III", 1, len(units), 12) + struct.pack(f"<{len(units)}I", *units)


class ShopNameHook:
    def __init__(self, pm, site):
        """site = address of the `call GetItemName` (E8 rel32) inside the buy-list builder."""
        self.pm, self.site = pm, site
        self.cave = None
        self.state = "off"
        self.last = None

    def _target(self, b):
        return self.site + 5 + struct.unpack_from("<i", b, 1)[0]

    def _alloc_near(self):
        h = self.pm.process_handle
        start = self.site & ~0xFFFF
        for step in range(1, 0x7000):
            for addr in (start - step * 0x10000, start + step * 0x10000):
                if addr > 0:
                    p = _k32.VirtualAllocEx(h, ctypes.c_void_p(addr), PAGE_SIZE, 0x3000, 0x40)
                    if p:
                        return p
        return None

    def _write_code(self, addr, data):
        old = ctypes.c_ulong()
        h = self.pm.process_handle
        _k32.VirtualProtectEx(h, ctypes.c_void_p(addr), len(data), 0x40, ctypes.byref(old))
        self.pm.write_bytes(addr, data, len(data))
        _k32.VirtualProtectEx(h, ctypes.c_void_p(addr), len(data), old.value, ctypes.byref(old))

    def ensure(self):
        if _k32 is None:
            self.state = "off"
            return self.state
        pre = self.pm.read_bytes(self.site - len(SIG_PREFIX), len(SIG_PREFIX))
        cur = self.pm.read_bytes(self.site, 5)
        if pre != SIG_PREFIX or cur[0] != 0xE8:
            self.state = "foreign"
            return self.state
        tgt = self._target(cur)
        try:
            if self.pm.read_bytes(tgt + 0x100, 8) == MAGIC:       # ours (this or an earlier client run)
                if self.cave != tgt:
                    self.cave, self.last = tgt, None
                self.state = "active"
                return self.state
        except Exception:
            pass
        # original call: tgt = GetItemName. Its decoder call sits at +0x3A (E8 rel32).
        gin = self.pm.read_bytes(tgt, 0x40)
        if gin[:2] != b"\x40\x53" or gin[0x3A] != 0xE8:
            self.state = "foreign"
            return self.state
        decoder = tgt + 0x3A + 5 + struct.unpack_from("<i", gin, 0x3B)[0]
        if self.cave is None:
            self.cave = self._alloc_near()
            if not self.cave:
                self.state = "off"
                return self.state
        page = bytearray(MSG_START)
        page[:len(CAVE)] = CAVE
        struct.pack_into("<QQ", page, 0xF0, decoder, tgt)
        page[0x100:0x108] = MAGIC
        self.pm.write_bytes(self.cave, bytes(page), len(page))
        rel = self.cave - (self.site + 5)
        self._write_code(self.site, b"\xE8" + struct.pack("<i", rel))
        self.last = None
        self.state = "active"
        return self.state

    def set_names(self, names):
        """names: {(shop index, item id): text}. Rewrites the table only when it changed."""
        if self.state != "active":
            return
        key = tuple(sorted(names.items()))
        if key == self.last:
            return
        entries, msgs, off = [], bytearray(), MSG_START
        for (shop, item), text in key[:MAX_ENTRIES]:
            m = encode_message(text[:60])
            entries.append(struct.pack("<HHI", shop, item, off + len(msgs)))
            msgs += m
            msgs += b"\0" * (-len(msgs) % 4)
            if MSG_START + len(msgs) > PAGE_SIZE - 0x100:
                break
        self.pm.write_bytes(self.cave + 0x108, struct.pack("<I", 0), 4)          # hide while rewriting
        if msgs:
            self.pm.write_bytes(self.cave + MSG_START, bytes(msgs), len(msgs))
        if entries:
            blob = b"".join(entries)
            self.pm.write_bytes(self.cave + 0x10C, blob, len(blob))
        self.pm.write_bytes(self.cave + 0x108, struct.pack("<I", len(entries)), 4)
        self.last = key
