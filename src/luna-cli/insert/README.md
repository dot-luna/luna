# Insert

Luna Menu groups Clipboard, Emoji, and GIFs under **Insert**. The emoji and GIF
backends use Luna's existing Lua runtime and compiled tools (`curl`,
`wl-copy`, `cliphist`, `wtype`); no Python package or separate emoji daemon is required.

Emoji names, category keywords, skin tones, flags, and joined sequences come from
Unicode Emoji 17.0, bundled for offline search. The picker uses bundled Fluent Emoji 3D graphics, with Twemoji artwork for sequences
Fluent does not cover. Noto Color Emoji remains an error fallback only. Inserted
text stays Unicode; receiving apps choose their own emoji appearance.
The data source is https://unicode.org/Public/17.0.0/emoji/emoji-test.txt and its
Unicode license is included in `data/LICENSE`. Only fully-qualified sequences are
listed, avoiding duplicate presentation variants. `data/emoji.json` retains their
original names and group/subgroup keywords.

Emoji and GIFs use compact grids without item labels or a separate detail pane.
Arrow keys navigate cells; Page Up/Down and Home/End move through the grid.
For emoji, Tab or click adds one copy without advancing focus, retaining duplicates
and selection order across searches. Enter inserts the full selection (or the
focused emoji when nothing is selected). Click a preview item to remove that copy;
Shift+click removes one copy of a grid emoji; Shift+Tab removes one copy of the
focused emoji without moving. Backspace with an empty search removes the last
selected copy. Leaving the Emoji view clears the selection.

## GIFs

**GIPHY** uses the official trending/search API directly from the desktop. Type to
search; scrolling or navigating to the bottom loads the next page automatically. The selected GIF animates in its grid tile.
Enter downloads the selected original GIF and pastes it as a file attachment
(maximum 25 MiB). The clipboard offers `text/uri-list`, which browsers expose as
an `image/gif` file. This preserves the animation; no GIPHY link is inserted.
The receiving app must support file pasting.
GIPHY results remain in provider order and show
provider/creator attribution. Preview media is not saved to Luna's disk cache. The chosen GIF is added to
clipboard history. Transfer files are removed after copying; the selected GIF
file remains privately under `$XDG_RUNTIME_DIR/luna-insert-gifs` until logout,
so the receiving app can read it asynchronously.

Create a key at https://developers.giphy.com/dashboard/ and run:

```sh
luna insert configure
```

The command reads the key without echoing it and saves it with mode 0600 to
`~/.config/luna/giphy.key`. The menu's **Set GIPHY API key** button opens this command
in a floating terminal. Reopen the GIPHY view after setup. `GIPHY_API_KEY` is also
supported for callers that manage their own environment; credentials never go
in process arguments or checked-in configuration.

Optional `~/.config/luna/insert.json`:

```json
{
  "gif_rating": "pg-13"
}
```

## CLI

```sh
luna insert emoji
luna insert gifs 'happy' 0
```

These commands return JSON. The menu captures the previously focused window and
passes its address to `paste-emoji` or `paste-giphy`. Paste is
cancelled if another app gains focus; the restored content stays on the clipboard.
