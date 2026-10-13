# Emoji artwork

The picker and selection preview use Microsoft's **Fluent Emoji 3D** artwork
(MIT, see LICENSE-fluent.txt). Unsupported sequences use **Twemoji** artwork by
Twitter, Inc. and other contributors (CC BY 4.0, see LICENSE-twemoji.txt).

Fluent PNGs are bundled from the official Microsoft repository at revision
`1ffb34c752ecf5d402f04cfb4b392c77f57c54bc`, preserving their colors and transparency.
Twemoji SVGs were obtained from Iconify on 2026-10-14, preserving their SVG bodies
and original colors. SVG wrappers supply the source viewBox dimensions.

Sources:
- https://github.com/microsoft/fluentui-emoji
- https://github.com/twitter/twemoji
- https://github.com/iconify/icon-sets/blob/master/json/twemoji.json

The Unicode-to-artwork mapping lives in `src/luna-cli/insert/data/emoji.json`.
Only referenced assets are bundled, and QML loads visible cells on demand.
These assets change presentation only, never the Unicode sequences inserted.
