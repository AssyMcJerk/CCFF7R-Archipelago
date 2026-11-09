"""Build the PopTracker pack (real map textures + list pages for map-less areas) from the apworld data.

Output: poptracker/ (pack folder) and poptracker/../ccff7r_poptracker.zip
"Maps" are generated list images (one row per location) so PopTracker can show pins without real maps.
Usage: python apworld_build/build_poptracker.py
"""
import json, os, re, shutil, zipfile
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..")
DATA = os.path.join(ROOT, "apworld", "ccff7r", "data")
OUT = os.path.join(ROOT, "poptracker")
VERSION = "0.3.12"

LOCS = json.load(open(os.path.join(DATA, "locations.json")))
ITEMS = json.load(open(os.path.join(DATA, "items.json")))
ITEM_ID = {i["name"]: i["id"] for i in ITEMS}

FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

if os.path.exists(OUT):
    shutil.rmtree(OUT)
for d in ("images/items", "images/maps", "items", "locations", "maps", "layouts", "scripts/autotracking"):
    os.makedirs(os.path.join(OUT, d), exist_ok=True)


def wjson(rel, obj):
    with open(os.path.join(OUT, rel), "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1, ensure_ascii=False)


def natural(s):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def slug(s):
    return re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")


# ------------------------------------------------------------------ item icons
def icon(path, text, color, fg="white"):
    im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((2, 2, 61, 61), 12, fill=color, outline="white", width=2)
    size = 26 if len(text) <= 2 else 18 if len(text) <= 4 else 13
    f = ImageFont.truetype(BOLD, size)
    lines = text.split("\n")
    total = sum(d.textbbox((0, 0), ln, font=f)[3] for ln in lines) + 2 * (len(lines) - 1)
    y = (64 - total) / 2
    for ln in lines:
        bb = d.textbbox((0, 0), ln, font=f)
        d.text(((64 - (bb[2] - bb[0])) / 2 - bb[0], y - bb[1]), ln, font=f, fill=fg)
        y += bb[3] + 2
    im.save(os.path.join(OUT, path))


items_json, item_map = [], {}          # item_map: ap id -> (code, type)

GODDESS = ["Light", "Heaven", "Ground", "Star", "Life", "Being", "Sabbath"]
GCOL = ["#d8b400", "#4aa3df", "#8a6a3a", "#e0e0ff", "#3fbf6f", "#b05fd0", "#c04040"]
for g, c in zip(GODDESS, GCOL):
    code = f"goddess_{g.lower()}"
    icon(f"images/items/{code}.png", g[:2], c)
    items_json.append({"name": f"{g} Materia", "type": "toggle", "img": f"images/items/{code}.png", "codes": code})
    item_map[ITEM_ID[f"{g} Materia"]] = (code, "toggle")

for code, name, txt, col, mx in (("rank", "Progressive Mission Rank", "Rank", "#3060c0", 10),
                                 ("chapterkey", "Progressive Chapter Key", "Ch\nKey", "#a05020", 9),
                                 ("accslot", "Progressive Accessory Slot", "Acc\nSlot", "#606060", 2)):
    icon(f"images/items/{code}.png", txt, col)
    items_json.append({"name": name, "type": "consumable", "img": f"images/items/{code}.png", "codes": code,
                       "max_quantity": mx, "increment": 1})
    if name in ITEM_ID:
        item_map[ITEM_ID[name]] = (code, "consumable")

icon("images/items/steal.png", "Steal", "#2e8b57")
items_json.append({"name": "Steal / Mug", "type": "toggle", "img": "images/items/steal.png", "codes": "steal"})
for n in ("Steal", "Steal (1* AP+1)", "Mug (1* AP+2)"):
    item_map[ITEM_ID[n]] = ("steal", "toggle")

shop_meta = {}
import csv
for r in csv.DictReader(open(os.path.join(ROOT, "data", "shop_names.csv"))):
    shop_meta[int(r["shop"])] = r
ADDR_CODE = {}
for s in range(1, 16):
    addr = shop_meta[s]["address_item"]
    code = f"addr_{s}"
    ADDR_CODE[addr] = code
    short = "".join(w[0] for w in re.sub(r"[^A-Za-z0-9 ]", " ", shop_meta[s]["name"]).split())[:4]
    icon(f"images/items/{code}.png", short, "#7a5c2e")
    items_json.append({"name": addr, "type": "toggle", "img": f"images/items/{code}.png", "codes": code})
    if addr in ITEM_ID:
        item_map[ITEM_ID[addr]] = (code, "toggle")

# mission sets (only used by mission_unlocks: per_set)
SETS = sorted({l["region"] for l in LOCS if l["kind"] in ("mission_reward", "mission_chest", "mission_bonus")},
              key=lambda s: [int(x) for x in s[1:].split("-")])
for st in SETS:
    code = f"set_{slug(st)}"
    icon(f"images/items/{code}.png", st, "#204060")
    items_json.append({"name": f"Mission Set {st}", "type": "toggle", "img": f"images/items/{code}.png", "codes": code})
    item_map[ITEM_ID[f"Mission Set {st}"]] = (code, "toggle")

# v0.6 options: DMW characters + Magic Pot
DMW_CHARS = ["Sephiroth", "Angeal", "Tseng", "Cloud", "Aerith", "Cissnei", "Genesis"]
DMW_COL = ["#6a6a90", "#4a6a4a", "#30304a", "#5a7090", "#b06080", "#a04030", "#902020"]
for nm, c in zip(DMW_CHARS, DMW_COL):
    code = f"dmw_{nm.lower()}"
    icon(f"images/items/{code}.png", nm[:3], c)
    items_json.append({"name": f"DMW: {nm}", "type": "toggle", "img": f"images/items/{code}.png", "codes": code})
    item_map[ITEM_ID[f"DMW: {nm}"]] = (code, "toggle")
icon("images/items/magicpot.png", "Pot", "#8a7030")
items_json.append({"name": "Magic Pot Tricks", "type": "toggle", "img": "images/items/magicpot.png", "codes": "magicpot"})
item_map[ITEM_ID["Magic Pot Tricks"]] = ("magicpot", "toggle")

icon("images/items/settings.png", "", "#000000")
items_json.append({"name": "settings refresh", "type": "consumable", "img": "images/items/settings.png",
                   "codes": "settings_refresh", "max_quantity": 9999})
wjson("items/items.json", items_json)

# ------------------------------------------------------------------ list "maps"
ROW, PAD, W = 22, 28, 760
maps_json = []


def list_map(name, file, rows, title):
    """rows: [(label, sublabel)]; returns pin coords per row."""
    h = PAD + 34 + ROW * len(rows) + PAD
    im = Image.new("RGB", (W, h), "#14161c")
    d = ImageDraw.Draw(im)
    d.text((PAD, PAD - 6), title, font=ImageFont.truetype(BOLD, 20), fill="#f0d070")
    f, fs = ImageFont.truetype(FONT, 14), ImageFont.truetype(FONT, 11)
    coords = []
    for i, (label, sub) in enumerate(rows):
        y = PAD + 34 + i * ROW
        if i % 2:
            d.rectangle((0, y, W, y + ROW - 1), fill="#1b1e26")
        d.text((PAD + 26, y + 3), label, font=f, fill="#e8e8e8")
        if sub:
            tw = d.textlength(label, font=f)
            d.text((PAD + 34 + tw, y + 5), sub, font=fs, fill="#8a90a0")
        coords.append((PAD + 8, y + ROW // 2))
    im.save(os.path.join(OUT, "images", "maps", file))
    maps_json.append({"name": name, "img": f"images/maps/{file}", "location_size": 16,
                      "location_border_thickness": 2})
    return coords


loc_groups, loc_map = [], {}           # loc_map: ap location id -> ["@path/section", ...]
MAPTEX, OVERVIEW = {}, {}               # map name -> texture; texture -> [(label, id, rules, vis)]


def location(group_name, name, sections, rules, mapname, xy, vis=None):
    entry = {"name": name, "sections": [], "map_locations": [{"map": mapname, "x": xy[0], "y": xy[1]}]}
    if rules:
        entry["access_rules"] = rules
    if vis:
        entry["visibility_rules"] = vis
    for sname, lid, svis in sections:
        sec = {"name": sname, "item_count": 1}
        if svis:
            sec["visibility_rules"] = svis
        entry["sections"].append(sec)
        loc_map.setdefault(lid, []).append(f"@{group_name}/{name}/{sname}")
        if mapname in MAPTEX:
            label = group_name.split("/")[-1].replace("Chapter ", "Ch") + " - " + name
            OVERVIEW.setdefault(MAPTEX[mapname], []).append((label, lid, rules, vis))
    return entry


# ------------------------------------------------------------------ real maps
TEXDIR = os.environ.get("CCFF7R_TEXDIR", os.path.join(ROOT, "fmode_export", "CCFF7R", "Content", "UI", "31_Map",
                                                       "01_Map", "00_Texture"))
CAL = {r["texture"]: (float(r["k"]), float(r["cx"]), float(r["cy"]))
       for r in csv.DictReader(open(os.path.join(ROOT, "data", "map_calibration.csv")))}
POS = {}
for r in csv.DictReader(open(os.path.join(ROOT, "data", "chest_positions.csv"))):
    if r["texture"] in CAL and r["x"]:
        POS[int(r["treasure_id"])] = (r["texture"], float(r["x"]), float(r["y"]))
SCALE = 0.5                                  # textures are 2048x2048; maps are shipped at half size
_texinfo = {}


def tex_px(tex, x, y):
    k, cx, cy = CAL[tex]
    return cx + k * x, cy + k * y            # pixel in the 2048 texture


def build_tex(tex, pins):
    """Crop (content + pins), brighten and halve a map texture once; returns (file, x0, y0, w, h)."""
    if tex in _texinfo:
        return _texinfo[tex]
    im = Image.open(os.path.join(TEXDIR, tex + ".png")).convert("RGBA")
    a = im.split()[3].point(lambda v: 255 if v > 12 else 0)
    bb = a.getbbox() or (0, 0, 2048, 2048)
    xs = [bb[0], bb[2]] + [p[0] for p in pins]
    ys = [bb[1], bb[3]] + [p[1] for p in pins]
    m = 40
    x0, y0 = max(0, int(min(xs)) - m), max(0, int(min(ys)) - m)
    x1, y1 = min(2048, int(max(xs)) + m), min(2048, int(max(ys)) + m)
    bg = Image.new("RGBA", im.size, (10, 14, 22, 255))
    bg.alpha_composite(im)
    rgb = bg.convert("RGB").crop((x0, y0, x1, y1))
    rgb = rgb.point(lambda v: min(255, int(v * 2.2)))
    rgb = rgb.resize((max(1, int((x1 - x0) * SCALE)), max(1, int((y1 - y0) * SCALE))), Image.LANCZOS)
    fn = f"tex_{tex[9:]}.png"
    rgb.save(os.path.join(OUT, "images", "maps", fn), optimize=True)
    _texinfo[tex] = (fn, x0, y0, rgb.width, rgb.height)
    return _texinfo[tex]


def texture_pins(locs):
    """{tex: [(loc, px, py)]} in 2048 texture space for the locations that have a calibrated pin."""
    out = {}
    for l in locs:
        p = POS.get(l.get("treasure"))
        if p:
            px, py = tex_px(*p)
            out.setdefault(p[0], []).append((l, px, py))
    return out


def map_for(mapname, tex, pins):
    fn, x0, y0, w, h = build_tex(tex, [(px, py) for _, px, py in pins])
    MAPTEX[mapname] = tex
    if not any(m["name"] == mapname for m in maps_json):
        maps_json.append({"name": mapname, "img": f"images/maps/{fn}", "location_size": 14,
                          "location_border_thickness": 2})
    return [(l, (min(w - 4, max(4, int((px - x0) * SCALE))), min(h - 4, max(4, int((py - y0) * SCALE)))))
            for l, px, py in pins]


def short(tex):
    return tex[9:] if tex.startswith("T_ui_Map_") else tex


# story chapters: a sub-tab per area map, plus a list of the locations that have no map
JAIL = set(range(160, 178))
STORY_TABS = {}


def story_entry(ch, l, group, mapname, xy):
    rules = [f"$chapter|{ch}"] if ch > 1 else []
    if l.get("treasure") in JAIL:
        rules = [f"$chapter|{ch},steal"]
    vis = ([f"$not_skipped|{l['treasure']}"] if "treasure" in l else [f"$loc_on|{l['id']}"]) if l.get("minigame") else None
    name = re.sub(rf"^Ch{ch} ", "", l["name"]) + (" (vanilla wagon part)" if l.get("locked") else "")
    return location(group, name, [("Clear" if l["kind"] == "chapter_clear" else "Check", l["id"], None)],
                    rules, mapname, xy, vis)


for ch in range(1, 11):
    group = f"Chapter {ch}"
    rows = [l for l in LOCS if l["kind"] in ("story_chest", "chapter_clear", "minigame_event") and l.get("chapter") == ch]
    rows.sort(key=lambda l: (l["kind"] == "chapter_clear", natural(l["name"])))
    bytex = texture_pins(rows)
    pinned = {id(l) for v in bytex.values() for l, _, _ in v}
    children, tabs_ch = [], []
    for tex in sorted(bytex):
        mapname = f"Ch{ch} {short(tex)}"
        for l, xy in map_for(mapname, tex, bytex[tex]):
            children.append(story_entry(ch, l, group, mapname, xy))
        tabs_ch.append({"title": f"{short(tex)} ({len(bytex[tex])})", "content": {"type": "map", "maps": [mapname]}})
    rest = [l for l in rows if id(l) not in pinned]
    if rest:
        mapname = f"Chapter {ch} list"
        coords = list_map(mapname, f"ch{ch}_list.png", [(re.sub(rf"^Ch{ch} ", "", l["name"]),
                          "minigame: " + l["minigame"] if l.get("minigame") else "") for l in rest],
                          f"Chapter {ch} - no map")
        for l, xy in zip(rest, coords):
            children.append(story_entry(ch, l, group, mapname, xy))
        tabs_ch.append({"title": f"No map ({len(rest)})", "content": {"type": "map", "maps": [mapname]}})
    STORY_TABS[ch] = tabs_ch
    loc_groups.append((f"story_ch{ch}.json", [{"name": group, "children": children}]))

# missions: per category M1..M10 a sub-tab per map; every check is its own pin (reward = where the fight starts)
missions = {}
for l in LOCS:
    if l["kind"] in ("mission_reward", "mission_chest", "mission_bonus"):
        missions.setdefault(l["number"], []).append(l)
MISSION_TABS = {}
for cat in range(1, 11):
    group = f"M{cat}"
    keys = sorted((k for k in missions if k.split("-")[0] == str(cat)), key=lambda k: [int(x) for x in k.split("-")])
    rows = [l for k in keys for l in sorted(missions[k], key=lambda l: (l["kind"] != "mission_reward",
                                                                        natural(l["name"])))]
    bytex = texture_pins(rows)
    place = {}
    tabs_m = []
    for tex in sorted(bytex, key=lambda t: -len(bytex[t])):
        mapname = f"M{cat} {short(tex)}"
        for l, xy in map_for(mapname, tex, bytex[tex]):
            place[id(l)] = (mapname, xy)
        nmis = len({l["number"] for l, _, _ in bytex[tex]})
        tabs_m.append({"title": f"{short(tex)} ({nmis} missions)", "content": {"type": "map", "maps": [mapname]}})
    rest = [l for l in rows if id(l) not in place]
    if rest:
        mapname = f"M{cat} list"
        coords = list_map(mapname, f"m{cat}_list.png", [(l["name"], f"rank {l['rank']}") for l in rest],
                          f"Missions M{cat} - no map")
        for l, xy in zip(rest, coords):
            place[id(l)] = (mapname, xy)
        tabs_m.append({"title": f"No map ({len(rest)})", "content": {"type": "map", "maps": [mapname]}})
    MISSION_TABS[cat] = tabs_m
    children = []
    for k in keys:
        ls = missions[k]
        mgroup = ls[0]["name"].rsplit(" - ", 1)[0]
        sub = []
        for l in sorted(ls, key=lambda l: (l["kind"] != "mission_reward", natural(l["name"]))):
            mapname, xy = place[id(l)]
            nm = l["name"].rsplit(" - ", 1)[1]
            sub.append(location(f"{group}/{mgroup}", nm, [("Check", l["id"], None)],
                                [f"$mission_open|{l['rank']}|{slug(l['region'])}|{l.get('unlock_ch', 0)},[$rank_chapter|{l['rank']}]"], mapname, xy,
                                [f"$not_skipped|{l['treasure']}"]))
        children.append({"name": mgroup, "children": sub})
    loc_groups.append((f"missions_m{cat}.json", [{"name": group, "children": children}]))

# overview: one tile per map texture; its single pin carries every check on that map (also tracked there)
TILE, COLS = 200, 8
otex = sorted(OVERVIEW, key=lambda t: (min(int(re.match(r"(?:Ch|M)(\d+)", lb).group(1)) + (0 if lb.startswith("Ch") else 100)
                                           for lb, _, _, _ in OVERVIEW[t]), t))
rows_n = -(-len(otex) // COLS)
ov = Image.new("RGB", (COLS * TILE, rows_n * TILE + 40), "#0c0d10")
od = ImageDraw.Draw(ov)
od.text((12, 8), "Overview - one pin per map (hover for its checks)", font=ImageFont.truetype(BOLD, 18), fill="#f0d070")
fl, fs2 = ImageFont.truetype(BOLD, 13), ImageFont.truetype(FONT, 11)
ochildren = []
for i, tex in enumerate(otex):
    x0, y0 = (i % COLS) * TILE, 40 + (i // COLS) * TILE
    th = Image.open(os.path.join(OUT, "images", "maps", _texinfo[tex][0])).convert("RGB")
    th.thumbnail((TILE - 16, TILE - 46))
    ov.paste(th, (x0 + (TILE - th.width) // 2, y0 + 6))
    od.rectangle((x0 + 2, y0 + 2, x0 + TILE - 3, y0 + TILE - 3), outline="#2a3040")
    ents = OVERVIEW[tex]
    tags = sorted({lb.split(" - ")[0].split("-")[0] if lb.startswith("M") else lb.split(" - ")[0] for lb, _, _, _ in ents},
                  key=natural)
    od.text((x0 + 8, y0 + TILE - 38), short(tex), font=fl, fill="#e8e8e8")
    od.text((x0 + 8, y0 + TILE - 20), ", ".join(tags)[:34], font=fs2, fill="#8a90a0")
    name = f"{short(tex)} ({', '.join(tags)})"
    entry = {"name": name, "sections": [], "map_locations": [{"map": "Overview", "x": x0 + TILE - 22, "y": y0 + 22}]}
    for lb, lid, rules, vis in ents:
        sec = {"name": lb, "item_count": 1}
        if rules:
            sec["access_rules"] = rules
        if vis:
            sec["visibility_rules"] = vis
        entry["sections"].append(sec)
        loc_map.setdefault(lid, []).append(f"@Overview/{name}/{lb}")
    ochildren.append(entry)
ov.save(os.path.join(OUT, "images", "maps", "overview.png"), optimize=True)
maps_json.append({"name": "Overview", "img": "images/maps/overview.png", "location_size": 22,
                  "location_border_thickness": 3})
loc_groups.append(("overview.json", [{"name": "Overview", "children": ochildren}]))

# shops: priced for the chapter where their address is found in vanilla (same as the apworld)
RC = {1: 1, 2: 1, 3: 3, 4: 4, 5: 5, 6: 7, 7: 8, 8: 9, 9: 10, 10: 10}
SHOP_TIER = {}
for l in LOCS:
    if l.get("vanilla") and ("rank" in l or "chapter" in l):
        t = RC[l["rank"]] if "rank" in l else l["chapter"]
        SHOP_TIER[l["vanilla"]] = min(t, SHOP_TIER.get(l["vanilla"], 99))
group = "Shops"
shops = {}
for l in LOCS:
    if l["kind"] == "shop_slot":
        shops.setdefault(l["shop"], []).append(l)
coords = list_map(group, "shops.png", [(shop_meta[s]["name"], shop_meta[s]["address_item"] or "always open")
                                       for s in sorted(shops)], "Shops (shopsanity)")
children = []
for s, xy in zip(sorted(shops), coords):
    ls = sorted(shops[s], key=lambda l: l["slot"])
    secs = [(f"Slot {l['slot'] + 1} ({l['vanilla']})", l["id"], [f"$shop_slot|{l['slot']}"]) for l in ls]
    addr = shop_meta[s]["address_item"]
    rule = ",".join(([ADDR_CODE[addr]] if addr else []) + [f"[$diffchapter|{SHOP_TIER.get(addr, 1)}]"])
    children.append(location(group, shop_meta[s]["name"], secs, [rule], group, xy, ["$shopsanity"]))
loc_groups.append(("shops.json", [{"name": group, "children": children}]))

# extras (options): DMW, Buster Sword proficiency, Magic Pot, mail
EXTRA_TABS = []
group = "DMW"
rows = [l for l in LOCS if l["kind"] in ("dmw_unlock", "dmw_memory", "magic_pot")]
rows.sort(key=lambda l: (l["kind"] == "magic_pot", l.get("slot", 9), l["kind"] == "dmw_memory", l.get("memory", 0)))
coords = list_map(group, "dmw.png", [(l["name"].replace("DMW - ", ""), {"dmw_unlock": f"story, Ch{l.get('chapter')}",
                  "dmw_memory": "memory scene", "magic_pot": "Jump, Fira, Gravity, Assault Twister"}[l["kind"]])
                  for l in rows], "DMW (DMW Characters / DMW Memories / Magic Pot options)")
children = []
for l, xy in zip(rows, coords):
    if l["kind"] == "dmw_unlock":
        rules, vis = ([f"$chapter|{l['chapter']}"] if l["chapter"] > 1 else []), ["$opt|dmw_characters"]
    elif l["kind"] == "dmw_memory":
        rules, vis = [f"$dmw_memory|{l['slot']}"], ["$opt|dmw_memories"]
    else:
        rules, vis = [f"$mission_open|{l['rank']}|{slug(l['region'])}|{l.get('unlock_ch', 0)},[$rank_chapter|{l['rank']}]"], ["$opt|magic_pot"]
    children.append(location(group, l["name"].replace("DMW - ", ""), [("Check", l["id"], None)], rules, group, xy, vis))
loc_groups.append(("dmw.json", [{"name": group, "children": children}]))
EXTRA_TABS.append({"title": "DMW", "content": {"type": "map", "maps": [group]}})

group = "Buster Sword"
rows = sorted((l for l in LOCS if l["kind"] == "proficiency"), key=lambda l: l["percent"])
coords = list_map(group, "buster.png", [(l["name"], "from Chapter 6") for l in rows],
                  "Buster Sword proficiency (client: /proficiency shows the current %)")
children = [location(group, l["name"], [("Check", l["id"], None)], ["$chapter|6"], group, xy, [f"$prof|{l['percent']}"])
            for l, xy in zip(rows, coords)]
loc_groups.append(("buster.json", [{"name": group, "children": children}]))
EXTRA_TABS.append({"title": "Buster Sword", "content": {"type": "map", "maps": [group]}})

group = "NPC missions"
rows = sorted((l for l in LOCS if l["kind"] == "npc_mission"), key=lambda l: [int(x) for x in l["number"].split("-")])
coords = list_map(group, "npc.png", [(l["name"].split(" - NPC handout")[0], l["name"].split("NPC handout ")[1] + f", Ch{l['chapter']}")
                                     for l in rows], "NPC mission handouts (NPC Mission Checks option; missed one? /warp back to its chapter)")
children = [location(group, l["name"].split(" - NPC handout")[0], [("Check", l["id"], None)],
                     [f"$chapter|{l['chapter']}"] if l["chapter"] > 1 else [], group, xy, ["$opt|npc_mission_checks"])
            for l, xy in zip(rows, coords)]
loc_groups.append(("npc.json", [{"name": group, "children": children}]))
EXTRA_TABS.append({"title": "NPC missions", "content": {"type": "map", "maps": [group]}})

mails = [l for l in LOCS if l["kind"] == "mail"]
mail_tabs, children = [], []
for title, sel in (("Ch1-5", lambda l: "rank" not in l and l["chapter"] <= 5),
                   ("Ch6-10", lambda l: "rank" not in l and l["chapter"] > 5),
                   ("Missions", lambda l: "rank" in l)):
    rows = sorted((l for l in mails if sel(l)), key=lambda l: (l.get("chapter", 0), l.get("number", ""), l["mail"][0]))
    mapname = f"Mail {title}"
    coords = list_map(mapname, f"mail_{slug(title)}.png",
                      [(l["name"].replace("Mail - ", ""), f"M{l['number']}" if "rank" in l else
                        f"Ch{l['chapter']}" + (", optional" if l["mail_kind"] == "optional" else "")) for l in rows],
                      f"Mail ({title}) - mailsanity")
    for l, xy in zip(rows, coords):
        rules = ([f"$mission_open|{l['rank']}|{slug(l['region'])}|{l.get('unlock_ch', 0)},[$rank_chapter|{l['rank']}]"] if "rank" in l
                 else [f"$chapter|{l['chapter']}"] if l["chapter"] > 1 else [])
        children.append(location("Mail", l["name"].replace("Mail - ", ""), [("Check", l["id"], None)], rules,
                                 mapname, xy, ["$opt|mailsanity"]))
    mail_tabs.append({"title": f"{title} ({len(rows)})", "content": {"type": "map", "maps": [mapname]}})
loc_groups.append(("mail.json", [{"name": "Mail", "children": children}]))
EXTRA_TABS.append({"title": "Mail", "content": {"type": "tabbed", "tabs": mail_tabs}})

wjson("maps/maps.json", maps_json)
for fn, obj in loc_groups:
    wjson(f"locations/{fn}", obj)

# ------------------------------------------------------------------ layouts
grid = [[f"goddess_{g.lower()}" for g in GODDESS],
        ["rank", "chapterkey", "accslot", "steal"],
        [f"addr_{s}" for s in range(1, 9)],
        [f"addr_{s}" for s in range(9, 16)],
        [f"dmw_{n.lower()}" for n in DMW_CHARS] + ["magicpot"]]
tabs = [{"title": "Overview", "content": {"type": "map", "maps": ["Overview"]}},
        {"title": "Story", "content": {"type": "tabbed", "tabs": [
            {"title": f"Ch{c}", "content": {"type": "tabbed", "tabs": STORY_TABS[c]}} for c in range(1, 11)]}},
        {"title": "Missions", "content": {"type": "tabbed", "tabs": [
            {"title": f"M{c}", "content": {"type": "tabbed", "tabs": MISSION_TABS[c]}} for c in range(1, 11)]}},
        {"title": "Shops", "content": {"type": "map", "maps": ["Shops"]}},
        {"title": "Extras", "content": {"type": "tabbed", "tabs": EXTRA_TABS}}]
main = {"type": "dock", "dropshadow": True, "content": [
    {"type": "dock", "dock": "left", "v_alignment": "stretch", "content": [
        {"type": "group", "header": "Items", "content": {"type": "layout", "key": "shared_item_grid"}}]},
    {"type": "tabbed", "tabs": tabs}]}
wjson("layouts/tracker.json", {
    "shared_item_grid": {"type": "itemgrid", "item_margin": "3,3", "item_size": 40, "rows": grid},
    "tracker_default": {"type": "container", "background": "#0c0d10", "content": main},
    "tracker_broadcast": {"type": "layout", "key": "shared_item_grid"},
})

# ------------------------------------------------------------------ scripts
def lua_str(v):
    """Quoted Lua string literal (names can contain quotes, e.g. the mail 'Thoughts on "the gift of the goddess"')."""
    return '"' + v.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


with open(os.path.join(OUT, "scripts/autotracking/item_mapping.lua"), "w") as f:
    f.write("ITEM_MAPPING = {\n")
    for iid, (code, typ) in sorted(item_map.items()):
        f.write(f'  [{iid}] = {{{lua_str(code)}, {lua_str(typ)}}},\n')
    f.write("}\n")
with open(os.path.join(OUT, "scripts/autotracking/location_mapping.lua"), "w") as f:
    f.write("LOCATION_MAPPING = {\n")
    for lid, paths in sorted(loc_map.items()):
        f.write(f'  [{lid}] = {{' + ", ".join(lua_str(p) for p in paths) + '},\n')
    f.write("}\n")

with open(os.path.join(OUT, "scripts/logic.lua"), "w") as f:
    f.write('''-- Logic mirrors apworld/ccff7r/__init__.py. Settings come from slot_data (scripts/autotracking.lua).
SLOT = {mission_unlocks = 2, starting_mission_rank = 2, chapter_gating = false, mission_difficulty_logic = true,
        shop_slots = 16, skip = {}, skip_loc = {}, dmw_characters = false, dmw_memories = false, magic_pot = false,
        mailsanity = false, npc_mission_checks = false, proficiency_checks = 0}
DMW_CODES = {"dmw_sephiroth", "dmw_angeal", "dmw_tseng", "dmw_cloud", "dmw_aerith", "dmw_cissnei", "dmw_genesis"}
RANK_CHAPTER = {1, 1, 3, 4, 5, 7, 8, 9, 10, 10}

local function count(code)
  -- ProviderCountForCode: 1 for an active toggle, the count for a consumable (AcquiredCount is 0 on toggles)
  return Tracker:ProviderCountForCode(code) or 0
end

function chapter(n)
  n = tonumber(n)
  if n <= 1 or not SLOT.chapter_gating then return true end
  return count("chapterkey") >= n - 1
end

-- mission_open: can you start it in the game (set / rank items); rank_chapter: difficulty logic. Tracker rules use
-- "$mission_open|r|set,[$rank_chapter|r]" so an open-but-early mission shows yellow (sequence break), not red.
function mission_open(rank, set, unlock_ch)
  rank = tonumber(rank)
  local mode = SLOT.mission_unlocks
  if mode == 0 and count("set_" .. set) == 0 then return false end
  -- per_set: missions the game opens at a chapter start (directly or via their chain) also need that chapter
  if mode == 0 and unlock_ch and tonumber(unlock_ch) > 1 and not chapter(unlock_ch) then return false end
  if mode == 2 and rank > SLOT.starting_mission_rank + count("rank") then return false end
  return true
end

function rank_chapter(rank)
  if not SLOT.mission_difficulty_logic then return true end
  return chapter(RANK_CHAPTER[tonumber(rank)])
end

function mission(rank, set)
  rank = tonumber(rank)
  local mode = SLOT.mission_unlocks
  if mode == 0 and count("set_" .. set) == 0 then return false end
  if mode == 2 and rank > SLOT.starting_mission_rank + count("rank") then return false end
  if SLOT.mission_difficulty_logic then return chapter(RANK_CHAPTER[rank]) end
  return true
end

function not_skipped(tid)
  return not SLOT.skip[tonumber(tid)]
end

function loc_on(id)
  return not SLOT.skip_loc[tonumber(id)]
end

function opt(name)
  return SLOT[name] and true or false
end

function prof(pct)
  return tonumber(pct) <= (SLOT.proficiency_checks or 0)
end

local DMW_ORDER = {"dmw_sephiroth", "dmw_angeal", "dmw_tseng", "dmw_cloud", "dmw_aerith", "dmw_cissnei", "dmw_genesis"}
function dmw_memory(slot)
  if not chapter(10) then return false end
  if SLOT.dmw_characters then return count(DMW_ORDER[tonumber(slot) + 1]) > 0 end
  return true
end

function diffchapter(n)
  if not SLOT.mission_difficulty_logic then return true end
  return chapter(n)
end

function shopsanity()
  return (SLOT.shop_slots or 0) > 0
end

function shop_slot(slot)
  return tonumber(slot) < (SLOT.shop_slots or 0)
end
''')

with open(os.path.join(OUT, "scripts/autotracking.lua"), "w") as f:
    f.write('''ScriptHost:LoadScript("scripts/autotracking/item_mapping.lua")
ScriptHost:LoadScript("scripts/autotracking/location_mapping.lua")

CUR_INDEX = -1

local function reset_object(code, typ)
  local o = Tracker:FindObjectForCode(code)
  if not o then return end
  if code:sub(1, 1) == "@" then
    o.AvailableChestCount = o.ChestCount
  elseif typ == "consumable" then
    o.AcquiredCount = 0
  else
    o.Active = false
  end
end

function onClear(slot_data)
  CUR_INDEX = -1
  for _, v in pairs(LOCATION_MAPPING) do for _, p in ipairs(v) do reset_object(p) end end
  for _, v in pairs(ITEM_MAPPING) do reset_object(v[1], v[2]) end
  if slot_data then
    if slot_data.mission_unlocks ~= nil then SLOT.mission_unlocks = slot_data.mission_unlocks end
    if slot_data.starting_mission_rank ~= nil then SLOT.starting_mission_rank = slot_data.starting_mission_rank end
    if slot_data.chapter_gating ~= nil then SLOT.chapter_gating = slot_data.chapter_gating and true or false end
    if slot_data.mission_difficulty_logic ~= nil then SLOT.mission_difficulty_logic = slot_data.mission_difficulty_logic and true or false end
    SLOT.shop_slots = slot_data.shop_slots or 0
    for _, k in ipairs({"dmw_characters", "dmw_memories", "magic_pot", "mailsanity", "npc_mission_checks"}) do
      SLOT[k] = slot_data[k] and true or false
    end
    SLOT.proficiency_checks = slot_data.proficiency_checks or 0
    SLOT.skip = {}
    for _, t in ipairs(slot_data.skip_treasures or {}) do SLOT.skip[t] = true end
    SLOT.skip_loc = {}
    for _, t in ipairs(slot_data.skip_locations or {}) do SLOT.skip_loc[t] = true end
  end
  local r = Tracker:FindObjectForCode("settings_refresh")      -- poke the tracker so rules re-evaluate
  if r then r.AcquiredCount = (r.AcquiredCount or 0) + 1 end
end

function onItem(index, item_id, item_name, player_number)
  if index <= CUR_INDEX then return end
  CUR_INDEX = index
  local v = ITEM_MAPPING[item_id]
  if not v then return end
  local o = Tracker:FindObjectForCode(v[1])
  if not o then return end
  if v[2] == "consumable" then
    o.AcquiredCount = o.AcquiredCount + o.Increment
  else
    o.Active = true
  end
end

function onLocation(location_id, location_name)
  local v = LOCATION_MAPPING[location_id]
  if not v then return end
  for _, p in ipairs(v) do
    local o = Tracker:FindObjectForCode(p)
    if o then o.AvailableChestCount = o.AvailableChestCount - 1 end
  end
end

Archipelago:AddClearHandler("ccff7r clear", onClear)
Archipelago:AddItemHandler("ccff7r item", onItem)
Archipelago:AddLocationHandler("ccff7r location", onLocation)
''')

with open(os.path.join(OUT, "scripts", "init.lua"), "w") as f:   # PopTracker entry point is scripts/init.lua
    f.write('Tracker:AddItems("items/items.json")\n')
    f.write('ScriptHost:LoadScript("scripts/logic.lua")\n')
    f.write('Tracker:AddMaps("maps/maps.json")\n')
    for fn, _ in loc_groups:
        f.write(f'Tracker:AddLocations("locations/{fn}")\n')
    f.write('Tracker:AddLayouts("layouts/tracker.json")\n')
    f.write('if Archipelago then ScriptHost:LoadScript("scripts/autotracking.lua") end\n')

wjson("manifest.json", {
    "name": "Crisis Core -FFVII- Reunion AP",
    "game_name": "Crisis Core -Final Fantasy VII- Reunion",
    "package_uid": "ccff7r_ap_assymcjerk",
    "package_version": VERSION,
    "platform": "pc",
    "author": "AssyMcJerk",
    "min_poptracker_version": "0.25.0",
    "variants": {"ap": {"display_name": "Archipelago", "flags": ["ap"]}},
})

zpath = os.path.join(ROOT, "ccff7r_poptracker.zip")
with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
    for root, _, files in os.walk(OUT):
        for fn in files:
            p = os.path.join(root, fn)
            z.write(p, os.path.relpath(p, OUT))
print(f"pack: {len(loc_map)} checks mapped, {len(item_map)} items mapped, {len(maps_json)} list maps -> {zpath}")
