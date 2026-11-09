from dataclasses import dataclass
from Options import Choice, Range, Toggle, DefaultOnToggle, OptionSet, PerGameCommonOptions, DeathLink


class GoddessMateria(Choice):
    """The door to the final boss needs all 7 Goddess Materia, so they are always required for the goal.
    shuffled: they are in the item pool (can be anywhere in the multiworld).
    vanilla: they stay in their Chapter 10 Banora Underground chests."""
    display_name = "Goddess Materia"
    option_shuffled = 0
    option_vanilla = 1
    default = 0


class ChapterGating(Toggle):
    """Each chapter after Chapter 1 needs a Progressive Chapter Key. Without the next key, walking into the
    chapter's final event bounces you back to the field (missions stay playable). The client's /warp
    command (chapter select) can also take you to any chapter you hold the key for.
    Off: the story is always playable."""
    display_name = "Chapter Gating"


class MissionUnlocks(Choice):
    """How missions are unlocked.
    progressive_rank: every mission up to your current rank is open. Each 'Progressive Mission Rank' raises it by 1
      (starts at Starting Mission Rank). Easy missions first, hard ones later.
    per_set: one item per mission set (51 items, e.g. 'Mission Set M2-1'). The set's first mission opens with the item;
      the rest open as you clear them, or at the chapter where the base game opens them (e.g. 5-1-2 in Ch3, 1-1-2 in
      Ch9; also when the set arrives later). NPC missions open once their NPC has handed them out.
      Two extra rank-1 sets are placed early, and in this world a set never sits in a location much earlier than
      its first mission's rank (e.g. a rank 9 set only in Ch9+ / rank 8+ locations).
    vanilla: missions unlock as in the base game (story, NPCs, mission chains). Midgar NPC missions stay missable."""
    display_name = "Mission Unlocks"
    option_per_set = 0
    option_vanilla = 1
    option_progressive_rank = 2
    default = 2


class StartingMissionRank(Range):
    """progressive_rank only: missions of this rank and below are open from the start (rank 1-2 = 109 checks)."""
    display_name = "Starting Mission Rank"
    range_start = 1
    range_end = 10
    default = 2


class MissionDifficultyLogic(DefaultOnToggle):
    """Logic expects higher-rank missions only after enough chapters: rank 1-2 any time, 3 Ch3, 4 Ch4,
    5 Ch5, 6 Ch7, 7 Ch8, 8 Ch9, 9-10 Ch10. Keeps important items off missions you can't survive yet.
    Shopsanity: a shop's slots are expected from the chapter where its address is found in vanilla (Shinra Shop
    from the start, Sec.5/6/8 shops Ch4, Wutai Secret Shop Ch7, Online Shop Shade Ch10, ...), so required items
    aren't put in shops you can't afford yet. Needs Chapter Gating to have an effect."""
    display_name = "Mission Difficulty Logic"


class MaxMissionRank(Range):
    """Missions above this rank are not checks at all: they are left out of the world (fewer locations, so
    hints and the location count only cover what you'll play) and their rewards stay vanilla in game.
    progressive_rank: there are only enough rank items to reach this rank. per_set: sets with no mission at
    or below this rank get no set item. 10 = every mission is a check."""
    display_name = "Max Mission Rank"
    range_start = 1
    range_end = 10
    default = 10


class MaxProgressionRank(Range):
    """Missions above this rank never hold progression items (they still count as checks).
    Ranks 9-10 are post-game difficulty, so the default keeps required items out of them.
    Has no effect above Max Mission Rank."""
    display_name = "Max Mission Rank for Progression"
    range_start = 1
    range_end = 10
    default = 8


class MissableProgression(Toggle):
    """Off (recommended): story chests and minigame rewards never hold progression items.
    Story areas can't be revisited once the story moves on (no chapter select), so a required item there could
    be lost for good. Missions can always be replayed and chapter clears always happen, so progression goes there."""
    display_name = "Progression in Missable Locations"


class ExpMultiplier(Range):
    """Multiplies EXP gained in battle (client side). Crisis Core levels up through the DMW, and the chance of
    a level-up roll rises with accumulated EXP, so more EXP = more frequent level-ups."""
    display_name = "EXP Multiplier"
    range_start = 1
    range_end = 10
    default = 2


class GilMultiplier(Range):
    """Multiplies the gil Zack earns from battles (client side). Only battle gil counts, i.e. gil gained during a
    fight or within a few seconds after it, so selling items is never multiplied. Handy with shopsanity."""
    display_name = "Gil Multiplier"
    range_start = 1
    range_end = 10
    default = 1


MINIGAMES = {
    "leviathan_statue": "Optional Crescent Unit fight at the Leviathan statue (Ch1, before the Ogre)",
    "banora_treasures": "Collecting the items on the way to Angeal's house (Ch2)",
    "banora_missile": "Missile shelling run back to Angeal's house (Ch2): one check for finishing it",
    "banora_sparkles": "Timed golden item points during Banora's destruction (Ch2)",
    "perfume_blending": "Perfume blending on Aerith's date (Ch4 slums): one check for the first blend",
    "materia_pickup": "Godspeed materia hunt on Aerith's date (Ch4 slums): one check for finishing it",
    "aerith_affection": "Aerith's affection on the Ch4 date reaching 25 / 50 / 75 (3 checks)",
    "kids_guessing": "Kids number guessing (Ch4 slums)",
    "wutai_spies": "Finding the 6 Wutai spies (Midgar / slums)",
    "hojo_lab": "Hojo's experiments: the 4 Ch3 simulation fights, and in his Ch4 lab the timed SP machine, the "
                "questionnaire and the virtual mission (7 checks)",
    "squats": "Training Room squats (Ch5)",
    "flower_wagon": "Flower wagon parts questline (Ch2-7)",
    "seven_wonders": "Seven Wonders of Nibelheim (Ch8-9)",
    "sniper_zack": "Sniper Zack (Nibel plains, Ch9)",
    "waterfall": "Waterfall treasure chase (Gongaga hills, Ch9)",
}


class ExcludedMinigames(OptionSet):
    """Minigames whose rewards are NOT checks. Their rewards stay vanilla, so you can skip them entirely.
    Use ["all"] to exclude every minigame. Valid: all, """ + ", ".join(MINIGAMES) + """."""
    display_name = "Excluded Minigames"
    valid_keys = frozenset(MINIGAMES) | {"all"}
    default = frozenset()


ExcludedMinigames.__doc__ = ("Minigames whose rewards are NOT checks. Their rewards stay vanilla, so you can skip them "
                             "entirely.\nUse [\"all\"] to exclude every minigame. Valid keys:\n"
                             + "\n".join(f"  {k}: {v}" for k, v in MINIGAMES.items()))


class ShopSlots(Range):
    """Shopsanity: how many slots of every shop are Archipelago checks (0 = off). Buying the slot's item the
    first time sends the check (you still get the item). Shops other than the Shinra Shop need their shop
    address. Use the client's /shops command to see what each slot holds."""
    display_name = "Shop Slots"
    range_start = 0
    range_end = 16
    default = 0


class DeathLinkQueue(Toggle):
    """DeathLink only. Off: deaths received while Zack isn't fighting collapse into one (he falls once, in his next
    battle). On: every received death is queued and costs Zack one battle each, one per battle."""
    display_name = "DeathLink Queue"


class DMWCharacters(Toggle):
    """The 7 DMW characters (Sephiroth, Angeal, Tseng, Cloud, Aerith, Cissnei, Genesis) are items ('DMW: <name>').
    Every portrait starts as a silhouette (three matching silhouettes still give Chain Slash); a character's
    limit breaks and memories only show up once you receive them. The moment the story would add a character
    to the DMW becomes a check."""
    display_name = "DMW Characters"


class DMWStartingCharacters(Range):
    """DMW Characters only: how many random DMW characters you start with (vanilla starts with Sephiroth and Angeal).
    With only one character the reel seems to never land limits, modes or summons (tester), so the default is 2.
    Testers saw limits start working at 2 characters in one run (Angeal first) and at 3 in another, so it may
    depend on which characters you have.
    Their story unlocks are still checks."""
    display_name = "DMW Starting Characters"
    range_start = 0
    range_end = 7
    default = 2


class DMWMemories(Toggle):
    """Every DMW memory scene is a check (6 per character, 2 for Genesis = 38). Memories roll at random during
    battle and most unlock with story progress, so these are grindy: they never hold progression items.
    With DMW Characters on, a character's memories need that character."""
    display_name = "DMW Memories"


class MagicPot(Toggle):
    """Adds the Magic Pot DMW summon (key item 'Magic Pot Tricks') to the item pool. Doing the Magic Pot's
    request in Mission 10-2-3 (Jump, Fira, Gravity, Assault Twister) becomes a check. The check never holds
    progression items."""
    display_name = "Magic Pot"


class BusterSwordProficiency(Range):
    """Buster Sword proficiency (Battle Stance growth, from Chapter 6): one check per 10% up to this value
    (0 = off, 50 = checks at 10/20/30/40/50%). Values are rounded down to a multiple of 10. Growing it is slow,
    so these checks never hold progression items."""
    display_name = "Buster Sword Proficiency Checks"
    range_start = 0
    range_end = 100
    default = 0


class ProficiencyBoosts(Range):
    """How many Buster Sword proficiency boosts of each kind are in the item pool (Perfect Guard, Command Kill,
    Strong Attack Kill). Each one adds a quarter of that stance's growth: 7.5%, 6.25% and 6.25% of the meter.
    The client applies them once the proficiency system is active (Chapter 6)."""
    display_name = "Proficiency Boosts"
    range_start = 0
    range_end = 4
    default = 2


class Mailsanity(Toggle):
    """Every mail is a check (100: the three Zack Fan Club endings share one). Story mails follow the story chest
    rule (no progression unless Progression in Missable Locations is on); fan club, Wonder Hunter and Cissnei's
    hint mails are optional and never hold progression; mission mails follow their mission."""
    display_name = "Mailsanity"


class NPCMissionChecks(Toggle):
    """The 16 missions handed out by Midgar NPCs (1-2-1, 2-1-1..2-1-6, 4-3-1..4-3-6 = the Wutai spies, 6-2-1, 7-1-1,
    8-2-1) send a check when the NPC gives them to you. Those missions stay locked until their NPC hands them out
    (the client no longer opens them early). Missed one? /warp back to its chapter and talk to the NPC
    (client command /npcmissions lists what's left). Handouts follow the story chest rule for progression."""
    display_name = "NPC Mission Checks"


@dataclass
class CCFF7ROptions(PerGameCommonOptions):
    goddess_materia: GoddessMateria
    chapter_gating: ChapterGating
    mission_unlocks: MissionUnlocks
    starting_mission_rank: StartingMissionRank
    mission_difficulty_logic: MissionDifficultyLogic
    max_mission_rank: MaxMissionRank
    max_progression_rank: MaxProgressionRank
    missable_progression: MissableProgression
    exp_multiplier: ExpMultiplier
    gil_multiplier: GilMultiplier
    excluded_minigames: ExcludedMinigames
    shop_slots: ShopSlots
    death_link: DeathLink
    death_link_queue: DeathLinkQueue
    dmw_characters: DMWCharacters
    dmw_starting_characters: DMWStartingCharacters
    dmw_memories: DMWMemories
    magic_pot: MagicPot
    buster_sword_proficiency: BusterSwordProficiency
    proficiency_boosts: ProficiencyBoosts
    mailsanity: Mailsanity
    npc_mission_checks: NPCMissionChecks
