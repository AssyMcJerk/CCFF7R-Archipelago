# Crisis Core –FFVII– Reunion (PC) — Archipelago Research Notes

Living notes for a possible Crisis Core Reunion APWorld + client.
Started 2026-10-14 from an Archipelago After Dark Discord idea post.

All addresses are **RVAs relative to `CCFF7R-Win64-Shipping.exe`** (write them in Cheat Engine as
`"CCFF7R-Win64-Shipping.exe"+OFFSET`). Values were found on the current Steam build
(exe size 90,314,520 bytes). If the game updates, re-verify everything.

---

## 1. Platform / tooling

| Item | Finding |
|---|---|
| Engine | Unreal Engine **4.27.2** (custom build string `4.27.2Plus`, CL 19744026) |
| Game module | Single native module **`/Script/Fair`** ("Fair" = internal project name) |
| DRM | **SteamStub** (`.bind` section). **No Denuvo** / VMProtect / Themida. Use Steamless on a copy for static analysis. |
| Paks | IoStore (`.utoc/.ucas`), **compressed + AES-encrypted (default key, zero GUID) + signed** |
| Real process | `CCFF7R-Win64-Shipping.exe` (the root `CCFF7R.exe` is a 340 KB launcher stub — never attach to it) |
| UE4SS | v3.0.0 works. Signatures all resolve. Install in `CCFF7R\Binaries\Win64`. |
| Mappings | `Mappings.usmap` generated via UE4SS (needed for FModel to parse unversioned assets) |

### Architecture insight
Reunion runs the **original PSP game logic as native C++** (`UFairPSPDrawTask`, save = raw
`TArray<uint8>` blob, PSP-style fixed structs). Unreal handles rendering/UI/assets.
Consequences:
- Game state (inventory, gil, flags, missions, mail) lives in a **static block in `.data`** — fixed RVAs, no pointer chains.
- Story/field logic runs on a **PSP-era event-script bytecode VM** with 1,172 named native commands.
- UE4SS reflection is useful for UI/hooks, but not for game state.

---

## 2. UE4SS setup notes (stability)

Crash causes found from `%LOCALAPPDATA%\CCFF7R\Saved\Crashes`:

| Crash | Cause | Fix |
|---|---|---|
| Fatal at publisher logos (first run) | GUI console OpenGL / starter mods | `GraphicsAPI = dx11`, starter mods off |
| `0xE06D7363` in UE4SS | `CallFunctionByNameWithArguments` hook threw | `HookCallFunctionByNameWithArguments = 0`, `HookLocalPlayerExec = 0` |
| Call to `0x0` from `StaticConstructObject_Internal` (exe+17EC110) | UE4SS object-construct hook (enabled by Lua `NotifyOnNewObject`) raced the async loader | **Don't use `NotifyOnNewObject`** |
| `0x80000004` single-step | Cheat Engine default debugger | Don't use CE debugger; use code-cave logging instead (or VEH) |

Performance: `HookProcessInternal = 0`, `HookProcessLocalScriptFunction = 0`,
`GuiConsoleEnabled = 0` unless needed. Never call `FindFirstOf` in a tight loop (full GUObjectArray scan).

Working settings file: `scripts/ue4ss/UE4SS-settings.ini`. Logger mod: `scripts/ue4ss/CCStoryLogger/`.

---

## 3. Game state block (static, `.data`)

Base of the block: **`exe+71B3F00`** (character status array, 0x250 bytes per character; Zack = index 0).

### 3.1 Character status (`exe+71B3F00 + idx*0x250`)
Source: opencheattables table (bbfox) + own verification.

| Off | Type | Field |
|---|---|---|
| +0x0C | u32 | SP |
| +0x10 / +0x14 / +0x18 | u32 | HP / Max HP / Base max HP |
| +0x1C / +0x20 / +0x24 | u32 | MP / Max / Base max |
| +0x28 / +0x2C / +0x30 | u32 | AP / Max / Base max |
| +0x36 | u8 | Level |
| +0x37..+0x3B | u8 | Str / Vit / Int / Spi / Lck |
| +0x3D..+0x41 | u8 | Base Str..Lck |
| +0x44..+0x4D | u8 | Equipped command IDs / availability |
| +0x53..+0x61 | u8 | Materia slot levels / equipped indices |
| +0x72 / +0x74 | u16 | Equipped accessory #1 / #2 |
| +0x7A | u8 | DMW limit level (1–4) |
| +0xB0 | u32 | **Gil** |
| +0xB8 | f64 | Play time (seconds × 60) |
| +0x1164 | u32 | Chapter 5 squats count |

Other: Chapter 9 sniper minigame points = `exe+71B4E04` (u8).
Cheat-table finds (cheat tables forum, not yet verified by us), all inside this saved block:
- `exe+71B4D54` (u16, treasure_bits+0xB24): **Aerith affection**. 80 is said to be the legit max, 75 for the achievement. Perfume blending and the Godspeed materia hunt only raise this, so a rise in their scene could be their completion check.
- `exe+71B5088` (u16, treasure_bits+0xE58): Ch9 waterfall minigame chests collected.
- `exe+71B52A0` (u16, treasure_bits+0x1070): perfume blending required amount (the "max"); `exe+51791C4` is a second, static perfume value.
- Code addresses (instructions, would need a code patch, not pollable): `exe+1270950` materia hunt count-up timer; `exe+12DC1C6` shared count-down timer (Ch2 shelling, Ch4 Hojo, Ch8 6th wonder).

### 3.2 Treasure (chests, supply pods, **mission rewards**)
| Address | What |
|---|---|
| `[exe+71AAD28]` | Pointer to **treasure table**: 4-byte records indexed by treasure ID |
| `exe+71B4230` | **Opened bitfield**: `byte = id >> 3`, `bit = id & 7` |

Treasure record:
| Off | Type | Field |
|---|---|---|
| +0 | u8 | type: **0 = item, 1 = gil, 2 = SP** |
| +1 | u8 | amount (item count) |
| +2 | u16 | item ID (type 0) / gil or SP amount (types 1/2) |

- 2,040 slots, **1,322 non-empty** (some likely unused/debug — needs reachability mapping).
- Vanilla contents exported: `data/treasure_table_vanilla.csv`; **with item/materia names: `data/treasure_table_named.csv`**.
- **Content replacement verified live:** with `treasure 114` (2-1-2's reward, vanilla Fire Armlet) rewritten in memory to `00 03 06 20`, the mission menu showed **Elixir ×3** and the game paid out 3 Elixirs. Both the menu and the payout read the table live, so the AP client can rewrite all contents after load (the table is rebuilt on game start).
- Gil records: the count byte appears to be a multiplier (vanilla is always 1 or 10). With count 0 the game paid 0 gil, and the reward popup printed a stale string ("Poison gil obtained!"). The mission menu ignores the type byte and always draws an item (id+count), so **only put item records into mission rewards**.
- Verified live: opened bits 23 (Bronze Bangle pod), 29 (Soma chest, Wutai), 30 (Potion chest, Wutai), **40 (Elixir — tutorial mission reward)** → mission rewards use the same system.

### 3.3 Missions
**State:** `exe+71B4330 + m*3` (300 missions, 0–299): byte 0 = unlocked (`MissionSet` writes `01 01`),
byte 2 = **cleared** (`MissionIsCompleted` reads `exe+71B4332 + m*3`). Verified: tutorial mission = index 200 (`01 00 01`).

**Mission definition table** (heap; pointer held by the mission menu widget `WB_ui_Mission_C + 0x2E8`;
records start at **ptr + 0x2F0**, 300 × **0x54** bytes = 21 × int32). Exported: `data/missions.csv`.

| Field | Meaning |
|---|---|
| f0 / f1 | 2m / 2m+1 (likely title / description text IDs) |
| f2 | 4 packed bytes (category / layout info, TBD) |
| f3 | difficulty rank 1–10 |
| **f5** | **mission unlocked when this one is cleared** (−1 = none). Confirmed against the PowerPyx guide: 192/196 match; the rest are guide typos |
| **f9** | **completion reward treasure ID** (all 300 set) |
| **f10–f18** | **treasure chests inside the mission map** (−1 terminated; what the menu's treasure counter counts) |
| f19 | permutation of 0–299 — likely menu display order |

Treasure-ID coverage: **1,322 = 300 mission rewards + 768 mission chests + 254 story/field treasures**
(field IDs in 15 contiguous ranges: 0–39, 47–68, 85–97, 144–185, 227–245, 316–333, 396–427, 470–479, 503–517,
548–568, 587, 752, 894–895, 1303–1308, 1310–1321).

**Unlock rules** (`data/mission_unlocks.csv`, built from game data f5 plus the PowerPyx all-missions guide):
| unlock_type | count | how |
|---|---|---|
| chain | 252 | clearing the f5-predecessor unlocks it (game data) |
| chapter | 29 | event script at chapter start (Ch1 1, Ch2 4, Ch3 3, Ch4 3, Ch5 4, Ch6 4, Ch7 1, Ch9 5, Ch10 4) |
| npc | 16 | talking to Midgar NPCs, Ch2–Ch7. **All 16 are missable** after leaving Midgar at the end of Ch7 (1-2-1, 2-1-1…2-1-6, 4-3-1…4-3-6, 6-2-1, 7-1-1, 8-2-1) |
| special | 3 | 8-4-1 (Sephiroth scene in Reactor 5, Ch3), 10-1-1 (defeat Cactuar in 3-1-3), 10-2-1 (defeat Tonberry in 6-1-5) |
No f5 predecessor although the guide gives one: **9-1-1** (guide: after 8-5-6) and **10-3-1** (guide: after 3-2-2). These are probably unlocked by script or by a different rule (TBD).
Data and guide disagree on 6-4-1 (data: after 6-2-6) and 8-3-1 (data: after 8-1-6). Trust the data, verify in game.
The mission menu shows a category once any of its missions is unlocked (`71B4330 + m*3`, byte 0). **Verified:** writing `01` to `71B4441` (2-1-1, an NPC mission) on a Ch1 save makes M2 / 2-1-1 show up and become playable. Clearing it out of order works normally: the chest set treasure bit 110 (`71B423D` 0→64), the reward set bit 111 (→192) right away, and the cleared byte `71B4443` flipped to 1 when the game returned to the field save point. Writing the cleared byte back to 0 un-clears it in the menu (M2 shows 0/1 again). The menu reads only these bytes. Treasure bits are separate, and a replay does **not** re-grant opened treasures. Verified on 2-1-1: the chest showed as already collected and the reward was skipped.

The widget pointer is reached via UE4SS (`FindAllOf("WB_ui_Mission_C")`, live instance is the `/Engine/Transient...` one)
— still TBD whether a static owner exists.

### 3.4 Mail
| Address | What |
|---|---|
| `exe+71B46B4` | Received-mail list, 4 bytes each: `u16 mailId, u8 ?(12–15 seen), u8 read` |
| `exe+71B4B9E` | `u16` received-mail count |
`MailAdd` → exe+13CE5B0 (dedupes by ID, appends, increments count).

### 3.5 Story progression — **confirmed**
| Address | Type | Meaning |
|---|---|---|
| **`exe+71B4EF8`** | u32 | **story_count**. Format `chapter*1000 + step`. **Chapter = story_count / 1000** |
| **`exe+71B4EFC`** | u32 | **current map ID**. Story field maps are `chapter*10000 + area*100 + sub` (10401, 10502, 20101–20402). 0 = battle or event scene. 3-digit IDs (203, 204, 205, 301, 403, 501, 601) seen during Ch.2 hub travel (Shinra HQ floors?). 5057 / 5109 appear at chapter transitions. Also 3 and 40003 (TBD) |

Observed (`dumps/story_watch.log`, `scripts/cheatengine/story_watch.lua`):
- Ch1: 1350 (Wutai, Yuffie scene) → 1352 → 1400 (Ogre boss) → 1402 → 1601 … 1606 (Ifrit). 1500 block skipped.
- Ch2 card: 2001 (map 5057) → 2002 … 2092 in steps of +1 / +10. One decrease seen (2073 → 2072), so it's not strictly monotonic within a chapter.
- Ch3 card: **3000** (map 5109).
- `exe+71B4FC0` u8 went 0 → 1 at the Ogre boss (TBD). `exe+71B5030` is **not** a flag: it pulses during map loads.

**When it changes:** at the save prompt that follows the end-of-chapter cutscene. That's when story_count jumps to the next thousand.

**`ChapterClear(ch)` (native 25A, handler `exe+131A720`)**: `ch` = the chapter just cleared (0 = prologue). It does the following:
- writes `exe+71B4BAF = 0` (TBD)
- writes **`exe+71B4BA4 = ch + 1`** = current chapter (u8). Live in Ch3: 3 ✔
- sets **unlock-group flags `exe+71B4BD6[0..9]`** (u8 each) via `exe+13CEAA0`: prologue → 0–2, Ch2 → 3–4, Ch3 → 5–7, Ch8 → 8. Live: Ch1 save `1 1 1 0…`, Ch3 save `1 1 1 1 1 0…`. **Not mission categories**: toggling them doesn't change the mission menu, which is driven by the per-mission unlocked bytes at `71B4330` (a category shows once any of its missions is unlocked). The only code references are the setter, the new-game reset and a getter for [9] at `exe+13CEAB0` (called from `exe+127C9ED`). Most likely read through the state block by UE-side code. Candidates: shop stock tiers or DMW. TBD
All of these are cleared by the new-game reset at `exe+13CEBF0`.

AP use: a chapter-complete check = story_count crossing into the next thousand. Chapter gating can wrap native 25A `ChapterClear` or block when story_count ≥ (n+1)*1000.

---

## 4. Inventory

### 4.1 Item ID categories (`id >> 12`)
| Prefix | Category | Container | Example |
|---|---|---|---|
| `0x2xxx` | Consumables (2000–2007) | `exe+71AAE20` | 2000 Potion … 2007 Phoenix Down |
| `0x3xxx` | Mako stones, stat stones, **key items**, Goddess Materia (3000–3059) | `exe+71AAE60` | 3000 ATK Mako Stone, 3035 Keychain, 3036 Backpack, 3053–3059 Goddess Materia |
| `0x5xxx` | Accessories (5000–506B) | `exe+71AADE0` | 5000 Bronze Bangle, 5049 Ribbon |
| `0x4xxx` | Materia, base IDs (4000–4092, 147) | own routine `exe+1394400` (list `exe+71AAF20`) | 4000 Fire, 400B Curaga, 4084 Hellfire |
| `0xCxxx` | **Preset materia**: index into preset table (174 entries) | same routine | C000 = Hellfire 5★ MAG+40 |
| `0xExxx` | Reference to an existing materia slot (not used by treasure) | same routine | |

**Full verified ID → name map: `data/item_names.csv`** (built from the FName pool, which registers item names
in ID order; 5 materia names — Stop, Death, Gravity, Flare, Jump — were missing because those FNames already
existed and were re-inserted after in-game verification; 31 materia anchors + all category endpoints verified).

Preset materia table: pointer `exe+71AAEB0`, count `exe+71AAEB8`, 12-byte records:
`+0 u16 base materia ID, +6 u8 stars (1–5), +8 s16 bonus type, +0xA s16 bonus value (≤100)`.
Bonus type: 0 HP, 1 MP, 2 AP, 3 ATK, 4 VIT, **5 MAG, 6 SPR** (verified), 7 LCK. Decoded: `data/materia_presets.csv`.

Materia list data: `exe+71AC220`, records **0x10** bytes (the cheat table said 0x18, which is wrong). See 4.y.

### 4.2 Container struct (e.g. `exe+71AAE20`)
| Off | Field |
|---|---|
| +0x00 | category (must equal `id >> 12`) |
| +0x28 | pointer to records (consumables → `exe+71ABA20`) |
| +0x30 | capacity |
| +0x34 | min count (0) |
| +0x38 | max count (cap) |

Item record (8 bytes): `u16 id, u16 count, u16 sortRank, u8 newFlag (yellow dot), u8 pad`.

### 4.3 Functions
| RVA | Function |
|---|---|
| `exe+13957E0` | **GiveItem(u16 id, int delta)** → amount changed. Dispatches by category; also notifies UI/log (`11E2530`, `11E2B40`). Negative delta removes. |
| `exe+116F7C0` | ChangeItemCount(container*, u16 id, int delta) — find/insert record, re-rank, set new-flag, clamp, clear at 0 |
| `exe+13ADCD0` | GetGil(charIdx) (cheat-table hook point) |

Verified: calling `GiveItem` via CE `executeCodeEx` works (Remedy, ATK Mako Stone, Bronze Bangle, Fire).

### 4.4 Who calls GiveItem (return address)
| Return | Source |
|---|---|
| `exe+12B9222` | Shop buy (sell also uses GiveItem with negative count) |
| `exe+13BEF9F` | **Event-script VM** (chests, pods, mission rewards) |
| — | Using items in battle does **not** go through GiveItem |

---

### 4.x Inventory container layout (from `ChangeItemCount` exe+116F7C0)
Containers: consumables `71AAE20`, key/other `71AAE60`, accessories `71AADE0`.
| Off | Type | Field |
|---|---|---|
| +0x00 | u32 | category (= id >> 12) |
| +0x28 | ptr | record array |
| +0x30 | i32 | slot count (fixed array) |
| +0x34 | i32 | min: a slot is empty if count <= min |
| +0x38 | i32 | max count (cap) |
Record (8 bytes): `u16 id, u16 count, u16 acquisition order (1 = newest), u8 new flag, u8 pad`.
Add logic: stack onto a slot with the same id, else take the first empty slot. A new slot ages every other owned item by +1 and is set to order 1 with the new flag. Count is clamped to max. Removing to <= min clears the slot.
**All three containers share ONE record array** (consumables, key items and accessories mixed in one list; confirmed live by the probe). The container only supplies the category used for the `id >> 12` check, so filter by category when reading. **No side effects outside the array**, so a pymem client can reproduce it exactly. Test script: `scripts/cheatengine/direct_add_item.lua`. **Verified live:** a Fire Armlet added this way appeared as newest, was equippable, and survived save → title → reload.

### 4.y Materia list layout (from exe+1394400, verified by diffing a GiveItem(0x4008) Thundaga grant)
Container `71AAF20`: +0x00 u32 type (4), +0x10 ptr definitions (stride 0x28), +0x18 def count, +0x28 ptr records (**stride 0x10**, array at `71AC220`), +0x30 slots, +0x34 min, +0x38 max.
| Off | Type | Field |
|---|---|---|
| +0x0 | u16 | materia id (0x4xxx) |
| +0x2 | u8 | count: 1 = present, 0 = empty slot |
| +0x4 | u16 | acquisition order (1 = newest; every other entry is incremented on add) |
| +0x6 | u8 | new flag |
| +0x7 | u8 | copied from def+0x18 |
| +0x8 | u16 | copied from def+0x08 |
| +0xA | u8 | stars 1–5 |
| +0xB | u8 | 0xFF |
| +0xC | u16 | bonus stat type 0–7 (5 = MAG, 6 = SPR, …) |
| +0xE | u16 | bonus value 0–100 |
Id prefixes: `0x4xxx` plain (1 star, default bonus from def+0x0C/+0x0E), `0xCxxx` preset (table `[71AAEB0]`: stars / bonus from preset), `0xExxx` copy of an existing record.
Thundaga via GiveItem landed in the first free slot with order 1. It was equippable and survived save → title → reload.
`GiveItem` (exe+13957E0) also calls exe+11E2530 / exe+11E2B40 after every grant. 11E2530 checks the Genji set (0x5066–0x5069), likely for a trophy. Direct writes skip this, which matters only for achievements.
Direct-write test: `directAddMateria()` in `scripts/cheatengine/direct_add_item.lua`. **Verified live:** Thunder (0x4002) added with no game code appeared as newest (1 star, default bonus = none, MP 9). It was equippable, cast fine in the Ifrit battle, and survived save → reload.

## 5. Event-script VM

| What | Where |
|---|---|
| Interpreter dispatch | `exe+13BEF30` (`call rax` at 13BEF9D) |
| Native table | `[exe+71B8230]` → object with `begin` at +0x10, `end` at +0x18 (vector of entry ptrs) |
| Native entry | +0x00 index, **+0x18 `char*` name**, +0x20 handler fn |
| VM context | `rbx` in interpreter; `+0x18` stack array (8-byte slots), `+0x24` sp, `+0x2A8/+0x2B0` return status/value, **`+0x2C8` current instruction ptr** |

Call-native instruction (13 bytes for 2 args):
```
29 | 00 00 02 4A | 00 | 02 | 00 02 | 00 01 | 00 00
op   native id    ret  argc  ?      argument stack offsets (arg = stack[sp - off - 1])
```
Other opcodes seen: `09` push imm32, `0A` push float, `17 xx xx xx xx` push local addr, `1B` load, `21` store, `27` jump(?), `5B`.

Treasure helper scripts are shared: chest ID / item / count are passed as locals, so the instruction
pointer does **not** identify a chest — the **treasure ID** (bitfield index) does.

### 5.1 Key natives (full list: `data/script_natives.tsv`)
| ID | Name | Handler | ID | Name | Handler |
|---|---|---|---|---|---|
| 015 | MapJump | | 255 | **MailAdd** | 131AAB0 |
| 249 | GetItemName | 131A990 | 256 | MissionSet | 131ADA0 |
| 24A | **AddItem** | 131A660 | 257 | MissionIsCompleted | 131AD40 |
| 24B | HaveItem | 131AA50 | 258 | **MissionComplete** | 131AAF0 |
| 24C | **AddGil** | 131A620 | 259 | MissionFailed | 131AD20 |
| 24E | **AddSP** | 131A6C0 | 25A | **ChapterClear** | 131A720 |
| 250 | TreasureIsEnable | 131B000 | 25B | DmwEnableSlot | 131A890 |
| 251 | **TreasureEnable** | 131AE40 | 282 | MenuMission | |
| 252 | TreasureGetType | 131AFA0 | 286 | EnableMateriaSynthesis | |
| 253 | TreasureGetAmount | 131AEE0 | 2F7–2FB | GetEventJump* (debug story jump) | |
| 254 | TreasureGetId | 131AF40 | 3F4 | FairClearChapter | |

Minigame natives exist for squats, Fort Tamblin, Junon defense, materia hunt, jail key, Banora treasure,
waterfall treasure hunter, fan club save, etc. — candidates for minigame checks.

### 5.2 Event scripts in `discimg.pkg` (static scan, 2026-10-21)
- **Package:** `FGKP`, u32 version 0x10, u32 count, 32-byte entries, then data. Each file = u32 LE table of compressed chunk sizes + zlib streams (each inflates to <= 32 KiB). 8,706 files, 769 of them `Atel` event scripts.
- **Atel script:** `Atel`, version, function count, **NAMES_LEN** (word 3), ...; function entries at 0x18; then an **XOR-obfuscated name table** of NAMES_LEN bytes; then bytecode. The keystream is position-based and identical in every file; recovered from NUL terminators plus native-name matching (`data/atel_name_keystream.json`, complete for offsets 0-6000, partial to ~11,200).
- **Calls** `29 | u32 BE name offset | ret | argc | argc..0 (u16 BE)`: the operand is the callee's name offset in the file's own name table (natives and local functions alike). The game links names to native indices at load, which is why live memory shows global IDs (0x254 etc.).
- **Field chest setup:** `09 <id> 18 00000004 21  09 <n> 18 00000008 21 ... 18 0000000c 21` followed by the position floats. 884 chest IDs, including 422/473 (Shinra Manor) and **548-568, 1308, 1320** (not yet mapped: probably Ch10).
- **No-bit grants** (TreasureGetId without TreasureEnable): 55-59 / **60-64** (Banora Treasures perfect / lower tier, same script), **86/87** (Fire/Blizzard, Ch3 start at Shinra HQ before the materia tips; also in `Chapter3_Init`), 178 (Jail Cell Key).
- **Unused:** 183, 184, 185, 316, 505, 506 have no chest setup and reach no Treasure* native anywhere (their literals only feed message, map-element, mail or mission natives).
- Tool: `scripts/discimg/atel_scan.py <discimg.pkg> [ids]`.

### 5.3 DMW character slots (tested live 2026-10-22)
- **Slot flags:** `exe+71B4BA8[0..6]`, u8 each (1 = portrait shown). Native 25B `DmwEnableSlot(slot, 1)` -> setter `exe+13CEA70`; getter `exe+13CF440` (used by the reel and DMW menu code). Saved with the save file.
- **Slots:** 0 Sephiroth, 1 Angeal, 2 Tseng, 3 Cloud, 4 Aerith, 5 Cissnei, 6 Genesis (tester, via the DMW menu).
- **Flag 0:** the portrait is a silhouette ("???"); three matching silhouettes give **Chain Slash** instead of the character's limit. All 7 at 0 from the prologue works (tester). No event script ever calls `DmwIsEnableSlot`, so the story does not depend on them.
- `exe+71B4BAF`: separate u8 flag (setter `exe+13CF5D0`, getter `exe+13CF4A0`), purpose TBD. `exe+71B4BB0[char*6 + n]`: DMW memory-movie flags (native 25D `DmwEnableMovie(char, n, 1)`, setter `exe+13CEA80`).
- The DMW menu has 18 entries; the other 11 "???" (2nd column below Genesis, 3rd column) are not these flags (probably summons).
- AP idea: 7 "DMW: <character>" items, every slot starts at 0; the story unlock moments become checks (hook native 25B, like the TreasureGetId read hook, since polling can't tell a story unlock from a received item).

### 5.4 Buster Sword proficiency (Battle Stance growth, Reunion-only; solved 2026-10-23)
- **Static object** at `exe+718D9B0` (getter `exe+1370B70` = `lea rax,[718D9B0]; ret`, 19 callers). Saved with the game.
  - `+0x00` double **Block** (Perfect Guard), `+0x08` double **Command** (AP-command materia kill), `+0x10` double **Sword** (Strong Attack kill).
  - `+0x18/+0x1C/+0x20` u32 count types (DamageBreakCount, PenetrationBarrierCount, InvalidBarrierCount); "achieved" when count >= the table limit (`exe+1106A90`).
  - `+0x24..` per-battle action counters (gain is capped per battle), `+0x3C` u8 flag (`exe+1106C20`, probably "system unlocked", Ch6 Junon).
- **Gain** (`exe+1106900(obj, type)`): adds the table increment to the double, clamped at the bucket's end value. Data-table rows hold start/end/increment/per-battle cap (BattleGlobalParam, not exported).
- **HUD %** (`exe+11F1730`, feeds the `WB_ui_Buster_Percentage` widget at `exe+126F160`):
  `% = 30*(Block-80)/20 + 25*(Command-200)/100 + 25*(Sword-100)/200 + 10*[count0 done] + 5*[count1 done] + 5*[count2 done]`
  Start values 80/200/100 (fresh Ch6), ends 100/300/300 (forum "legit max"). Checked against 4 HUD readings (e.g. 80.29/200.9/108.4 -> 1.71, HUD 1.70).
  The popular guide's "31.66% x3 + 5% barrier" is wrong: it's 30/25/25 for the stance actions and 10/5/5 for the three count goals.

### 5.5 Mail (mapped 2026-10-23)
- 102 "real" mails (ids 0-107; 99 from scripts + 0, 25, 37 from game code) + ~95 tutorial/system entries (ids 121-230) in the same list. One run gets at most 100: 81/82/83 (Zack Fan Club, Ch9) are mutually exclusive (one picked by how many of 3 fan tasks were done).
- Received list `exe+71B46B4` {u16 id, u8 0, u8 read}, count `exe+71B4B9E`. `MailAdd` (exe+13CE5B0) only dedupes and appends; writing an entry + count from outside works (tester: 99/100/101 injected, show and open normally).
- **Mission mails** (85-104): the SavePoint `touch` script runs the mission->mail routine only if script global 0x973 ("mission cleared since last save point") is set; no script sets it (native code). Tester: 99-101 never arrived after 100% missions, nor after re-clearing 8-6-3 with or without the client. Pairs (mission index -> mail): 69>85 68>86 70>87 72>88 173>89 74>90 75>91 77>92 177>93 78>94 79>95 80>96 81>97 83>98 84>99 184>100 85>101 27>102 113>103 108>104.
- Client v0.5.5 delivers any of these mails whose mission is cleared but missing (`deliver_mission_mails`).
- Silver Elite chain: 75 (Ch5 quiz), 76 (Ch7 park), 77 (Ch9 manor). Yuffie chain subjects: 97 Notice, 98 Another notice, 99 I'm alright, 100 Don't come, 101 (no title).

---

## 6. UE4SS-visible systems (reflection)

Managers hang off `FairGameInstance` as subsystems: `FairSaveLoadManager`, `FairGameStateManager`,
`FairDestinationManager` (mission destinations), `FairEventSkipManager`, `FairMapChangeInfoManager`,
`FairDebugEventJump` (story-beat table; **list is null in shipping build** → get via FModel),
`ZDebugMenuSystem`, etc.

Story position struct (`FFairEventInfo`): `Map_id, story_count, sub_id, debug_storyCount, chapter_number`.
Cutscenes: `/Game/Fair/Camera/Event/seqNN_eveNN/LS_seqNN_eveNN_cNN` (sequence/event/cut).

Debug event-jump data table row: `hierarchy_level, display_name, Map_id, story_count, sub_id, debug_storyCount, chapter_number`.

---

## 7. AP design implications

### 7.1 Verified building blocks (live tests, Oct 2026)
| Need | Mechanism | Status |
|---|---|---|
| Detect chest / pod / mission-reward checks | opened bitfield `71B4230` | ✅ |
| Change what a check gives | rewrite treasure table `[71AAD28]` after load (menu + payout read it live) | ✅ items. Gil works only with count ≥ 1, and never in mission rewards |
| Detect mission clears | `71B4330 + m*3 + 2` (set on return to field) | ✅ |
| Unlock any mission, incl. the 16 missables | `71B4330 + m*3` = 1 | ✅ |
| No double payout on replay | treasure bits are independent of clear bytes | ✅ |
| Chapter progress / goal | story_count `71B4EF8` / 1000, chapter byte `71B4BA4` | ✅ |
| Give received items | direct inventory writes, no game code: accessories ✅, materia ✅ (consumables/key items share the accessory path) | ✅ |
| Placeholder for other worlds' items | item record with **count 0** (e.g. `00 00 06 20`): popup reads "Elixir × 0 obtained!", inventory unchanged, treasure bit still set | ✅ (cosmetic text only) |
| Chapter gating | hook `RequestJump` exe+1329A00: turn the field→final-event jump into the mission-return jump (save-point scene, flag 1) until the Chapter Key arrives | ✅ (proof of concept, Ch1) |
| DMW / shops / mail / minigames | — | ❓ |

### 7.2 Architecture plan
**Core: Python client bundled in `ccff7r.apworld`** (same model as the USF4 APWorld). All logic lives here: locations/items/rules, check detection, treasure-table rewriting, mission unlocks, goal. Updates = ship a new .apworld.

**Phase-2 helper: a small native DLL** (proxy-loaded like `dwmapi.dll`, **no UE4SS dependency**: UE4SS caused crashes and stutter here). It does only what external memory access can't do well:
- give items on the game thread via `GiveItem` (correct for materia, sorting, caps)
- show in-game "Received X from Y" / "Sent X to Y" popups via the game's own message system
- chapter gating: hook chapter clear and hold it until the unlock item arrives
- turn vanilla grants for remote items into a message instead of a placeholder item
The client talks to it over a named pipe or shared memory. The DLL just carries out commands.

**Streamlining rules**
1. **AOB signature scanning from day one.** Every address is an exe RVA today, and a Steam patch breaks all clients. Resolve every address/function from a byte signature at startup (one `addresses.py`).
2. **Single data source.** The `data/*.csv` files (treasure, missions, mission_unlocks, items, materia, collectibles) feed a build script that generates the APWorld item/location tables. Fixes are CSV edits, not code edits.
3. **Save ↔ seed binding.** Store seed/slot plus the received-item index (spare save byte or a sidecar file per save) to prevent double-giving and wrong-save loads.
4. **Minimal player install.** Phase 1: .apworld + AP Launcher only (no CE / UE4SS). Phase 2: + one DLL.
5. **Later: a PopTracker pack** (mission data maps directly onto it).
6. **Steam Deck/Proton:** pymem is unreliable under Proton. Long-term option: let the DLL talk to AP directly (apclientpp), making the Python client optional. Phase 2 keeps that path open.

### 7.3 Roadmap
1. **Groundwork:** AOB resolver for all known addresses, plus the CSV → APWorld data build. *Data build done:* `apworld_build/build_data.py` → `apworld/ccff7r/data/locations.json` (1,293 locations: 300 mission rewards, 768 mission chests, 216 story chests, 9 chapter clears; 38 chapterless/debug treasures excluded) + `items.json` (368 vanilla items incl. 7 Goddess Materia as progression, 52 Mission Set items, Progressive Chapter Key ×9); pool is 52 over the location count → drop filler. *Probe verified live: all 20 signatures resolve, `problems: none`.* *Resolver done:* `client/ccff7r/addresses.py` (13 data + 7 code signatures, all unique in .text, verified offline to resolve to the reference RVAs; state-block fields derived from `treasure_bits` with layout cross-checks), `client/ccff7r/game.py` (pymem state API: story/chapter, missions, treasure bits and contents, inventory/materia read, direct add_item), `client/probe.py` (read-only live check).
2. **Playable alpha (pymem only):** chests, mission rewards, mission unlocks, story-count goal. Received items via direct inventory writes (consumables + accessories first).
3. **Helper DLL:** GiveItem on game thread, in-game messages, chapter gating.
4. **Extra check types:** DMW, shops (shopsanity), mail, minigames, plus the PopTracker pack.

### 7.3c Chapter-end script sequence (native trace, Ch1 → Ch2)
Captured with `native_trace.cea` v2 (`dumps/native_trace_v2_2.bin`):
```
MapJump(5018)  ... Ifrit battle/event ...  MapJump(5019) ... post-battle cutscene ...
MapJump(5000)                      <- generic chapter-end script (0x1388)
  SetMapName(0x5F) FairSetEventSkipForceMode(1) StopAllSound
  MissionSet(210)                  <- end-of-Ch1 mission unlock (index 210)
  SetMapName(0x60)
  ChapterClear(1)                  <- arg = chapter just cleared
  Fade / ChapterLoadingAsyncLoad / ChapterLoadingOpen / EyeCatchStart / EyeCatchEnd   (chapter card)
  FairClearChapter
  Choice -> SaveMenu -> Choice     (the end-of-chapter save prompt)
  FairSetEventSkipForceMode(2)
MapJump(5057)                      <- Ch2 opening event (0x13C1); story_count becomes 2001 here
  CreateMap(0x15D) ...  MapJump(5058) ... FairStartAutoSave
```
- **MapJump target ids = the "map" value at `71B4EFC`**: 50xx are event scripts (5000 chapter end, 5057 Ch2 open, 5109 Ch3 open), and 1xxxx/2xxxx are field maps.
- **Single choke point:** native 015 MapJump (exe+1304D80) reads its target at exe+1304E06 and posts it via exe+1329A00 (call at exe+1304E0A). A hook there can redirect any jump. Test: `scripts/cheatengine/mapjump_gate_test.cea` redirects 5000 → 10502 when `mj_on` = 1 and logs the last 64 targets.
- **Test 1 (failed):** redirecting 5000 → 10502 hung forever on the loading screen (no crash). `mj_hits` = 1. Afterwards the readouts showed story 2001 / map 5057 although the 5000 script never ran, so the transition may be partly handled outside the script (TBD). 10502 (the field id seen at `71B4EFC`) is apparently not a valid MapJump destination. Next: log real field / mission-return MapJump targets with `mj_on` = 0 to find a valid "back to field" id.
- **Real choke point = exe+1329A00** `RequestJump(mgr, id, flag)` (forwards to exe+1327680 with `rcx = [exe+717A7C8]`). It has 7 callers: script MapJump native (flag 0); **mission start exe+13CCE50: id = 5500 + mission index**, flag 0; **mission return exe+13CCB10: id = [exe+71B4B98] (saved field id), flag 1**; plus exe+116EFC3, exe+1213EFA (×2) and exe+132A050 (TBD). The v1 hook on the MapJump native saw nothing during a mission round-trip because missions bypass it.
- **Capture (Beginnings round-trip from the Ch1 Mt. Tamblin save point):** start = `5591` (5500 + 91), flag 0, caller exe+13CCEDF. Return = `5015`, flag 1, caller exe+13CCB67. `[71B4B98]` = 5015 = **save-point scene id** (not the 10502 field id). Field save points are 50xx scenes entered with flag 1.
- Test 2: `mapjump_gate_test.cea` v2 hooks exe+1329A00, logs (id, flag, caller) and redirects 5000 → (5015, flag 1), exactly the mission-return request.
- **Test 2 result:** redirecting the chapter-end jump 5000 → (5015, flag 1) gave a black but skippable scene, then an endless load. The log shows no further jump requests after the redirect. By then story_count was already **2001** and the map value **5057** (set by the post-battle event 5019 *before* it jumps to 5000), but the chapter byte was still 1. **Conclusion: redirecting mid-event, after the story state has advanced, is not safe.**
- **Revised gate idea: gate the field→event entry instead.** Block the jump *into* the chapter's final event (Ch1: 5018 = Ifrit event, requested from the field while story = 1605) by turning it into the mission-return request (5015, flag 1). The player bounces back to the save point with an untouched field state, the same as returning from a mission. Release = stop redirecting. This needs a per-chapter "final event id" list (trace each chapter end) and the current save-point scene (`[71B4B98]`, valid after any mission). Test 3: `mj_from` = 5018.
- ✅ **Test 3 VERIFIED (chapter gate works):** with `mj_from` = 5018 → (5015, flag 1), walking into the Ifrit event bounced the player back to the Mt. Tamblin save point in a normal, playable state. After `mj_on` = 0, the Ifrit event started normally, and beating it led into Chapter 2 as usual. **Gate = block the field→final-event jump; release = stop blocking.**
- **Ch2 jump log** (Ch2 start → Ch3 card, `dumps/mapjump_hist.txt`): 5057 (opener), 5058, mission 5698 (5500 + 198) → return **5058 flag 1**, then 5063, 5059, 5061, 5062, 5050–5056, **5054 → 5000 → 5109** (Ch3 opener). Ch2 scenes are 5050–5063. **Tentative Ch2 final-event jump = 5054** (needs a gate test like Ch1). Save-point scene in the Ch2 hub = 5058.
- Scene-id map so far: chapter end 5000 · Ch1 5015 (Mt. Tamblin save point), 5018 (→ Ifrit), 5019 · Ch2 5050–5063 (5057 opener, 5058 hub save point) · Ch3 opener 5109 · missions 5500 + index.
- Gate follow-ups: (1) per-chapter final-event jump ids (trace each chapter end with the v2 hook's log: id, flag, caller, story_count); (2) the redirect target: `[71B4B98]` is **only** written when a mission starts. Touching 4 different save points through Ch2 left it at 5058. **Planned fix:** the gate hook tracks the *current scene* (the last RequestJump id it let through) and bounces the blocked final-event jump back to that scene with flag 1. In Ch1 that is 5015, which is exactly what worked; (3) implementation: it's a code hook, so it belongs in the helper DLL (phase 2). The pymem-only alpha can ship with chapters ungated (chapter clears as checks).
- Gate candidates (superseded): (a) redirect the chapter-end jump (5000) back to a field map with a save point while the next Chapter Key is missing, so the player can still do missions, and let it through once the key arrives; (b) redirect the next-chapter opener (5057, …). (a) is preferred because ChapterClear hasn't run yet.

### 7.3b Progression items (proposal)
**Missions:** unlock items, granularity as a YAML option:
- `per_set` (default): one item per mission set (e.g. "M2-1: Monsters in Midgar", about 50 items). Receiving it unlocks the set's first mission, and the vanilla f5 chain opens the rest. Missables stop being missable.
- `per_category`: 10 items (M1…M10). Small pool, big unlocks.
- `per_mission`: 300 items (chaos mode).
Implementation: the client writes `71B4330 + m*3` = 1, and vanilla chapter/NPC unlocks are suppressed by re-zeroing anything not yet received.

**Chapters:** progressive "Chapter Key" ×9 (Ch2–Ch10), **if** a clean hold point exists (investigating with `native_trace.cea`: ChapterClear → SaveMenu → ChapterLoading* → MapJump sequence). Fallback if no clean hold exists: chapters are not items. Chapter clears are checks, and logic places story locations by chapter reached (the story is always playable; missions and items carry progression).

**Goal options:** defeat Genesis (story_count reaches Ch10 end), and/or collect 7 Goddess Materia (key items 0x3053–0x3059, shuffled into the pool).

### 7.3d APWorld alpha (generates)
`apworld/ccff7r/` (packed: `apworld/ccff7r.apworld`). Options: goal (genesis / goddess_materia), chapter_gating, mission_unlocks (per_set / vanilla), mission_difficulty_logic (rank → chapter: 1-2→1, 3→3, 4→4, 5→5, 6→7, 7→8, 8→9, 9-10→10), max_mission_rank (no progression above it), exp_multiplier (client side, default 2).
Regions: Menu → Chapter 1..10 (Chapter n needs Progressive Chapter Key ×(n-1) when gating is on) and 52 mission-set regions (need "Mission Set Mx-y" when per_set). Victory = "Defeat Genesis" in Chapter 10 (+ all 7 Goddess Materia for that goal).
Tested with current Archipelago main (Oct 2026): `Generate.py` succeeds for both {genesis, no gating, vanilla missions, rank cap 6} and {goddess_materia, gating, per_set, rank cap 4}.
**Leveling:** level-ups only happen on a DMW 777, and the chance rises with accumulated EXP (IGN "How to Level Up"). The client multiplies EXP gains (Zack EXP = `char_status + 0x08`). Progressive Chapter Keys keep late chapters behind earlier ones, so players can't reach Ch9/10 under-levelled.
**Chapter select (Reunion):** replaying chapters lets players recover missed chests (good), but with gating on, the gate hook must also block chapter-select jumps into locked chapters (TBD: find the chapter-select jump ids/caller).

### 7.3e Client alpha (`apworld/ccff7r/client.py`, Launcher entry "CCFF7R Client")
Memory-only (pymem, bundled with Archipelago). Per tick: patch every location treasure to the count-0 placeholder (all items incl. own come from the server); read treasure bits + chapter byte → LocationChecks; apply received items (direct inventory/materia/gil/SP writes; Mission Set → unlock the set's first mission); per_set mode re-locks missions of sets not yet received; EXP multiplier; `/victory` sends the goal manually (Genesis-kill detection TBD). Applied-item index saved in `<AP user dir>/ccff7r/<seed>_<slot>.json`. "Mission Set M1-1" is precollected (1-1-1 is story-required). Offline-tested: `add_materia(0x4008)` produces the byte-identical record the game wrote for Thundaga; `add_item` stacks and ages correctly; full `Generate.py` output OK.

### 7.3f Chapter warp test (worked!)
On the Ch1 save at the Mt. Tamblin save point: story_count = 3000, chapter byte = 3, `71B4BD6..BDA` = 1, then the mission-start jump (5591) was redirected to the Ch3 opener (5109, flag 0). Result: the Ch3 opening cutscene and tutorial hints played, story went to 3001, and **the whole of Ch3 was completed normally**, through to the Ch3→Ch4 save prompt (story 4000, chapter byte 4, map 5150 = Ch4 opener).
Side effect: the game thought a mission was active (treasure counter icon, wrong waypoint), because we hijacked the *mission-start* path. That path (exe+13CCE50) first does:
- `[71B4B98] = [71B4B64]`: **`71B4B64` = current scene id** (copied as the mission-return target). → **use this as the gate's bounce-back target.**
- `u16 [71B4B9C] = mission index`: **active mission** (0xFFFF = none; the return path writes -1).
- `71B4331 + 3m = 0` (clears byte 1 of the mission record).
Fix for warps: after the redirect, write `u16 [71B4B9C] = 0xFFFF`, or trigger the warp from a non-mission jump.
Reunion has **no chapter select**, so an AP "chapter warp" would be our own feature: set story_count = N·1000, chapter byte = N, unlock groups, then RequestJump(opener_N, 0). Openers known: Ch2 5057, Ch3 5109, Ch4 5150.

### 7.3g Playtest 1 (Oct 16, full game, v0.1) and changes in v0.2
**Worked:** connect, placeholders, checks for ~140 locations, item delivery (all types incl. materia presets), chapter-clear checks, reconnects, game restart re-attach.
**Problems → fixes (v0.2):**
| Problem | Fix |
|---|---|
| Final door needs all 7 Goddess Materia even for the Genesis goal; tester had to cheat 6 | `Defeat Genesis` always requires all 7. Option `goddess_materia`: shuffled / vanilla |
| Only 2 mission sets found all game (51 set items in a 1,288-location pool) → most checks unreachable | New default `mission_unlocks: progressive_rank`: ranks ≤ `starting_mission_rank` (2) are open (109 checks); 8× "Progressive Mission Rank" raise the cap. `max_mission_rank` default 8 (rank 9-10 = post-game) |
| M1-4 (rank 6) opened in Ch2 → too hard | covered by rank mode; difficulty-by-chapter logic only binds when chapter gating is on |
| SOLDIER Outfit (treasure 427 = Shinra Manor drawer; openable in Ch8, outfit needed in Ch9) was opened in Ch8 and replaced → Ch9 softlock | Story-required treasures kept vanilla (not locations, not patched): 427 SOLDIER Outfit, 548 Laboratory Key, 549 Iron Bars Key, 178 Jail Cell Key, 471 Dresser Key (`data/treasure_overrides.csv`) |
| Ch2 timed "sparkle" treasures showed "Potion × 0" but never set a treasure bit (no check) | 65 story chests never seen in the playtest are now **unverified**: excluded (filler only) and left vanilla (not patched). Client logs every newly set treasure bit (listed or not) to `<AP>/ccff7r/treasure_log.txt` for mapping |
| Treasure 67 is Banora Factory Chest 2 (58 isn't) | renamed |
| 156/157 ("Jail Cells") are the Sector 5 kids' guessing-game prizes | renamed; 155-176 no longer called jail cells, unverified |
| Ch4 fusion-room chests (2) and Upper Junon Lv8 (2 of 5) gave no checks | probably ids outside the list (e.g. Reunion-only 1303-1321) → treasure log next run |
| Goal sent manually | auto: story_count ≥ 11000 (final boss done; credits start at scene 5950) |
| Launcher: "missing manifest" warning | `archipelago.json` (world_version 0.2.0) |

**story_count ≠ chapter × 1000 after Ch6:** Ch7 starts at 6500, Ch8 7000, Ch9 8000 (a 9000 phase inside Ch9), Ch10 10000, end 11000. **Use the chapter byte (`71B4BA4`) for chapters.**

**Scene table from `dumps/jump_log.txt`** (opener = first jump after 5000; final-chain = last field→event jumps before 5000):
| Ch | opener (story) | final chain before 5000 | gate candidate |
|---|---|---|---|
| prologue | 5900, 5901 | — | — |
| 1 | 5011 (1000) | 5015 → **5018** (1605) → 5019 | 5018 ✅ tested |
| 2 | 5057 (2001) | 5056 (2072) → 5054 (2090) | 5054 |
| 3 | 5109 (3000) | 5107 (3027) → 5106 (3034) | 5106 |
| 4 | 5150 (4000) | 5158 (4922) → 5156 (4941) | 5158 / 5156 |
| 5 | 5200 (5000) | 5213 (5111) → 5214 (5131) | 5214 |
| 6 | 5250 (6000) | 5255 → 5256 (6351) | 5256 |
| 7 | 5260 (6500) | 5272 → 5261 (6750) → 5264 (6752) | 5261 / 5264 |
| 8 | 5300 (7000) | 5306 → 5304 (7370) | 5304 |
| 9 | 5311 (8000) | 5405 (9060) → 5406 (9062) | 5405 |
| 10 | 5450 (10000) | 5460 → 5453 (10063) → 5463 (11000) → 5950 credits | (goal) |
Hub/other ids: missions 5500 + index; mission return = (scene at mission start, flag 1).

### 7.3h Minigame exclusion (v0.2.1)
YAML `excluded_minigames` (OptionSet; `["all"]` or any of: banora_missile, banora_sparkles, perfume_blending, materia_pickup, kids_guessing, wutai_spies, squats, flower_wagon, seven_wonders, sniper_zack, waterfall). Excluded minigame rewards are not locations, are not patched (vanilla reward), and their vanilla items leave the pool; the client gets the list as `skip_treasures` in slot_data. Mapping lives in `data/minigames.csv`. Known so far: squats 401-404, wutai_spies 398, flower_wagon 396/397/399/400, seven_wonders 409/410/413/414/424, kids_guessing 156/157. Seven Wonders #3 = 425 (**disputed**: tester's alternative theory is that 425 and 427, opened 8 s apart, are two more Mt. Nibel Trail chests (the IGN "Chest 2-3" label covers two chests, only 1318 is mapped), in which case wonder #3, like #5, sets no treasure bit. Resolve in the next run with the per-chest client log; opened between #2 and #4 in playtest 1; 427 SOLDIER Outfit opened 8 s later and stays vanilla), #5 = 426 (guess: done after Underground Cave Chest 3 but no check fired). Availability windows (tester): squats and Wutai spies Ch5–Ch8; Seven Wonders Ch8 → Ch9 (after escaping the Shinra Manor); #7 is missable once the story advances. **Still unmapped** (need the treasure log): banora_missile, banora_sparkles (likely in Ch2 55-64, already unverified/vanilla), perfume_blending, materia_pickup, sniper_zack, waterfall.

**Missables (v0.2.2):** story areas can't be revisited (no chapter select), so every story chest is missable once the story moves on. New option `missable_progression` (default off): story chests and minigame rewards never hold progression; progression goes to missions (always replayable) and chapter clears.

### 7.3i Playtest 2 (Oct 16-17, v0.2.3): tutorial + Ch1 + all rank 1-4 missions
- **Missions: perfect.** 94 missions cleared (rank 1: 13, 2: 30, 3: 22, 4: 28, 5: 1); all 94 rewards and all 183 in-mission chests fired, 0 missed, 0 stray.
- **Rank progression works:** all 8 Progressive Mission Ranks arrived during the rank 1-4 grind; all 7 Goddess Materia were in missions (missable_progression off). 290 items delivered with no errors; state file now per seed (`<seed>_<slot>_<name>.json`).
- **Ch1 story chests confirmed:** exactly 12 real chests: 23, 24, 26 (Mt. Tamblin, scene 5015), 29-35, 39, 1310. **25, 27, 28, 36, 37, 38 removed** (never opened in two full Ch1 clears). No unlisted treasure bits seen.
- Mail log: 39 ids so far (prologue 132-179, mission-clear mails during the grind, Ch1 story mails 26/37/138/167/170/172/181/182/227).
- `data/treasure_overrides.csv`: new action `remove`; fixed a broken (unquoted) row for 427.

### 7.3j Accessory slots + stable item ids (v0.2.5)
- Tested live: adding the **Backpack (0x3036) alone gives 4 accessory slots** (presence-based, no extra flag). Keychain (0x3035) = 3 slots (M7-2-2 reward), Backpack = M7-2-5 reward.
- Both are now **"Progressive Accessory Slot" ×2** (useful): the 1st received gives the Keychain, the 2nd the Backpack.
- **Item ids are now stable:** `data/item_ids.json` is an append-only name→id registry. New items get new ids, and removed items stay as receivable `legacy` entries (vanilla_count 0), so seeds generated with older versions keep working with newer clients. v0.2.4 → v0.2.5: 0 ids changed.

### 7.4 Open questions
- **254 story/field treasure IDs → map/area** (partially done in `data/story_treasures.csv`).
- Direct inventory write: does a hand-written record show correctly, sort and survive save/reload? Materia records (0x18 bytes) are more complex.
- ~~Placeholder for remote items~~: count-0 item verified. Open: choose the least confusing item name for the popup, or replace the text later via the DLL.
- Chapter gating mechanism: native-call tracer `scripts/cheatengine/native_trace.cea` + `dump_native_trace.lua` to capture the end-of-chapter script sequence. Note: story_count `71B4EF8` has **no direct code references** (no rip-relative access, no static pointer). It's probably an event-script global written by the VM through an index, so gating has to hook the chapter-transition natives, not the counter.
- `71B4BD6[0..9]` unlock-group flags (set by ChapterClear): shop tiers or DMW?
- 9-1-1 and 10-3-1 unlock source (no f5 predecessor).
- Notable key items for AP: Keychain/Backpack (accessory slots), wagon parts, summon key items, shop addresses (shopsanity), **Goddess Materia ×7 (3053–3059)**.
- Shops (`ShopIDget/Set`), DMW unlocks (`DmwEnableSlot`), materia fusion unlock (`EnableMateriaSynthesis`), mail record byte 2.

---

## 8. Files in this folder

| Path | Contents |
|---|---|
| `CCFF7R_AP_Research.md` | This document |
| `data/treasure_table_vanilla.csv` | All 1,322 treasure entries with vanilla contents (raw) |
| `data/treasure_table_named.csv` | Same, with item/materia names, preset stars/bonus, gil/SP amounts |
| `data/item_names.csv` | Verified item ID → name map (consumables, key items, accessories, materia) |
| `data/materia_presets.csv` | 0xCxxx preset materia table decoded |
| `data/missions.csv` | All 300 missions: reward treasure + chest treasures (with names), rank, raw fields |
| `scripts/cheatengine/dump_mission_data.lua` | Dumps mission table via widget addresses from logger F7 |
| `data/script_natives.tsv` | All 1,172 script natives: index, handler RVA, name |
| `scripts/cheatengine/giveitem_hook.cea` | GiveItem logging hook (code cave, no debugger) |
| `scripts/cheatengine/research_snippets.lua` | GiveItem test, native/state/VM dumpers, live check readers |
| `scripts/ue4ss/CCStoryLogger/` | UE4SS Lua logger (v3, safe) |
| `scripts/ue4ss/UE4SS-settings.ini` | Stable UE4SS settings for this game |
| `dumps/` | Raw memory dumps (put new dumps here) |

### 7.3k Banora Treasures minigame (playtest 2, v0.2.6)
- Ch2 Banora collect-the-items minigame: on reaching Angeal's house the game shows one "Collected items" popup built from treasure records 55-59 (Ether, Soma, X-Potion, Elixir, Phoenix Down), plus 1000 gil and a 500 gil PERFECT BONUS.
- The minigame reads the records but never sets their opened bits. With 58 patched, the popup showed "Potion x 0" and no check was sent.
- v0.2.6 keeps 55-64 vanilla and drops them as locations (60-64 is assumed to be the other reward tier). Locations go from 1282 to 1272.
- Possible future option: detect minigame completion by flag or achievement and send 55-59 as checks.

### 7.3l Mission rollback and the item canary (v0.2.7)
- Playtest 2 found that failing or quitting a mission rolls game state back to the mission start: inventory and treasure opened bits revert. Items the client gave during the mission (including chest items) disappeared. The client's `applied` counter had already moved past them, so they were never given again.
- Fix: a "canary" in 4 spare bytes at the end of the treasure-bit array, `treasure_bits+0xFC` (the highest real treasure id is 1321, which is byte 0xA5). Layout: magic `A5 7A` plus a u16 holding the number of received items applied to this game state. The client rewrites it after every item it gives.
- Because the canary lives in the treasure bits, the game saves and restores it together with the inventory. Each tick, if the canary is lower than `applied`, the state was rolled back (a failed mission or an older save loaded), so `applied` is reset to the canary value and the missing items are given again.
- If the magic is missing (a save from before v0.2.7), the client trusts the state file and writes the canary.
- Checks already sent stay sent. Re-opening a chest in a rolled-back mission still shows the placeholder, but its item is given back through the canary.
- treasure_log ignores bytes 0xFC and above.

### 7.3m Ch5 naming fixes (playtest 2, v0.2.8)
- 231 was mislabelled "Bathhouse - Chest 2". It is Modeo Ravine - North - Chest 3 (scene 5207, opened during the sneaking section).
- The real Bathhouse chests come from scenes 5210 and 5211: 239 Chest 1 (Ether), 242 Chest 2 (Dispel), 240 Chest 3 (Hi-Potion), 243 Chest 4 (Ether). 241 is the phone package. The boiler room is scene 5212 (244, 245).
- 1315, a Reunion-only chest (Soma), is in the Ch5 Bathhouse (scene 5210) and is now a location. That brings the total to 1273.
- The rollback canary was confirmed live: being caught while sneaking reloaded state, the client re-gave 2 items, and 229/231 were opened again.
- The client now only patches and sends chests that exist in the connected seed, so a newer apworld is safe to use with an older seed.

### 7.3n Mako Stone exchange labels + Reunion chests (playtest 2, v0.2.9)
- 327 had the "researcher exchange" label but is a Ch7 supply pod (scene 5267). It is now "Ch7 Supply Pod (scene 5267)".
- 328-333 really are the Mako Stone Researcher Exchange (Materia Room). They are renamed Exchange 1-6:
  - 328/329/330/332 were received in Ch2 (scene 5062) and 331 in Ch5 (scene 5219).
  - 333 (Regen) was never set, even though the user had turned in all six stones (8-2-1..6) and the researcher had no more scenes. One exchange is given without setting an opened bit (same as Banora 55-59), so from v0.2.11 on 333 is kept vanilla and is not a location.
- 1316 and 1317 (Reunion-only, Ether x2 / Soma x2) are in Ch6, scene 5253 (Junon, alongside 322-324). They are now locations, bringing the total to 1275.
- Open question: since about Ch3, NPC mission-givers still show their orange interact marker but don't respond. Seen so far: a woman on Sector 8 LOVELESS Ave, a man at the Sector 8 brick alley, a trooper in the Shinra HQ Exhibit Room, and a girl in the Sector 5 slums. Likely cause: the client pre-unlocks every mission up to the current rank, so the NPC's script branch ("unlock mission X") has nothing left to do, while the marker is driven by a different flag. Missions aren't affected (they're all reachable by rank). Still to check: whether any of these NPCs give mail or items.

### 7.3o Ch8 Nibelheim / Mt. Nibel fixes (playtest 2, v0.2.12)
- On the Mt. Nibel trail (scene 5307), 419 is Chest 1, 418 is Chest 2 and 417 is Chest 3. 418 was mislabelled "Shinra Manor - Basement Facility - Chest 1".
- That label now goes to 420 (Elixir), **confirmed in playtest 2** (scene 5311).
- 1318 (Reunion-only, Elixir) is **Shinra Manor - Chest 1** (confirmed in playtest 2).
- **Seven Wonders #3 is 411 (Safety Bit)**, set in scene 5300 after the Bombs / gold shard. 425 is not #3 and is back to an untagged "Treasure 425" (seen in playtest 1 after the trail).
- **Seven Wonders #5 gives no item** (confirmed in playtest 2: nothing in game and no bit set), so the minigame has 6 checks: 409, 410, 411, 424, 414 (#6, late Ch8) and 413 (#7, early Ch9). 426 (Lightning Ring) is no longer tagged as a wonder. It stays an unverified, unseen Ch8 chest.

### 7.3p Ch9 Shinra Manor (playtest 2, v0.2.15)
- 471 is Basement Facility - Chest 1: the Dresser Key the scientist has. It stays vanilla.
- 470 (1000 Gil) is Basement Facility - Chest 2. It is now verified.
- 425 (5000 Gil) is the Shinra Manor Wardrobe. It is moved to Ch9 for logic (it was Ch8 / "Seven Wonders #3?").
- 427 is the drawer holding the SOLDIER Outfit. It stays vanilla.
- 426 (Lightning Ring) is removed as a location. Guides list no Lightning Ring in Ch8/9, and it never appeared in either playtest. It is probably the unused reward record for Seven Wonders #5, which gives nothing. Ch8/9 is now fully mapped.
- **Zack sniper minigame (Ch9):** its rewards are 474-477 (Dragon Armlet, Gravity, Dash, Thundaga), handed out together without setting opened bits, the same pattern as Banora 55-59. 474-479 are kept vanilla (478/479, Thundara/Blizzara, are assumed to be the lower tier). The `sniper_zack` exclusion therefore has no locations to remove.
- So far, every minigame that hands out a batch reward ignores the opened bits. Detecting these would need a minigame-result flag. That's for later.

### 7.3q Ch9 Abandoned Reactor / Hills / waterfall (playtest 2, v0.2.18)
- Abandoned Mako Reactor (scene 5400): 503 is Chest 1, 504 Chest 2, 507 Chest 3 and 508 Chest 4.
- In the hills (scene 5401), 510 is Hills - Chest 1. It was mislabelled "Abandoned Mako Reactor - Chests 1-4". 509 is Hills - Chest 2.
- 517 (Remedy, scene 5403, opened together with Gongaga Outskirts 515/516/1319) was labelled "Hills - Chest 1". It is now Gongaga - Outskirts - Chest 1, which is a guess.
- Waterfall minigame:
  - The end popup shows "3000-gil bonus, Potion x0, Hi-Potion, X-Potion, Elixir".
  - 514 (Goblin Punch, the 10-chest prize) sets its bit, so it's a real check tagged `waterfall`. Its patched placeholder is the "Potion x0" line.
  - 511-513 are handed out without bits and are kept vanilla.
- Still unseen in Ch9: 505 (MAG Mako Stone) and 506 (2000 Gil).

### 7.3r Ch10 (playtest 2, v0.2.19)
- Cage of Binding (scene 5456):
  - 557-562 are Chests 1-4, 6 and 7, and 1320 is Chest 5.
  - 548 is the Laboratory room chest holding the Laboratory Key. It stays vanilla.
- Howling Fang (scene 5461):
  - 568 is Chest 1, 567 Chest 2, 563 Chest 3, 564 Chest 4, 565 Chest 6 and 566 Chest 7. 563/564 are now verified.
  - 549 is Chest 8 with the Iron Bars Key. It stays vanilla.
- 1308 (Flare) is Howling Fang - Chest 10 (named by the user). It had been mismatched to "Chest 7", which is 566.
- Goddess materia in scenes 5454/5455: 550, 551, 553, 554, 555 and 556 were seen. 552 (Ground) hasn't been seen yet.
- The goddess materia locations are now named by materia, e.g. "Ch10 Banora Underground - Goddess Materia (Light)".

### 7.3s Minigame prizes via TreasureGetId hook (v0.2.20)
- The CE dump of the Banora treasures prize (`scripts/cheatengine/treasure_read_logger.cea`, `dumps/treasure_read_log_105136.txt`) shows the sequence: `AddGil 1500` (perfect bonus), then for each prize `AddMultipleMes`, `TreasureGetId(t)`, `TreasureGetAmount(t)` and `AddItem(amount, id)`, for t = 55..59.
- **`TreasureEnable` is never called**, which is why the opened bits stay 0. The VM stack top at the call site is the treasure id.
- Client (`game/readhook.py`):
  - Hooks the VM call-native site `VM_CallNativeSite` (exe+13BEF86, `48 63 C2 49 8B 04 C0`) with a 5-byte jmp to a cave allocated within ±2 GB.
  - On native 254, the cave appends the top stack value (u16) to a 256-entry ring: magic `APTRHOOK` at cave+0x100, u32 count at +0x108, entries at +0x110.
  - Each tick, the client polls the ring and sends a check for any treasure marked `detect: read`.
  - It re-adopts its own hook after a client restart and re-hooks if a CE script restored the original bytes. While another hook is on the site (for example the CE logger), it pauses.
  - The cave was verified in a unicorn emulation: registers preserved, stack balanced, only native 254 logged.
- Data: override action `read` creates a normal (patched) location with `detect: read`.
  - 55-59 are now "Ch2 Banora Treasures Prize - <item>" and tagged with the new minigame key `banora_treasures`.
  - 60-64 stay vanilla until we know what they are.
- Next: sniper (474-477) and waterfall (511-513) dumps, which are expected to show the same pattern.
- **Sniper dump:** with 0 enemies escaped, the prize reads 474-477 via TreasureGetId plus AddItem, and never calls TreasureEnable. It also calls `AddItem(-1, 0x3048)` to remove the minigame's key item. 474-477 are now read-detected locations tagged `sniper_zack`. 478/479 stay vanilla (presumably the prize when enemies escape).
- **Waterfall dump:** this was a failed run with 8 of 10 chests:
  - AddGil 2400 (scaled by chests found), then 511-513 via TreasureGetId plus AddItem, given even on failure.
  - The script then calls `TreasureEnable(id, 0)` for 511-513, which **clears** those bits. So TreasureEnable's arguments are (id, flag), with the flag on top of the stack.
  - 511-513 are now read-detected locations tagged `waterfall`. 514 (all 10 chests) still uses its opened bit.

### 7.3t Multiworld playtest 3 (v0.2.21 → v0.2.22)
- A full multiworld run completed: items flowed both ways, the goal was sent, and the read-detected minigame prizes worked. Three treasures were opened that weren't locations:
  - **333** (Mako Stone Researcher Exchange 6) **does** set its bit. It was set in Ch2 scene 5062 right after 332, between handing in the stones and talking to Tseng. Playtest 2 probably never triggered the 6th exchange. It is a location again.
  - **1313/1314** (Reunion-only, Ether/Soma) are in Ch4 scene 5155 (story 4560). They are now locations "Ch4 Reunion Chest 1/2 (scene 5155)" until we have better names.
- Genji set: only the Genji Glove (treasure 1287) is in the treasure table, and the other three pieces aren't in any chest or mission reward. **Genji Helm/Armor/Shield** (0x5066-0x5068) are now added to the pool as extra useful items, each replacing one filler.
- **Ch4 jail cells (scene 5159): 160-177 = 18 chests**, all seen in playtest 3. They were unverified. They are now "Ch4 Jail Cells - Chest 1..18".
  - The cell keys have to be stolen from the guards, so these locations require Steal or Mug materia (`Steal`, `Steal (1* AP+1)`, `Mug (1* AP+2)`, now progression).
  - One `Steal` is forced into this world's sphere 1 via `local_early_items`, because story areas can't be revisited.
  - 158 (Ch4 scene 5151) is verified too.

### 7.3u Chapter gating, chapter select, DeathLink, shop logger (v0.3.0)
- **Generic cave hooks** (`game/cavehook.py`): 7-byte `jmp` + 2 nops at a site, with an RWX cave within ±2 GB.
  - Layout: code at 0, u64 slot at 0xF0, return address at 0xF8, magic at 0x100, data from 0x108.
  - A restarted client re-adopts its own cave. A foreign hook (CE) means "paused".
  - `readhook.py` now subclasses it, keeping its original cave (it returns via 0xF0).
- **Jump hook** (`game/jumphook.py`): sits on RequestJump (exe+1329A00, first instruction `mov rcx,[jump_mgr_ptr]`, re-executed from the cave with the pointer at 0xF0). Data: gate_from/gate_to, a one-shot warp_to, warp_hits/src, gate_hits, last_id, count. Verified in unicorn: gate redirect, warp only on mission-start ids 5500-5799, one-shot, registers and stack preserved.
- **Chapter gating** (option `chapter_gating`, client side now live):
  - When the chapter byte = n, Progressive Chapter Keys < n and story_count ≥ the chapter's final-jump story value, the final field→event jump (`CHAPTER_GATE`) is redirected to (current scene `71B4B64`, flag 1). This is the Ch1-tested mechanism.
  - Gate ids Ch2-9 come from the playtest jump log and **need an in-game check**: 5054, 5106, 5158, 5214, 5256, 5261, 5304, 5405.
- **Chapter select** `/warp <n>` (replay included):
  - Allowed chapters: 1..max(furthest chapter reached, keys+1 if gating). The furthest chapter is kept in the client state file.
  - Arming sets warp_to = opener(n). The next mission start is replaced by (opener, flag 0).
  - The client then writes story_count = chapter start, chapter byte = n, unlock groups of cleared chapters (never cleared again), and active mission = 0xFFFF, and restores the hijacked mission's record byte 1. This is the same recipe as the 7.3f warp test.
  - Chapter starts: 1:5011/1000, 2:5057/2000, 3:5109/3000, 4:5150/4000, 5:5200/5000, 6:5250/6000, 7:5260/6500, 8:5300/7000, 9:5311/8000, 10:5450/10000.
  - **Replaying earlier chapters is untested** (story flags beyond story_count may not rewind).
- **DeathLink** (option `death_link`): Zack's **in-battle HP is static at exe+718DC28** (u32, found by the user). Writing 0 there kills him, while writing 0 to the menu copy `char_status+0x10` does nothing (in-battle 799 vs menu 805). The client now uses exe+718DC28 (RVA only, no signature yet). Original notes:
  - Zack's HP is `char_status+0x10`. HP going >0 → 0 sends a death. A received death writes HP = 0, followed by a 10 s grace period with no echo.
  - Still to check: does +0x10 update live in battle, and does writing 0 kill Zack?
- **Shop logger** (`scripts/cheatengine/shop_logger.cea` + `shop_dump.lua`): GiveItem hook that logs every call (id, count, return address, caller callee-saved registers). For shop purchases (return exe+12B9222) it hex-dumps 0x100 bytes at each register pointer.
- DeathLink receive, v0.3.2: writing 0 to the battle HP **doesn't kill instantly**. The game only checks for death when Zack takes damage, so HP just shows 0 until the next hit. The client now holds battle HP at 0 for 30 s after a received death, which makes the next hit fatal (including the first hit of a battle that starts within that window). Deaths are not sent during that window plus 10 s.
- In-game DeathLink tests: at battle HP 0, **using an Ether kills Zack, but healing doesn't**. HP -1 shows as a huge number (unsigned display) and he dies to the next hit. So death is checked on damage and on some item uses, not every frame. v0.3.2's "hold at 0 for 30 s" fits this: heals get overwritten back to 0, and the next hit or item use is fatal. The client writes 0, never -1.

### 7.3v Battle internals from the module dump (v0.3.3)
`scripts/cheatengine/dump_module.lua` saves the mapped image to `dumps/module_image.bin` (130 MB). All existing signatures resolve on it with no problems.
- **Battle actors:** `GetBattleActor(i)` exe+1370510 = `exe+718DA40 + i*0x740` (32 slots). Zack = actor 0. **HP i32 at +0x1E8** (= exe+718DC28, the address the user found). Flags at +0x24A (mask 0x11 is checked by the game-over test).
- **SetBattleFinish(side, type)** exe+1378BA0: if `byte [717AD52]` (battle active) and `dword [717AD5C] == 3` (fighting), then state = 4, `byte [717AD55] = side`, `dword [717AD64] = type`.
  - `BtlSetFinishGameOver` (native 1E5) = SetBattleFinish(0, 3).
  - `FairCloudBtlSetFinishGameOver` uses type 4.
  - `FairIsGameOver` = actor0 HP ≤ 0 or (flags & 0x11).
- New signatures: `battle_actors`, `battle_active`, `battle_state`. Derived: battle_hp = actors + 0x1E8, finish side = active + 3, finish type = active + 0x12.
- **DeathLink v0.3.3:**
  - A received death waits for a running battle (state 3), then writes HP 0, side 0, type 3 and state 4, i.e. what BtlSetFinishGameOver does. The result is an instant game over.
  - Sending: actor-0 HP goes from >0 to ≤0 while in battle (state 3/4), with 10 s of no echo after a received death.
  - The 30 s "hold HP at 0" approach is gone.
  - Test: `scripts/cheatengine/deathlink_test.lua`.
- **Correction / v0.3.4:** `byte [717AD52]` is not "battle active". It was 0 in a running mission battle while state was 3. It acts as a "battle may end through SetBattleFinish" switch, so BtlSetFinishGameOver does nothing in such battles. (1376DF0 ends a battle with type 5 ignoring that switch, but it's the retreat/give-up path, called from a menu handler at 132837D.)
- **Verified kill:** in a mission battle, actor-0 HP = 0 **plus flags |= 0x01** (`exe+718DC8A`) kills Zack instantly, giving the normal death and failure flow.
- DeathLink v0.3.4:
  - Receive: wait for battle state 3 and an alive Zack, then write HP 0 and flags |= 0x01.
  - Send: Zack goes from alive to dead (HP ≤ 0 or flags & 0x11) while state is 3/4, with 10 s of no echo.
  - Signature-derived `battle_flags` = battle_actors + 0x24A.
- flag1 kill also verified in a story boss fight (Ch1 Ifrit). Confirmed so far for mission battles and story/boss battles.
- flag1 kill also verified in a random field encounter. Confirmed for all battle types tested (mission, story boss, random encounter).
- **Chapter select test (v0.3.4):** warps to every chapter work, including going backwards (10 → 1 plays normally), **except Ch2**, which hung on the loading screen. Cause: the jump log shows Ch2's opener 5057 is entered with **story 2001**. The Ch1 post-Ifrit event sets 2001 before the 5000 chapter-end script, while every other opener is entered at exactly N×1000. 5057 is also an ordinary Ch2 hub scene, so with story 2000 nothing matches and the load never finishes. Fixed in v0.3.5: Ch2 warps set story 2001.

### 7.3w Shops (shop logger run + module dump)
- Shop log (`dumps/shop_log_210536.txt`), 3 shops:
  - Buys return to exe+12B9222: Ether 0x2003, 0x2004, and materia 0xC074, 0xC077, 0xC01C, 0xC01D.
  - **Sells use a separate call, returning to exe+12B92A8** (negative count).
  - The caller registers point at UE widgets (heap), so on their own they don't help.
- **Shop widget** (buy/sell handler exe+12B9190): buy list TArray at +0x330 (40-byte entries, u16 item at +0), selected index +0x2EC, quantity +0x300, total price +0x2FC (gil subtracted via exe+13AD6D0(-price)). Sell list at +0x348, count +0x340, index +0x2F0.
- **Shop stock table:** the list builder exe+12B8EA0 takes the current shop id from widget +0x318[+0x2E8].
  - If `id>>12 == [71AADB8]` and `(id & 0xFFF) < [71AADD0]`, the record is `[71AADC8] + (id & 0xFFF) * 36`.
  - Record = u32 header + **16 × u16 item ids** (0-terminated).
  - The container header has the same layout as the inventory containers (category, base, data ptr, count). Count = 17 shops.
  - Price comes from item data (1394A10 / 13966A0).
- Next: a live dump with `scripts/cheatengine/dump_shops.lua` gives `dumps/shops.txt`/`.bin`. Then map shop ids to the shop-address key items and decide the shopsanity design (rewrite stock slots, detect purchases at exe+12B921D).
- **Live shop table** (`dumps/shops.txt`/`.bin`, named in `data/shops.csv`): 17 shops with 130 stock slots in total. Record header = shop index. Highlights:
  - Shop 0: Potion/Ether/Soma/Remedy.
  - Shops 1/2/5/6/7/8/11/12: materia, as presets 0xC0xx.
  - Shops 3/4/9/10/13/14: accessories.
  - Shop 15: Precious Watch, Jeweled Ring, Apocalypse, Dualcast, **Genji Helm**. Shop 16 = shop 15 without the Genji Helm.
  - There are 15 shop-address key items (0x3026-0x3034). The shop index ↔ address mapping is still TBD (shop 0 is probably the default shop).

### 7.3x Shopsanity (v0.4.0)
- Shop names (from the user's list) are mapped to stock-table indices in `data/shop_names.csv`. Order: 0 Shinra Shop (always open), then 1..15 = the shop-address key items 0x3026..0x3034 in id order: Sec.8 Materia, Sec.5 Materia, Sec.6 Accessory, Sec.7, QMC, QMC+, Happy Turtle, Wutai Secret, Gongaga Trading, Nibel Accessories, Junon Souvenirs, Bone Village Outlet, Mythril Mine Trading, Online Shop Duo, Online Shop Shade. Index 16 is a Shade variant. **This mapping is inferred from the stock, so verify it in game.**
- Option `shop_slots` (0-16, default 0 = off): the first N stock slots of shops 0-15 become locations "Shop <name> - Slot k" (126 in total at 16). Each slot's vanilla item joins the pool. A shop region needs its address, and addresses become progression when shopsanity is on. The Sec.6 Accessory Shop Address had no source, so it was added as an extra pool item.
- Client: `ShopHook` (`game/shophook.py`) on the buy path at exe+12B9201 (`movsxd rax,[rdi+2EC]`; signature "ShopBuySite", hook-tolerant). It logs (shop id from widget +0x318[+0x2E8], slot +0x2EC, qty +0x300). A purchase from an AP slot sends the check, and the player still receives the vanilla item. Shop 16 maps onto 15. The cave was verified in unicorn.
- `/shops [filter]` lists each AP slot's scouted item (LocationScouts with no hint on connect).
- v0.4.1: with shopsanity on, extra **Gold Rolling Pins** (sold for gil) replace filler: ceil(shop locations / 16), so +3 at 3 slots and +8 at 16 slots (7 vanilla → 10 / 15).
- **Shopsanity verified in game (v0.4.1):** Shinra Shop and The Happy Turtle, first 3 slots of each sent checks, and the client named both shops correctly (The Happy Turtle = index 7 = address 0x302C). This supports the inferred index↔address mapping. Shop UI text still shows the vanilla items; `/shops` lists the AP contents.

### 7.3y PopTracker pack (map-less, v0.1.0)
- Built by `apworld_build/build_poptracker.py` into `poptracker/` and `ccff7r_poptracker.zip`.
- 21 generated "list maps", one row and pin per location: Story Ch1-10, Missions M1-M10 (one pin per mission, with reward and chests as sections), and Shops.
- Items: 7 Goddess Materia, Rank, Chapter Key, Accessory Slot, Steal/Mug, 15 shop addresses, and the mission sets (hidden, used for per_set). 80 AP item ids are mapped.
- All 1405 locations are mapped for AP autotracking (`scripts/autotracking.lua`, variant flag `ap`).
- Logic mirrors the apworld: chapter keys (gating), mission rank / set / difficulty→chapter, Steal for the jail cells, shop addresses.
- Settings come from slot_data: mission_unlocks, starting_mission_rank, chapter_gating, mission_difficulty_logic (added to slot_data in v0.4.2), shop_slots, skip_treasures.
- Shop slots beyond `shop_slots` and skipped minigames are hidden through visibility rules.
- Lua and handlers were checked under lupa with a mocked Tracker. Not yet loaded in real PopTracker.

### 7.3z Pak AES key
- The .pak/.utoc containers are encrypted. AES-256 key, found in the module dump (key callback at exe+14486A0) and verified by decrypting the pakchunk2 index (mount point "../../../"):
  `0x277041CBB2888087611DB5CBFEA119462920E1F67092C87E87825725E38B320F`
- FModel: Directory > AES, paste the key, then load all archives.

### 5.5.1 Mail table (data/mails.csv, 2026-10-23)
- All 102 mails mapped to internal IDs (wiki subject/sender, chapter of first receipt from the mail log, trigger).
- Unused IDs: 8, 15, 17, 23, 105, 106 (no script ever adds them). 0, 25, 37 come from the mail tutorial (native code); every other ID has a MailAdd in the Atel scripts.
- 107 = Kunsel "A SOLDIER legend, so they say", added after mission 9-6-6 (index 199, Minerva).
- Blocks: Kunsel 0-18 + 107, Luxiere 19-24, Shinra News 25-36, Lazard 37-41, Friends 42-49 (+ Cissnei hint 78), Reporter 50/52-57, Wonder Hunter 51, Keepers 58-63, Genesis clubs 64-74, Silver Elite 75-77, Zack Fan Club 79-83, Treasure Princess/Anonymous/Yuffie 84-101, Shop News 102-104. Inside a block the IDs follow the game's chronology, not the wiki order.
- Fan club joins are Choice branches in scripts 19 (Keepers, Red Leather) and 20 (Study Group). Zack Fan Club endings 81/82/83 are mutually exclusive.
- kind: story 54 (auto-delivered by story progress), optional 27 (fan clubs, Wonder Hunter, Cissnei hint: missable), mission 21.
- Rows with verify=yes were placed by timing/script context only.

### 7.3aa v0.6.0 options (2026-10-23): DMW characters, DMW memories, Magic Pot, proficiency, mailsanity
- New location ids (LOC_BASE 0xCCF70000): +0x40000+slot DMW joins, +0x40010+char*6+n memories, +0x40050 Magic Pot,
  +0x40060+k proficiency k*10%, +0x40100+mail id mails (81 covers 81-83). Existing ids unchanged. New items: DMW: <char> x7, Magic Pot Tricks.
- DMW slot writes only come from script native 25B (setter exe+13CEA70, callers: native wrapper exe+131A8E8 only). Client keeps unreceived
  slots at 0; a 0->1 it didn't cause = the story unlock = check. Fallback: check also sent once the unlock chapter is cleared
  (PowerPyx: Seph/Angeal/Aerith Ch1, Tseng Ch2, Cissnei Ch3, Cloud/Genesis Ch5).
- Movie flags exe+71B4BB0[char*6+n] (38 bytes) = memories made available by story scripts (DmwEnableMovie 25D; chars 0-4, n 0-4 seen in scripts).
  The reel (exe+1204380..) picks an available memory and records it as watched via exe+13AE280(0, byte, bit, 1):
  **watched = char_status(exe+71B3F00)+0x168 + byte, bit n (byte <= 6, bit <= 5)**. Byte/bit mapping goes through a reel table not yet
  read, so memory checks are counted per byte (Memory k = k memories watched). Needs a live check that byte c = DMW slot c.
- Magic Pot: battle drop path exe+138962E special-cases item 0x3025. Client: vanilla copy removed until the AP item is received; if the AP item
  is already owned, it's held out of the inventory while active_mission == 238 (10-2-3) so the drop can be seen.
- Proficiency: obj signature `48 8D 05 ?? ?? ?? ?? C3 CC*8 48 83 EC 28 E8 97 E8 FF` (exe+718D9B0); goal table [[exe+717AE08]+0xD8], 12-byte rows,
  u32 goal at +4 (exe+1106A90). Client formula = HUD formula, each stance part clamped 0..1. `/proficiency` prints it.
- Mailsanity polls the mail list; client also delivers mail 107 after 9-6-6 (mission 199) like the other mission mails.

### 7.3ab Chapter gate timing (v0.6.3)
- Tester (Ch2): the "end of Chapter 2 is locked" message appeared but the ending still played. The Ch2 ending scripts set story 2072 -> 2090 and jump to 5054 within one client poll (0.5 s), so a gate armed at story >= 2090 comes too late.
- Gates now sit on the jump out of the chapter's last free field, armed with the story value held while standing in that field (the value logged on the jump into it): Ch1 5018@1402, Ch2 5056@2071, Ch3 5106@3027, Ch4 5158@4550, Ch5 5214@5111, Ch6 5256@6302, Ch7 5261@6702, Ch8 5306@7320 (from the reactor field 5310), Ch9 5405@9060. Each gate scene is jumped to only once in its chapter after its arm value (jump log check). Ch2-9 still need an in-game check.

### 7.3ac v0.6.4: wagon parts randomized, NPC mission handouts (tester feedback 2026-10-24)
- **Wagon parts:** the 8 better parts (treasures 397-404: Craftsman Monthly/Walnut Wood/Premium Tires/Mythril Tools + the 4 squat parts) are no longer locked. The 4 cheap Ch7 parts (405-408) stay locked, so the Ch7 wagon can always be built.
  - Categories by item id: 3038/303C/3040 manual, 3039/303D/3041 wood, 303A/303E/3042 tires, 303B/303F/3043 tools. Givers per category: manual 397+401, wood 398+402, tires 399+403, tools 400+404.
  - Client: a received better part is held out of the inventory until every unchecked giver of its category is checked, or chapter byte >= 9. Handed-over flags live in treasure bits 2000-2007 (byte +0xFA), which are saved and rolled back with the game.
  - Gated on slot_data `wagon_random`, so older seeds keep the locked behavior.
- **NPC mission handouts** (option `npc_mission_checks`): 16 locations at LOC_BASE+0x40400+mission. The script native MissionSet (0x256) takes the mission on top of the stack.
  - The VM hook cave is now `APTRHK02`. It logs 0x254 treasure ids and 0x256 missions|0x8000 into the same ring (unicorn-verified). The old `APTRHOOK` cave is unhooked and replaced on attach.
  - In non-vanilla modes the client keeps a pending NPC mission locked until its handout is seen (or chapter byte >= 8), because NPCs don't respond to missions that are already unlocked (7.3n open question).
  - Logic: an NPC mission's checks also need its handout chapter. 2-1-6's handout needs 2-1-1..2-1-5. Spies 4-3-2..6 need 4-3-1's handout.
- **No-item minigames (tester):** banora_missile, perfume_blending and materia_pickup/Godspeed give no items in vanilla, so there are no checks to map.
- v0.6.5 (user): no Ch8 cutoff for held NPC missions; a missed NPC is reached again with /warp. `/npcmissions` lists open handouts, `/npcmissions release` stops holding for the session (escape hatch while chapter replay is untested).

### 7.3ad v0.6.6 (tester notes on v0.6.2 run, 2026-10-25)
- `/maillist` (client): mail list in stored order + apworld names -> mail_order.txt. Tester says the Ch7 Shinra News check names don't match the mails received (IDs 32-35 were placed by wiki order; the first-receipt order in our log is 34, 32, 35, 33). Resolve with /maillist vs the in-game Mail menu, or the mail DataTable/locres from FModel.
- New option `dmw_starting_characters` (default 2, random): tester with only Tseng (+ Moogle/Phoenix summons) never got a limit, mode or summon. Hypothesis: the reel needs at least 2 character portraits. Not verified yet (CE test: close the client, set a 2nd slot byte at 71B4BA8+n to 1).
- Not bugs: mail 107 (9-6-6, rank 10) already never holds progression at the default Max Progression Rank 8 and is skipped below Max Mission Rank 10. The 3 Black Cowls are vanilla (2-5-5, 7-3-1, 9-3-3).
- Open: Ch7 wagon. Zack force-walked after leaving the church, the ground part outside the church was not visible, and Aerith accepted a "???" part. This suggests the wagon can be finished without all parts, so the cheap Ch7 parts may not need to stay locked. Need the tester's treasure_log.txt.
- Ideas logged: wagon hand-in scene as a check; shopsanity marker in item names (needs the name-editing work).
- v0.6.7 (user): the Ch7 pickup scene (outside the church) force-walks Zack if you already own the part being picked up; reloading the autosave fixes it. The wagon groups sent the cheap parts 405-408 together with 397-400, so the server delivered them early. The client now holds received cheap parts (3040-3043) until that pickup's own treasure bit (405-408) is set, or chapter byte >= 8. Flags in treasure byte +0xFB: bits 0-3 held, 4-7 handed over. This applies to every seed.
- PopTracker 0.3.5 (user, M10-2-3 red and not clearing): two pack bugs.
  - (1) location_mapping.lua had an unescaped quote from the mail subject `Thoughts on "the gift of the goddess"`, so the whole autotracking script failed to load (since pack 0.3.0). Nothing cleared and SLOT kept its defaults. Lua strings are now escaped.
  - (2) logic count() used `AcquiredCount or Active`, and toggles have AcquiredCount 0, so every toggle (mission sets, shop addresses, Steal, DMW) counted as 0. It now uses Tracker:ProviderCountForCode.
  - Both were verified by running the pack's scripts in a Lua runtime with a fake Tracker (strict `load()` syntax check + clear/item/location handlers).

### 7.3ae v0.6.8: Proficiency Boost items (user)
- 3 items: "Proficiency Boost: Perfect Guard / Command Kill / Strong Attack Kill". Payload {type: proficiency, part 0-2, fraction 0.25}. Each adds 25% of that stance value's range: Block +5 (7.5%), Command +25 (6.25%), Sword +50 (6.25%), clamped at the end value.
- Option `proficiency_boosts` (0-4 of each kind, default 2, i.e. 6 items, 40% of the meter). Independent of the proficiency checks option.
- Client: applied from Ch6 once a value is at or above its start (80/200/100). Applied counts are in treasure bytes +0xF8/+0xF9 (4 bits per part), so a rollback re-applies them. The unlisted-treasure logger now ignores bytes >= 0xF8.

### 7.3af Shop menu names (v0.6.9)
- **Name path (module dump):**
  - The buy-list builder exe+12B8EA0 fills 40-byte entries {+0 id, +4 owned, +8 1395DA0(id), +C price, +10 FString name, +20 flag, +24}.
  - The name comes from `call GetItemName` at exe+12B8FD6. GetItemName is exe+120E070(id, FString*).
  - GetItemName gets the item text via exe+1395F90. That function switches on the category; consumables use def table [71AAE30] (0x60-byte rows, u32 text id at +0) and the message file at [71B83C8].
  - The text is then decoded by exe+120D900(msg, page, FString*, float*).
- **Row widget:** UUIShopItemList::SetRow exe+12BAFA0(name FText, price, count, ...). Widgets: +318 Text_Shop_Itemlist_1, +320 num_money, +328 num.
- **Message format:**
  - u32 page count, then per page {u32 units, u32 byte offset}, then u32 units.
  - 0x80|(UTF-16<<16) = a plain character. 0x40 = a tag (type in byte 1). 0x41 = a special glyph (< 0x118).
  - Message file: offset table at base + (n*11 + 2 + lang)*4, then base + table[id].
- **Hook** (`game/shopnamehook.py`):
  - Redirects only that call site. The cave keys on (stock index from widget [r13+318]+[r13+2E8]*4, item id). On a hit it decodes our message into the row's FString; otherwise it tail-jumps to the original. Unicorn-verified.
  - Client: each unbought AP slot shows "<vanilla> * <AP item> (<player>)". Shop 15 entries are mirrored to 16. `/shopnames on|off`.
  - Untested in game: the font's support for non-ASCII, the column width, and whether the list rebuilds after a purchase.
- **Verified in game (user, v0.6.9):** the Shinra Shop buy list shows "Potion * Courage Boost! (1* MP+2)" etc. The text fits the column at this length. After a purchase the row keeps the AP text until you leave the shop, and the plain name is back on the next visit, because the list is only rebuilt when the shop opens. Note: a slot whose item you already hold 99 of is greyed out (can't be bought), so its check needs you to use or sell one first.
- Dropped idea (user): Shinra Manor keys. Enemies in the manor drop them endlessly, and they only gate Seven Wonders #5 (Vincent's room), so shuffling them adds nothing.

### 7.3ag Game text found: PSP `system.bin` (2026-10-25)
- `fmode_export/PSP/Discimg/system.bin` holds all the game text in the same message format the PC build decodes (u32 pages / {units, offset} / u32 units, char = 0x80|UTF-16<<16). Each record is [message][UTF-16 key]: a message belongs to the key that FOLLOWS it. All languages are included. The header is a u32 count of 23 sub-files followed by a table (layout not decoded yet).
- **Mail keys** are `mail_<sender>_txt_NN_title/_description`. Sender blocks in internal-ID order: 2ndA (Kunsel) 19, 2ndB (Luxiere) 6, nwes 12, lazard 5, cloud 3, tifa 3, cissnei 2, kisha 8 (kisha_02 = The Last Wonder), ange 6, gene 11, sephi 3, zack 6 (zack_01 = Cissnei's hint), yuffie 18 (84-101), urban 6 (102-104 Shop News, 105/106 empty, 107 = "A SOLDIER legend").
  - Internal ID = running index over these keys, holes included. The empty keys are exactly the unused IDs 8, 15, 17, 23, 105, 106.
- **mails.csv corrected from the game text** (all rows are now confirmed, `verify` cleared, new `game_key` column):
  - Kunsel 3 = "Went to see LOVELESS", 4 = "Angel in white?" (they were swapped; this was the tester's Kunsel-order report).
  - Shinra News 28 = PA0103, 29 = President's declaration, 32 = Space development report, 33 = Budget report, 34 = PA0207, 35 = Analysis of the simultaneous attacks (this was the tester's Ch7 Shinra News report).
  - Small spelling fixes.
  - Location IDs are unchanged; only these check names changed.
- `data/mail_text_en.json`: English subject + body per mail key. `data/game_text_en.json`: a heuristic English dump of all keys (6.6k: menu, mission, MATERIA, ITEM, Tips, ...), for future names.
- v0.6.11 (multiworld test): a 44-character row ('Soma * Progressive Chun-Li (DudeWheresMyCar)') ran into the Gil column. Rows are now capped at about 36 characters. The item name has priority and the player name gets 6-12 characters, cut with a '.'.
- v0.6.12 (user): shop rows drop the vanilla item name and show '* <AP item> (<player>)'. The vanilla name comes back after purchase, since the list is rebuilt when the shop next opens.
- v0.6.13 (tester: a boost during battle didn't show; client said 9.21%, HUD 1.83%):
  - HUD formula exe+11F1730 takes (table, battle actor, static obj). With an actor it reads actor +0x228/+0x230/+0x238 (Block/Command/Sword) and +0x240.. (counts); without one it reads the static obj via exe+11069F0. So battles run on a copy, and a mid-battle write to the static obj is presumably lost when the copy is written back.
  - Boosts are now applied only outside battle (battle_active == 0 and state not 3/4).
  - Each write is watched through the next battle. If the value comes back lower, the applied count is decremented and the boost re-applied.
  - `/proficiency` shows the raw values and applied counts; `/proficiency reapply` clears the applied counts.
- v0.6.14 (tester): '/proficiency reapply' applied nothing because battle_active (exe+717AD52) stays set in the field. in_battle now uses only battle_state in (3,4), the same check DeathLink uses. /proficiency also prints chapter, battle state and active.
- Verified (user, v0.6.14): a boost applied out of battle persists through a finished mission fight and a reload. Forfeiting a mission rolls the meter back to its mission-start value (same rollback as inventory and treasure bits). The applied counts live in the same save block, so they roll back with it and the client applies the boost again out of battle.
- v0.6.15 (user): option gil_multiplier (1-10, default 1). Only battle gil is multiplied: gains while battle_state is 3/4 or within 8 s after. It is checked at the start of each tick against the gil seen at the end of the last tick, so AP gil items and selling are never multiplied.
- v0.6.16 (user): 'Shop Online Shop Shade - Slot 5' (Genji Helm, 1,000,000 gil) never holds progression (EXPENSIVE_SHOP_ITEMS).
- Pack 0.3.7 (user: 1-2-6 red while playable): mission rules are now "$mission_open|r|set,[$rank_chapter|r]" and shop rules "addr,[$diffchapter|t]". Open but early checks show yellow (sequence break, out of logic) instead of red. Red now means not open in the game.
- v0.6.17: before Ch6 the client logs once that proficiency boosts are being held (again whenever the count changes).

### 7.3ah Banora prize / missile investigation (v0.6.18)
- Run 2026-10-25: the five "Ch2 Banora Treasures Prize" checks (55-59) were all read by one script within 1 s (21:32:10-11, scene 5051); the 55 vs 56-59 split in the client log is just a poll boundary. The tester's popup showed 4x "Potion x0" plus an Ether, so one prize line came from somewhere other than a patched 55-59 record (unknown: another treasure id or a direct AddItem). Tester expectation: 5 treasure prizes + 1 missile-completion check.
- To find out, the read hook cave is now APTRHK03 (replaces APTRHK02 on attach). It logs these natives with their top 3 stack args into a ring of {u16 native, u16 arg0, arg1, arg2}: 254 TreasureGetId, 256 MissionSet, 24A AddItem(amount, id), 24C AddGil, 251 TreasureEnable, 33A FairSetMiniGameMode, 3E3 FairShowMinigameFinish, 3E4 FairShowMinigameTimeup, 3F8 FairBanoraTreasure, 403 FairDestroyAllMissile. Verified in unicorn (registers and rsp preserved, other natives untouched).
- Every logged call goes to `<AP>/ccff7r/script_log.txt` (time, native, args, AddItem item name, story/chapter/scene). Minigame natives and TreasureGetId reads of non-location treasures also print in the client.
- Next: replay Ch2 Banora (golden points, factory, missiles, house) and map which calls belong to which minigame; then decide the missile completion check (likely FairShowMinigameFinish / AddGil perfect bonus in that scene).
- v0.6.19: the client logs every change of Aerith's affection (u16 treasure_bits+0xB24) with the scene to script_log.txt and the client, to map the Ch4 date activities (guide: 3 shops 30, potions to the boy 10, waiting for the girl 10, Bruno's medicine 10, perfume 3 perfect in a row 10, materia hunt under 14 s 5 = 75).
- Replay result (v0.6.19, warp to Ch2, chests skipped): `FairDestroyAllMissile(0)` at the end of the missile shelling (scene 5051, story 2071), then 21 s later the house prize script: `AddGil 1500` and 55-59 via TreasureGetId + AddItem, all five patched (Potion x0, no Ether). So the missiles and the treasure prize are one sequence, and the earlier stray Ether did not come from this script (most likely a golden item point pickup, which logs no native).
- v0.6.20 / tracker 0.3.8: new location kind `minigame_event` (LOC_BASE+0x40070 "Ch2 Banora - Missile Shelling Complete", minigame key `banora_missile`, native 0x403 in Ch2). Missable like a story chest. slot_data `skip_locations` lists excluded event locations; tracker `$loc_on|id`. Open question: whether 0x403 also fires when the run fails.
- v0.6.21: cave APTRHK04 also logs 24E AddSP, 169 SpAdd, 17C AddStat (shown in the client) and 29A Choice (file only; the picked answer is a return value, so only the call is visible). Aim: Ch3 Shinra HQ 67th floor (a timed machine gives SP; Hojo's questionnaire and virtual mission). Cave source: `scripts/caves/readhook_cave.py`, re-verified in unicorn (14 natives, 237 bytes).

### 7.3ai Ch4 log: Aerith's date and Hojo's lab (v0.6.21 run → v0.6.22)
- Aerith's date, scene 5151: shops +10 each at story 4100/4110/4120 (0→30); the girl +10 after the "wait" Choice 79 repeats; the boy +10 after 5x AddItem(Potion, -1); Bruno's medicine Choice 164 → **+5** (guide says 10); every paid perfume blend **+5, repeatable** (AddGil -550..-580 then +5); Godspeed: Choice 93 → FairSetMiniGameMode(1) → AddGil 100 → +5 → FairSetMiniGameMode(0), repeatable. Affection reached **100** with repeated perfumes (cheat table's "80 max" is wrong).
- Aerith takes the wallet: AddGil -10243 (story 4081); returned with +10243 at story 4260. AddGil logs now print signed.
- Already-working checks confirmed: gift shop owner 179-181, kids guessing 154/155/150, Bruno's gift 182 (all read as Potion x0).
- Hojo's lab is **Ch4**, scene 5155 (story 4899): timed machine SpAdd(100) (tester), three Choices then SpAdd(1000) = questionnaire. No native for the virtual mission. Then the jail (178 key reads, cell chests).
- New `minigame_event` locations (trigger in locations.json, all scene-limited): 0x40071 Perfume Blending (affection gain within 30 s of paying 200-5000 gil, not in minigame mode; key perfume_blending), 0x40072 Godspeed Materia Hunt (FairSetMiniGameMode 1→0; key materia_pickup), 0x40073-75 Aerith's Date - Affection 25/50/75 (u16 >= N; new key aerith_affection), 0x40076 Hojo's Lab - Timed Machine (SpAdd 1-999), 0x40077 Questionnaire (SpAdd >= 1000; new key hojo_lab). Replaying this log through the client's event code fires all 8 at the right moments and nothing else.
- v0.6.23: Hojo's virtual mission (Ch4, scene 5155) plays like a regular mission and swaps Zack's materia (tester). The client now logs `State` lines to script_log.txt whenever scene, active mission (u16), battle state or Zack's equipped-materia bytes (char_status+0x53..0x61) change, to find its trigger.

### 7.3aj Simulation fights and Hojo's virtual mission (v0.6.23 run → v0.6.24)
- Battle state sequence seen: 0 → (1) → 2 → 3 fighting → (5) → 6 results → 0. State 5 appeared once together with a materia level-up byte (char_status+0x54 01→02). Not yet seen: what a lost fight does.
- Ch3 simulation fights (story 3001): hub scene 5111, four rooms 5120, 5121, 5123, 5122 (play order), one fight each.
- Ch4 virtual mission: scene 5155 → 5161, Zack's materia swapped to a fixed loadout (01 01 00.. / e001 e002 e003 e0) 2 s after entering, one fight, materia restored as battle state returns to 0, back to 5155. No mission id is used (active mission stays 0xFFFF).
- Replaying the date resets affection to 0 at story 4080.
- v0.6.24: `minigame_event` trigger `battle_won` (battle state enters 6 in the given scene): Ch3 Shinra HQ - Simulation Fight 1-4 (0x40078-0x4007B, scenes 5120/5121/5123/5122) and Ch4 Hojo's Lab - Virtual Mission (0x4007C, scene 5161), key hojo_lab. Replaying both logs fires all 13 event checks at the right time and no regular fight triggers one. Script log: repeated identical Choice calls are collapsed.
- v0.6.25 (tester, per_set + npc_mission_checks): "Mission Set M1-2 received but the set stays ???". Working as designed: 1-2-1 is an NPC handout (Shinra Captain, Sector 8 LOVELESS Avenue, Ch2), so the client re-locks it until the NPC hands it out, and 1-2-2+ only open after clearing 1-2-1. Same for sets M2-1, M4-3, M6-2, M7-1, M8-2. The client now says so when such a set item arrives (who, which chapter, /warp hint), and /npcmissions shows each handout's chapter. Logic already requires the NPC chapter for these missions.
- v0.6.26: that notice is now checked every tick for every owned set (once per session), so a set received in an earlier session or under an older client is reported too, e.g. right after connecting.
- DMW characters (tester notes, 2026-10-26/27): with DMW Characters on, the reel started landing limits/modes after **3** characters in DrMisunderstood's run, but after **2** in the user's run (first character Angeal). Possibly depends on which characters are owned. The tester prefers it as is; no change, documented in the DMW Starting Characters option text (ships with the next build).
- v0.6.27: research commands `/snapshot <name>` (saves exe+71B3F00..+0x2400, the saved state block, to <AP>/ccff7r/snap_<name>.bin) and `/snapdiff <a> <b>` (lists differing bytes as exe offsets, skipping Zack EXP and play time). Aim: find what makes the DMW reel start landing limits (user's idea: a tutorial flag skipped by a fast Behemoth kill; candidates also exe+71B4BAF, the unexplained u8 next to the DMW slot flags).
- **v0.6.28 bug fix (per_set + npc_mission_checks, tester):** M1-2 stayed ??? even after the Shinra Captain's handout (checked in Ch2) and the set item (Ch3). Cause: the client's SET_MISSIONS table was built from every location with a mission, including the npc_mission locations, whose region is "Chapter N". Those pseudo-sets are never owned, so per_set mode re-locked every uncleared NPC mission (1-2-1, 2-1-1..6, 4-3-1..6, 6-2-1, 7-1-1, 8-2-1) every tick, forever. Since v0.6.4. Fix: npc_mission locations are left out of SET_MISSIONS, and every tick an owned set's first mission is unlocked if it isn't (self-healing for sets received while the bug re-locked them; NPC-held first missions are still re-locked right after until the handout).

### 7.3ak per_set and chapter-start mission unlocks (v0.6.29)
- Tester: 5-1-2 opened without clearing 5-1-1, right after Bahamut (Ch3 start). Vanilla opens 18 non-first missions at a chapter start (MissionSet calls in the chapter-start script, e.g. 220/159/207 at Ch3 = 3-1-1, 8-1-3, 5-1-2): 1-1-2, 2-2-2..5, 3-1-3, 3-1-6, 3-2-2, 3-2-5, 3-2-6, 5-1-2..6, 5-2-2, 5-2-3, 8-1-3. Not chained to the previous mission.
- Latent bug: if the set item arrived after that chapter start, the client had re-locked the mission (set not owned) and nothing re-opened it, so it and its chain successors were unreachable for good.
- First attempt (requiring the unlock chapter in per_set logic) made fill fail in 2 of 8 seeds with the tester's YAML and difficulty logic off. Final fix: locations.json marks these missions `chapter_unlock`; with the set owned, the client opens them right away, so logic stays "set item = whole set reachable" (difficulty logic still decides when they're expected). Generation: tester YAML 8/8 (diff off), 6/6 (diff on).
- v0.6.30 (tester): the Ch4 jail-key quest reads treasure 178 every frame and a finish screen calls FairShowMinigameFinish(0,0,0) every frame ("count to 5" after the monster escape), which spammed the client. Research lines (also spammed during the Ch5 squats) no longer show in the client by default: `/scriptlog on` echoes each distinct call once per session; script_log.txt collapses consecutive repeats of Choice/FairShowMinigameFinish/TreasureGetId. Neither is a check.
- Hojo's timed machine (Ch4, "count to 5"): retryable; pressing early gives a lower result (60% seen = 60 SP), 100% = 100 SP. The check (SpAdd 1-999 in scene 5155) fires on any result. Pending tester feedback on whether only 100% should count (one-line change: trigger min 100).

### 7.3al Tester run 3 feedback (2026-10-28) → v0.6.31/32
- **DMW Cloud check came at the chapter end** although Cloud was received before meeting him: polling can't see a story unlock of an owned portrait, so it fell back to DMW_FALLBACK_CB. v0.6.31: the read hook also logs native 25B DmwEnableSlot and the client sends the character's check on it (slot = arg1 when arg0 is the 0/1 flag, like TreasureEnable; to verify in script_log.txt). The fallback stays. The cave no longer fit as a cmp chain: APTRHK05 scans a 0-terminated u16 native table at cave+0xC0 (15 natives, code 154 bytes; unicorn-verified, scripts/caves/readhook_cave.py).
- **Wrong room:** the tester's client connected to an old room while his real save was loaded; the old seed's items/canary were written into the save, and the real room then left his mission sets locked. v0.6.32: the save remembers its seed: crc32("<seed>|<slot>") + magic 5E ED in treasure bytes +0xF0..+0xF5 (unused ids 1920-1967). A save without the tag is claimed by the connected seed; a save tagged for another seed is left alone (no items, no checks) with a warning until `/claimsave`. treasure_log now stops at byte 0xF0.
- **Ch7 ending soft-lock (open):** reached Aerith without the Ch7 key, bounced by the gate; later, with the key, the game acted as if he was still in a mission and Aerith wouldn't advance; /warp 8 then /warp 7 restarted Ch7 with the wagon parts already handed in and their pickups gone, so the chapter could not be finished. Entering and leaving a mission cleared the "in mission" state. Need: client log of the bounce, and how the Ch7 hand-in works (when parts are removed).
- Ideas: building the 2 extra wagons as checks; "fix all 3 wagons" as an alternative goal (user: only once wagon parts can't be lost / all parts are in missions or Ch1-7).

### 7.3am Ch7 soft-lock, tester log (v0.6.33)
- Log (DrMisunderstood, 2026-10-28): cheap parts handed to him by the client at their pickups 408/406/407/405 (21:13-21:21); Ch7 gate message 21:22:58 (bounce); key #7 at 21:40:30; then /warp 8 (21:44:58, "Chapter 7 Clear" sent only then) and /warp 7 (21:54:46). So the Ch7 ending never ran: the gate (jump to 5261 at story >= 6702) bounced him after the parts were with Aerith, and with the key he still couldn't trigger it ("game thought I was in a mission"; entering and leaving a mission cured that).
- The bounce reuses the mission-return request (current scene, flag 1). Ch1 was fine with it; in Ch7 it seems to leave mission state behind. v0.6.33: when the gate's hit counter rises, the client writes active mission = 0xFFFF (unverified guess) and tells the player.
- Warp back: the story restarts at 7000 but the 4 cheap parts are gone (given to Aerith) and their pickups 405-408 stay opened, so the ending can't be reached. v0.6.33: every warp to Ch7 or earlier clears treasure bits 405-408, removes leftover cheap parts, and marks every cheap part received so far as held again, so the client hands each one over again at its pickup.
- Still to verify: that the Aerith quest itself restarts with the story reset, and whether the gate should bounce earlier in Ch7 (before the parts are handed over).

### 7.3an Tester follow-up (2026-10-29/30) → v0.6.34
- **NPC missions stuck after the handout** (M2-1-2..2-1-4 ???, M4-3-5 with a Chapter Key on it, earlier M1-2-1): the NPC hands a mission out once. Under the v0.6.4-v0.6.27 per_set bug the handout was sent and the mission re-locked; nothing re-opened it afterwards (v0.6.28 only re-opens a set's first mission). Same for any NPC mission handed out while its set was missing. v0.6.34: with the set owned, an NPC mission is opened once its handout is done (handout checked, seen this session, /npcmissions release, or NPC Mission Checks off).
- **Ch7 is not about the parts:** after v0.6.33's /warp 7 reset (and with all 4 cheap parts in the inventory, re-handed at the /warp 8), Aerith only says "Thanks for gathering materials. But still, it's not enough..." and the map shows the "Shinra's Basic Training" zone. User (watched the stream): probably the Bruno scene earlier in Ch7 (he loses the wagon book inside a Shinra helmet and you have to find it) has its own progress flag. So the quest state lives in flags our warp/bounce don't restore. v0.6.34 drops the v0.6.33 wagon reset (it only duplicated parts) and warns at the start of Ch7 without key #7 not to bring Aerith the parts yet.
- To fix properly: a clean Ch7 run with the v0.6.23+ client (script_log State lines give every scene change) plus /snapshot before/after the Bruno helmet scene, each part hand-in and the final Aerith talk, to find the quest flags and the jump where the gate should sit (before the hand-in).

### 7.3ao Ch7 wagon quest from the user's snapshots (2026-10-31) → v0.6.35
- Snapshots (tire cutscene / in front of the helmet / helmet cutscene / handing Aerith the materials): story 6601, 6601, 6601, **6650**; scenes 5271, 5260, 5260, **5272** (Aerith's church). Treasure byte tb+0x32: 1E → 9E (407 Worn Tires) → 9E → BE (405 How to Build a Wagon, from the helmet). Quest variable u32 at **exe+71B4DAC** (tb+0xB7C): 20 → 30 (after the tires) → 30 → **99** at the hand-in; the neighbouring u32s (tb+0xB70: 40, 1, 1) look like more script variables.
- So the parts are handed over in 5272 at story 6601 → 6650, and only afterwards does the ending jump to 5261 (6750). The old Ch7 gate (5261 @ 6702) therefore bounced the player after the hand-in: quest variable already 99 and parts gone, so Aerith only repeats "not enough" and the ending can't start again.
- v0.6.35: Ch7 gate = the jump into 5272 at story >= 6601 (while out collecting parts), so the church is closed until key #7 and nothing is consumed. The start-of-Ch7 warning says so.
- Not verified: whether anything else in Ch7 needs 5272 between story 6601 and the hand-in (user's run suggests not: tires 5271 → Bruno/helmet 5260 → Aerith 5272).
- The snapshot run had no script_log: the client wasn't connected (the save has no seed tag), so ticks didn't run. Snapshots work without a connection.
- Saves already past the hand-in (quest variable 99, story >= 6650) can't be repaired by the client yet; testers in that state /warp 8 (Chapter 7 Clear is sent then).
- v0.6.36 (user: didn't connect so an old save wouldn't receive a new seed's items): offline research mode. Attached but not connected, the client still writes script_log.txt (script calls, State lines, affection) and treasure_log.txt, and /snapshot works; it gives no items, sends no checks and doesn't tag the save.

### 7.3ap Tester run 3 results (2026-11-06/07) → v0.6.37
- Run 3 finished (goal reached). Tester thinks it's releasable; user will fix the points below, make the GitHub repo and release as alpha.
- **1-1-2 open from the start:** v0.6.29 opened chapter-start missions as soon as the set was owned, and M1-1 is precollected, so 1-1-2 (rank 5, vanilla: Ch9 in the Shinra Manor) and its 50/100/200/1000-troop chain opened at once; a Chapter Key landed there (logic only asked rank 5 = Ch5). v0.6.37: such missions open once their chapter has been reached (client max_chapter; also when the set comes later), and per_set logic requires that chapter for them and their chain (locations.json `unlock_ch`, 64 locations; loc_tier includes it). Gated on slot_data `chapter_unlock_timing` so older seeds keep the old behaviour. Fill: the per_set SET_TIER item rule made 2 of 12 tester seeds fail with difficulty logic off; the rule now only applies with difficulty logic (it's a difficulty measure anyway): tester YAML 20/20 (off), 15/15 (on), progressive_rank 6/6, default 4/4. Tracker 0.3.11: `$mission_open|rank|set|unlock_ch`.
- **Ch6 (Guard Scorpion):** fought and beaten without key #6, then bounced; the arena then let him walk in with no fight and no way on (only quitting the game reset the scene). Jump log: 5252 (6302) → 5255 (save point, missions) → boss in 5255 → 5256 (6351). The gate jump 5256 comes after the boss. v0.6.37: Ch6 bounce = entrance of the current scene, and GATE_RESUME: once key #6 arrives after a bounce, the next mission start is turned into the jump to 5256 (state file `gate_bounced`).
- **Ch7 church:** the new gate works ("no key = no church") but the mission-return bounce (flag 1) put Zack under the church floor. v0.6.37: Ch7 bounces with flag 0 (the scene's entrance spawn). Jump cave APJMPHK2: gate_to bit 31 = flag 0 (scripts/caves/jumphook_cave.py, unicorn-verified).
- **Ch8 (Sephiroth):** expected loop (bounce back into the reactor 5310). v0.6.37: Ch8 bounces to 5309 (field outside the reactor, save point), entrance spawn.
- DMW: no issues in run 3 (25B hook). Wagon parts arriving "at odd times" is the hold: better parts wait for their vanilla giver's check (or Ch9), cheap parts for their Ch7 pickup (or Ch8).
- Reminder (tester): Crescent unit fight at the Ch1 Leviathan statue is not a check (unique-fight checks idea).
- v0.6.38: last open tester item is the optional Crescent Unit fight at the Ch1 Leviathan statue (before the Ogre boss). Scripted fights should go through native 156 CallBattle (154 LoadBattleData); both are now in the read hook's table (APTRHK06, 17 natives, unicorn-verified) and logged to script_log.txt with the battle state lines. Next: a log of that fight → check = CallBattle(<its id>) in Ch1 followed by battle state 6.
- **Crescent Unit fight (user's log, 2026-11-10):** at the Leviathan statue (Ch1, scene 5020, story 1350) the game calls LoadBattleData(3), then CallBattle (args 0, 0, 9830), battle state 0 → 3 → 6 → 0. v0.6.39: location "Ch1 Leviathan Statue - Crescent Unit Fight" (0x4007D, minigame key `leviathan_statue`): LoadBattleData(3) in that scene arms it, the next battle state 6 sends it (a lost fight keeps it armed for the retry; another scripted fight clears it). Replays: fires once in the user's log, nothing new in the two older logs. Tracker 0.3.12. Missable like a story chest.
