# Branding

Dīvi's logo was designed by the project founder: a drone inside three rings, each with a meaning
that the whole colour system follows (`src/avispria/app/ui/theme.py`).

| Colour | Hex | Meaning | In the interface |
|---|---|---|---|
| Green | `#669762` | vegetation, forest | the main action, good news |
| Yellow | `#DBB241` | agriculture | attention that is not an error |
| Blue-grey | `#7A96AA` | urban | the second action, built things |
| Slate | `#47545E` | the drone | outlines, the dark parts of the logo |

Errors use a brick red (`#C4513C`), never a logo colour.

- `logo-source.png`: the logo as supplied (transparent, 2048 px).
- `logo.png`, `logo-dark.png`: 1024 px copies. In the dark one the slate drone is lifted to light
  slate so it shows on a dark page; the three colours are unchanged.
- Smaller copies (window, browser tab, phone page and home-screen icons) are made with
  `python scripts/make_branding.py`.

**Licence: not yet decided.** The code is AGPL-3.0-or-later, but that is not automatically the right
licence for a logo. The owner should choose (for example all rights reserved, or a Creative Commons
licence) and state it here. Because an AI tool was used for the colouring, it is worth checking that
tool's terms before choosing.
