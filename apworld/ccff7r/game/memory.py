"""Read/write CCFF7R game state through pymem, using addresses from addresses.resolve().
Formats documented in CCFF7R_AP_Research.md sections 3-4."""
import struct
import pymem
from . import addresses

INV_CONTAINERS = {2: "inv_consumable", 3: "inv_key", 5: "inv_accessory"}


class Game:
    def __init__(self, pm=None):
        self.pm = pm or pymem.Pymem(addresses.MODULE)
        self.a = addresses.resolve(self.pm)

    # ---------- basic ----------
    def u8(self, addr):  return self.pm.read_uchar(addr)
    def u16(self, addr): return self.pm.read_ushort(addr)
    def i32(self, addr): return self.pm.read_int(addr)
    def ptr(self, addr): return self.pm.read_ulonglong(addr)

    # ---------- progress ----------
    def story_count(self):  return self.i32(self.a["state_story_count"])
    def chapter(self):      return self.story_count() // 1000
    def chapter_byte(self): return self.u8(self.a["state_chapter_byte"])
    def map_value(self):    return self.i32(self.a["state_map_value"])
    def return_scene(self): return self.i32(self.a["state_return_scene"])
    def gil(self):          return self.i32(self.a["char_status"] + 0xB0)
    def sp(self):           return self.i32(self.a["char_status"] + 0x0C)

    # ---------- checks ----------
    def treasure_opened(self, tid):
        return bool(self.u8(self.a["treasure_bits"] + (tid >> 3)) >> (tid & 7) & 1)

    def opened_treasures(self, max_id=2040):
        raw = self.pm.read_bytes(self.a["treasure_bits"], (max_id + 7) // 8)
        return [i for i in range(max_id) if raw[i >> 3] >> (i & 7) & 1]

    def mission(self, m):
        b = self.pm.read_bytes(self.a["state_mission_state"] + m * 3, 3)
        return {"unlocked": bool(b[0]), "cleared": bool(b[2])}

    def missions(self):
        raw = self.pm.read_bytes(self.a["state_mission_state"], 300 * 3)
        return [(bool(raw[i*3]), bool(raw[i*3+2])) for i in range(300)]

    def set_mission_unlocked(self, m, on=True):
        self.pm.write_uchar(self.a["state_mission_state"] + m * 3, 1 if on else 0)

    # ---------- mail ----------
    MAIL_CAPACITY = 314                       # list at mail_list, 4 bytes each, ends at mail_count

    def mail_ids(self):
        n = self.u16(self.a["mail_count"])
        if not 0 <= n <= self.MAIL_CAPACITY:
            return None
        raw = self.pm.read_bytes(self.a["mail_list"], n * 4) if n else b""
        return [int.from_bytes(raw[i*4:i*4+2], "little") for i in range(n)]

    def add_mail(self, mail_id):
        """Same as the game's MailAdd (exe+13CE5B0): append {u16 id, u8 0, u8 unread} and bump the count."""
        n = self.u16(self.a["mail_count"])
        if n >= self.MAIL_CAPACITY:
            return False
        self.pm.write_bytes(self.a["mail_list"] + n * 4, struct.pack("<HBB", mail_id, 0, 0), 4)
        self.pm.write_ushort(self.a["mail_count"], n + 1)
        return True

    # ---------- DMW / proficiency (doc 5.3, 5.4) ----------
    def dmw_slots(self):
        return list(self.pm.read_bytes(self.a["state_dmw_slots"], 7))

    def set_dmw_slot(self, slot, on):
        self.pm.write_uchar(self.a["state_dmw_slots"] + slot, 1 if on else 0)

    def dmw_watched(self):
        """Watched DMW memories: one byte per character, bit n = memory n (exe+13AE280)."""
        return list(self.pm.read_bytes(self.a["char_status"] + 0x168, 7))

    # HUD formula exe+11F1730: 30/25/25 for the three stance values (start -> end), 10/5/5 for the count goals
    PROF_PARTS = ((0x00, 80.0, 100.0, 30.0), (0x08, 200.0, 300.0, 25.0), (0x10, 100.0, 300.0, 25.0))
    PROF_COUNTS = (10.0, 5.0, 5.0)

    def add_proficiency(self, part, fraction):
        """Add `fraction` of one stance value's range (0 Block, 1 Command, 2 Sword), clamped at its end value.
        Returns False (nothing written) while the value is below its start, i.e. before the system is set up."""
        off, lo, hi, _ = self.PROF_PARTS[part]
        addr = self.a["proficiency"] + off
        v, = struct.unpack("<d", self.pm.read_bytes(addr, 8))
        if not v == v or v < lo - 1e-9:
            return False
        self.pm.write_bytes(addr, struct.pack("<d", min(hi, v + (hi - lo) * fraction)), 8)
        return True

    def proficiency_percent(self):
        raw = self.pm.read_bytes(self.a["proficiency"], 0x24)
        pct = 0.0
        for off, lo, hi, w in self.PROF_PARTS:
            v, = struct.unpack_from("<d", raw, off)
            if v == v:                                    # not NaN
                pct += w * max(0.0, min(1.0, (v - lo) / (hi - lo)))
        try:
            mgr = self.ptr(self.a["battle_param_ptr"])
            tbl = self.ptr(mgr + 0xD8) if mgr else 0
        except Exception:
            tbl = 0
        if tbl:
            for i, w in enumerate(self.PROF_COUNTS):
                goal = self.pm.read_uint(tbl + i * 12 + 4)
                cnt, = struct.unpack_from("<I", raw, 0x18 + i * 4)
                if goal and cnt >= goal:
                    pct += w
        return pct

    # ---------- treasure contents ----------
    def treasure_record(self, tid):
        t, amt, val = struct.unpack("<BBH", self.pm.read_bytes(self.ptr(self.a["treasure_table_ptr"]) + tid * 4, 4))
        return t, amt, val          # type 0 item / 1 gil / 2 SP

    def set_treasure_item(self, tid, item_id, count):
        self.pm.write_bytes(self.ptr(self.a["treasure_table_ptr"]) + tid * 4,
                            struct.pack("<BBH", 0, count, item_id), 4)

    # ---------- inventory ----------
    def _container(self, name):
        c = self.a[name]
        typ, = struct.unpack("<I", self.pm.read_bytes(c, 4))
        recs, slots, minc, maxc = struct.unpack("<QiiI", self.pm.read_bytes(c + 0x28, 0x14))
        return c, typ, recs, slots, minc, maxc

    def inventory(self, cat):
        """All three containers share ONE record array (consumables, key items, accessories mixed);
        the container only supplies the category used for the id>>12 check. Filter by category here."""
        _, _, recs, slots, minc, _ = self._container(INV_CONTAINERS[cat])
        raw = self.pm.read_bytes(recs, slots * 8)
        out = []
        for i in range(slots):
            iid, cnt, order, new = struct.unpack_from("<HHHB", raw, i * 8)
            if cnt > minc and iid >> 12 == cat:
                out.append((iid, cnt, order))
        return out

    def materia(self):
        _, _, recs, slots, minc, _ = self._container("inv_materia")
        raw = self.pm.read_bytes(recs, slots * 0x10)
        out = []
        for i in range(slots):
            iid, cnt = struct.unpack_from("<HB", raw, i * 0x10)
            if iid and cnt > minc:
                stars, btype, bval = raw[i*0x10 + 0xA], *struct.unpack_from("<HH", raw, i*0x10 + 0xC)
                out.append((iid, stars, btype, bval))
        return out

    # ---------- extra writers for the AP client ----------
    def exp(self):          return self.i32(self.a["char_status"] + 0x08)
    def add_exp(self, n):   self.pm.write_int(self.a["char_status"] + 0x08, self.exp() + n)
    def add_gil(self, n):   self.pm.write_int(self.a["char_status"] + 0xB0, min(self.gil() + n, 99999999))
    def add_sp(self, n):    self.pm.write_int(self.a["char_status"] + 0x0C, min(self.sp() + n, 99999999))

    def materia_preset(self, pid):
        """0xCxxx preset -> (base id, stars, bonus type, bonus value) from the preset table."""
        tbl = self.ptr(self.a["materia_presets_ptr"])
        cnt = self.i32(self.a["materia_presets_ptr"] + 8)
        idx = pid & 0xFFF
        if idx >= cnt:
            return None
        b = self.pm.read_bytes(tbl + idx * 12, 12)
        base, = struct.unpack_from("<H", b, 0)
        stars = max(1, min(5, b[6]))
        btype, bval = struct.unpack_from("<hh", b, 8)
        return base, stars, max(0, min(7, btype)), max(0, min(100, bval))

    def add_materia(self, mid, stars=None, btype=None, bval=None):
        """Direct write, mirrors exe+1394400. mid 0x4xxx (plain) or 0xCxxx (preset)."""
        if mid >> 12 == 0xC:
            p = self.materia_preset(mid)
            if not p:
                return False
            mid, stars, btype, bval = p
        c, typ, recs, slots, minc, _ = self._container("inv_materia")
        defs = self.ptr(c + 0x10)
        dcount = self.i32(c + 0x18)
        idx = mid & 0xFFF
        if typ != 4 or idx >= dcount:
            return False
        d = self.pm.read_bytes(defs + idx * 0x28, 0x28)
        raw = bytearray(self.pm.read_bytes(recs, slots * 0x10))
        free = next((i for i in range(slots) if raw[i*0x10 + 2] <= minc), None)
        if free is None:
            return False
        for j in range(slots):
            if struct.unpack_from("<H", raw, j*0x10)[0] and raw[j*0x10 + 2] > minc:
                struct.pack_into("<H", raw, j*0x10 + 4, struct.unpack_from("<H", raw, j*0x10 + 4)[0] + 1)
        o = free * 0x10
        struct.pack_into("<HBBHBBHBBHH", raw, o, mid, 1, 0, 1, 1, d[0x18],
                         struct.unpack_from("<H", d, 8)[0],
                         stars or 1, 0xFF,
                         btype if btype is not None else struct.unpack_from("<H", d, 0xC)[0],
                         bval if bval is not None else struct.unpack_from("<H", d, 0xE)[0])
        self.pm.write_bytes(recs, bytes(raw), len(raw))
        return True

    def give(self, payload):
        """Apply an AP item payload from items.json."""
        t = payload.get("type")
        if t == 1:
            self.add_gil(payload["id"] * payload["amount"]); return True
        if t == 2:
            self.add_sp(payload["id"] * payload["amount"]); return True
        if t == 0:
            iid, n = payload["id"], payload["amount"]
            if iid >> 12 in (4, 0xC):
                return all(self.add_materia(iid) for _ in range(n))
            return self.add_item(iid, n)
        return False

    def item_count(self, iid):
        return sum(c for i, c, _ in self.inventory(iid >> 12) if i == iid)

    def remove_item(self, iid):
        """Take every copy of a consumable/key/accessory item out (record freed, list order closed up)."""
        c, typ, recs, slots, minc, maxc = self._container(INV_CONTAINERS[iid >> 12])
        raw = bytearray(self.pm.read_bytes(recs, slots * 8))
        for i in range(slots):
            rid, cnt, order = struct.unpack_from("<HHH", raw, i * 8)
            if cnt > minc and rid == iid:
                struct.pack_into("<H", raw, i * 8 + 2, minc)
                for j in range(slots):
                    cj, oj = struct.unpack_from("<HH", raw, j * 8 + 2)
                    if cj > minc and oj > order:
                        struct.pack_into("<H", raw, j * 8 + 4, oj - 1)
        self.pm.write_bytes(recs, bytes(raw), len(raw))

    def add_item(self, iid, n=1):
        """Direct write, mirrors ChangeItemCount (exe+116F7C0). Consumables/key/accessories."""
        c, typ, recs, slots, minc, maxc = self._container(INV_CONTAINERS[iid >> 12])
        assert typ == iid >> 12
        raw = bytearray(self.pm.read_bytes(recs, slots * 8))
        hit = free = None
        for i in range(slots):
            rid, cnt = struct.unpack_from("<HH", raw, i * 8)
            if cnt > minc and rid == iid:
                hit = i; break
            if free is None and cnt <= minc:
                free = i
        i = hit if hit is not None else free
        if i is None:
            return False
        if hit is None:
            for j in range(slots):
                if struct.unpack_from("<H", raw, j*8 + 2)[0] > minc:
                    struct.pack_into("<H", raw, j*8 + 4, struct.unpack_from("<H", raw, j*8 + 4)[0] + 1)
            struct.pack_into("<HB", raw, i*8 + 4, 1, 1)
            cnt = 0
        else:
            cnt = struct.unpack_from("<H", raw, i*8 + 2)[0]
        struct.pack_into("<HH", raw, i*8, iid, min(cnt + n, maxc))
        self.pm.write_bytes(recs, bytes(raw), len(raw))
        return True
