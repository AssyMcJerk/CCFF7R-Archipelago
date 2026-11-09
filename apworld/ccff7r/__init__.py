"""Crisis Core -Final Fantasy VII- Reunion (PC) — Archipelago world (alpha)."""
from BaseClasses import Region, ItemClassification, LocationProgressType
from worlds.AutoWorld import World, WebWorld
from worlds.LauncherComponents import Component, components, Type, launch as launch_component
from .options import CCFF7ROptions
from .items import ITEMS, ITEM_BY_NAME, GODDESS, CLASS, CCFF7RItem, item_name_to_id, item_name_groups
from .locations import LOCATIONS, RANK_CHAPTER, CCFF7RLocation, location_name_to_id

GAME = "Crisis Core -Final Fantasy VII- Reunion"
GODDESS_TREASURES = range(550, 557)
JAIL_CELLS = range(160, 178)                       # Ch4 jail cells (scene 5159), 18 chests
STEAL_MATERIA = ("Steal", "Steal (1* AP+1)", "Mug (1* AP+2)")
SHOP_ADDRESSES = {l["address"] for l in LOCATIONS if l.get("address")}
MISSION_KINDS = ("mission_reward", "mission_chest", "mission_bonus")
CHAPTER_KINDS = ("story_chest", "chapter_clear", "dmw_unlock", "dmw_memory", "proficiency", "npc_mission",
                 "minigame_event")
NPC_CHAPTER = {l["mission"]: l["chapter"] for l in LOCATIONS if l["kind"] == "npc_mission"}
DMW_CHARS = ["Sephiroth", "Angeal", "Tseng", "Cloud", "Aerith", "Cissnei", "Genesis"]
FILLER = ("Potion", "Potion", "Hi-Potion", "Ether", "Phoenix Down")
EXPENSIVE_SHOP_ITEMS = {"Genji Helm"}             # shop slots priced out of normal play (user: 1,000,000 gil)
# "tier" = the chapter by which a location is normally reached (missions: RANK_CHAPTER of their rank)
_SOURCE_TIER = {}
for _l in LOCATIONS:
    if _l.get("vanilla") and ("rank" in _l or "chapter" in _l):
        _t = RANK_CHAPTER[_l["rank"]] if "rank" in _l else _l["chapter"]
        _SOURCE_TIER[_l["vanilla"]] = min(_t, _SOURCE_TIER.get(_l["vanilla"], 99))
# shops are priced for the point where their address is found in vanilla (Shinra Shop: from the start)
SHOP_TIER = {l["region"]: _SOURCE_TIER.get(l.get("address"), 1) for l in LOCATIONS if l["kind"] == "shop_slot"}
_FIRST_RANK = {l["mission"]: l["rank"] for l in LOCATIONS if l["kind"] == "mission_reward"}
SET_TIER = {i["name"]: RANK_CHAPTER[_FIRST_RANK[i["payload"]["first_mission"]]]
            for i in ITEMS if i["payload"].get("type") == "mission_set"}


def _FIRST_RANK_OF_SET(name):
    i = next(i for i in ITEMS if i["name"] == name)
    return _FIRST_RANK[i["payload"]["first_mission"]]


def loc_tier(loc):
    if "rank" in loc:
        return max(RANK_CHAPTER[loc["rank"]], loc.get("unlock_ch", 0))
    if loc["kind"] == "shop_slot":
        return SHOP_TIER[loc["region"]]
    return loc.get("chapter", 1)


def launch_client(*args):
    from .client import launch
    launch_component(launch, name="CCFF7RClient", args=args)


components.append(Component("CCFF7R Client", func=launch_client, component_type=Type.CLIENT))


class CCFF7RWeb(WebWorld):
    theme = "ocean"


class CCFF7RWorld(World):
    """Zack Fair's story. Story chests, missions and chapter clears are checks; missions open by rank."""
    game = GAME
    web = CCFF7RWeb()
    options_dataclass = CCFF7ROptions
    options: CCFF7ROptions
    item_name_to_id = item_name_to_id
    location_name_to_id = location_name_to_id
    item_name_groups = item_name_groups
    topology_present = False

    # ------------------------------------------------------------------ helpers
    def chapter_ok(self, state, ch):
        if ch <= 1 or not self.options.chapter_gating:
            return True
        return state.has("Progressive Chapter Key", self.player, ch - 1)

    def mission_mode(self):
        o = self.options.mission_unlocks
        return {o.option_per_set: "per_set", o.option_vanilla: "vanilla", o.option_progressive_rank: "rank"}[o.value]

    def skipped(self, loc):
        k, o = loc["kind"], self.options
        if k == "dmw_unlock":
            return not o.dmw_characters
        if k == "dmw_memory":
            return not o.dmw_memories
        if k == "proficiency":
            return loc["percent"] > o.buster_sword_proficiency.value // 10 * 10
        if k == "magic_pot" and not o.magic_pot:
            return True
        if k == "mail" and not o.mailsanity:
            return True
        if k == "npc_mission":
            return not o.npc_mission_checks
        if "rank" in loc:                      # missions, mission mails, the Magic Pot
            return loc["rank"] > o.max_mission_rank.value
        if loc["kind"] == "shop_slot":
            return loc["slot"] >= self.options.shop_slots.value
        mg = loc.get("minigame")
        ex = self.options.excluded_minigames.value
        return bool(mg) and ("all" in ex or mg in ex)

    def create_item(self, name):
        d = ITEM_BY_NAME[name]
        cls = CLASS[d["classification"]]
        if d["payload"].get("type") == "dmw_slot" and self.options.dmw_memories:
            cls = ItemClassification.progression       # memories need their character
        if name in SHOP_ADDRESSES and self.options.shop_slots.value:
            cls = ItemClassification.progression
        return CCFF7RItem(name, cls, d["id"], self.player)

    # ------------------------------------------------------------------ regions
    def create_regions(self):
        mw, p = self.multiworld, self.player
        menu = Region("Menu", p, mw)
        mw.regions.append(menu)
        chapters = {}
        for ch in range(1, 11):
            r = Region(f"Chapter {ch}", p, mw)
            mw.regions.append(r)
            chapters[ch] = r
            menu.connect(r, f"To Chapter {ch}", lambda s, c=ch: self.chapter_ok(s, c))
        mode = self.mission_mode()
        start = self.options.starting_mission_rank.value
        sets = {}
        for loc in LOCATIONS:
            if loc["kind"] in ("mission_reward", "mission_chest", "mission_bonus") and loc["region"] not in sets \
                    and not self.skipped(loc):
                r = Region(loc["region"], p, mw)
                mw.regions.append(r)
                sets[loc["region"]] = r
                item = f"Mission Set {loc['region']}"
                menu.connect(r, f"Open {loc['region']}",
                             (lambda s, it=item: s.has(it, p)) if mode == "per_set" else (lambda s: True))
        shops = {}
        for loc in LOCATIONS:
            if loc["kind"] == "shop_slot" and not self.skipped(loc) and loc["region"] not in shops:
                r = Region(loc["region"], p, mw)
                mw.regions.append(r)
                shops[loc["region"]] = r
                addr = loc.get("address")
                menu.connect(r, f"Open {loc['region']}", (lambda s, a=addr: s.has(a, p)) if addr else (lambda s: True))
        diff = bool(self.options.mission_difficulty_logic)
        maxrank = self.options.max_progression_rank.value
        for loc in LOCATIONS:
            if self.skipped(loc):
                continue
            kind = loc["kind"]
            region = (chapters[loc["chapter"]] if kind in CHAPTER_KINDS or (kind == "mail" and "rank" not in loc)
                      else shops[loc["region"]] if kind == "shop_slot" else sets[loc["region"]])
            l = CCFF7RLocation(p, loc["name"], loc["id"], region)
            if "rank" in loc:                           # missions, mission mails, the Magic Pot
                rank = loc["rank"]
                need_ch = RANK_CHAPTER[rank] if diff else 1
                if mode == "per_set":                   # opened at a chapter start (directly or via its chain)
                    need_ch = max(need_ch, loc.get("unlock_ch", 0))
                if self.options.npc_mission_checks and mode != "vanilla" and loc.get("mission") in NPC_CHAPTER:
                    need_ch = max(need_ch, NPC_CHAPTER[loc["mission"]])   # held locked until its NPC hands it out
                need_rank = max(0, rank - start) if mode == "rank" else 0
                l.access_rule = lambda s, c=need_ch, n=need_rank: \
                    self.chapter_ok(s, c) and (n == 0 or s.has("Progressive Mission Rank", p, n))
                if rank > maxrank:
                    l.item_rule = lambda it: not it.advancement
            if loc.get("also_on"):                          # also sent when its trigger location is checked
                trig = next((t for t in LOCATIONS if t["id"] == loc["also_on"]), None)
                if trig and not self.skipped(trig):
                    l.access_rule = lambda s, n=trig["name"]: s.can_reach_location(n, p)
            if loc.get("treasure") in JAIL_CELLS:           # the cell keys have to be stolen from the guards
                l.access_rule = lambda s: s.has_any(STEAL_MATERIA, p)
            if loc.get("unverified"):
                l.progress_type = LocationProgressType.EXCLUDED
            elif kind in ("story_chest", "dmw_unlock", "npc_mission", "minigame_event") \
                    and not self.options.missable_progression:
                l.item_rule = lambda it: not it.advancement      # can't revisit story areas
            if kind == "mail" and "rank" not in loc and (loc["mail_kind"] == "optional"
                                                         or not self.options.missable_progression):
                l.item_rule = lambda it: not it.advancement      # missable / story-timed mails
            if kind in ("dmw_memory", "proficiency", "magic_pot"):
                l.item_rule = lambda it: not it.advancement      # grindy: never required
            if kind == "dmw_memory" and self.options.dmw_characters:
                l.access_rule = lambda s, it=f"DMW: {DMW_CHARS[loc['slot']]}": s.has(it, p)
            if kind == "npc_mission":
                req = []
                if loc["number"] == "2-1-6":                # the researcher wants 2-1-1..2-1-5 cleared first
                    req = [l2["name"] for l2 in LOCATIONS if l2["kind"] == "mission_reward"
                           and l2["number"] in ("2-1-1", "2-1-2", "2-1-3", "2-1-4", "2-1-5")]
                elif loc["number"].startswith("4-3-") and loc["number"] != "4-3-1":   # spies: after 4-3-1's NPC
                    req = [l2["name"] for l2 in LOCATIONS if l2["kind"] == "npc_mission" and l2["number"] == "4-3-1"]
                l.access_rule = lambda s, c=loc["chapter"], req=tuple(req): self.chapter_ok(s, c) and all(
                    s.can_reach_location(n, p) for n in req)
            if kind == "shop_slot" and loc.get("vanilla") in EXPENSIVE_SHOP_ITEMS:
                l.item_rule = lambda it: not it.advancement      # 1,000,000 gil (Online Shop Shade): never required
            if kind == "shop_slot" and diff:                # shop prices: expect the gil of the shop's tier
                l.access_rule = lambda s, c=SHOP_TIER[loc["region"]]: self.chapter_ok(s, c)
            if mode == "per_set" and diff:                  # no high-rank set items in early locations of this world
                # (only with difficulty logic: without it the rule fights the per_set chapter requirements, fill
                # failed in ~1 of 6 seeds, doc 7.3ap)
                old, t = l.item_rule, loc_tier(loc)
                l.item_rule = lambda it, old=old, t=t: old(it) and not (
                    it.player == p and SET_TIER.get(it.name, 0) > t + 1)
            region.locations.append(l)
            if (self.options.goddess_materia == self.options.goddess_materia.option_vanilla
                    and loc.get("treasure") in GODDESS_TREASURES):
                l.place_locked_item(self.create_item(loc["vanilla"]))
            elif loc.get("locked"):                     # quest items that must stay with their giver
                l.place_locked_item(self.create_item(loc["vanilla"]))
        fin = CCFF7RLocation(p, "Defeat Genesis", None, chapters[10])
        fin.place_locked_item(CCFF7RItem("Victory", ItemClassification.progression, None, p))
        fin.access_rule = lambda s: s.has_all(GODDESS, p)      # the final door needs all 7
        chapters[10].locations.append(fin)
        mw.completion_condition[p] = lambda s: s.has("Victory", p)

    # ------------------------------------------------------------------ items
    def create_items(self):
        # Steal is needed in Ch4 (jail cell keys) and story areas can't be revisited -> put one in our sphere 1
        self.multiworld.local_early_items[self.player]["Steal"] = 1
        mode = self.mission_mode()
        pool = []
        if mode == "per_set":
            self.multiworld.push_precollected(self.create_item("Mission Set M1-1"))
            # two more rank-1 sets in this world's first sphere so the early game has missions to play
            early = sorted(n for n, t in SET_TIER.items() if _FIRST_RANK_OF_SET(n) == 1 and n != "Mission Set M1-1")
            for n in self.random.sample(early, min(2, len(early))):
                self.multiworld.local_early_items[self.player][n] = 1
            open_sets = {f"Mission Set {l['region']}" for l in LOCATIONS
                         if l["kind"] in ("mission_reward", "mission_chest", "mission_bonus") and not self.skipped(l)}
            pool += [self.create_item(i["name"]) for i in ITEMS
                     if i["payload"].get("type") == "mission_set" and i["name"] != "Mission Set M1-1"
                     and i["name"] in open_sets]
        elif mode == "rank":
            pool += [self.create_item("Progressive Mission Rank")
                     for _ in range(max(0, self.options.max_mission_rank.value
                                        - self.options.starting_mission_rank.value))]
        if self.options.chapter_gating:
            pool += [self.create_item("Progressive Chapter Key") for _ in range(9)]
        if self.options.dmw_characters:
            start = set(self.random.sample(DMW_CHARS, self.options.dmw_starting_characters.value))
            for c in DMW_CHARS:
                if c in start:
                    self.multiworld.push_precollected(self.create_item(f"DMW: {c}"))
                else:
                    pool.append(self.create_item(f"DMW: {c}"))
        if self.options.magic_pot:
            pool.append(self.create_item("Magic Pot Tricks"))
        for nm in ("Perfect Guard", "Command Kill", "Strong Attack Kill"):
            pool += [self.create_item(f"Proficiency Boost: {nm}") for _ in range(self.options.proficiency_boosts.value)]
        vanilla = []
        for i in ITEMS:
            if i["payload"].get("type") in (0, 1, 2, "accessory_slot"):
                vanilla += [i["name"]] * i["vanilla_count"]
        for loc in LOCATIONS:                 # skipped minigame / mission rewards stay in the game, not in the pool
            v = loc.get("vanilla")
            if self.skipped(loc) and v in vanilla:
                # keep progression (Steal) and shop addresses: other locations or shops may still need them
                if ITEM_BY_NAME[v]["classification"] == "progression" or v in SHOP_ADDRESSES:
                    continue
                vanilla.remove(v)
        if self.options.goddess_materia == self.options.goddess_materia.option_vanilla:
            for g in GODDESS:
                vanilla.remove(g)
        for loc in LOCATIONS:                 # locked quest items are placed at their own location
            if loc.get("locked") and not self.skipped(loc) and loc.get("vanilla") in vanilla:
                vanilla.remove(loc["vanilla"])
        if self.options.shop_slots.value:      # shopsanity: extra gil (sell value) in place of filler
            shop_locs = sum(1 for l in LOCATIONS if l["kind"] == "shop_slot" and not self.skipped(l))
            vanilla += ["Gold Rolling Pin"] * -(-shop_locs // 16)
        locs = len(self.multiworld.get_unfilled_locations(self.player))
        keep = [n for n in vanilla if ITEM_BY_NAME[n]["classification"] != "filler"]
        filler = [n for n in vanilla if ITEM_BY_NAME[n]["classification"] == "filler"]
        room = locs - len(pool) - len(keep)
        if room < 0:                          # few locations (low Max Mission Rank): drop useful extras
            spare = [n for n in keep if ITEM_BY_NAME[n]["classification"] == "useful" and n not in SHOP_ADDRESSES]
            self.random.shuffle(spare)
            for n in spare[:-room]:
                keep.remove(n)
            room = locs - len(pool) - len(keep)
        self.random.shuffle(filler)
        pool += [self.create_item(n) for n in keep + filler[:max(0, room)]]
        while len(pool) < locs:
            pool.append(self.create_item(self.get_filler_item_name()))
        self.multiworld.itempool += pool

    def get_filler_item_name(self):
        return self.random.choice(FILLER)

    def fill_slot_data(self):
        return {
            "chapter_gating": bool(self.options.chapter_gating),
            "mission_unlocks": self.options.mission_unlocks.value,
            "starting_mission_rank": self.options.starting_mission_rank.value,
            "exp_multiplier": self.options.exp_multiplier.value,
            "gil_multiplier": self.options.gil_multiplier.value,
            "death_link": bool(self.options.death_link),
            "death_link_queue": bool(self.options.death_link_queue),
            "skip_treasures": sorted(l["treasure"] for l in LOCATIONS if "treasure" in l and self.skipped(l)),
            "chapter_unlock_timing": True,
            "skip_locations": sorted(l["id"] for l in LOCATIONS if l["kind"] == "minigame_event" and self.skipped(l)),
            "shop_slots": self.options.shop_slots.value,
            "mission_difficulty_logic": bool(self.options.mission_difficulty_logic),
            "dmw_characters": bool(self.options.dmw_characters),
            "dmw_memories": bool(self.options.dmw_memories),
            "magic_pot": bool(self.options.magic_pot),
            "proficiency_checks": self.options.buster_sword_proficiency.value // 10 * 10,
            "mailsanity": bool(self.options.mailsanity),
            "npc_mission_checks": bool(self.options.npc_mission_checks),
            "wagon_random": True,                       # v0.6.4+: better wagon parts are in the pool
        }
