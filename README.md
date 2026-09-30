<p align="center">
  <img src="docs/media/banner.png" alt="universal-modder" width="100%">
</p>

<p align="center">
  <b>Skills, tools and the fal MCP that let Claude Code mod almost any PC game you own.</b><br>
  It finds the game, works out the engine and the modding route, reads the real code, builds the mod,<br>
  generates art, 3D and sound with <a href="https://fal.ai">fal</a>, tests it in the running game, and cuts the showcase video.
</p>

<p align="center">
  <a href="#install"><img alt="Claude Code plugin" src="https://img.shields.io/badge/Claude%20Code-plugin-B6FF3B?labelColor=0A0D12"></a>
  <a href="https://fal.ai"><img alt="assets by fal" src="https://img.shields.io/badge/assets-fal-B6FF3B?labelColor=0A0D12"></a>
  <a href="LICENSE"><img alt="MIT" src="https://img.shields.io/badge/license-MIT-B6FF3B?labelColor=0A0D12"></a>
</p>

<p align="center">
  <img src="docs/media/teaser.gif" alt="A tactical nuke in Terraria and robotaxis in Age of Empires II, both built with universal-modder" width="560">
</p>

## Install

**As a Claude Code plugin** (recommended):
```
/plugin marketplace add rehan-remade/universal-modder
/plugin install universal-modder@universal-modder
```

**Or clone it and run Claude inside it** (works with Codex/Cursor via `AGENTS.md` too):
```bash
git clone https://github.com/rehan-remade/universal-modder && cd universal-modder && claude
```

Then give it a [fal API key](https://fal.ai/dashboard/keys) for assets. It powers both the bundled fal MCP
server and the `um fal` CLI:
```bash
export FAL_KEY=...
```
You also need Python 3.10+ and ffmpeg. `uv` is recommended; the CLI sets up its own env with it. Blender is
needed for 3D → sprite renders. Windows games are driven natively or from WSL; on Linux, native and Proton games
are driven under Hyprland (grim, gpu-screen-recorder, uinput; check with `um win setup`).

## Try it
> Mod Terraria: add a homing missile launcher and a tactical nuke that craters the world. Make the sprites with fal.

> Make a new civilization for Age of Empires II with a unique unit rendered from 3D.

> I own Skyrim SE. What would it take to put a Minecraft-style block-building mode in it?

> What engine is `C:\Games\Foo`, and how do people mod it?

Claude starts with the **mod-any-game** skill and runs the same loop every time: recon, pick a route, set up a
safe lab (saves backed up), read the actual code, build one working slice, generate assets, verify in the
real game, record, then package.

## What's inside

**Skills** (`skills/`)

| Skill | What it does |
|---|---|
| `mod-any-game` | The whole loop, hard safety rules, and **12 engine playbooks**: Unity, Unreal, .NET/XNA (Terraria, Stardew, Celeste), Godot, Source 1/2, Bethesda, Minecraft, AoE2/Genie, RE Engine/FromSoft/GTA/Cyberpunk/BG3, native C++, indie engines (GameMaker, RPG Maker, Ren'Py, Paradox, Doom, HTML5, LÖVE, Java), retro decomps |
| `game-recon` | Which engine and version, managed or native, anti-cheat, loaders, save folders, community route → `MODDING_PLAN.md` |
| `reverse-engineering` | ILSpy / Cpp2IL / Vineflower / Ghidra and IDA over MCP / Cheat Engine / Frida / RenderDoc; reverse-engineer a file format and prove it with a round trip |
| `fal-assets` | Sprites with real transparency, consistent variants, pixel art, seamless textures, PBR maps, image-to-3D, auto-rigging, SFX, music, voice, cutscene video |
| `asset-pipeline` | Art → engine-exact frames: cutout, nearest-neighbour fit, palettes, sheets, team-colour masks, 3D → 8/16-heading sprites |
| `game-automation` | Launch, screenshot (GPU-safe), click/type, windowed mode, crash-reporter cleanup, in-game agent bridges |
| `showcase-video` | Record the window with only the game's audio, pick moments, cut a styled video from an EDL |
| `mashup-mods` | Game-inside-a-game: content ports, passthrough mods, decomps as libraries, reimplementations |
| `publish-mod` | Lint, package per platform, credits, the post |

**The `um` CLI** (`bin/um`, Python). Every command has `--help` with examples.

| | |
|---|---|
| `um scan` | Find Steam/Epic/Xbox installs; fingerprint engine and version, .NET vs native, anti-cheat, installed loaders, save folders, ranked routes |
| `um fal` | `sprite`, `image`, `edit`, `rmbg`, `pixelate`, `upscale`, `texture`, `pbr`, `model3d`, `rig`, `sfx`, `music`, `voice`, `video`, `run`, `search`, `schema`, `price`. Plain REST, with a manifest of every generation |
| `um sprite` | `cutout`, `fit`, `pixelate`, `palette`, `sheet`, `slice`, `frames`, `team-mask`, `seamless`, `preview` |
| `um render3d` | GLB → sprite frames from the game's camera (`aoe2`, `iso8`, `trueiso`, `topdown`, `side`, `turntable`) with Blender |
| `um win` | `shot`, `record` (gfxcapture + process-loopback audio), `drive` (input that only reaches the game), `ps`, `kill`, `launch`, `reg` |
| `um video` | `contact` sheets, `compile` (EDL → titled, beat-cut video with music), `mux`, `beats`, `first-frame` |
| `um backup` | Snapshot, diff and restore save folders |
| `um publish check` | Blocks shipping game files, decompiled code and leaked keys |

Also bundled: the **fal MCP server** (`.mcp.json`), a SessionStart hook that puts `um` on PATH, and two
no-build Windows tools in `tools/win/`: WinDrive input and ProcLoopback game-only audio, both PowerShell with
embedded C#.

<p align="center"><img src="docs/media/pipeline.png" alt="3D route: fal concept to 3D to 16 AoE2 headings. 2D route: fal art to cutout to a 64x26 Terraria sprite in game." width="100%"></p>

## Built with it
- **[examples/terraria-tmodloader](examples/terraria-tmodloader)**: *Fal Arsenal* for tModLoader. A homing
  missile launcher, a tactical nuke (crater + mushroom cloud), a chain-lightning rifle, a black-hole gun, an
  orbital strike, three new enemies and a two-phase Drone Mothership boss. Every sprite came from fal.
- **[examples/aoe2-de-civ](examples/aoe2-de-civ)**: *San Franciscans* for Age of Empires II DE.
  - A new civilization with a Robotaxi unique unit and Delivery Drones, rendered from fal image-to-3D models
    at AoE2's camera angle.
  - A Transamerica Pyramid wonder.
  - A reverse-engineered `.sld` sprite writer.

Both started as one-line prompts. The non-obvious lessons from each are written into the skills
(`skills/mod-any-game/references/case-studies.md`).

## Rules it follows
- **Single-player and offline, on games you own.** It refuses to inject into online games with anti-cheat,
  write multiplayer cheats, or bypass anti-cheat, DRM or ownership checks.
- **It never ships game files or decompiled code.** Mods ship as code, your own assets, patches or
  converters.
- **It backs up before touching saves**, and kills processes by PID only.
- **It asks before** driving your mouse and keyboard, installing loaders into game folders, or publishing.

Full reasoning: [`skills/mod-any-game/references/safety.md`](skills/mod-any-game/references/safety.md).

## Credits
- Built from real sessions of Claude Code modding Terraria and Age of Empires II.
- Assets: [fal](https://fal.ai) (GPT Image 2, Nano Banana 2, FLUX, Trellis 2, ElevenLabs...).
- Standing on the shoulders of tModLoader, genieutils-py, AoE2ScenarioParser, BepInEx, Harmony, UE4SS,
  REFramework, SKSE, Fabric, ILSpy, Ghidra and every modding community that documented its game.
- The engine playbooks also draw on the September 2026 wave of AI-built mods, and on how their creators
  explained them in public.

MIT licensed. Fonts: Space Grotesk and JetBrains Mono (SIL OFL).
