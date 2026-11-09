# Crisis Core -Final Fantasy VII- Reunion for Archipelago

An [Archipelago](https://archipelago.gg) multiworld randomizer world (apworld), client and PopTracker pack for
**Crisis Core -Final Fantasy VII- Reunion** (PC, Steam).

> **Status: alpha.** Seeds are beatable from start to finish (several full test runs), but expect rough edges.
> Please report problems with your client log (`<Archipelago>/logs/Launcher_*.txt`) and YAML.

## What gets randomized

Every item source below is a check, and the items they held go into the multiworld pool:

- **Story chests** in all 10 chapters, plus chapter clears.
- **Missions:** every mission reward and the treasure chests inside missions (300 missions).
- **Minigames:** Banora treasures and missile shelling, Aerith's date (perfume, Godspeed materia hunt, affection
  milestones), kids' guessing game, Hojo's experiments (simulation fights, timed machine, questionnaire, virtual
  mission), Wutai spies, squats, the flower wagon parts, the Seven Wonders of Nibelheim, sniper Zack, the waterfall
  chase and the Crescent Unit fight at the Leviathan statue. Each can be excluded.
- **Optional:** shopsanity (the first N slots of every shop, with Archipelago names shown in the buy list), DMW
  characters and memories, the Magic Pot, Buster Sword proficiency milestones, mailsanity, NPC mission handouts.

Progression items include **7 Goddess Materia** (the goal door needs all of them), **Progressive Chapter Keys**
(chapter gating), **Mission Sets** or **Progressive Mission Ranks**, Steal/Mug, shop addresses and accessory slots.

**Goal:** defeat Genesis at the end of Chapter 10.

## Setup

1. Install [Archipelago](https://github.com/ArchipelagoMW/Archipelago/releases) 0.6.x.
2. Put `ccff7r.apworld` from the [latest release](../../releases) into `Archipelago/custom_worlds/`.
3. Create your YAML from `Crisis Core Reunion.yaml` (release attachment), or from the Archipelago launcher's
   "Generate Template Options".
4. Generate and host as usual.
5. Start the game, then open **CCFF7R Client** from the Archipelago launcher and connect to the room.
   The client attaches to the running game on its own; no game files are modified on disk.
6. Optional: drop the PopTracker pack zip into PopTracker's `packs` folder for map tracking and autotracking.

Use a **new save** for every seed. The client stamps each save with its seed; a save from another seed is left
alone until you type `/claimsave`.

## Client commands

| Command | What it does |
|---|---|
| `/status` | Game attachment and progress |
| `/warp <chapter>` | Chapter select: arm a warp, then start any mission at a save point |
| `/shops [name]` | Shopsanity: what each shop's AP slots hold |
| `/shopnames on\|off` | Show or hide Archipelago names in shop menus |
| `/npcmissions [release]` | NPC handouts still waiting (or stop holding their missions for the session) |
| `/proficiency [reapply]` | Buster Sword proficiency and received boosts |
| `/claimsave` | Use the loaded save for this seed anyway |
| `/victory` | Send the goal manually (only if automatic detection failed) |
| `/maillist`, `/scriptlog`, `/snapshot`, `/snapdiff` | Research tools (see `docs/RESEARCH.md`) |

## How it works

The client is pure Python (pymem, bundled with Archipelago). It reads and writes the game's state in memory: it
replaces chest contents with placeholders, detects opened chests, cleared missions and other checks, and gives
received items directly. Four small code caves are installed at runtime: a script-native logger (minigames, NPC
handouts, DMW unlocks), a scene-jump hook (chapter gating and chapter select), a shop-purchase hook and a shop-name
hook (shopsanity). Everything is
documented in [`docs/RESEARCH.md`](docs/RESEARCH.md).

Tested on the Steam build (UE 4.27.2). Other builds may need new signatures (`apworld/ccff7r/game/addresses.py`).

## Repository layout

| Path | Contents |
|---|---|
| `apworld/ccff7r/` | The apworld: world logic, options, client and game-memory code |
| `apworld_build/build_data.py` | Builds `apworld/ccff7r/data/locations.json` and `items.json` from `data/` |
| `apworld_build/build_poptracker.py` | Builds the PopTracker pack into `poptracker/` (map images need the game's map textures exported with FModel, path in `CCFF7R_TEXDIR`) |
| `data/` | Mapped game data: treasures, missions, shops, mails, minigames |
| `docs/RESEARCH.md` | Reverse-engineering notes and the change history |
| `scripts/` | Cheat Engine and UE4SS research scripts, assembly sources of the client's code caves |

Build the apworld: run `python apworld_build/build_data.py`, then zip `apworld/ccff7r` as `ccff7r.apworld`.

## Credits

- **AssyMcJerk** – apworld, client, research, PopTracker pack.
- **DrMisunderstood** – testing, feedback and many bug reports.
- The Archipelago community, and the cheat table authors whose finds are credited in `docs/RESEARCH.md`.

Crisis Core -Final Fantasy VII- Reunion is © Square Enix. This is an unofficial fan project and is not affiliated
with or endorsed by Square Enix.
