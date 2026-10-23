# MarioCamXT 0.1 — Experimental

An unofficial modification of BunnymodXT nov-11-2024 for Half-Life, adding relative 45-degree turns and a consistent view-angle reset for keyboard and blindfolded play.

The finished camera code is inside **BunnymodXT.dll**. Players do not need Python or the source folder to use it. The original BXT functionality is retained in the modified DLL; individual BXT features have not all been retested.

## Download

On the GitHub project page, open **Releases** and download the attached **MarioCamXT.zip**. Extract the ZIP before launching anything.

This is an experimental Windows build for the supported Half-Life/GoldSrc setup. A user has reported working camera commands in-game. Compatibility with every Half-Life branch, mod, and long run has not been established; see VALIDATION.txt.

## Camera commands

| Command | Action |
| --- | --- |
| `mariocam_left` | Turn 45 degrees left relative to the current view. |
| `mariocam_right` | Turn 45 degrees right relative to the current view. |
| `mariocam_reset` | Reset pitch, yaw, and roll to c1a0's player-start orientation. |
| `mariocam_info` | Show the MarioCam version and reset angles. |

Left/right preserve pitch and roll. Eight presses make a full turn. Reset reads the first `info_player_start` in `maps/c1a0.bsp` through the game filesystem and caches its angles for the active game directory. The reference stays consistent across maps and save loads. If that reference cannot be read, the command reports an error and leaves the view alone.

## Install and launch

1. Keep **Injector.exe** and **BunnymodXT.dll** together in the extracted MarioCamXT folder. Do not replace the game's `hl.dll` or `client.dll`.
2. Back up your existing `Half-Life\valve\config.cfg`. Review the supplied settings described below, then copy **mariocam.cfg** into `Half-Life\valve`.
3. Make sure Steam is running and Half-Life is fully closed.
4. Create a Windows shortcut to this package's **Injector.exe**. Open its Properties. In **Target**, keep the quoted Injector.exe path, then add a space, the quoted full path to your Half-Life **hl.exe**, and ` +exec mariocam.cfg`.
5. Set **Start in** to the folder containing this Injector.exe and BunnymodXT.dll, in quotes. Apply the shortcut changes and launch it.
6. In the game console, run `mariocam_info`. After loading a singleplayer map, try the camera keys.

For example, if the extracted files are in `C:\Tools\MarioCamXT` and Half-Life uses Steam's default installation path, the shortcut Target is:

```text
"C:\Tools\MarioCamXT\Injector.exe" "C:\Program Files (x86)\Steam\steamapps\common\Half-Life\hl.exe" +exec mariocam.cfg
```

In that example, Start in is `"C:\Tools\MarioCamXT"`. Use the actual folders on your own computer. A shortcut made on someone else's computer may point to folders you do not have.

Alternatively, start Half-Life normally, run this package's Injector.exe once, and execute `exec mariocam.cfg` in the game console after injection. Use a fresh Half-Life process when changing DLL versions.

## Supplied config: all controls and settings

The supplied config is a keyboard-practice profile. It changes the following keys:

| Key | Action |
| --- | --- |
| HOME | Reset view to c1a0's player-start angles. |
| Left arrow | Relative 45-degree turn left. |
| Right arrow | Relative 45-degree turn right. |

**The config disables mouse view movement** with `m_yaw 0` and `m_pitch 0`. Remove those two lines before executing it if you want to retain your existing mouse settings. If already applied, restore your previous values from your config backup.

The V/B aliases enable `fps_override`. The config hides BXT's incorrect-FPS indicator. These are configurable practice settings; hiding an indicator does not change a category's rules.

Numpad 2 starts demo numbering at `run_1.dem` each time. Preserve wanted recordings before starting another attempt because the same names can be reused. Executing the config only defines the alias and its key; pressing Numpad 2 runs it.

The binds use BXT's `bxt_append` to run after commands already in the command buffer. If controls do not apply automatically, check `bind HOME` and try `exec mariocam.cfg` after startup. An `Unknown command: bxt_append` or unknown `mariocam_*` command indicates that the required DLL commands are not available; check which DLL was loaded.

You can rename this config and change the corresponding `exec`/`+exec` filename, or copy its commands into another config that you already execute. Copy the alias definitions along with their bindings. To use only the camera keys, retain these lines in your own config:

```cfg
bxt_append "bind HOME mariocam_reset"
bxt_append "bind LEFTARROW mariocam_left"
bxt_append "bind RIGHTARROW mariocam_right"
```

There are no custom Options > Keyboard entries in this package. Change the key names in your config to rebind the camera commands.

## Quick check

On a singleplayer map, check `mariocam_info`. Press left then right and verify that the view returns to the same heading. Eight left presses should make a full turn. Look away using your available view controls, press HOME, and check that the reference angles are restored. Repeat the reset after loading a save on another map, then check a BXT feature you normally use.

## Source, build, and validation

`source/mariocam.c` contains the added camera code, `source/build_patch.py` produces the modified DLL, and `source/test_patch.py` runs development checks. None of these files runs when players launch the game. Build instructions are in `source/BUILD.txt`.

This is a compiled extension of one exact BXT binary, with its command registration patched; it is not a full rebuild of upstream BXT. The input is locked to the SHA256 documented in the source and VALIDATION.txt. A different BXT version needs a new integration. The original input DLL and game maps are not bundled.

SHA256SUMS.txt lists the packaged files for integrity checks. Passing these checks establishes file consistency, not compatibility with a particular game installation.

## Credits and licenses

BunnymodXT and its original injector are by their upstream authors and contributors. This package adds the MarioCam commands and includes an unchanged copy of the injector. It is an unofficial modification.

- [BunnymodXT source at the base commit](https://github.com/YaLTeR/BunnymodXT/tree/cbc496b1ba7f6c242a961c33f16d3b5741371dd6)
- [BunnymodXT Injector](https://github.com/YaLTeR/BunnymodXT-Injector)
- [Valve Half-Life SDK](https://github.com/ValveSoftware/halflife)

Keep LICENSE-BunnymodXT.txt, LICENSE-Injector.txt, and LICENSE-MarioCam.txt with redistributed packages. Those files contain the applicable notices and license terms.
