# Brand package

Single source of truth for the SELL AGENT look and feel, derived from the FITRON logo
(gold mark on a near-black background). Both the Windows desktop app and both Android apps
must use these tokens; do not introduce other accent colours.

| File | Used by |
| --- | --- |
| `tokens.json` | reference values; `scripts/check_brand_sync.py` verifies the generated files match |
| `assets/fitron_mark.svg` | vector recreation of the mark used for app icons, splash and sidebar |
| `assets/fitron_logo.png` | **place the original logo PNG here** (ignored by git) for pixel-exact icons; `scripts/make_icons.py` generates `.ico` and Android mipmaps from it |
| `qt/theme.qss` | desktop stylesheet (loaded by `sellagent_desktop.theme`) |
| `android/colors.xml`, `android/BrandTheme.kt` | copied verbatim into each Android app |

Rules: gold `#D4AF37` is the only accent; backgrounds are `#0B0B0B`/`#141414`/`#1C1C1C`; text is warm off-white `#F5F0E1`;
the emergency stop is the only element allowed to use red as a fill. Hindi text must render with a Devanagari-capable font.
