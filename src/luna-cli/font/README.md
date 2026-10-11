# Font commands

## Requirements

- Lua, lua-argparse, and fontconfig.
- The checkout's `bin/` directory on `PATH` to run `luna` directly.
- yay or paru for AUR operations.

## Search

```bash
luna font search jetbrains
luna font search jetbrains --aur
```

- Searches configured pacman catalogs for font/typeface matches.
- `--aur` adds live AUR results after official results.
- Results show package names, descriptions, and repositories.

## Install

```bash
luna font install ttf-jetbrains-mono noto-fonts
luna font install font-package --aur
luna font install ./regular.ttf ./font-family/
luna font install -r ./downloaded-fonts/
```

- Mix multiple package names, files, and folders in one batch.
- `--aur` selects AUR for every package target in the batch.
- Pacman installation includes a full system upgrade.
- Folders scan immediate files; `-r` includes subfolders.
- Local files support TTF, OTF, and TTC, validated before installation.
- Existing fonts are skipped; `--force` reinstalls them.
- Refreshes the cache once after a successful batch.

## List

```bash
luna font list
```

- Shows families, styles, file paths, and sources.
- Sources: pacman, foreign package, or local file.
- Foreign packages may come from AUR or a manually installed package archive.

## Remove

```bash
luna font remove ttf-jetbrains-mono "Font Family"
```

- Resolves package names, families, filenames, or full installed file paths.
- Previews targets and asks for confirmation.
- Ambiguous matches require a more specific name.
- Package removal may remove multiple families.
- Local removal supports files in user font directories, including manual installs.
- System files without package owners are left alone.

## Refresh

```bash
luna font refresh
```

## Storage

- Font files: `${XDG_DATA_HOME:-$HOME/.local/share}/fonts/luna/`.
- Uses original filenames; conflicting files require renaming or `--force`.
- No ownership database: Fontconfig finds files and pacman identifies package owners.

## Not supported yet

- Direct URL downloads.
- Archive extraction.
