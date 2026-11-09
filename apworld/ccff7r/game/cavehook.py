"""Tiny code-cave hooks installed from the client with pymem (no DLL, no debugger).

A hook replaces 7 bytes at `site` with `jmp cave` + 2 nops. The cave lives in one RWX page allocated
within +-2 GB of the site:
  0x000  code
  0x0F0  u64 slot for the subclass (e.g. an absolute pointer the relocated instruction needs)
  0x0F8  u64 return address (site + 7), used by the code's final `jmp [rip+..]`
  0x100  8-byte magic, then the subclass's data block
The magic lets a restarted client re-adopt its own hook instead of stacking a second one. If the site
holds anything else (e.g. a Cheat Engine script on the same spot), the hook reports "foreign" and waits.
"""
import ctypes
import struct

_k32 = ctypes.WinDLL("kernel32", use_last_error=True) if hasattr(ctypes, "WinDLL") else None
if _k32:
    _k32.VirtualAllocEx.restype = ctypes.c_void_p
    _k32.VirtualAllocEx.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_ulong, ctypes.c_ulong]
    _k32.VirtualProtectEx.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t, ctypes.c_ulong,
                                      ctypes.POINTER(ctypes.c_ulong)]


class CaveHook:
    ORIGINAL = b""          # the 7 original bytes at the site
    CAVE = b""              # cave code
    MAGIC = b""             # 8 bytes at cave+0x100
    OLD_MAGICS = ()         # magics of older versions of this hook: their jmp is removed and the new cave installed
    DATA_SIZE = 0x100       # bytes after the magic

    def __init__(self, pm, site):
        self.pm, self.site = pm, site
        self.cave = None
        self.state = "off"          # off / active / foreign

    @property
    def data(self):
        return self.cave + 0x108

    def slot_f0(self):
        """Value for the u64 at cave+0xF0 (override if the code needs it)."""
        return 0

    def on_adopt(self):
        """Called when the hook (new or re-adopted) becomes active."""

    # ---- helpers
    def _alloc_near(self):
        h = self.pm.process_handle
        start = self.site & ~0xFFFF
        for step in range(1, 0x7000):
            for addr in (start - step * 0x10000, start + step * 0x10000):
                if addr <= 0:
                    continue
                p = _k32.VirtualAllocEx(h, ctypes.c_void_p(addr), 0x1000, 0x3000, 0x40)
                if p:
                    return p
        return None

    def _write_code(self, addr, data):
        old = ctypes.c_ulong()
        h = self.pm.process_handle
        _k32.VirtualProtectEx(h, ctypes.c_void_p(addr), len(data), 0x40, ctypes.byref(old))
        self.pm.write_bytes(addr, data, len(data))
        _k32.VirtualProtectEx(h, ctypes.c_void_p(addr), len(data), old.value, ctypes.byref(old))

    def _our_cave_at_site(self, cur):
        if cur[0] != 0xE9:
            return None
        tgt = self.site + 5 + struct.unpack_from("<i", cur, 1)[0]
        try:
            if self.pm.read_bytes(tgt + 0x100, 8) == self.MAGIC:
                return tgt
        except Exception:
            pass
        return None

    def ensure(self):
        """Install (or re-adopt) the hook. Returns the state string."""
        if _k32 is None:
            self.state = "off"
            return self.state
        cur = self.pm.read_bytes(self.site, 7)
        mine = self._our_cave_at_site(cur)
        if mine:
            if self.cave != mine:
                self.cave = mine
                self.on_adopt()
            self.state = "active"
            return self.state
        if cur[0] == 0xE9 and self.OLD_MAGICS:          # an older client's cave: put the original bytes back first
            tgt = self.site + 5 + struct.unpack_from("<i", cur, 1)[0]
            try:
                old = self.pm.read_bytes(tgt + 0x100, 8)
            except Exception:
                old = b""
            if old in self.OLD_MAGICS:
                self._write_code(self.site, self.ORIGINAL)
                cur = self.ORIGINAL
        if cur != self.ORIGINAL:
            self.state = "foreign"
            return self.state
        if self.cave is None:
            self.cave = self._alloc_near()
            if not self.cave:
                self.state = "off"
                return self.state
            page = bytearray(0x108 + self.DATA_SIZE)
            page[:len(self.CAVE)] = self.CAVE
            struct.pack_into("<QQ", page, 0xF0, self.slot_f0(), self.site + 7)
            page[0x100:0x108] = self.MAGIC
            self.pm.write_bytes(self.cave, bytes(page), len(page))
        self.on_adopt()
        rel = self.cave - (self.site + 5)
        self._write_code(self.site, b"\xE9" + struct.pack("<i", rel) + b"\x90\x90")
        self.state = "active"
        return self.state

    def u32(self, off):
        return self.pm.read_uint(self.data + off)

    def set_u32(self, off, v):
        self.pm.write_uint(self.data + off, v & 0xFFFFFFFF)
