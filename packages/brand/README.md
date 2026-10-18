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

Rules (from the approved mockups): dark gold chrome (desktop sidebar, Android splash and live-call screen) on `#0B0B0B` with
gold `#D4AF37`; light content surfaces `#F7F6F2`/`#FFFFFF` with dark text `#1A1A1A`; gold is the only accent and the only
primary-button colour; status chips use tinted backgrounds; emergency stop / end call is the only red filled button.
Hindi text must render with a Devanagari-capable font (Nirmala UI on Windows, Noto Sans Devanagari elsewhere).
