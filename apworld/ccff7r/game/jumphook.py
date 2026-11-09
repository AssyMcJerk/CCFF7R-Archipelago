"""Scene-jump hook: chapter gate + chapter select (warp).

Every scene change goes through RequestJump (exe+1329A00, edx = target scene id, r8b = flag); its
first instruction is `mov rcx,[jump_mgr_ptr]` (7 bytes), which the cave re-executes with an absolute
pointer stored at cave+0xF0.

Data block (cave+0x108):
  +00 u32 gate_from   if != 0 and the request is for this scene, it becomes (gate_to, flag 1):
  +04 u32 gate_to     the player bounces back to the field like a mission return (tested in Ch1); bit 31 set =
                      flag 0 instead (the scene's own entrance spawn, v0.6.37)
  +08 u32 warp_to     one-shot: the next MISSION START request (5500..5799) becomes (warp_to, flag 0)
  +0C u32 warp_hits
  +10 u32 warp_src    the mission-start id that was replaced (5500 + mission index)
  +14 u32 gate_hits
  +18 u32 last_id     last requested scene id
  +1C u32 count       number of requests seen
"""
from .cavehook import CaveHook

# v0.6.37 cave (APJMPHK2), source scripts/caves/jumphook_cave.py; unicorn-verified (flag 1 / flag 0 bounce, untouched
# jumps, warp; rax/rcx/rsp as before). APJMPHK1 (v0.3.x-v0.6.36) always bounced with flag 1.
CAVE = bytes.fromhex("50488d05f8000000895020ff40248b480885c9741b39ca75178b500c41b8010000000fbaf21f73034531c0ff401ceb298b481085c9742281fa7c150000721a81faa8160000731289501889ca4531c0c7401000000000ff4014488b48f0488b0958ff2591000000")
ORIGINAL_PREFIX = bytes.fromhex("488b0d")   # mov rcx,[rip+rel32]


class JumpHook(CaveHook):
    CAVE = CAVE
    MAGIC = b"APJMPHK2"
    OLD_MAGICS = (b"APJMPHK1",)
    DATA_SIZE = 0x20

    def __init__(self, pm, site, jump_mgr_ptr):
        super().__init__(pm, site)
        self.jump_mgr_ptr = jump_mgr_ptr
        rel = jump_mgr_ptr - (site + 7)
        self.ORIGINAL = ORIGINAL_PREFIX + rel.to_bytes(4, "little", signed=True)
        self.seen_warps = 0

    def slot_f0(self):
        return self.jump_mgr_ptr

    def on_adopt(self):
        self.seen_warps = self.u32(0x0C)

    # ---- gate
    def set_gate(self, from_id, to_id, entrance=False):
        """Redirect requests for from_id to to_id. entrance=True: flag 0 (spawn at the scene's entrance) instead of
        the mission-return flag 1 (spawn where the last mission was started)."""
        if self.state != "active":
            return
        if entrance and to_id:
            to_id |= 0x80000000
        if self.u32(0x04) != to_id:
            self.set_u32(0x04, to_id)
        if self.u32(0x00) != from_id:
            self.set_u32(0x00, from_id)

    def gate_hits(self):
        return self.u32(0x14) if self.state == "active" else 0

    # ---- warp
    def arm_warp(self, scene_id):
        self.set_u32(0x08, scene_id)

    def warp_armed(self):
        return self.state == "active" and self.u32(0x08) != 0

    def poll_warp(self):
        """Returns the replaced mission-start id if a warp fired since the last poll, else None."""
        if self.state != "active":
            return None
        n = self.u32(0x0C)
        if n == self.seen_warps:
            return None
        self.seen_warps = n
        return self.u32(0x10)
