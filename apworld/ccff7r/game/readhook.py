"""Script-native hook: minigame prize reads (TreasureGetId), NPC mission handouts (MissionSet) and a few
diagnostic natives (v0.6.18).

Minigame prize popups (Banora treasures, sniper, waterfall, ...) read their reward records with the
script native TreasureGetId(254), give the item with AddItem, and never call TreasureEnable, so the
opened bit stays 0. We hook the event VM's call-native site (the same site native_trace.cea uses) and
log selected native calls with their top 3 stack arguments into a ring buffer that the client polls.

Site (VM_CallNativeSite): 48 63 C2 / 49 8B 04 C0   movsxd rax,edx / mov rax,[r8+rax*8]   (7 bytes)
At the site edx = native index, rbx = VM context, [rbx+18] = VM stack base, [rbx+24] = stack depth.

Allocation layout (one RWX page within +-2 GB of the site):
  0x000  code (see CAVE below)
  0x0F0  u64 return address (site + 7) used by the code's `jmp [rip+..]`
  0x100  b"APTRHK06" magic (APTRHK05 v0.6.31-37, APTRHK04 v0.6.21-30, APTRHK03 v0.6.18-20, APTRHK02 v0.6.4-v0.6.17: u16 ring of 254/256 only; APTRHOOK before)
  0x108  u32 write count
  0x110  ring[256] of {u16 native, u16 arg0 (stack top), u16 arg1, u16 arg2}
"""
import struct

from .cavehook import CaveHook

ORIGINAL = bytes.fromhex("4863c2498b04c0")
MAGIC = b"APTRHK06"
OLD_MAGICS = (b"APTRHOOK", b"APTRHK02", b"APTRHK03", b"APTRHK04", b"APTRHK05")   # older caves: replaced on attach
RING = 256

# v0.6.31 cave (APTRHK05): the logged natives are a u16 table at cave+0xC0 (0-terminated, scanned per call) instead of
# a cmp chain, which no longer fit. Source: scripts/caves/readhook_cave.py. Logged natives:
#   254 TreasureGetId, 256 MissionSet, 24A AddItem, 24C AddGil, 24E AddSP, 169 SpAdd, 17C AddStat, 29A Choice,
#   25B DmwEnableSlot, 156 CallBattle, 154 LoadBattleData (v0.6.38), 251 TreasureEnable, 33A FairSetMiniGameMode,
#   3E3 FairShowMinigameFinish, 3E4 FairShowMinigameTimeup, 3F8 FairBanoraTreasure, 403 FairDestroyAllMissile
# Verified in unicorn (17 natives incl. 25B, 156, 154): logged natives store {native, top 3 args} (missing args = 0), other
# natives untouched,
# rcx/r9/r10/r11/rsp preserved (rax is overwritten by the relocated original instructions anyway).
CAVE = bytes.fromhex("51488d0db8000000668b016685c0740b6639d074094883c102ebed59eb6f595141515041524153488d0dd20000008b410825ff0000004c8d54c1106641891241c74202000000006641c7420600004c8b4b184863432485c07e284d8b5cc1f86645895a0283f8017e194d8b5cc1f06645895a0483f8027e0a4d8b5cc1e86645895a06ff4108415b415a584159594863c2498b04c0ff25560000000000000000000000000000000000000000000000000000000000000000000000000000000000540256024a024c024e0269017c0151029a023a03e303e403f80303045b02560154010000000000000000000000000000")
NATIVE_NAMES = {0x254: "TreasureGetId", 0x256: "MissionSet", 0x24A: "AddItem", 0x24C: "AddGil",
                0x251: "TreasureEnable", 0x24E: "AddSP", 0x169: "SpAdd", 0x17C: "AddStat",
                0x29A: "Choice", 0x25B: "DmwEnableSlot", 0x156: "CallBattle", 0x154: "LoadBattleData", 0x33A: "FairSetMiniGameMode", 0x3E3: "FairShowMinigameFinish",
                0x3E4: "FairShowMinigameTimeup", 0x3F8: "FairBanoraTreasure", 0x403: "FairDestroyAllMissile"}
MISSION_FLAG = 0x8000


class TreasureReadHook(CaveHook):
    ORIGINAL, CAVE, MAGIC, OLD_MAGICS = ORIGINAL, CAVE, MAGIC, OLD_MAGICS
    DATA_SIZE = 8 + RING * 8            # u32 count, pad, ring[256] of 4 x u16

    def __init__(self, pm, site):
        super().__init__(pm, site)
        self.seen = 0

    def slot_f0(self):
        return self.site + 7                # this cave jumps back through [cave+0xF0]

    def on_adopt(self):
        self.seen = self.u32(0)

    def poll(self):
        """Calls logged since the last poll: (native, arg0, arg1, arg2) tuples, arg0 = stack top."""
        if self.state != "active":
            return []
        n = self.u32(0)
        if n == self.seen:
            return []
        first = max(self.seen, n - RING)
        ring = self.pm.read_bytes(self.data + 8, RING * 8)
        self.seen = n
        return [struct.unpack_from("<4H", ring, (i % RING) * 8) for i in range(first, n)]
