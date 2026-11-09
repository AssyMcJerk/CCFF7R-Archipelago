"""Build APWorld data tables from the research CSVs (single source of truth: ../data/*.csv).

Outputs ../apworld/ccff7r/data/locations.json, items.json and build_report.txt.
Run:  py -3 build_data.py
"""
import csv, json, os, re, collections

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")
OUT = os.path.join(HERE, "..", "apworld", "ccff7r", "data")
os.makedirs(OUT, exist_ok=True)

LOC_BASE = 0xCCF7_0000          # location id = LOC_BASE + treasure id / +0x10000 + mission / +0x20000 + chapter
ITEM_BASE = 0xCCF7_0000

def rows(name):
    with open(os.path.join(DATA, name), newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))

treasure = {int(r["index"]): r for r in rows("treasure_table_named.csv")}
missions = rows("mission_unlocks.csv")
story = rows("story_treasures.csv")
names = {int(r["id_hex"], 16): r for r in rows("item_names.csv")}
minigame_of = {int(r["treasure_id"]): r["minigame"] for r in rows("minigames.csv")}
overrides = {}
for r in rows("treasure_overrides.csv"):
    overrides.setdefault(int(r["treasure_id"]), {})[r["action"]] = r["name"] or True

# ---------------------------------------------------------------- vanilla contents -> item name
def content_name(tid):
    r = treasure[tid]
    t, amt = r["type"], int(r["amount"])
    val = int(r["id_hex"], 16)
    if t == "gil":
        return f"{val * max(amt, 1)} Gil", {"type": 1, "id": val, "amount": max(amt, 1)}
    if t == "sp":
        return f"{val * max(amt, 1)} SP", {"type": 2, "id": val, "amount": max(amt, 1)}
    if val in (0x3035, 0x3036):              # Keychain (3 slots) / Backpack (4 slots) -> progressive
        return "Progressive Accessory Slot", {"type": "accessory_slot"}
    nm = r["name"] or f"Item 0x{val:04X}"
    if val >> 12 == 0xC and r["detail"]:
        nm = f"{nm} ({r['detail']})"
    if amt > 1:
        nm = f"{nm} x{amt}"
    return nm, {"type": 0, "id": val, "amount": amt}

# ---------------------------------------------------------------- locations
locations, used = [], set()
def add_loc(name, lid, kind, region, **kw):
    base, n = name, 2
    while name in used:
        name = f"{base} ({n})"; n += 1
    used.add(name)
    locations.append(dict(name=name, id=lid, kind=kind, region=region, **kw))

set_of = lambda num: "M" + "-".join(num.split("-")[:2])            # "2-1-3" -> "M2-1"
for m in missions:
    num, mname, idx = m["number"], m["name"], int(m["mission_index"])
    region = set_of(num)
    rt = int(m["reward_treasure"])
    vname, payload = content_name(rt)
    add_loc(f"M{num} {mname} - Reward", LOC_BASE + rt, "mission_reward", region,
            treasure=rt, mission=idx, number=num, rank=int(m["rank"]), vanilla=vname, vanilla_payload=payload)
    if m["chest_treasures"]:
        for k, tid in enumerate(m["chest_treasures"].split(), 1):
            tid = int(tid); vname, payload = content_name(tid)
            add_loc(f"M{num} {mname} - Chest {k}", LOC_BASE + tid, "mission_chest", region,
                    treasure=tid, mission=idx, number=num, rank=int(m["rank"]), vanilla=vname, vanilla_payload=payload)

excluded = []
mission_by_num = {m["number"]: m for m in missions}
for s in story:
    tid = int(s["treasure_id"])
    ov = overrides.get(tid, {})
    if "mission" in ov:                      # extra reward granted when a mission is cleared (not a chest)
        m = mission_by_num[ov["mission"]]
        vname, payload = content_name(tid)
        add_loc(f"M{m['number']} {m['name']} - Bonus ({vname})", LOC_BASE + tid, "mission_bonus",
                set_of(m["number"]), treasure=tid, mission=int(m["mission_index"]), number=m["number"],
                rank=int(m["rank"]), vanilla=vname, vanilla_payload=payload)
        continue
    if not s["chapter"]:
        excluded.append((tid, s["location"], s["contents"])); continue
    ch = int(s["chapter"])
    ov = overrides.get(tid, {})
    if "remove" in ov:                       # confirmed not a real chest
        excluded.append((tid, s["location"], s["contents"] + "  [removed: never seen]")); continue
    if "vanilla" in ov:                      # story-required item: never randomized, never patched
        excluded.append((tid, s["location"], s["contents"] + "  [kept vanilla]")); continue
    loc = s["location"]
    if loc.startswith("(unmatched"):
        loc = f"Treasure {tid}"
    if "rename" in ov:
        loc = ov["rename"]
    vname, payload = content_name(tid)
    add_loc(f"Ch{ch} {loc}", LOC_BASE + tid, "story_chest", f"Chapter {ch}",
            treasure=tid, chapter=ch, match=s["match"], unverified="unverified" in ov,
            minigame=minigame_of.get(tid),
            **({"detect": "read"} if "read" in ov else {}),
            **({"group": ov["group"]} if "group" in ov else {}),
            **({"also_on": LOC_BASE + int(ov["also_on"])} if "also_on" in ov else {}),
            **({"locked": True} if "locked" in ov else {}),
            vanilla=vname, vanilla_payload=payload)

# shopsanity: every stock slot of shops 0-15 (16 is a variant of 15 and maps onto it); the world only
# creates the first `shop_slots` slots of each shop
shop_meta = {int(r["shop"]): r for r in rows("shop_names.csv")}
for r in rows("shops.csv"):
    s_, k = int(r["shop"]), int(r["slot"])
    if s_ > 15:
        continue
    m = shop_meta[s_]
    add_loc(f"Shop {m['name']} - Slot {k + 1}", LOC_BASE + 0x30000 + s_ * 16 + k, "shop_slot", f"Shop {m['name']}",
            shop=s_, slot=k, address=m["address_item"] or None,
            vanilla=r["item"], vanilla_payload={"type": 0, "id": int(r["item_id"], 16), "amount": 1})

for ch in range(1, 10):
    add_loc(f"Chapter {ch} Clear", LOC_BASE + 0x20000 + ch, "chapter_clear", f"Chapter {ch}", chapter=ch)

# ---------------------------------------------------------------- v0.6 optional checks (LOC_BASE + 0x40000 ..)
# DMW character slots (doc 5.3): exe+71B4BA8[slot]; the story's own unlock becomes a check
DMW_CHARS = ["Sephiroth", "Angeal", "Tseng", "Cloud", "Aerith", "Cissnei", "Genesis"]
DMW_UNLOCK_CH = {0: 1, 1: 1, 2: 2, 3: 5, 4: 5, 5: 3, 6: 5}     # PowerPyx DMW guide; Aerith = start of Ch5 (tester)
for s_, nm in enumerate(DMW_CHARS):
    add_loc(f"DMW - {nm} joins the DMW", LOC_BASE + 0x40000 + s_, "dmw_unlock", f"Chapter {DMW_UNLOCK_CH[s_]}",
            slot=s_, chapter=DMW_UNLOCK_CH[s_])
# DMW memories: watched bits at char_status+0x168+char (bit n); 6 per character, Genesis 2 (counted)
for c, nm in enumerate(DMW_CHARS):
    for n in range(2 if c == 6 else 6):
        add_loc(f"DMW - {nm} Memory {n + 1}", LOC_BASE + 0x40010 + c * 6 + n, "dmw_memory", "Chapter 10",
                slot=c, memory=n, chapter=10)
# Magic Pot: use the 4 abilities it asks for (M10-2-3) -> key item Magic Pot Tricks (0x3025)
add_loc("M10-2-3 Master Tonberry - Magic Pot's request", LOC_BASE + 0x40050, "magic_pot", "M10-2",
        mission=238, number="10-2-3", rank=next(int(m["rank"]) for m in missions if m["number"] == "10-2-3"))
# minigame completions with no item in vanilla, detected by a script native (doc 7.3ah): {native, chapter}
# trigger: native (+ optional min/max on its first argument), "perfume" (affection gain right after paying for a
# blend), "minigame_end" (FairSetMiniGameMode 1 -> 0) or affection >= N. doc 7.3ai
add_loc("Ch2 Banora - Missile Shelling Complete", LOC_BASE + 0x40070, "minigame_event", "Chapter 2",
        chapter=2, minigame="banora_missile", trigger={"native": 0x403, "scene": 5051})
add_loc("Ch4 Sector 5 Slums - Perfume Blending", LOC_BASE + 0x40071, "minigame_event", "Chapter 4",
        chapter=4, minigame="perfume_blending", trigger={"perfume": True, "scene": 5151})
add_loc("Ch4 Sector 5 Slums - Godspeed Materia Hunt", LOC_BASE + 0x40072, "minigame_event", "Chapter 4",
        chapter=4, minigame="materia_pickup", trigger={"minigame_end": True, "scene": 5151})
for k, n in enumerate((25, 50, 75)):
    add_loc(f"Ch4 Aerith's Date - Affection {n}", LOC_BASE + 0x40073 + k, "minigame_event", "Chapter 4",
            chapter=4, minigame="aerith_affection", trigger={"affection": n})
for k, sc in enumerate((5120, 5121, 5123, 5122)):   # order played in the tester's run (hub scene 5111)
    add_loc(f"Ch3 Shinra HQ - Simulation Fight {k + 1}", LOC_BASE + 0x40078 + k, "minigame_event", "Chapter 3",
            chapter=3, minigame="hojo_lab", trigger={"battle_won": True, "scene": sc})
# optional scripted fight: LoadBattleData(3) at the Leviathan statue (Ch1 scene 5020, story 1350), then won. doc 7.3aq
add_loc("Ch1 Leviathan Statue - Crescent Unit Fight", LOC_BASE + 0x4007D, "minigame_event", "Chapter 1",
        chapter=1, minigame="leviathan_statue", trigger={"battle": 3, "scene": 5020})
add_loc("Ch4 Hojo's Lab - Virtual Mission", LOC_BASE + 0x4007C, "minigame_event", "Chapter 4",
        chapter=4, minigame="hojo_lab", trigger={"battle_won": True, "scene": 5161})
add_loc("Ch4 Hojo's Lab - Timed Machine (SP)", LOC_BASE + 0x40076, "minigame_event", "Chapter 4",
        chapter=4, minigame="hojo_lab", trigger={"native": 0x169, "min": 1, "max": 999, "scene": 5155})
add_loc("Ch4 Hojo's Lab - Questionnaire (SP)", LOC_BASE + 0x40077, "minigame_event", "Chapter 4",
        chapter=4, minigame="hojo_lab", trigger={"native": 0x169, "min": 1000, "max": 0xFFFF, "scene": 5155})
# Buster Sword proficiency milestones (doc 5.4)
for k in range(1, 11):
    add_loc(f"Buster Sword Proficiency {k * 10}%", LOC_BASE + 0x40060 + k, "proficiency", "Chapter 6",
            percent=k * 10, chapter=6)
# NPC mission handouts (LOC_BASE + 0x40400 + mission index): the NPC's MissionSet call is the check
for m in missions:
    if m["unlock_type"] != "npc":
        continue
    ch = int(m["unlock_chapter"] or 5)                      # 4-3-2..4-3-6 = Wutai spies 2-6, Ch5+
    where = m["availability_guide"].split(" in Chapter")[0].replace("Speak to the ", "")
    where = re.sub(r" 3 times.*", "", where).split(",")[0]
    if m["number"] in ("4-3-2", "4-3-3", "4-3-4", "4-3-5", "4-3-6"):
        where += f", Wutai spy {int(m['number'][-1])}"
    add_loc(f"M{m['number']} {m['name']} - NPC handout ({where})", LOC_BASE + 0x40400 + int(m["mission_index"]),
            "npc_mission", f"Chapter {ch}", chapter=ch, mission=int(m["mission_index"]), number=m["number"])
# mailsanity (data/mails.csv): LOC_BASE + 0x40100 + mail id; Zack Fan Club endings 81-83 share one check
for r in rows("mails.csv"):
    mid = int(r["id"])
    if mid in (82, 83):
        continue
    kw = dict(mail=[81, 82, 83] if mid == 81 else [mid], mail_kind=r["kind"])
    label = "Zack Fan Club: final newsletter" if mid == 81 else f"{r['sender']}: {r['subject']}"
    if r["kind"] == "mission":
        m = next(m for m in missions if int(m["mission_index"]) == int(r["mission_index"]))
        add_loc(f"Mail - {label}", LOC_BASE + 0x40100 + mid, "mail", set_of(m["number"]),
                mission=int(r["mission_index"]), number=m["number"], rank=int(m["rank"]), **kw)
    else:
        ch = int(r["chapter"])
        add_loc(f"Mail - {label}", LOC_BASE + 0x40100 + mid, "mail", f"Chapter {ch}", chapter=ch, **kw)

# ---------------------------------------------------------------- items
pool = collections.Counter(l["vanilla"] for l in locations if "vanilla" in l)
payloads = {l["vanilla"]: l["vanilla_payload"] for l in locations if "vanilla" in l}
# ---- stable item ids: data/item_ids.json is append-only, so running seeds never break
REG_PATH = os.path.join(DATA, "item_ids.json")
reg = json.load(open(REG_PATH)) if os.path.exists(REG_PATH) else {}
def item_id(name, payload):
    if name not in reg:
        reg[name] = {"id": max([v["id"] for v in reg.values()] + [ITEM_BASE]) + 1, "payload": payload}
    return reg[name]["id"]
items = []
STEAL_MATERIA = {"Steal", "Steal (1* AP+1)", "Mug (1* AP+2)"}    # needed to steal the Ch4 jail cell keys
def classify(name, p):
    if name in STEAL_MATERIA:
        return "progression"
    if p["type"] == "accessory_slot":
        return "useful"
    if p["type"] == 0 and 0x3053 <= p["id"] <= 0x3059:
        return "progression"              # Goddess Materia
    if p["type"] == 0 and p["id"] >> 12 == 3:
        return "useful"
    if p["type"] == 0 and (p["id"] >> 12 in (4, 5, 0xC)):
        return "useful"
    return "filler"
for name in sorted(pool):
    items.append(dict(name=name, id=item_id(name, payloads[name]), classification=classify(name, payloads[name]),
                      vanilla_count=pool[name], payload=payloads[name]))
# extra items with no treasure-table source (vanilla: battle drops/steals), added to complete sets
EXTRA_ITEMS = {"Genji Helm": 0x5066, "Genji Armor": 0x5067, "Genji Shield": 0x5068}
# (Sec.6 Accessory Shop Address used to be an extra item; it is the 6-2-6 bonus, treasure 396, since playtest 4)
for name, iid in EXTRA_ITEMS.items():
    p = {"type": 0, "id": iid, "amount": 1}
    items.append(dict(name=name, id=item_id(name, p), classification="useful", vanilla_count=1, payload=p))
# option items (vanilla_count 0: the world adds them when their option is on)
p = {"type": 0, "id": 0x3025, "amount": 1}
items.append(dict(name="Magic Pot Tricks", id=item_id("Magic Pot Tricks", p), classification="useful",
                  vanilla_count=0, payload=p))
# Buster Sword proficiency boosts (doc 5.4): each adds 25% of one stance value's range (Block 80-100, Command 200-300,
# Sword 100-300), i.e. 7.5% / 6.25% / 6.25% on the proficiency meter
for k, nm in enumerate(("Perfect Guard", "Command Kill", "Strong Attack Kill")):
    p = {"type": "proficiency", "part": k, "fraction": 0.25}
    items.append(dict(name=f"Proficiency Boost: {nm}", id=item_id(f"Proficiency Boost: {nm}", p),
                      classification="useful", vanilla_count=0, payload=p))
for s_, nm in enumerate(DMW_CHARS):
    p = {"type": "dmw_slot", "slot": s_}
    items.append(dict(name=f"DMW: {nm}", id=item_id(f"DMW: {nm}", p), classification="useful",
                      vanilla_count=0, payload=p))
sets = sorted({set_of(m["number"]) for m in missions}, key=lambda s: [int(x) for x in s[1:].split("-")])
for s_ in sets:
    first = sorted((m for m in missions if set_of(m["number"]) == s_), key=lambda m: int(m["number"].split("-")[2]))[0]
    p = {"type": "mission_set", "set": s_, "first_mission": int(first["mission_index"])}
    items.append(dict(name=f"Mission Set {s_}", id=item_id(f"Mission Set {s_}", p), classification="progression",
                      vanilla_count=0, payload=p))
for name, p in (("Progressive Mission Rank", {"type": "mission_rank"}), ("Progressive Chapter Key", {"type": "chapter_key"})):
    items.append(dict(name=name, id=item_id(name, p), classification="progression", vanilla_count=0, payload=p))
# legacy names (no longer generated) stay receivable so seeds made with older versions keep working
made = {i["name"] for i in items}
for name, v in reg.items():
    if name not in made:
        items.append(dict(name=name, id=v["id"], classification="filler", vanilla_count=0, payload=v["payload"], legacy=True))
json.dump(reg, open(REG_PATH, "w"), indent=1)

# per_set: missions vanilla opens at a chapter start rather than by clearing the previous mission (5-1-2..5-1-6 ...).
# With their set owned, the client opens them right away (else they'd stay locked if the set came after that chapter
# start). doc 7.3ak
for l in locations:
    if l["kind"] == "mission_reward":
        m = mission_by_num[l["number"]]
        first = min((x for x in missions if set_of(x["number"]) == l["region"]), key=lambda x: int(x["number"].split("-")[2]))
        if m["unlock_type"] == "chapter" and first["number"] != l["number"]:
            l["chapter_unlock"] = int(m["unlock_chapter"])
# unlock_ch: the chapter a mission needs through its own chapter unlock or one earlier in its chain (per_set logic)
def _unlock_ch(num):
    m = mission_by_num[num]
    first = min((x for x in missions if set_of(x["number"]) == set_of(num)), key=lambda x: int(x["number"].split("-")[2]))
    if first["number"] == num:
        return 0
    if m["unlock_type"] == "chapter":
        return int(m["unlock_chapter"])
    if m["unlock_type"] == "chain" and m["prereq_by_f5"]:
        return _unlock_ch(m["prereq_by_f5"])
    return 0
for l in locations:
    if "number" in l and l["kind"] != "npc_mission" and _unlock_ch(l["number"]):
        l["unlock_ch"] = _unlock_ch(l["number"])
json.dump(locations, open(os.path.join(OUT, "locations.json"), "w"), indent=1)
json.dump(items, open(os.path.join(OUT, "items.json"), "w"), indent=1)

kinds = collections.Counter(l["kind"] for l in locations)
with open(os.path.join(OUT, "build_report.txt"), "w") as f:
    f.write(f"locations: {len(locations)}  {dict(kinds)}\n")
    f.write(f"distinct vanilla items: {len(pool)}  mission sets: {len(sets)}\n")
    f.write(f"item pool from vanilla contents: {sum(pool.values())}\n")
    prog = len(sets) + 9
    f.write(f"unverified story chests (filler only, left vanilla): {sum(1 for l in locations if l.get('unverified'))}\n")
    f.write(f"progression items added: {prog}  (52 mission sets + 9 chapter keys) -> pool {sum(pool.values()) + prog} vs locations {len(locations)}: drop {sum(pool.values()) + prog - len(locations)} filler\n")
    f.write(f"excluded story treasures (no chapter): {len(excluded)}\n")
    for e in excluded: f.write(f"  {e}\n")
print(open(os.path.join(OUT, "build_report.txt")).read().splitlines()[:4])
