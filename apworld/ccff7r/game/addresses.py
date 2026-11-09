"""Signature-based address resolution for CCFF7R-Win64-Shipping.exe.

Each data address is found from an instruction that references it RIP-relatively:
    target = match + disp_off + 4 + rel32 (+ any trailing bytes up to the end of that instruction)
Signatures were generated against the Steam build (UE 4.27.2, CL 19744026) and checked unique in .text.
`rva` is the value on that build, used only as a fallback/consistency hint.
"""
import re
import struct

MODULE = "CCFF7R-Win64-Shipping.exe"

# name: (signature, disp_off, ins_len, rva_on_reference_build)
DATA_SIGS = {
    "treasure_bits":       ("48 8D 1D ?? ?? ?? ?? 8B D1",                    3, 7, 0x71B4230),
    "char_status":         ("48 8D 05 ?? ?? ?? ?? 48 03 D8 74 55",           3, 7, 0x71B3F00),
    "mail_list":           ("48 8D 2D ?? ?? ?? ?? 33 C0",                    3, 7, 0x71B46B4),
    "mail_count":          ("44 0F B7 15 ?? ?? ?? ?? 33 FF",                 4, 8, 0x71B4B9E),
    "treasure_table_ptr":  ("48 8B 0D ?? ?? ?? ?? 48 8B C2",                 3, 7, 0x71AAD28),
    "inv_consumable":      ("83 3D ?? ?? ?? ?? 02 75 6A",                    2, 7, 0x71AAE20),
    "inv_key":             ("83 3D ?? ?? ?? ?? 03 75 75",                    2, 7, 0x71AAE60),
    "inv_accessory":       ("48 8D 0D ?? ?? ?? ?? BA 18 50 00 00",           3, 7, 0x71AADE0),
    "inv_materia":         ("48 8D 0D ?? ?? ?? ?? 44 0F BF 60 0C",           3, 7, 0x71AAF20),
    "materia_presets_ptr": ("48 8B 05 ?? ?? ?? ?? 4B 8D 0C 49 48 8D 34 88",  3, 7, 0x71AAEB0),
    "return_scene":        ("44 89 3D ?? ?? ?? ?? 66 44 89 35 ?? ?? ?? ?? C6 05 ?? ?? ?? ?? 00", 3, 7, 0x71B4B98),
    "native_table_ptr":    ("48 8B 35 ?? ?? ?? ?? 48 8B EA",                 3, 7, 0x71B8230),
    "jump_mgr_ptr":        ("48 83 3D ?? ?? ?? ?? 00 75 2A B9 10 0C 00 00",  3, 8, 0x717A7C8),
    # GetBattleActor(i): lea rcx,[battle_actors]; actor = battle_actors + i*0x740 (Zack = 0, HP at +0x1E8)
    "battle_actors":       ("48 63 C1 48 8D 0D ?? ?? ?? ?? 48 69 C0 40 07 00 00", 6, 10, 0x718DA40),
    # SetBattleFinish(side, type) exe+1378BA0: if [active] && [state]==3 { state=4; [+3]=side; [+0x12]=type }
    "battle_active":       ("80 3D ?? ?? ?? ?? 00 74 22 83 3D ?? ?? ?? ?? 03 75 19 C7 05",  2, 7, 0x717AD52),
    "battle_state":        ("80 3D ?? ?? ?? ?? 00 74 22 83 3D ?? ?? ?? ?? 03 75 19 C7 05", 11, 16, 0x717AD5C),
    # Buster Sword proficiency object (doc 5.4): getter exe+1370B70 = lea rax,[obj] / ret
    "proficiency":         ("48 8D 05 ?? ?? ?? ?? C3 CC CC CC CC CC CC CC CC 48 83 EC 28 E8 97 E8 FF", 3, 7, 0x718D9B0),
    # battle param manager (exe+1106A90): [[ptr]+0xD8] = proficiency goal table, 12-byte rows, u32 count goal at +4
    "battle_param_ptr":    ("48 83 EC 18 48 8B 05 ?? ?? ?? ?? 48 85 C0 74 2E 48 8B 80 D8 00 00 00", 7, 11, 0x717AE08),
}

# Functions / patch sites: address = match + optional adjust (3rd field).
CODE_SIGS = {
    "GiveItem":          ("48 89 5C 24 08 57 48 83 EC 20 0F B7 F9 33 DB", 0x13957E0),
    "ChangeItemCount":   ("48 89 5C 24 18 48 89 6C 24 20 56 41 56 33 F6", 0x116F7C0),
    "MateriaAdd":        ("40 55 57 41 54 41 56 48 83 EC 28 45 33 E4", 0x1394400),
    # matched 7 bytes in, so it still resolves while a 5-byte jmp hook (CE gate test / helper DLL) sits on the entry
    "RequestJump":       ("48 85 C9 0F 85 ?? ?? ?? ?? C3 CC CC CC CC CC CC CC CC CC CC CC CC CC CC CC 48 83 EC 28 48 83 3D ?? ?? ?? ?? 00", 0x1329A00, -7),
    "MissionStartJump":  ("48 89 5C 24 08 48 89 6C 24 10 48 89 74 24 18 48 89 7C 24 20 41 56 48 83 EC 30 44 8B F1", 0x13CCE50),
    "MissionReturnJump": ("48 89 5C 24 08 48 89 6C 24 10 48 89 74 24 18 57 48 83 EC 30 B9 18 00 00 00", 0x13CCB10),
    "VM_CallNativeSite": ("48 63 C2 49 8B 04 C0 48 85 C0", 0x13BEF86),
    # shop widget buy path: cmp byte [rdi+2F4],0 / je sell / >>movsxd rax,[rdi+2EC]<< / mov edx,[rdi+300] (hook-tolerant)
    # buy-list builder exe+12B8EA0: movzx ecx,[rsi] / lea rdx,[rbp-19] / mov [rbp+3],eax / >>call GetItemName<<
    "ShopNameCallSite":  ("0F B7 0E 48 8D 55 E7 89 45 03 E8", 0x12B8FD6, 10),
    "ShopBuySite":       ("80 BF F4 02 00 00 00 0F 84 ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? ?? 8B 97 00 03 00 00", 0x12B9201, 13),
}

# Static addresses with no signature yet (RVA on the reference build only).
RVA_ONLY = {}

# Fields inside the save/state block, relative to treasure_bits (one contiguous struct on the reference build).
# These have no unique code reference of their own; the probe cross-checks the block layout via
# return_scene / mail_count / mail_list, which DO have signatures.
STATE_OFFSETS = {
    "mission_state":  0x100,   # 300 x 3 bytes: [unlocked, ?, cleared]
    "current_scene":  0x934,   # u32 scene id the player is in (copied to return_scene when a mission starts)
    "active_mission": 0x96C,   # u16 mission index, 0xFFFF = none
    "mail_list":      0x484,
    "return_scene":   0x968,
    "mail_count":     0x96E,
    "chapter_byte":   0x974,
    "dmw_slots":      0x978,   # 7 x u8 DMW character portraits (0 = silhouette), doc 5.3
    "dmw_movies":     0x980,   # 38 x u8 memory scenes enabled by the story ([char*6 + n])
    "unlock_groups":  0x9A6,   # 10 bytes, set by ChapterClear
    "story_count":    0xCC8,   # NOT chapter*1000 after Ch6: Ch7 starts at 6500, Ch8 7000, Ch9 8000, Ch10 10000; final boss done = 11000
    "map_value":      0xCCC,
}


def _compile(sig):
    out = b""
    for tok in sig.split():
        out += b"." if tok == "??" else re.escape(bytes([int(tok, 16)]))
    return re.compile(out, re.DOTALL)


def text_section(pm, base):
    """Return (text_va, text_bytes) of the loaded module, read from its PE header in memory."""
    hdr = pm.read_bytes(base, 0x1000)
    e_lfanew = struct.unpack_from("<I", hdr, 0x3C)[0]
    nsec = struct.unpack_from("<H", hdr, e_lfanew + 6)[0]
    opt_size = struct.unpack_from("<H", hdr, e_lfanew + 20)[0]
    sec = e_lfanew + 24 + opt_size
    for i in range(nsec):
        o = sec + i * 40
        name = hdr[o:o + 8].rstrip(b"\0")
        vsize, vaddr = struct.unpack_from("<II", hdr, o + 8)
        if name == b".text":
            chunks, step = [], 0x400000
            for off in range(0, vsize, step):
                chunks.append(pm.read_bytes(base + vaddr + off, min(step, vsize - off)))
            return vaddr, b"".join(chunks)
    raise RuntimeError(".text section not found")


def resolve(pm, base=None):
    """Resolve every signature. Returns {name: absolute_address} plus '_problems' (list of str)."""
    if base is None:
        import pymem.process
        base = pymem.process.module_from_name(pm.process_handle, MODULE).lpBaseOfDll
    tva, text = text_section(pm, base)
    res, problems = {"_base": base}, []

    def find_one(name, sig):
        ms = [m.start() for m in _compile(sig).finditer(text)]
        if len(ms) != 1:
            problems.append(f"{name}: {len(ms)} matches")
            return None
        return ms[0]

    for name, (sig, doff, ilen, rva) in DATA_SIGS.items():
        m = find_one(name, sig)
        if m is None:
            res[name] = base + rva
            continue
        rel = struct.unpack_from("<i", text, m + doff)[0]
        res[name] = base + tva + m + ilen + rel
        if res[name] != base + rva:
            problems.append(f"{name}: moved (rva {res[name]-base:#x}, reference {rva:#x})")

    for name, spec in CODE_SIGS.items():
        sig, rva = spec[0], spec[1]
        adj = spec[2] if len(spec) > 2 else 0
        m = find_one(name, sig)
        res[name] = base + (tva + m + adj if m is not None else rva)
        if m is not None and tva + m + adj != rva:
            problems.append(f"{name}: moved (rva {tva+m+adj:#x}, reference {rva:#x})")

    for name, rva in RVA_ONLY.items():
        res[name] = base + rva

    res["battle_hp"] = res["battle_actors"] + 0x1E8          # i32 Zack's in-battle HP
    res["battle_flags"] = res["battle_actors"] + 0x24A       # u16 Zack's status flags; (flags & 0x11) = dead
    res["battle_finish_side"] = res["battle_active"] + 0x3   # u8  (0 = player side lost)
    res["battle_finish_type"] = res["battle_active"] + 0x12  # u32 (3 = game over, as BtlSetFinishGameOver)

    tb = res["treasure_bits"]
    for k, off in STATE_OFFSETS.items():
        key = "state_" + k
        res[key] = tb + off
    for k in ("return_scene", "mail_count", "mail_list"):
        if res[k] != res["state_" + k]:
            problems.append(f"state block layout changed: {k} sig={res[k]-base:#x} vs treasure_bits+{STATE_OFFSETS[k]:#x}")
    res["_problems"] = problems
    return res
