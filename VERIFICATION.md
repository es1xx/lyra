# Verification record

## Full monochrome themes (2026-11-02)

Theme colors now cover the entire interface, including all metadata, lyric
context, progress, notices, help, player selection, settings, switches, and
expanded color choices. Neutral dark surfaces replace blue-tinted backgrounds.
Word transitions dim the chosen color without blending toward white.

Verification commands:

```bash
/home/arch/.local/share/pipx/venvs/lyra-terminal/bin/python scripts/verify.py --sandbox-poll
# 90 tests passed, zero skipped.
ruff check src tests scripts
ruff format --check src tests scripts
.venv/bin/python -m build --wheel --no-isolation
git diff --check
sober preflight
```

A new headless rendering check inspects actual compositor foreground and
background colors after live theme changes. It covers white, cyan, violet, and
green across the main ASCII screen, help, player chooser, settings, and expanded
color selector. White must have equal RGB channels everywhere; colored themes
must retain the selected hue. Existing display settings and cancellation tests
remain in place. Live desktop playback was not retested.

## White default, color picker, and ASCII parentheses (2026-11-02)

New configurations use white. Display settings (S) now offer a color selector;
T still cycles themes. White, violet, green, cyan, and amber are available, and
legacy neon configurations remain valid. Existing saved themes and custom
accents are preserved until the user changes color. The ASCII font includes
both parentheses, so bracketed Latin and Ukrainian words render as large text
when they fit; narrow-terminal fallback remains intact.

Verified with:

```bash
/home/arch/.local/share/pipx/venvs/lyra-terminal/bin/python scripts/verify.py --sandbox-poll
# 89 tests passed, zero skipped.
ruff check src tests scripts
ruff format --check src tests scripts
.venv/bin/python -m build --wheel --no-isolation
git diff --check
sober preflight
```

Ruff was run from the locally installed Zed language-server distribution.
Headless UI checks cover applying each requested color, cancelling a color
change, theme cycling, and clearing a custom accent when cycling. Configuration
checks cover the white default and palette persistence, including legacy neon.
ASCII checks cover both bracket glyphs, parenthesized words, and narrow widths.
Live desktop playback was not retested for these display-only changes.

## Repository presentation

README now contains a real headless demo capture, quick start, feature overview,
and keyboard reference. The complete original guide is in docs/GUIDE.md.
Local Markdown targets and SVG XML were checked with Python, the SVG was rendered
with rsvg-convert and visually inspected, and the source distribution was rebuilt
using `.venv/bin/python -m build --sdist --no-isolation`. The MIT license and
author identity were selected by the owner; runtime code was not changed.

## Current display settings and ASCII update

Added S display settings (ASCII words, small lyric text, compact view), A ASCII
toggle, --ascii, and persisted ascii_art/show_context options. ASCII uses an
original built-in five-row font, including Ukrainian letters, with a normal-text
fallback when words cannot fit. No new dependencies were added.

The pipx Python 3.14 interpreter ran `scripts/verify.py --sandbox-poll`: **86 tests
passed, zero skipped**. New checks cover glyph geometry, Ukrainian text,
small-terminal fallback, settings Apply/Cancel, small-text visibility, and ASCII
rendering in full and compact views. Config roundtripping includes the new
options. Ruff, compilation and wheel rebuilding pass. The installed pipx
application is updated; an already running LYRA process must be restarted.


## Current follow-up: song-detection diagnosis

The user's pipx environment now contains Textual 8.2.8, dbus-next, and RapidFuzz
under Python 3.14. The full source suite ran using that interpreter:

```bash
/home/arch/.local/share/pipx/venvs/lyra-terminal/bin/python scripts/verify.py --sandbox-poll
# 80 tests passed, zero skips.
```

This includes Textual Pilot controls, help/player modals, small-terminal resizing,
actual dbus-next message encoding, and six new diagnostic/error-reporting tests.
A resize event handling issue was corrected. Player read failures now remain
visible instead of being reported as an absent player. `lyra --doctor` reports
bus access, available MPRIS names, title, artist, position, and refresh failures.
The wheel was rebuilt and installed into the existing pipx environment without
changing its dependency installations.

The session bus remains inaccessible to this tool sandbox (`Operation not
permitted`), so the cause of the user's live song-detection failure remains
unconfirmed until a diagnostic report is collected from their desktop terminal.
Headless UI verification is now complete; live player/network acceptance and
visual inspection remain pending. Earlier dependency-related skips below are
the historical initial-build record.

## Initial build record (historical)

This checkout implements the application, but **full runtime acceptance remains
pending**. Do not label it production-verified based on these results.

## Environment

- Arch Linux workspace, system Python 3.14.9, isolated CPython 3.12.14 venv.
- Shell network access/DNS is restricted. Normal `uv pip install -e '.[dev]'`
  failed; offline resolution lacked Textual/dbus-next/RapidFuzz.
- Existing local wheel-cache distributions supplied HTTPX, Rich, PyYAML,
  platformdirs, their dependencies, Ruff, setuptools and build tools inside
  `.venv` only. No system Python packages were modified.
- Metadata-matching tests ran with the standard-library fallback because
  RapidFuzz could not be installed.
- `playerctl -l` failed with `Could not connect: Operation not permitted`.
- A private `dbus-run-session -- true` also failed: binding a bus socket is
  prohibited here. It cannot stand in for a live integration check.

## Executed checks

From `/home/arch/lyra`:

```bash
.venv/bin/python scripts/verify.py --sandbox-poll
# 74 tests: 71 passed, 3 explicitly skipped.

# Ruff's binary came from the existing cached distribution:
.venv/lib/python3.12/site-packages/ruff-*.data/scripts/ruff check src tests scripts
.venv/lib/python3.12/site-packages/ruff-*.data/scripts/ruff format --check src tests scripts

.venv/bin/python -m compileall -q src tests scripts
.venv/bin/python -m build --no-isolation
PYTHONPATH=src .venv/bin/python -m lyra --help
PYTHONPATH=src .venv/bin/python -m lyra --version
```

Parsing, enhanced/standard timing, grouping, gaps, offsets, clock interpolation,
pause/resume/rate/seek behavior, track changes, metadata normalization and match
rejection, player priority, manual selection, capability guards, position reads,
provider failures, rate-limit cooldown, local files, cache TTL/eviction, TOML
validation and persistence are covered. HTTPX MockTransport exercises the actual
provider using original sample text without network requests.

`--sandbox-poll` works around denied asyncio socket wakeups by capping selector
waits in the test runner. It does not patch production code, replace worker
threads, or change clock math. A normal unrestricted environment should run
`python scripts/verify.py` or `python -m unittest discover -s tests -v` directly.

Packaging produced a source distribution and a Python wheel. This proves build
configuration and package inclusion, not that unavailable runtime dependencies
work together.

## Not verified here

Three tests skip with explicit reasons: one dbus-next signal test and two Textual
Pilot tests. Textual and dbus-next could not be installed. `lyra --demo` therefore
reports a missing Textual dependency; **the UI was not launched or visually
inspected**. No live Spotify, browser MPRIS connection, or live LRCLIB HTTP lookup
was possible. No 30 FPS benchmark or limited-color terminal test was performed.

## Remaining acceptance checks on an unrestricted desktop

1. Install with `pipx install .` or a development venv, then run the whole suite
   with no dependency-related skips. Confirm RapidFuzz-backed matching too.
2. Launch `lyra --demo`; inspect full/compact views at 100×34, 80×24, and 38×16.
   Test all shortcuts, help and player modals, and preferences after restart.
3. Play Spotify desktop: verify discovery, lyric retrieval, pause/resume,
   forward/back seeks, rapid track switching, and exit/restart reconnection.
4. Repeat with Spotify Web and YouTube Music in Chromium and Firefox. Record
   missing metadata/position/capabilities instead of inferring support.
5. With two players, switch which one plays and verify Automatic selection;
   pin one with P, disconnect it, and reconnect it.
6. Compare local enhanced LRC against a known recording; verify exact boundaries
   and rest gaps, then check the approximate label with standard LRC.
7. Test offline cache reuse, no-match and HTTP cooldown status, custom keymaps,
   true-color/256-color output, and CPU use with animations enabled/disabled.

Publication update: the owner selected MIT and confirmed the GitHub identity
Es1xx. The root LICENSE covers the original code, documentation, and demo assets.
The default LRCLIB User-Agent still has no repository URL; update it once the
public repository exists.
