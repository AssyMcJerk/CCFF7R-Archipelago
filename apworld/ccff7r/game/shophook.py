"""Shop purchase hook (shopsanity).

The shop widget's buy handler (exe+12B9190) reaches `movsxd rax,[rdi+0x2EC]` (exe+12B9201, 7 bytes) only on
the BUY path, right before GiveItem. rdi = shop widget:
  +0x318 -> array of 4-byte entries, u16 shop id at +0 (current shop = [+0x318][+0x2E8])
  +0x2EC  selected row in the buy list (= slot in the shop stock table, the list builder keeps every slot)
  +0x300  quantity
The cave appends (u16 shop id, u16 slot, u32 quantity) to a 256-entry ring:
  data (cave+0x108): u32 count, pad, entries[256] x 8 bytes
"""
import struct

from .cavehook import CaveHook

ORIGINAL = bytes.fromhex("486387ec020000")    # movsxd rax,dword ptr [rdi+0x2ec]
CAVE = bytes.fromhex(
    "5051524150488d0dfc0000008b0125ff000000488d54c108488b87180300004c6387e8020000420fb7048066"
    "89028b87ec020000668942028b8700030000894204ff0141585a5958486387ec020000ff25a3000000")
RING = 256


class ShopHook(CaveHook):
    ORIGINAL, CAVE = ORIGINAL, CAVE
    MAGIC = b"APSHOPH1"
    DATA_SIZE = 8 + RING * 8

    def __init__(self, pm, site):
        super().__init__(pm, site)
        self.seen = 0

    def on_adopt(self):
        self.seen = self.u32(0)

    def poll(self):
        """[(shop_id, slot, quantity)] bought since the last poll."""
        if self.state != "active":
            return []
        n = self.u32(0)
        if n == self.seen:
            return []
        first = max(self.seen, n - RING)
        ring = self.pm.read_bytes(self.data + 8, RING * 8)
        self.seen = n
        return [struct.unpack_from("<HHi", ring, (i % RING) * 8) for i in range(first, n)]
