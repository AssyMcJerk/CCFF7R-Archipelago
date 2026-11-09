"""CCFF7R Archipelago client (alpha, v0.6.39).

Each tick (game running + save loaded):
  * every location chest/mission reward in the treasure table becomes a count-0 placeholder (all items,
    including your own, are delivered by the server -> no double rewards)
  * opened-treasure bits and the chapter byte -> LocationChecks
  * minigame prizes that never set an opened bit -> caught by a tiny hook on the script VM that logs
    TreasureGetId() calls (game/readhook.py; the only code patch the client makes)
  * received items -> written straight into the inventory / gil / SP; Mission Set items unlock missions
  * per_set mode: missions of sets you don't have yet are kept locked
  * EXP multiplier
Received-item progress is stored per seed+slot in <AP user dir>/ccff7r/<seed>_<slot>.json.
"""
import asyncio, json, os, random, struct, time, zlib

import Utils
from CommonClient import CommonContext, ClientCommandProcessor, gui_enabled, logger, get_base_parser, server_loop
from NetUtils import ClientStatus

from .items import ITEMS
from .locations import LOCATIONS

GAME = "Crisis Core -Final Fantasy VII- Reunion"
ITEM_BY_ID = {i["id"]: i for i in ITEMS}
TREASURE_LOCS = {l["treasure"]: l["id"] for l in LOCATIONS if "treasure" in l}
SHOP_LOCS = {(l["shop"], l["slot"]): l["id"] for l in LOCATIONS if l["kind"] == "shop_slot"}
SHOP_SLOT_ITEM = {l["id"]: (l["shop"], l["vanilla_payload"]["id"], l["vanilla"]) for l in LOCATIONS
                  if l["kind"] == "shop_slot"}
LOC_NAME = {l["id"]: l["name"] for l in LOCATIONS}
DEATH_LINES = (                                  # DeathLink message sent when Zack dies (one picked at random)
    "{name} spun the DMW and got nothing but silhouettes.",
    "{name} forgot to Perfect Guard.",
    "{name} won't be making 1st Class today.",
    "{name} ran out of Phoenix Downs.",
    "{name} got flattened by a Behemoth.",
    "{name} lost a fight to a Tonberry. Again.",
    "{name} should have bought more Potions at the Shinra Shop.",
    "{name} learned that Cactuars hit for exactly 1000.",
    "{name}'s Buster Sword proficiency did not help.",
    "{name} took a Genesis copy's blade to the face.",
    "{name} skipped the squats and paid for it.",
    "{name} is now a very honorable puddle.",
)

DEATH_RECEIVED_LINES = (                         # client log line when a received DeathLink kills Zack
    "{source} died, and the DMW took Zack with them.",
    "{source} went down. Zack's honor demands he follows.",
    "{source} fell, and Zack's SOLDIER training didn't cover this.",
    "{source} died. Zack drops mid-swing.",
    "{source} perished. The Lifestream calls for Zack too.",
    "{source} is out. Zack's Phoenix Down was on backorder.",
    "{source} died, and a Tonberry quietly followed it up on Zack.",
    "{source} took the fall. Zack takes one too.",
)

READ_LOCS = {l["treasure"]: l["id"] for l in LOCATIONS if l.get("detect") == "read"}
EVENT_LOCS = [l for l in LOCATIONS if l["kind"] == "minigame_event"]   # completions without an item (doc 7.3ai)
NATIVE_EVENTS = {}                 # script native -> [location]
for _l in EVENT_LOCS:
    if "native" in _l["trigger"]:
        NATIVE_EVENTS.setdefault(_l["trigger"]["native"], []).append(_l)
PERFUME_WINDOW = 30                # s between paying for a blend and Aerith's +5
# treasure groups: mutually exclusive rewards (e.g. Fort Tamblin soldier-count tiers 25-28); opening any one
# member checks every member, since a revisit can't reach the other tiers
TREASURE_GROUP = {}
for _l in LOCATIONS:
    if _l.get("group"):
        TREASURE_GROUP.setdefault(_l["group"], []).append(_l["id"])
GROUP_OF = {l["id"]: TREASURE_GROUP[l["group"]] for l in LOCATIONS if l.get("group")}
# one-way links: checking the trigger location also checks these (e.g. clearing 2-1-6 sends Mythril Tools, whose
# giver disappears once 2-1-6 is cleared)
ALSO_ON = {}
for _l in LOCATIONS:
    if _l.get("also_on"):
        ALSO_ON.setdefault(_l["also_on"], []).append(_l["id"])
PATCHED = [t for t in TREASURE_LOCS
           if not next(l for l in LOCATIONS if l.get("treasure") == t).get("unverified")]   # unverified chests stay vanilla
MISSION_RANK = {l["mission"]: l["rank"] for l in LOCATIONS if l["kind"] == "mission_reward"}
GOAL_STORY = 11000             # story_count after the final boss (playtest 1: 10063 -> 11000 -> credits)
CHAPTER_LOCS = {l["chapter"]: l["id"] for l in LOCATIONS if l["kind"] == "chapter_clear"}
SET_MISSIONS = {}
for l in LOCATIONS:
    if "mission" in l and l["kind"] != "npc_mission":     # NPC handouts sit in "Chapter N" regions, not sets
        SET_MISSIONS.setdefault(l["region"], set()).add(l["mission"])
CHAPTER_UNLOCK = {}               # set -> [(mission, chapter)]: missions vanilla opens at a chapter start
for l in LOCATIONS:
    if l.get("chapter_unlock"):
        CHAPTER_UNLOCK.setdefault(l["region"], []).append((l["mission"], l["chapter_unlock"]))
SET_FIRST = {i["payload"]["set"]: i["payload"]["first_mission"] for i in ITEMS
             if i["payload"].get("type") == "mission_set"}
SNAP_BASE, SNAP_SIZE = 0x71B3F00, 0x2400     # /snapshot: the saved state block (char_status = exe+71B3F00)
SNAP_NOISE = ((0x08, 0x0C), (0xB8, 0xC0))     # Zack EXP, play time: change constantly
PLACEHOLDER = (0x2000, 0)          # "Potion x0" = nothing

# v0.6 optional checks (ids from apworld_build/build_data.py)
DMW_UNLOCK_LOCS = {l["slot"]: (l["id"], l["chapter"]) for l in LOCATIONS if l["kind"] == "dmw_unlock"}
DMW_MEMORY_LOCS = {(l["slot"], l["memory"]): l["id"] for l in LOCATIONS if l["kind"] == "dmw_memory"}
PROFICIENCY_LOCS = {l["percent"]: l["id"] for l in LOCATIONS if l["kind"] == "proficiency"}
# chapter byte at which a DMW unlock check is sent anyway (character received before its story moment):
# start of the chapter for start-of-chapter joins, the next chapter for mid-chapter ones
DMW_FALLBACK_CB = {0: 1, 1: 1, 2: 2, 3: 6, 4: 5, 5: 4, 6: 6}   # Seph/Angeal Ch1, Tseng Ch2 start, Cissnei Ch3,
#                                                                Aerith Ch5 start, Cloud/Genesis during Ch5
MAGIC_POT_LOC = next(l["id"] for l in LOCATIONS if l["kind"] == "magic_pot")
MAGIC_POT_ITEM, MAGIC_POT_MISSION = 0x3025, 238            # key item "Magic Pot Tricks", mission 10-2-3
NPC_LOCS = {l["mission"]: l["id"] for l in LOCATIONS if l["kind"] == "npc_mission"}
NPC_MISSIONS = set(NPC_LOCS)
NPC_CH = {l["mission"]: l["chapter"] for l in LOCATIONS if l["kind"] == "npc_mission"}
NPC_WHO = {l["mission"]: l["name"].rsplit("(", 1)[-1].rstrip(")") for l in LOCATIONS if l["kind"] == "npc_mission"}
# Flower wagon: better parts (randomized since v0.6.4) by category, and the treasure ids of that category's givers.
# A giver skips you if you already hold a part of its category, so a received part is held back until they're done.
WAGON_CAT = {0x3038: "manual", 0x303C: "manual", 0x3039: "wood", 0x303D: "wood",
             0x303A: "tires", 0x303E: "tires", 0x303B: "tools", 0x303F: "tools"}
WAGON_GIVERS = {"manual": (397, 401), "wood": (398, 402), "tires": (399, 403), "tools": (400, 404)}
WAGON_HOLD_UNTIL_CB = 9               # squats / spies stay possible through Ch8
WAGON_FLAGS = 0xFA                    # 8 spare treasure bits (ids 2000-2007), saved with the game: part handed over
# Ch7 cheap parts (pickups 405-408 in Ch7): the pickup scene force-walks Zack if you already own the part (tester), and
# the wagon groups send them early together with 397-400. Held until the pickup's own treasure bit is set, or Ch8.
WAGON_CHEAP = {0x3040: 405, 0x3041: 406, 0x3042: 407, 0x3043: 408}
WAGON_CHEAP_FLAGS = 0xFB              # bits 0-3 held, bits 4-7 handed over (treasure ids 2008-2015)
WAGON_CHEAP_UNTIL_CB = 8
PROF_FLAGS = 0xF8                     # treasure bytes +0xF8/+0xF9 (ids 1984-1999): boosts applied per part, 4 bits each
CHEAP_NAME = {i["payload"]["id"]: i["name"] for i in ITEMS
              if i["payload"].get("type") == 0 and i["payload"].get("id") in WAGON_CHEAP and i["payload"].get("amount") == 1}
MAIL_LOCS = {m: l["id"] for l in LOCATIONS if l["kind"] == "mail" for m in l["mail"]}

# chapter -> (opener scene, story_count at chapter start)   (research doc 7.3f/7.3g)
CHAPTER_START = {1: (5011, 1000), 2: (5057, 2001), 3: (5109, 3000), 4: (5150, 4000), 5: (5200, 5000),
                 6: (5250, 6000), 7: (5260, 6500), 8: (5300, 7000), 9: (5311, 8000), 10: (5450, 10000)}
# chapter -> (jump that leaves the chapter's last free field for its ending, story_count while standing in that field).
# The gate must be armed BEFORE the ending starts: the ending scripts raise story_count and jump within a frame or two
# (tester, Ch2: story 2072 -> 2090 -> jump 5054 happened between two client polls, so the old Ch2 gate never fired).
# Values from the playtest jump log: the story value is the one logged on the jump INTO that last field.
#   Ch1 5015 -> 5018 | Ch2 5051 -> 5056 (Banora burning -> bombing/Bahamut) | Ch3 5107 -> 5106 | Ch4 5155 -> 5158
#   Ch5 5213 -> 5214 | Ch6 5255 -> 5256 | Ch7 5272 -> 5261 | Ch8 5310 -> 5306 (reactor) | Ch9 5403 -> 5405
CHAPTER_GATE = {1: (5018, 1402), 2: (5056, 2071), 3: (5106, 3027), 4: (5158, 4550), 5: (5214, 5111),
                6: (5256, 6302), 7: (5272, 6601), 8: (5306, 7320), 9: (5405, 9060)}
# Ch7: the gate used to sit on 5261 (story 6702), after the wagon parts were already handed to Aerith in 5272 (story
# 6601 -> 6650); a bounce there left the quest unfinishable. It now stops the walk back into her church (5272) while
# the parts quest runs (story >= 6601, user's snapshots 2026-10-31). doc 7.3ao
# Where a gated chapter sends you back: (scene or None = the scene you're in, entrance spawn?). Default (None, False)
# = mission-return bounce into the current scene (tested Ch1). Tester run 3 (2026-11-06): Ch7's mission-return
# bounce dropped Zack under the church floor -> entrance spawn; Ch8 bounced back into the reactor (Sephiroth loop)
# -> the field outside it (5309, save point). doc 7.3ap
GATE_BOUNCE = {6: (None, True), 7: (None, True), 8: (5309, True)}
# Chapters whose ending is resumed by the client after a bounce: the gated jump comes after something that can't be
# replayed (Ch6: Guard Scorpion is fought inside 5255 before the jump to 5256). Once the key is there, the next
# mission start is turned into that jump.
GATE_RESUME = {6}
# unlock-group flags set by ChapterClear: chapters cleared -> groups (doc 3.5)
UNLOCK_GROUPS = {1: (0, 1, 2), 2: (3, 4), 3: (5, 6, 7), 8: (8,)}


class CCFF7RCommands(ClientCommandProcessor):
    def _cmd_status(self):
        """Show game attachment and progress."""
        ctx: CCFF7RContext = self.ctx
        if ctx.game_mem:
            g = ctx.game_mem
            logger.info(f"story {g.story_count()}  chapter byte {g.chapter_byte()}  gil {g.gil()}  "
                        f"received {ctx.applied}/{len(ctx.items_received)}")
        else:
            logger.info("game not attached")

    def _cmd_warp(self, chapter: str = ""):
        """Chapter select: /warp <chapter> (incl. earlier chapters), /warp cancel, /warp (list)."""
        ctx: CCFF7RContext = self.ctx
        hook = ctx.jump_hook
        allowed = ctx.warp_limit()
        if not chapter:
            logger.info(f"Chapters you can warp to: 1-{allowed}. Furthest reached: {ctx.max_chapter}. "
                        f"Usage: /warp <chapter>, then start any mission.")
            return
        if hook is None or hook.state != "active":
            logger.info("Chapter select needs the game attached (and no Cheat Engine script on the jump hook).")
            return
        if chapter.lower() == "cancel":
            hook.arm_warp(0)
            ctx.warp_target = None
            logger.info("Warp cancelled.")
            return
        try:
            n = int(chapter)
        except ValueError:
            logger.info("Usage: /warp <chapter number>")
            return
        if not 1 <= n <= allowed:
            logger.info(f"Chapter {n} is not available (you can warp to 1-{allowed}).")
            return
        ctx.warp_target = n
        ctx.warp_snapshot = ctx.game_mem.pm.read_bytes(ctx.game_mem.a["state_mission_state"], 300 * 3)
        hook.arm_warp(CHAPTER_START[n][0])
        logger.info(f"Warp to Chapter {n} armed: open the mission menu at a save point and start ANY mission. "
                    f"(/warp cancel to undo)")

    def _cmd_shops(self, shop: str = ""):
        """Shopsanity: list what the AP slots of each shop hold. /shops <part of a shop name> to filter."""
        ctx: CCFF7RContext = self.ctx
        if not ctx.slot_data.get("shop_slots"):
            logger.info("Shopsanity is off for this seed.")
            return
        for lid in sorted(ctx.shop_scouts):
            name = LOC_NAME.get(lid, str(lid))
            if shop and shop.lower() not in name.lower():
                continue
            it = ctx.shop_scouts[lid]
            done = "  [bought]" if lid in ctx.checked_locations else ""
            logger.info(f"{name}: {ctx.item_names.lookup_in_slot(it.item, it.player)} "
                        f"for {ctx.player_names.get(it.player, it.player)}{done}")

    def _cmd_claimsave(self):
        """Use the loaded save for the connected seed even though it was played with another seed/slot."""
        self.ctx.claim_save = True
        logger.info("The loaded save will be claimed for this seed on the next update.")

    def _cmd_scriptlog(self, mode: str = ""):
        """Research aid: '/scriptlog on' also shows minigame events and unknown prize reads in this window (each
        distinct one once per session). They always go to <AP>/ccff7r/script_log.txt. '/scriptlog off' hides them."""
        ctx = self.ctx
        if mode.lower() in ("on", "off"):
            ctx.script_echo = mode.lower() == "on"
        logger.info(f"Script log echo is {'on' if ctx.script_echo else 'off'} (file: <AP>/ccff7r/script_log.txt).")

    def _cmd_snapshot(self, name: str = ""):
        """Research aid: save the game's state block (exe+71B3F00, 0x2400 bytes: characters, treasure bits, story
        flags, DMW, ...) as <AP>/ccff7r/snap_<name>.bin. Compare two with /snapdiff <a> <b>."""
        g = self.ctx.game_mem
        if not g:
            logger.info("game not attached")
            return
        name = name or time.strftime("%H%M%S")
        path = os.path.join(Utils.user_path("ccff7r"), f"snap_{name}.bin")
        with open(path, "wb") as f:
            f.write(g.pm.read_bytes(g.a["char_status"], SNAP_SIZE))
        logger.info(f"Snapshot '{name}' saved ({path}).")

    def _cmd_snapdiff(self, a: str = "", b: str = ""):
        """Research aid: /snapdiff <a> <b> lists every byte that differs between two /snapshot files (exe offsets),
        also written to <AP>/ccff7r/snapdiff_<a>_<b>.txt. Play time and other always-changing bytes are skipped."""
        if not a or not b:
            logger.info("Usage: /snapdiff <snapshot a> <snapshot b>")
            return
        d = Utils.user_path("ccff7r")
        try:
            x, y = (open(os.path.join(d, f"snap_{n}.bin"), "rb").read() for n in (a, b))
        except OSError as e:
            logger.info(f"Can't read snapshot: {e}")
            return
        lines = []
        for i in range(min(len(x), len(y))):
            if x[i] != y[i] and not any(lo <= i < hi for lo, hi in SNAP_NOISE):
                lines.append(f"exe+{SNAP_BASE + i:07X}  (state+0x{i:04X})  {x[i]:02X} -> {y[i]:02X}")
        out = os.path.join(d, f"snapdiff_{a}_{b}.txt")
        with open(out, "w") as f:
            f.write("\n".join(lines) + "\n")
        logger.info(f"{len(lines)} bytes differ (saved to {out})" + (":\n  " + "\n  ".join(lines[:40]) if lines else "."))
        if len(lines) > 40:
            logger.info(f"... {len(lines) - 40} more in the file.")

    def _cmd_proficiency(self, arg: str = ""):
        """Show the Buster Sword proficiency the client reads. '/proficiency reapply' forgets which boosts were
        applied to this save, so every received boost is applied again (use it if a boost didn't stick)."""
        ctx: CCFF7RContext = self.ctx
        g = ctx.game_mem
        if not g:
            logger.info("game not attached")
            return
        if arg.lower() == "reapply":
            g.pm.write_bytes(g.a["treasure_bits"] + PROF_FLAGS, b"\0\0", 2)
            ctx.prof_written.clear()
            logger.info("Proficiency boosts will be applied again (outside battle).")
            return
        raw = g.pm.read_bytes(g.a["proficiency"], 0x24)
        b_, c_, s_ = struct.unpack_from("<ddd", raw)
        n = struct.unpack_from("<III", raw, 0x18)
        f = g.pm.read_bytes(g.a["treasure_bits"] + PROF_FLAGS, 2)
        logger.info(f"Buster Sword proficiency: {g.proficiency_percent():.2f}%  (block {b_:.2f}, command {c_:.2f}, "
                    f"sword {s_:.2f}, counts {n[0]}/{n[1]}/{n[2]}; boosts applied {f[0] & 15}/{f[0] >> 4}/{f[1] & 15}; "
                    f"chapter {g.chapter_byte()}, battle state {g.i32(g.a['battle_state'])}, "
                    f"active {g.u8(g.a['battle_active'])})")

    def _cmd_npcmissions(self, release: str = ""):
        """NPC Mission Checks: list the NPC handouts still waiting. '/npcmissions release' stops holding their
        missions locked for this session (escape hatch if an NPC can't be reached again)."""
        ctx: CCFF7RContext = self.ctx
        if not ctx.slot_data.get("npc_mission_checks"):
            logger.info("NPC Mission Checks is off for this seed.")
            return
        if release.lower() == "release":
            ctx.npc_released = True
            logger.info("NPC missions are no longer held locked (this session). Their handout checks stay open.")
            return
        left = [f"{LOC_NAME[lid]} - Chapter {NPC_CH[m]}+" for m, lid in NPC_LOCS.items()
                if lid in ctx.server_locations and lid not in ctx.checked_locations]
        logger.info(f"{len(left)} NPC handouts left" + (":\n  " + "\n  ".join(left) if left else "."))

    def _cmd_maillist(self):
        """Mailsanity mapping aid: print every mail in the order the game stores it (oldest first) with the name the
        apworld uses, and save it to <AP user dir>/ccff7r/mail_order.txt. Compare with the in-game Mail menu."""
        ctx: CCFF7RContext = self.ctx
        if not ctx.game_mem:
            logger.info("game not attached")
            return
        ids = ctx.game_mem.mail_ids() or []
        lines = [f"{i + 1:3}  #{m:3}  {LOC_NAME.get(MAIL_LOCS.get(m), '(not a mailsanity check)')}"
                 for i, m in enumerate(ids)]
        path = os.path.join(Utils.user_path("ccff7r"), "mail_order.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        logger.info("\n".join(lines[-40:]) + f"\n({len(ids)} mails; full list saved to {path})")

    def _cmd_shopnames(self, onoff: str = ""):
        """Shopsanity: '/shopnames off' shows the plain item names in shop menus again, '/shopnames on' brings the
        Archipelago names back (for this session)."""
        ctx: CCFF7RContext = self.ctx
        if onoff.lower() in ("on", "off"):
            ctx.shop_names_on = onoff.lower() == "on"
        logger.info(f"Archipelago names in shop menus: {'on' if ctx.shop_names_on else 'off'} "
                    f"(they show up the next time a shop list opens).")

    def _cmd_victory(self):
        """(alpha) Send goal completion manually after defeating Genesis."""
        asyncio.create_task(self.ctx.send_msgs([{"cmd": "StatusUpdate", "status": ClientStatus.CLIENT_GOAL}]))
        self.ctx.finished_game = True


class CCFF7RContext(CommonContext):
    game = GAME
    items_handling = 0b111
    command_processor = CCFF7RCommands

    def __init__(self, server_address, password):
        super().__init__(server_address, password)
        self.game_mem = None
        self.slot_data = {}
        self.applied = 0
        self.last_exp = None
        self.state_file = None
        self.prev_bits = None
        self.prev_mail = None
        self.goal_sent = False
        self.read_hook = None
        self.read_hook_state = None
        self.shop_hook = None
        self.shop_hook_state = None
        self.shop_scouts = {}
        self.shop_name_hook = None
        self.shop_name_state = None
        self.shop_names_on = True
        self.jump_hook = None
        self.jump_hook_state = None
        self.max_chapter = 1
        self.warp_target = None
        self.warp_snapshot = None
        self.gate_info = None
        self.deathlink_pending = 0                     # queued deaths (capped at 1 unless death_link_queue)
        self.deathlink_grace = 0.0
        self.deathlink_waiting = False
        self.last_alive = False
        self.last_hp = None
        self.pot_held = False
        self.npc_done = set()
        self.prof_written = {}
        self.prof_told = 0
        self.affection = None
        self.npc_set_told = set()     # per_set: sets already reported as waiting for their NPC (this session)
        self.gate_hits_seen = None
        self.pending_battle = None    # location of a scripted fight that was loaded and not won yet
        self.gate_bounced = None      # chapter whose ending the gate stopped (GATE_RESUME chapters), saved
        self.resume_armed = None      # chapter whose ending is armed on the next mission start
        self.offline_told = False
        self.ch7_told = False
        self.seed_tag = 0
        self.save_owner_told = None
        self.claim_save = False
        self.script_echo = False      # /scriptlog on: also show research lines in the client window
        self.told_calls = set()       # script calls already shown in the client window this session
        self.last_choice = None       # debug: last logged Choice (menus repeat it every frame)
        self.state_seen = None        # debug: last (scene, active mission, battle state, Zack's materia bytes)
        self.mg_mode = 0              # FairSetMiniGameMode state seen through the script hook
        self.paid_at = 0.0            # time of the last negative AddGil (perfume blend payment)
        self.last_gil = None
        self.last_battle_time = 0.0
        self.npc_released = False
        self.wagon_told = set()

    async def server_auth(self, password_requested=False):
        if password_requested and not self.password:
            await super().server_auth(password_requested)
        await self.get_username()
        await self.send_connect()

    def on_package(self, cmd, args):
        if cmd == "RoomInfo":
            self.room_seed = args.get("seed_name")
        if cmd == "Connected":
            self.slot_data = args.get("slot_data", {})
            d = Utils.user_path("ccff7r")
            os.makedirs(d, exist_ok=True)
            seed = getattr(self, "room_seed", None) or self.seed_name
            if not seed:
                logger.warning("Server did not report a seed name; received-item progress will not be saved.")
                self.state_file = None
                self.applied = 0
                return
            self.state_file = os.path.join(d, f"{seed}_{self.slot}_{self.username}.json")
            self.seed_tag = zlib.crc32(f"{seed}|{self.slot}".encode()) or 1
            self.save_owner_told = None
            try:
                st = json.load(open(self.state_file))
            except (OSError, ValueError):
                st = {}
            self.applied = st.get("applied", 0)
            self.max_chapter = st.get("max_chapter", 1)
            self.gate_bounced = st.get("gate_bounced")
            logger.info(f"Connected. {self.applied} items already applied to this seed's save.")
            shop_ids = [lid for lid in SHOP_LOCS.values() if lid in self.server_locations]
            if shop_ids:
                asyncio.create_task(self.send_msgs([{"cmd": "LocationScouts", "locations": shop_ids, "create_as_hint": 0}]))
            if self.slot_data.get("death_link"):
                asyncio.create_task(self.update_death_link(True))
                logger.info("DeathLink is on (experimental).")

        if cmd == "LocationInfo":
            for it in args.get("locations", []):
                self.shop_scouts[it.location] = it

    def save_state(self):
        if self.state_file:
            json.dump({"applied": self.applied, "max_chapter": self.max_chapter, "gate_bounced": self.gate_bounced},
                      open(self.state_file, "w"))

    def chapter_keys(self):
        return sum(1 for n in self.items_received if ITEM_BY_ID.get(n.item, {}).get("name") == "Progressive Chapter Key")

    def warp_limit(self):
        """Highest chapter the player may warp to."""
        lim = self.max_chapter
        if self.slot_data.get("chapter_gating"):
            lim = max(lim, min(10, self.chapter_keys() + 1))
        return lim

    def on_deathlink(self, data):
        super().on_deathlink(data)
        self.deathlink_source = data.get("source") or "Someone"
        if self.slot_data.get("death_link_queue"):
            self.deathlink_pending += 1
        else:
            self.deathlink_pending = 1

    def run_gui(self):
        from kvui import GameManager

        class CCFF7RManager(GameManager):
            logging_pairs = [("Client", "Archipelago")]
            base_title = "CCFF7R Client"

        self.ui = CCFF7RManager(self)
        self.ui_task = asyncio.create_task(self.ui.async_run(), name="UI")


def attach():
    from .game.memory import Game
    try:
        g = Game()
    except Exception:
        return None
    probs = [p for p in g.a["_problems"]
             if not (p.startswith("VM_CallNativeSite: 0 matches") and g.pm.read_bytes(g.a["VM_CallNativeSite"], 1) == b"\xE9")]
    if probs:                                    # (a 0-match on the VM site just means our hook is already in)
        logger.warning("Address problems: " + "; ".join(probs))
    return g


async def game_loop(ctx: CCFF7RContext):
    g = None
    while not ctx.exit_event.is_set():
        await asyncio.sleep(0.5)
        try:
            if g is None:
                g = attach()
                ctx.game_mem = g
                ctx.read_hook = None
                ctx.jump_hook = None
                ctx.shop_hook = None
                ctx.shop_name_hook = None
                if g:
                    logger.info("Attached to CCFF7R.")
                continue
            if not ctx.slot or ctx.state_file is None:
                if g.story_count() > 0:
                    research_tick(ctx, g)       # not connected: logs only, never items or checks
                continue
            story = g.story_count()
            if story <= 0:                       # title screen / loading
                ctx.last_exp = None
                ctx.last_gil = None
                ctx.last_hp = None
                ctx.prev_bits = None
                ctx.prev_mail = None
                continue
            if not save_belongs_here(ctx, g):
                continue
            tick(ctx, g)
        except Exception as e:                   # game closed or memory moved
            logger.debug(f"game loop: {e!r}")
            if g is not None:
                logger.info("Lost the game process; waiting for it again.")
            g = None
            ctx.game_mem = None


# Rollback canary: 4 spare bytes at the end of the treasure-bit array (highest real treasure id is 1321,
# i.e. byte 0xA5). They are saved with the game and restored with it, so after a failed/quit mission
# (which rolls inventory + treasure bits back to the mission start) or loading an older save, the
# stored count tells us exactly which received items that game state still contains.
SEED_TAG = 0xF0                       # treasure bytes +0xF0..+0xF5 (ids 1920-1967, unused): u32 seed tag + magic
SEED_TAG_MAGIC = b"\x5E\xED"


def save_belongs_here(ctx, g):
    """The loaded save remembers which seed/slot it was played with. A save from another seed (e.g. the client
    connected to an old room) is left alone: no items, no checks, until '/claimsave'. New saves are claimed."""
    addr = g.a["treasure_bits"] + SEED_TAG
    raw = g.pm.read_bytes(addr, 6)
    tag = struct.unpack_from("<I", raw)[0]
    if raw[4:6] != SEED_TAG_MAGIC or ctx.claim_save:
        g.pm.write_bytes(addr, struct.pack("<I", ctx.seed_tag) + SEED_TAG_MAGIC, 6)
        if ctx.claim_save:
            logger.info("This save now belongs to the connected seed.")
        ctx.claim_save = False
        return True
    if tag == ctx.seed_tag:
        ctx.save_owner_told = None
        return True
    if ctx.save_owner_told != tag:
        ctx.save_owner_told = tag
        logger.warning("The loaded save was played with a different seed or slot, so the client is leaving it alone "
                       "(no items, no checks). Load this seed's save, or type /claimsave to use this save for the "
                       "connected seed anyway.")
    return False


CANARY = 0xFC
CANARY_MAGIC = b"\xA5\x7A"


def write_canary(g, n):
    g.pm.write_bytes(g.a["treasure_bits"] + CANARY, CANARY_MAGIC + bytes((n & 0xFF, n >> 8 & 0xFF)), 4)


def sync_canary(ctx, g, raw):
    c = raw[CANARY:CANARY + 4]
    if c[:2] != CANARY_MAGIC:                    # save from before v0.2.7: trust the state file
        write_canary(g, ctx.applied)
        return
    saved = c[2] | c[3] << 8
    if saved < ctx.applied:
        logger.info(f"Game state was rolled back (failed/quit mission or older save) - "
                    f"re-giving {ctx.applied - saved} received item(s).")
        ctx.applied = saved
        ctx.save_state()
    elif saved > ctx.applied:
        write_canary(g, ctx.applied)


GIL_AFTER_BATTLE = 8.0          # seconds after a fight in which gil gains still count as battle gil


def gil_multiplier(ctx, g):
    """Battle gil x gil_multiplier. Runs first in the tick and compares with the gil seen at the end of the last
    tick, so gil the client itself gives (AP items) is never multiplied."""
    mult = ctx.slot_data.get("gil_multiplier", 1)
    now = time.time()
    if in_battle(g):
        ctx.last_battle_time = now
    gil = g.gil()
    if mult > 1 and ctx.last_gil is not None and gil > ctx.last_gil \
            and now - ctx.last_battle_time <= GIL_AFTER_BATTLE:
        g.add_gil((gil - ctx.last_gil) * (mult - 1))


def tick(ctx: CCFF7RContext, g):
    gil_multiplier(ctx, g)
    # 1. placeholders (the table is rebuilt every launch); skipped minigames stay vanilla
    skip = set(ctx.slot_data.get("skip_treasures", ()))
    # only chests that exist in this seed (a newer apworld may know chests an older seed doesn't)
    patched = [t for t in PATCHED if t not in skip and TREASURE_LOCS[t] in ctx.server_locations]
    if any(g.treasure_record(t)[1:] != (0, PLACEHOLDER[0]) for t in patched[:3]):
        for t in patched:
            g.set_treasure_item(t, PLACEHOLDER[0], PLACEHOLDER[1])
        logger.info("Treasure table patched with placeholders.")

    # 2. checks
    found = []
    raw = g.pm.read_bytes(g.a["treasure_bits"], 0x100)
    for t, lid in TREASURE_LOCS.items():
        if t in skip:
            continue
        if raw[t >> 3] >> (t & 7) & 1 and lid not in ctx.checked_locations and lid in ctx.server_locations:
            found.append(lid)
    log_new_treasures(ctx, g, raw[:SEED_TAG])
    rise = log_affection(ctx, g)
    state_events = log_state_changes(ctx, g)
    sync_canary(ctx, g, raw)
    log_new_mail(ctx, g)
    deliver_mission_mails(g)
    found += optional_checks(ctx, g)
    cb = g.chapter_byte()
    for ch, lid in CHAPTER_LOCS.items():
        if cb >= ch + 1 and lid not in ctx.checked_locations:
            found.append(lid)
    # 2a. minigame prizes read via TreasureGetId (no opened bit)
    if READ_LOCS or NPC_LOCS or EVENT_LOCS:
        if ctx.read_hook is None:
            from .game.readhook import TreasureReadHook
            ctx.read_hook = TreasureReadHook(g.pm, g.a["VM_CallNativeSite"])
        try:
            st = ctx.read_hook.ensure()
        except Exception as e:
            st = f"error ({e!r})"
        if st != ctx.read_hook_state:
            ctx.read_hook_state = st
            msg = {"active": "Minigame prize detection active.",
                   "foreign": "Minigame prize detection paused: another hook (a Cheat Engine script?) is on the "
                              "script VM. Turn it off and the client re-hooks automatically."}.get(st)
            logger.info(msg or f"Minigame prize detection unavailable: {st}")
        process_script_calls(ctx, g, ctx.read_hook.poll(), rise, cb, skip, found, state_events)
    for trig, deps in ALSO_ON.items():                 # also covers a trigger checked in an earlier session
        if trig in found or trig in ctx.checked_locations:
            for d in deps:
                if d not in found and d not in ctx.checked_locations and d in ctx.server_locations:
                    found.append(d)
    for lid in list(found):
        for other in GROUP_OF.get(lid, ()):
            if other not in found and other not in ctx.checked_locations and other in ctx.server_locations:
                found.append(other)
    if found:
        asyncio.create_task(ctx.send_msgs([{"cmd": "LocationChecks", "locations": found}]))

    # 2b2. shopsanity: purchases from the first `shop_slots` slots of each shop
    if ctx.slot_data.get("shop_slots"):
        if ctx.shop_hook is None:
            from .game.shophook import ShopHook
            ctx.shop_hook = ShopHook(g.pm, g.a["ShopBuySite"])
        try:
            sst = ctx.shop_hook.ensure()
        except Exception as e:
            sst = f"error ({e!r})"
        if sst != ctx.shop_hook_state:
            ctx.shop_hook_state = sst
            logger.info({"active": "Shopsanity active (/shops lists the slots).",
                         "foreign": "Shopsanity paused: another hook (a Cheat Engine script?) is on the shop's buy "
                                    "code. Turn it off and the client re-hooks automatically."}.get(sst)
                        or f"Shopsanity unavailable: {sst}")
        bought = []
        for sid, slot, qty in ctx.shop_hook.poll():
            lid = SHOP_LOCS.get((15 if sid == 16 else sid, slot))
            if lid and lid in ctx.server_locations and lid not in ctx.checked_locations and lid not in bought:
                bought.append(lid)
                it = ctx.shop_scouts.get(lid)
                what = f" -> {ctx.item_names.lookup_in_slot(it.item, it.player)} for " \
                       f"{ctx.player_names.get(it.player, it.player)}" if it else ""
                logger.info(f"Shop check: {LOC_NAME[lid]}{what}")
        if bought:
            asyncio.create_task(ctx.send_msgs([{"cmd": "LocationChecks", "locations": bought}]))
        shop_names(ctx, g, bought)

    # 2c. chapter gate + chapter select (scene-jump hook)
    cb = g.chapter_byte()
    if 1 <= cb <= 10 and cb > ctx.max_chapter:
        ctx.max_chapter = cb
        ctx.save_state()
    if ctx.jump_hook is None:
        from .game.jumphook import JumpHook
        ctx.jump_hook = JumpHook(g.pm, g.a["RequestJump"], g.a["jump_mgr_ptr"])
    try:
        jst = ctx.jump_hook.ensure()
    except Exception as e:
        jst = f"error ({e!r})"
    if jst != ctx.jump_hook_state:
        ctx.jump_hook_state = jst
        logger.info({"active": "Chapter select ready (/warp)." + (" Chapter gating active." if ctx.slot_data.get("chapter_gating") else ""),
                     "foreign": "Chapter select/gating paused: another hook (a Cheat Engine script?) is on the scene-jump "
                                "function. Turn it off and the client re-hooks automatically."}.get(jst)
                    or f"Chapter select/gating unavailable: {jst}")
    if jst == "active":
        hook = ctx.jump_hook
        src = hook.poll_warp()
        if src is not None and ctx.warp_target:
            n = ctx.warp_target
            ctx.warp_target = None
            g.pm.write_int(g.a["state_story_count"], CHAPTER_START[n][1])
            g.pm.write_uchar(g.a["state_chapter_byte"], n)
            for ch, groups in UNLOCK_GROUPS.items():         # chapters cleared before n (never cleared again)
                if ch < n:
                    for i in groups:
                        g.pm.write_uchar(g.a["state_unlock_groups"] + i, 1)
            g.pm.write_ushort(g.a["state_active_mission"], 0xFFFF)  # we hijacked a mission start
            m = src - 5500
            if ctx.warp_snapshot and 0 <= m < 300:
                g.pm.write_uchar(g.a["state_mission_state"] + 3 * m + 1, ctx.warp_snapshot[3 * m + 1])
            logger.info(f"Warped to Chapter {n}.")
            cb = n
        elif src is not None and ctx.resume_armed:
            ctx.resume_armed = None
            ctx.gate_bounced = None
            g.pm.write_ushort(g.a["state_active_mission"], 0xFFFF)  # we hijacked a mission start
            m = src - 5500
            if ctx.warp_snapshot and 0 <= m < 300:
                g.pm.write_uchar(g.a["state_mission_state"] + 3 * m + 1, ctx.warp_snapshot[3 * m + 1])
            ctx.save_state()
            logger.info(f"Continuing Chapter {cb}'s ending.")
        if ctx.resume_armed and ctx.resume_armed != cb:      # left the chapter some other way: disarm
            hook.arm_warp(0)
            ctx.resume_armed = None
        if cb == 7 and ctx.slot_data.get("chapter_gating") and ctx.chapter_keys() < 7 and not ctx.ch7_told:
            ctx.ch7_told = True
            logger.warning("Chapter 7: once you're out collecting the wagon parts, Aerith's church stays locked until "
                           "you have Progressive Chapter Key #7 (handing her the parts starts the chapter's ending).")
        hits = hook.gate_hits()
        if ctx.gate_hits_seen is not None and hits > ctx.gate_hits_seen:
            # the gate bounce reuses the mission-return jump; make sure no mission is left marked as active
            # (tester, Ch7: after a bounce the map acted as if he was still in a mission). Unverified fix, doc 7.3am
            g.pm.write_ushort(g.a["state_active_mission"], 0xFFFF)
            logger.info(f"Chapter {cb}'s ending is locked: you were sent back to the field (no key #{cb} yet).")
            if cb in GATE_RESUME:
                ctx.gate_bounced = cb
                ctx.save_state()
        ctx.gate_hits_seen = hits
        gate = CHAPTER_GATE.get(cb)
        if ctx.slot_data.get("chapter_gating") and gate and ctx.chapter_keys() < cb \
                and g.story_count() >= gate[1]:
            here = g.i32(g.a["state_current_scene"])
            to, entrance = GATE_BOUNCE.get(cb, (None, False))
            to = to or here
            if to and here != gate[0]:
                hook.set_gate(gate[0], to, entrance)
            if ctx.gate_info != cb:
                ctx.gate_info = cb
                logger.info(f"The end of Chapter {cb} is locked until you receive Progressive Chapter Key #{cb}. "
                            f"Missions and the rest of the chapter stay open.")
        else:
            hook.set_gate(0, 0)
            ctx.gate_info = None
            if ctx.gate_bounced == cb and cb in GATE_RESUME and not ctx.resume_armed and not ctx.warp_target \
                    and ctx.chapter_keys() >= cb:
                ctx.resume_armed = cb
                ctx.warp_snapshot = g.pm.read_bytes(g.a["state_mission_state"], 300 * 3)
                hook.arm_warp(CHAPTER_GATE[cb][0])
                logger.info(f"Key #{cb} is here: open the mission menu at a save point and start ANY mission to "
                            f"continue Chapter {cb}'s ending.")

    # 2d. DeathLink. Zack = battle actor 0: HP at +0x1E8, flags at +0x24A; the game treats HP <= 0 or
    # (flags & 0x11) as dead. Verified in a mission battle: HP 0 + flag 0x01 kills him instantly (death animation,
    # normal game over / mission failure). Battle state (exe+717AD5C): 3 = fighting, 4 = finishing.
    if ctx.slot_data.get("death_link"):
        hp = g.i32(g.a["battle_hp"])
        flags = g.u16(g.a["battle_flags"])
        bstate = g.i32(g.a["battle_state"])
        fighting, in_battle = bstate == 3, bstate in (3, 4)
        dead = hp <= 0 or flags & 0x11
        now = time.time()
        if ctx.deathlink_pending:
            if fighting and not dead and now > ctx.deathlink_grace:     # at most one kill per battle
                ctx.deathlink_pending -= 1
                ctx.deathlink_grace = now + 10
                g.pm.write_int(g.a["battle_hp"], 0)
                g.pm.write_ushort(g.a["battle_flags"], flags | 0x01)
                logger.info("DeathLink: " + random.choice(DEATH_RECEIVED_LINES).format(
                    source=getattr(ctx, "deathlink_source", "Someone"))
                            + (f" ({ctx.deathlink_pending} more queued)" if ctx.deathlink_pending else ""))
                dead = True
            elif not ctx.deathlink_waiting and not (fighting and not dead):
                ctx.deathlink_waiting = True
                logger.info(f"DeathLink: {getattr(ctx, 'deathlink_source', 'Someone')} died - Zack falls in his next battle.")
        elif in_battle and ctx.last_alive and dead and now > ctx.deathlink_grace:
            name = ctx.player_names.get(ctx.slot, 'Zack')
            asyncio.create_task(ctx.send_death(random.choice(DEATH_LINES).format(name=name)))
            logger.info("DeathLink: death sent.")
        if not ctx.deathlink_pending:
            ctx.deathlink_waiting = False
        ctx.last_alive = in_battle and not dead

    # 2b. goal: story_count reaches 11000 after the final boss
    if not ctx.goal_sent and g.story_count() >= GOAL_STORY:
        ctx.goal_sent = True
        asyncio.create_task(ctx.send_msgs([{"cmd": "StatusUpdate", "status": ClientStatus.CLIENT_GOAL}]))
        logger.info("Genesis defeated - goal sent!")

    # 3. received items
    sets_owned = set()
    ranks = 0
    for i, net in enumerate(ctx.items_received):
        it = ITEM_BY_ID.get(net.item)
        if it and it["payload"].get("type") == "mission_set":
            sets_owned.add(it["payload"]["set"])
        if it and it["payload"].get("type") == "mission_rank":
            ranks += 1
        if i < ctx.applied or not it:
            continue
        p = it["payload"]
        ok = True
        if p.get("type") == 0 and p.get("id") in WAGON_CHEAP:
            hold_cheap_part(g, p["id"])            # Ch7 pickup part: handed over by wagon_parts() after the pickup
        elif p.get("type") == "mission_set":
            g.set_mission_unlocked(p["first_mission"])
        elif p.get("type") == "accessory_slot":   # 1st = Keychain (3 slots), 2nd = Backpack (4 slots)
            nth = sum(1 for n in ctx.items_received[:i + 1]
                      if ITEM_BY_ID.get(n.item, {}).get("payload", {}).get("type") == "accessory_slot")
            ok = g.add_item(0x3035 if nth == 1 else 0x3036, 1)
        elif p.get("type") == 0 and p.get("id") in WAGON_CAT and ctx.slot_data.get("wagon_random"):
            pass                                   # flower wagon part: handed over by wagon_parts() when safe
        elif p.get("type") == "proficiency":
            pass                                   # applied by proficiency_boosts() once Ch6 set the meter up
        elif p.get("type") == "dmw_slot":
            g.set_dmw_slot(p["slot"], 1)
        elif p.get("type") in ("chapter_key", "mission_rank"):
            pass                                   # chapter key: helper DLL gate (phase 2); rank: applied below
        else:
            ok = g.give(p)
        if not ok:
            logger.warning(f"Could not give {it['name']} (inventory full?) - will retry")
            break
        ctx.applied = i + 1
        write_canary(g, ctx.applied)
        logger.info(f"Received {it['name']}")
        ctx.save_state()

    # 4. mission unlocks
    mode = ctx.slot_data.get("mission_unlocks", 2)
    ms = g.missions()
    timed = ctx.slot_data.get("chapter_unlock_timing")   # v0.6.37+ seeds; older ones open them with the set
    if mode == 0:                                  # per_set: keep unowned sets locked
        for s, mids in SET_MISSIONS.items():
            if s not in sets_owned:
                for m in mids:
                    if ms[m][0] and not ms[m][1]:
                        g.set_mission_unlocked(m, False)
            else:
                if s in SET_FIRST and not ms[SET_FIRST[s]][0]:
                    g.set_mission_unlocked(SET_FIRST[s])  # owned set: its first mission is always open (NPC-held
                                                          # ones are locked again just below until the handout)
                for m, ch in CHAPTER_UNLOCK.get(s, ()):  # missions the game opens at a chapter start: open
                    if (ch <= ctx.max_chapter or not timed) and not ms[m][0]:   # them once that chapter was reached
                        g.set_mission_unlocked(m)                # came later (doc 7.3ak; v0.6.37: not before, tester)
                for m in mids & NPC_MISSIONS:            # NPC handouts: the NPC hands a mission out only once, so
                    lid = NPC_LOCS[m]                    # one that came while the set was missing stayed locked
                    handed = (not ctx.slot_data.get("npc_mission_checks") or ctx.npc_released or m in ctx.npc_done
                              or lid in ctx.checked_locations or lid not in ctx.server_locations)
                    if handed and not ms[m][0]:          # (tester: M1-2-1, M2-1-2..4, M4-3-5). doc 7.3an
                        g.set_mission_unlocked(m)
    elif mode == 2:                                # progressive_rank: open everything <= current rank
        cap = ctx.slot_data.get("starting_mission_rank", 2) + ranks
        for m, r in MISSION_RANK.items():
            unlocked, cleared = ms[m]
            if r <= cap and not unlocked:
                g.set_mission_unlocked(m, True)
            elif r > cap and unlocked and not cleared:
                g.set_mission_unlocked(m, False)

    npc_set_notice(ctx, mode)
    if ctx.slot_data.get("npc_mission_checks") and mode != 1:   # NPCs only hand out missions that are still locked
        # held until the NPC hands it out - no chapter cutoff: a missed NPC is reached again with /warp
        if not ctx.npc_released:
            ms = g.missions()                          # after this tick's rank/set unlocks
            for m, lid in NPC_LOCS.items():
                if lid in ctx.server_locations and lid not in ctx.checked_locations and m not in ctx.npc_done \
                        and ms[m][0] and not ms[m][1]:
                    g.set_mission_unlocked(m, False)
    wagon_parts(ctx, g)
    wagon_cheap_parts(ctx, g)
    proficiency_boosts(ctx, g)

    # 5. EXP multiplier
    mult = ctx.slot_data.get("exp_multiplier", 1)
    exp = g.exp()
    if ctx.last_exp is not None and mult > 1 and exp > ctx.last_exp:
        g.add_exp((exp - ctx.last_exp) * (mult - 1))
        exp = g.exp()
    ctx.last_exp = exp
    ctx.last_gil = g.gil()


def optional_checks(ctx, g):
    """DMW characters / memories, Magic Pot, Buster Sword proficiency and mailsanity (all off by default)."""
    sd = ctx.slot_data
    out = []

    def want(lid):
        if lid in ctx.server_locations and lid not in ctx.checked_locations and lid not in out:
            out.append(lid)

    applied = [ITEM_BY_ID.get(n.item, {}) for n in ctx.items_received[:ctx.applied]]
    # DMW characters: a portrait we didn't receive goes back to a silhouette; the story's unlock is the check.
    # A character received before its story moment can't be told apart, so the check also fires at the
    # chapter byte in DMW_FALLBACK_CB.
    if sd.get("dmw_characters"):
        owned = {i["payload"]["slot"] for i in applied if i.get("payload", {}).get("type") == "dmw_slot"}
        slots = g.dmw_slots()
        cb = g.chapter_byte()
        for s_, (lid, ch) in DMW_UNLOCK_LOCS.items():
            if slots[s_] and s_ not in owned:
                if lid not in ctx.checked_locations and lid not in out:
                    logger.info(f"DMW: {LOC_NAME[lid]} (check) - portrait stays a silhouette until you receive it.")
                want(lid)
                g.set_dmw_slot(s_, 0)
            elif not slots[s_] and s_ in owned:
                g.set_dmw_slot(s_, 1)
            if cb >= DMW_FALLBACK_CB[s_]:
                want(lid)
    if sd.get("dmw_memories"):
        w = g.dmw_watched()
        for (c, n), lid in DMW_MEMORY_LOCS.items():     # counted per character (Memory k = k memories seen)
            if bin(w[c] & 0x3F).count("1") > n:
                want(lid)
    # Magic Pot: the vanilla copy is taken back until the AP item arrives. If the AP item is already here, it is
    # held out of the inventory during Mission 10-2-3 so the Magic Pot's own reward can be seen.
    if sd.get("magic_pot"):
        have_ap = any(i.get("name") == "Magic Pot Tricks" for i in applied)
        pending = MAGIC_POT_LOC in ctx.server_locations and MAGIC_POT_LOC not in ctx.checked_locations
        in_mission = g.u16(g.a["state_active_mission"]) == MAGIC_POT_MISSION
        cnt = g.item_count(MAGIC_POT_ITEM)
        if not have_ap:
            if cnt:
                if pending:
                    logger.info("Magic Pot request done (check). Magic Pot Tricks is held until you receive it.")
                    want(MAGIC_POT_LOC)
                g.remove_item(MAGIC_POT_ITEM)
        elif pending and in_mission:
            if ctx.pot_held and cnt:
                logger.info("Magic Pot request done (check).")
                want(MAGIC_POT_LOC)
                ctx.pot_held = False
            elif not ctx.pot_held and cnt:
                g.remove_item(MAGIC_POT_ITEM)
                ctx.pot_held = True
        elif cnt == 0:                                   # mission over (or client restarted): give it back
            g.add_item(MAGIC_POT_ITEM, 1)
            ctx.pot_held = False
    mx = sd.get("proficiency_checks", 0)
    if mx:
        pct = g.proficiency_percent()
        for k, lid in PROFICIENCY_LOCS.items():
            if k <= mx and pct >= k - 1e-6:
                want(lid)
    if sd.get("mailsanity"):
        for m in g.mail_ids() or ():
            if m in MAIL_LOCS:
                want(MAIL_LOCS[m])
    return out


def in_battle(g):
    """Battle state (exe+717AD5C) 3 = fighting, 4 = finishing - the same test DeathLink uses. (battle_active at
    exe+717AD52 stays set in the field, so it can't be used here - tester, v0.6.13.)"""
    try:
        return g.i32(g.a["battle_state"]) in (3, 4)
    except Exception:
        return False


def proficiency_boosts(ctx, g):
    """Apply received Proficiency Boosts, outside battle only. Applied counts live in the save (treasure bytes
    +0xF8/+0xF9), so a reload or a failed mission that rolls the meter back also rolls the counts back.
    In battle the game works on its own copy of the meter (the HUD reads battle actor +0x228/+0x230/+0x238), so a
    value written then can be overwritten when the battle ends (tester, v0.6.8). Each write is therefore watched
    through the next battle: if the value comes back lower, the boost is re-applied."""
    want = [0, 0, 0]
    frac = [0.25, 0.25, 0.25]
    for n in ctx.items_received[:ctx.applied]:
        p = ITEM_BY_ID.get(n.item, {}).get("payload", {})
        if p.get("type") == "proficiency":
            want[p["part"]] += 1
            frac[p["part"]] = p.get("fraction", 0.25)
    if not any(want):
        return
    if g.chapter_byte() < 6:
        held = sum(want)
        if held != ctx.prof_told:
            ctx.prof_told = held
            logger.info(f"Proficiency boost held by the client ({held} so far) - Buster Sword proficiency starts in "
                        f"Chapter 6, they're applied then.")
        return
    battle = in_battle(g)
    addr = g.a["treasure_bits"] + PROF_FLAGS
    raw = g.pm.read_bytes(addr, 2)
    done = [raw[0] & 0xF, raw[0] >> 4, raw[1] & 0xF]
    changed = False
    raw_vals = g.pm.read_bytes(g.a["proficiency"], 0x18)
    for part, (val, seen) in list(ctx.prof_written.items()):
        if battle:
            ctx.prof_written[part] = (val, True)
            continue
        cur, = struct.unpack_from("<d", raw_vals, part * 8)
        if cur < val - 1e-6 and done[part] > 0:
            done[part] -= 1
            changed = True
            logger.info("A proficiency boost was undone by the game - applying it again.")
        if seen or cur < val - 1e-6:
            del ctx.prof_written[part]
    if battle:
        if changed:
            g.pm.write_bytes(addr, bytes((done[0] | done[1] << 4, done[2] | (raw[1] & 0xF0))), 2)
        return
    for part in range(3):
        while done[part] < min(want[part], 15) and g.add_proficiency(part, frac[part]):
            done[part] += 1
            changed = True
            val, = struct.unpack("<d", g.pm.read_bytes(g.a["proficiency"] + part * 8, 8))
            ctx.prof_written[part] = (val, False)
            logger.info(f"Proficiency boost applied ({('Perfect Guard', 'Command Kill', 'Strong Attack Kill')[part]})"
                        f" - meter now {g.proficiency_percent():.2f}%")
    if changed:
        g.pm.write_bytes(addr, bytes((done[0] | done[1] << 4, done[2] | (raw[1] & 0xF0))), 2)


def hold_cheap_part(g, iid):
    addr = g.a["treasure_bits"] + WAGON_CHEAP_FLAGS
    g.pm.write_uchar(addr, g.pm.read_uchar(addr) | 1 << (iid - 0x3040))


def reset_ch7_wagon(ctx, g):
    """Warp to Chapter 7 or earlier: Chapter 7 will be played again, and its ending needs the 4 cheap wagon parts,
    which were handed to Aerith (gone) and whose pickups (treasures 405-408) don't respawn once opened. Clear the
    pickups and our hand-over flags so the parts can be picked up again; remove leftover copies (owning a part
    before its pickup scene force-walks Zack). Their checks were sent the first time. doc 7.3am"""
    tb = g.a["treasure_bits"]
    for iid, t in WAGON_CHEAP.items():
        a = tb + (t >> 3)
        g.pm.write_uchar(a, g.pm.read_uchar(a) & ~(1 << (t & 7)) & 0xFF)
        if g.item_count(iid):
            g.remove_item(iid)
    flags = g.pm.read_uchar(tb + WAGON_CHEAP_FLAGS)
    held = flags & 0x0F | (flags >> 4 & 0x0F)              # every part ever received counts as held again
    g.pm.write_uchar(tb + WAGON_CHEAP_FLAGS, held)
    ctx.prev_bits = None                                   # don't log the cleared bits as changes
    logger.info("Chapter 7's wagon part pickups are reset, so its ending can be played again.")


def wagon_cheap_parts(ctx, g):
    addr = g.a["treasure_bits"] + WAGON_CHEAP_FLAGS
    flags = g.pm.read_uchar(addr)
    if not flags & 0x0F:
        return
    cb = g.chapter_byte()
    for iid, t in WAGON_CHEAP.items():
        k = iid - 0x3040
        if flags >> k & 1 and not flags >> (k + 4) & 1 and (g.treasure_opened(t) or cb >= WAGON_CHEAP_UNTIL_CB):
            if g.add_item(iid, 1):
                flags |= 1 << (k + 4)
                g.pm.write_uchar(addr, flags)
                logger.info(f"Flower wagon part handed over: {CHEAP_NAME.get(iid, hex(iid))}")


SHOP_LABEL_MAX = 36          # characters that fit before the Gil column (tester: 44 overlapped the price)


def _cut(text, n):
    return text if len(text) <= n else text[:max(1, n - 1)].rstrip() + "."


def shop_label(vanilla, what, who=""):
    """'* <AP item> (<player>)', shortened to SHOP_LABEL_MAX characters (item name first, player name 6-12
    characters). `vanilla` is unused since v0.6.12."""
    head = "* "                                # vanilla name dropped (user): the row shows it again once bought
    room = SHOP_LABEL_MAX - len(head)
    if who:
        # the player name gets what the item name leaves over (6-12 characters), the item name the rest
        keep = min(12, len(who), max(6, room - 3 - len(what)))
        tail = f" ({_cut(who, keep)})"
        return head + _cut(what, max(8, room - len(tail))) + tail
    return head + _cut(what, room)


def shop_names(ctx, g, bought=()):
    """Buy list shows '<vanilla item> * <AP item> (<player>)' on every unbought AP slot; the star line goes back to
    the plain name once the slot is bought (next time the list is built)."""
    if ctx.shop_name_hook is None:
        from .game.shopnamehook import ShopNameHook
        ctx.shop_name_hook = ShopNameHook(g.pm, g.a["ShopNameCallSite"])
    try:
        st = ctx.shop_name_hook.ensure()
    except Exception as e:
        st = f"error ({e!r})"
    if st != ctx.shop_name_state:
        ctx.shop_name_state = st
        logger.info({"active": "Shop menus show what each Archipelago slot holds.",
                     "foreign": "Shop item names unavailable: the shop list code isn't what the client expects "
                                "(another hook, or a different game build)."}.get(st) or f"Shop item names unavailable: {st}")
    if st != "active":
        return
    names = {}
    for lid, it in (ctx.shop_scouts.items() if ctx.shop_names_on else ()):
        if lid in ctx.checked_locations or lid in bought or lid not in SHOP_SLOT_ITEM:
            continue
        shop, item_id, vanilla = SHOP_SLOT_ITEM[lid]
        what = ctx.item_names.lookup_in_slot(it.item, it.player)
        who = "" if it.player == ctx.slot else str(ctx.player_names.get(it.player, it.player))
        text = shop_label(vanilla, what, who)
        for s_ in ((15, 16) if shop == 15 else (shop,)):          # 16 = Online Shop Shade variant
            names[(s_, item_id)] = text
    ctx.shop_name_hook.set_names(names)


def wagon_parts(ctx, g):
    """Hand over received flower wagon parts once no unchecked giver of that category could still skip you.
    Seeds from before v0.6.4 keep the parts locked at their givers (no slot_data flag) and get them directly."""
    if not ctx.slot_data.get("wagon_random"):
        return
    raw = g.pm.read_bytes(g.a["treasure_bits"] + WAGON_FLAGS, 1)[0]
    cb = g.chapter_byte()
    for n in ctx.items_received[:ctx.applied]:
        p = ITEM_BY_ID.get(n.item, {}).get("payload", {})
        iid = p.get("id")
        if p.get("type") != 0 or iid not in WAGON_CAT:
            continue
        bit = 1 << (iid - 0x3038)
        if raw & bit:
            continue
        waiting = [t for t in WAGON_GIVERS[WAGON_CAT[iid]] if t in TREASURE_LOCS
                   and TREASURE_LOCS[t] in ctx.server_locations and TREASURE_LOCS[t] not in ctx.checked_locations]
        if waiting and cb < WAGON_HOLD_UNTIL_CB:
            if iid not in ctx.wagon_told:
                ctx.wagon_told.add(iid)
                logger.info(f"{ITEM_BY_ID[n.item]['name']} is held by the client until you've visited its wagon part "
                            f"giver(s) ({', '.join(LOC_NAME[TREASURE_LOCS[t]] for t in waiting)}) - they skip you "
                            f"if you already carry one.")
            continue
        if g.add_item(iid, 1):
            raw |= bit
            g.pm.write_uchar(g.a["treasure_bits"] + WAGON_FLAGS, raw)
            logger.info(f"Flower wagon part handed over: {ITEM_BY_ID[n.item]['name']}")


def npc_set_notice(ctx, mode):
    """per_set + NPC Mission Checks: say once per session when an owned set waits for its first mission's NPC
    (also covers sets received before this client version or in an earlier session)."""
    if not (ctx.slot_data.get("npc_mission_checks") and mode == 0 and not ctx.npc_released):
        return
    for net in ctx.items_received:
        it = ITEM_BY_ID.get(net.item)
        if not it or it["payload"].get("type") != "mission_set":
            continue
        first = it["payload"]["first_mission"]
        npc = NPC_LOCS.get(first)
        if npc and npc in ctx.server_locations and npc not in ctx.checked_locations \
                and first not in ctx.npc_done and first not in ctx.npc_set_told:
            ctx.npc_set_told.add(first)
            logger.info(f"{it['name']}: its first mission is an NPC handout and stays locked until you talk to "
                        f"the NPC - {NPC_WHO[first]} (Chapter {NPC_CH[first]}+, /warp back if you've passed "
                        f"it). /npcmissions lists every handout left.")


def process_script_calls(ctx, g, calls, rise, cb, skip, found, state_events=()):
    """Script-native calls from the read hook: NPC handouts, minigame prize reads and minigame completions."""
    events = list(state_events)
    if calls:
        log_script_calls(ctx, g, calls)
    for nat, a0, a1, a2 in calls:
        if nat == 0x256:                           # MissionSet from an NPC script
            m = a0 & 0x7FFF
            lid = NPC_LOCS.get(m)
            if lid and lid in ctx.server_locations:
                ctx.npc_done.add(m)
                if lid not in ctx.checked_locations and lid not in found:
                    logger.info(f"NPC mission handout: {LOC_NAME[lid]}")
                    found.append(lid)
            continue
        if nat == 0x25B and ctx.slot_data.get("dmw_characters"):
            # DmwEnableSlot(slot, flag), flag on top like TreasureEnable: the story adds a character to the DMW.
            # Exact even when the character was already received (polling can only fall back to a chapter then).
            slot = a1 if a0 in (0, 1) and a1 < 7 else a0
            lid = DMW_UNLOCK_LOCS.get(slot, (None,))[0]
            if lid and lid in ctx.server_locations and lid not in ctx.checked_locations and lid not in found:
                logger.info(f"DMW: {LOC_NAME[lid]} (check)")
                found.append(lid)
            continue
        if nat == 0x24C and a0 & 0x8000 and 200 <= 0x10000 - a0 <= 5000:
            ctx.paid_at = time.time()              # paid for a perfume blend (~550 gil; not the -50 kids game
                                                   # or Aerith taking the whole wallet)
        if nat == 0x154:                           # LoadBattleData(id): a scripted fight is coming
            sc = g.i32(g.a["state_current_scene"])
            ctx.pending_battle = next((l["id"] for l in EVENT_LOCS if l["trigger"].get("battle") == a0
                                       and l["trigger"].get("scene", sc) == sc and l["chapter"] == cb), None)
        if nat == 0x33A:                           # FairSetMiniGameMode
            if ctx.mg_mode and not a0:
                events.append("minigame_end")
            ctx.mg_mode = a0
        for l in NATIVE_EVENTS.get(nat, ()):
            t = l["trigger"]
            if t.get("min", 0) <= a0 <= t.get("max", 0xFFFF):
                events.append(l["id"])
        if nat in NATIVE_EVENTS or nat in (0x24C, 0x33A):
            continue
        if nat != 0x254:
            continue
        t = a0
        lid = READ_LOCS.get(t)
        if lid and lid not in ctx.checked_locations and lid in ctx.server_locations and lid not in found \
                and t not in skip:
            logger.info(f"Minigame prize: treasure #{t}")
            found.append(lid)
    if rise and not ctx.mg_mode and time.time() - ctx.paid_at < PERFUME_WINDOW:
        events.append("perfume")
    aff = ctx.affection or 0
    scene = g.i32(g.a["state_current_scene"]) if events else None
    for l in EVENT_LOCS:
        t, lid = l["trigger"], l["id"]
        hit = (lid in events or ("perfume" in t and "perfume" in events)
               or ("minigame_end" in t and "minigame_end" in events)
               or ("battle_won" in t and "battle_won" in events)) and cb == l["chapter"] \
            and t.get("scene", scene) == scene
        hit = hit or ("affection" in t and aff >= t["affection"])
        hit = hit or ("battle" in t and lid == ctx.pending_battle and "battle_won" in events)
        if hit and lid in ctx.server_locations and lid not in ctx.checked_locations and lid not in found:
            logger.info(f"Minigame complete: {LOC_NAME[lid]}")
            found.append(lid)


GAME_ITEM_NAME = {}
for _i in ITEMS:
    _p = _i.get("payload") or {}
    if isinstance(_p, dict) and _p.get("type") == 0 and _p.get("id") is not None:
        GAME_ITEM_NAME.setdefault(_p["id"], _i["name"])
MINIGAME_NATIVES = {0x33A, 0x3E3, 0x3E4, 0x3F8, 0x403, 0x24E, 0x169, 0x17C, 0x156}   # + SP / stat grants


def log_script_calls(ctx, g, calls):
    """Debug aid for mapping minigames: every logged script-native call goes to script_log.txt; minigame natives
    and TreasureGetId reads of treasures that aren't locations are also shown in the client."""
    from .game.readhook import NATIVE_NAMES
    where = f"story={g.story_count()}\tchap={g.chapter_byte()}\tscene={g.i32(g.a['state_current_scene'])}"
    path = os.path.join(Utils.user_path("ccff7r"), "script_log.txt")
    with open(path, "a") as f:
        for nat, a0, a1, a2 in calls:
            if nat in (0x29A, 0x3E3, 0x254):              # repeated every frame by some scripts: log changes only
                if ctx.last_choice == (nat, a0, a1):
                    continue
                ctx.last_choice = (nat, a0, a1)
            name = NATIVE_NAMES.get(nat, hex(nat))
            extra = ""
            if nat == 0x24C:                              # AddGil(amount), signed
                extra = f"\t{a0 - 0x10000 if a0 & 0x8000 else a0:+d} gil"
            if nat == 0x24A:                              # AddItem(amount, id)
                extra = f"\t{GAME_ITEM_NAME.get(a1, hex(a1))} x{a0 - 0x10000 if a0 & 0x8000 else a0}"
            f.write(f"{time.strftime('%H:%M:%S')}\t{name}\t{a0}\t{a1}\t{a2}{extra}\t{where}\n")
            # research notes: the file gets every call, the client window each distinct one once per session
            # (some scripts call these every frame, e.g. the Ch4 jail key reads 178, a finish screen 3E3)
            if not ctx.script_echo:
                continue
            if nat in MINIGAME_NATIVES and (nat, a0, a1, a2) not in ctx.told_calls:
                ctx.told_calls.add((nat, a0, a1, a2))
                logger.info(f"Minigame event: {name}({a0}, {a1}, {a2}) (logged)")
            elif nat == 0x254 and a0 not in READ_LOCS and a0 not in TREASURE_LOCS and (nat, a0) not in ctx.told_calls:
                ctx.told_calls.add((nat, a0))
                logger.info(f"Minigame prize read: treasure #{a0} - not a location yet (logged)")


AFFECTION = 0xB24          # u16 at treasure_bits+0xB24 (exe+71B4D54): Aerith affection (cheat tables; 75 = trophy)


def research_tick(ctx, g):
    """Offline research mode (client attached to the game but not connected to a room): write script_log.txt
    (script calls, scene/mission/battle/materia changes, affection) and treasure_log.txt like a connected client,
    without giving items, sending checks or touching the save. Lets a tester trace an old save safely."""
    if not ctx.offline_told:
        ctx.offline_told = True
        logger.info("Not connected: research logging only (script_log.txt, treasure_log.txt, /snapshot). "
                    "No items are given and no checks are sent until you /connect.")
    if ctx.read_hook is None:
        from .game.readhook import TreasureReadHook
        ctx.read_hook = TreasureReadHook(g.pm, g.a["VM_CallNativeSite"])
    try:
        if ctx.read_hook.ensure() == "active":
            calls = ctx.read_hook.poll()
            if calls:
                log_script_calls(ctx, g, calls)
    except Exception:
        pass
    log_state_changes(ctx, g)
    log_affection(ctx, g)
    log_new_treasures(ctx, g, g.pm.read_bytes(g.a["treasure_bits"], SEED_TAG))


def log_state_changes(ctx, g):
    """Debug aid (v0.6.23): log scene, active mission, battle state and Zack's equipped-materia bytes
    (char_status+0x53..0x61) whenever they change, to find a trigger for Hojo's virtual mission (Ch4), which swaps
    the materia like a regular mission does."""
    try:
        cur = (g.i32(g.a["state_current_scene"]), g.u16(g.a["state_active_mission"]), g.i32(g.a["battle_state"]),
               g.pm.read_bytes(g.a["char_status"] + 0x53, 0x0F).hex())
    except Exception:
        return []
    old, ctx.state_seen = ctx.state_seen, cur
    if old is None or old == cur:
        return []
    events = ["battle_won"] if cur[2] == 6 and old[2] != 6 else []   # battle state 6 = results screen (doc 7.3aj)
    names = ("scene", "mission", "battle", "materia")
    diff = "\t".join(f"{n}={o}->{c}" for n, o, c in zip(names, old, cur) if o != c)
    with open(os.path.join(Utils.user_path("ccff7r"), "script_log.txt"), "a") as f:
        f.write(f"{time.strftime('%H:%M:%S')}\tState\t{diff}\tstory={g.story_count()}\tchap={g.chapter_byte()}\n")
    return events


def log_affection(ctx, g):
    """Debug aid: log every change of Aerith's affection with the scene, to map the Ch4 date activities."""
    v = g.u16(g.a["treasure_bits"] + AFFECTION)
    if v == ctx.affection:
        return False
    old, ctx.affection = ctx.affection, v
    if old is None:
        return False
    where = f"story={g.story_count()}\tchap={g.chapter_byte()}\tscene={g.i32(g.a['state_current_scene'])}"
    with open(os.path.join(Utils.user_path("ccff7r"), "script_log.txt"), "a") as f:
        f.write(f"{time.strftime('%H:%M:%S')}\tAffection\t{old}\t{v}\t{v - old:+d}\t{where}\n")
    logger.info(f"Aerith affection {old} -> {v} ({v - old:+d})")
    return v > old


def log_new_treasures(ctx, g, raw):
    """Debug aid for mapping: append every newly opened treasure bit (listed or not) to treasure_log.txt."""
    if ctx.prev_bits is None:
        ctx.prev_bits = raw
        return
    if raw == ctx.prev_bits:
        return
    path = os.path.join(Utils.user_path("ccff7r"), "treasure_log.txt")
    with open(path, "a") as f:
        for i in range(len(raw) * 8):
            if raw[i >> 3] >> (i & 7) & 1 and not ctx.prev_bits[i >> 3] >> (i & 7) & 1:
                listed = "listed" if i in TREASURE_LOCS else "NOT LISTED"
                line = (f"{time.strftime('%H:%M:%S')}\ttreasure={i}\t{listed}\tstory={g.story_count()}\t"
                        f"chap={g.chapter_byte()}\tscene={g.i32(g.a['state_current_scene'])}")
                f.write(line + "\n")
                if i not in TREASURE_LOCS:
                    logger.info(f"Opened treasure #{i} - not a location yet (logged)")
                else:
                    logger.info(f"Opened treasure #{i}")
    ctx.prev_bits = raw


# Mission -> mail pairs from the save-point script routine (all field scripts; doc 5.5). The game only runs it when
# a "mission cleared since the last save point" flag is set, which some clears never set (tester: 99-101 never came
# after 100% missions). The client delivers any mail whose mission is cleared but that isn't in the list yet.
MISSION_MAILS = {69: 85, 68: 86, 70: 87, 72: 88, 173: 89, 74: 90, 75: 91, 77: 92, 177: 93, 78: 94, 79: 95, 80: 96,
                 81: 97, 83: 98, 84: 99, 184: 100, 85: 101, 27: 102, 113: 103, 108: 104, 199: 107}


def deliver_mission_mails(g):
    have = g.mail_ids()
    if have is None:
        return
    have = set(have)
    ms = g.missions()
    for m, mail in MISSION_MAILS.items():
        if ms[m][1] and mail not in have and g.add_mail(mail):
            have.add(mail)
            logger.info(f"Delivered mission mail #{mail} (mission cleared, mail was missing).")


def log_new_mail(ctx, g):
    """Mapping aid for a future mailsanity option: log every newly received mail id."""
    n = g.u16(g.a["mail_count"])
    if n > g.MAIL_CAPACITY:
        return
    raw = g.pm.read_bytes(g.a["mail_list"], n * 4)
    ids = {int.from_bytes(raw[i*4:i*4+2], "little") for i in range(n)}
    if ctx.prev_mail is None:
        ctx.prev_mail = ids
        return
    new = sorted(ids - ctx.prev_mail)
    if new:
        path = os.path.join(Utils.user_path("ccff7r"), "mail_log.txt")
        with open(path, "a") as f:
            for m in new:
                f.write(f"{time.strftime('%H:%M:%S')}\tmail={m}\tstory={g.story_count()}\tchap={g.chapter_byte()}\t"
                        f"scene={g.i32(g.a['state_current_scene'])}\n")
                logger.info(f"New mail #{m} (logged)")
    ctx.prev_mail = ids


def launch(*args):
    async def main(a):
        ctx = CCFF7RContext(a.connect, a.password)
        ctx.server_task = asyncio.create_task(server_loop(ctx), name="server loop")
        if gui_enabled:
            ctx.run_gui()
        ctx.run_cli()
        loop_task = asyncio.create_task(game_loop(ctx), name="CCFF7R game loop")
        await ctx.exit_event.wait()
        ctx.server_address = None
        await loop_task
        await ctx.shutdown()

    import colorama
    parser = get_base_parser(description="CCFF7R Archipelago client")
    a, _ = parser.parse_known_args(args)
    colorama.just_fix_windows_console()
    asyncio.run(main(a))
    colorama.deinit()
