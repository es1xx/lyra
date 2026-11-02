# ◉ LYRA

**Your music, in words.** A native Linux terminal lyrics player with MPRIS discovery,
word and duo karaoke, a dark monochrome interface, and honest timing indicators.
Python 3.12+; Spotify desktop and any browser/player exposing MPRIS2 on your
session bus. No account, root access, microphone, or audio capture is needed to run it.

## Install on Arch Linux

From this checkout (`~/lyra`), with Python and pipx already installed:

```bash
cd ~/lyra
pipx install .
pipx ensurepath
# Open a new terminal if ~/.local/bin was not already on PATH.
lyra --demo
lyra
```

If prerequisites are missing, an administrator can install Arch's packages first:

```bash
sudo pacman -Syu python python-pipx
# Optional diagnostic tool:
sudo pacman -S playerctl
```

See [Arch's Python package](https://archlinux.org/packages/core/x86_64/python/)
and [python-pipx](https://security.archlinux.org/package/python-pipx).
LYRA itself installs into pipx's isolated environment, never system Python.
Do not use `sudo pip`, `--break-system-packages`, or run LYRA with sudo.

Alternative with a virtual environment (Arch package `python-pip` supplies pip):

```bash
cd ~/lyra
python -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/lyra --demo
```

With `uv` installed, `uv venv && uv pip install -e '.[dev]'` is another option.
For updates after source changes, run `pipx reinstall lyra-terminal`.
If an Arch Python upgrade invalidates pipx environments, use `pipx reinstall-all`.
The distribution is `lyra-terminal`; the executable is **`lyra`**.

## Use

Start music, then launch LYRA in a terminal in the same graphical login session:

```bash
lyra
lyra --compact
lyra --ascii
lyra --mode word
lyra --mode duo
lyra --player spotify
lyra --lyrics ~/Music/song.lrc
lyra --demo
lyra --debug
lyra --doctor
lyra --config /path/to/config.toml
lyra --help
```

Automatic selection prefers a **playing** player, then your preferred player.
`--player` sets this preference; press **P** to pin a specific connected player
for the session. Select Automatic to follow the currently playing player again.
If a selected player disappears, LYRA follows an available player and recognizes
the selected player again when it returns. A local `--lyrics` file stays pinned
across tracks: it is your responsibility to pair it with the right recording.
**R** reloads that file or forces a fresh provider lookup, respecting cooldowns.

The original, 44-second demo loops and supports play/pause, seeking, offsets,
and all UI controls. It requires installed Python dependencies but no music
player, session D-Bus connection, or network requests.

| Key | Action |
| --- | --- |
| Space | Pause / resume |
| Left / Right | Seek −5 / +5 seconds |
| Up / Down | Advance / delay lyrics by 50 ms |
| W / D | Word / duo mode |
| C | Compact view |
| A | Toggle large ASCII letters; enabling selects word mode |
| S | Display settings: color, ASCII, small lyric text, compact view |
| T | Cycle white, violet, green, cyan, amber, legacy neon |
| P | Player chooser; arrows and Enter select, Escape cancels |
| R | Refresh lyrics |
| H / ? | Help; Escape closes |
| Q / Ctrl+C | Quit |

Positive offset means **show lyrics earlier**: lookup time is player position
plus offset. Offset is limited to ±60 seconds. Unsupported player controls show
a status message. Plain lyrics can be scrolled with the mouse wheel.
Press **S** to choose large ASCII words, retain/hide the small lyric text beneath
them, or enable compact view. Press Apply to use the changes; Escape cancels.
**A** quickly toggles ASCII and starts in word mode; **D** can still select duo.
The built-in five-row ASCII font supports parentheses `()`, Latin letters, Ukrainian/Cyrillic,
digits and common punctuation. Words that do not fit, or have unsupported glyphs,
remain normal text with their original spelling. Preferences are saved on exit.
Compact view hides status and timing labels; C restores them. With small lyric
text enabled, the current full line remains visible below the active word.

Each theme colors the whole interface: lyrics, track details, progress, help,
player chooser, and settings. White uses only white, gray, and black; colored
themes use shades of the selected color on neutral dark backgrounds.
White is the default for new configurations. Choose a color with **S**, or cycle
with **T**. Existing saved themes and custom accents are preserved until changed.

## Timing and lyric sources

The UI distinguishes three kinds of synchronized data:

- **WORD TIMESTAMPS**: actual word/group timestamps from enhanced LRC or LRCLIB
  Lyricsfile YAML. End markers and explicit word ends preserve pauses.
- **≈ ESTIMATED WORD TIMING**: standard LRC lines divided proportionally by word
  length. Useful as a guide, often wrong around rests or held notes.
- **LINE TIMESTAMPS**: exact line starts with estimation disabled; a whole line is
  shown, regardless of word/duo mode. Word precision cannot be recovered from lines.

Plain lyrics are labeled **UNSYNCED** and displayed as scrollable text with no
karaoke highlighting. They are never assigned invented timestamps. In compact
mode they show an UNSYNCED LYRICS notice; return to full mode to read them.
A timestamped multiword group remains intact even in word mode. Splitting it
would invent timing. Duo mode combines adjacent timestamped groups within each
line. LRC's last word ends at an explicit terminal tag, the next line, or track
end; with no track duration the final line is capped at five seconds.

Local files must be UTF-8 (BOM supported). LYRA accepts standard `[mm:ss.xx]`,
millisecond timestamps, repeated line timestamps, `[offset:milliseconds]`,
metadata tags, and enhanced `<mm:ss.xx>` timestamps. Negative file offsets are
clamped at zero when necessary. Invalid timestamps produce a visible error.
The files in `examples/` contain only original demo material.

LYRA uses [LRCLIB's public API](https://lrclib.net/docs.txt): signature lookup
(`/api/get`) followed by conservative metadata search (`/api/search`). It reads
word timing from `lyricsfile` where available, with LRC/plain fallbacks. Requests
are serialized with a 400 ms interval. HTTP 429/503 `Retry-After` triggers a
shared cooldown with jitter; press R after it expires. There is no scraping,
authentication bypass, or automatic upload. Track title, artist, album and
length are sent to LRCLIB; artwork is retained as metadata but never downloaded.

Matches require strong title/artist similarity (score ≥0.90), matching version
markers such as live/acoustic/remix, and a duration difference of at most three
seconds when both lengths are known. Remaster and featured-artist decorations
are normalized; album affects ranking. Ambiguous distinct matches are rejected.
This intentionally rejects some legitimate matches. Use a local LRC for those.
The default User-Agent identifies LYRA; distributors should set `user_agent` to
include their actual project homepage or contact, as requested by LRCLIB.
No project URL or owner contact has been invented in the source.

## Browser integration

Compatibility depends on both the browser and the website exposing metadata,
position, and control capabilities through the Media Session API/MPRIS bridge.
A working desktop media popup alone does not guarantee a position is exposed.

- **Spotify desktop** normally supplies its own MPRIS player. Start playback
  before checking `playerctl -l`.
- **Spotify Web / YouTube Music / Chromium-based browsers**: keep the music tab
  open and playback active. Enable the browser's media controls/media session
  integration if you previously disabled it; remove custom flags that disable
  Linux MPRIS. Feature names vary by browser version. Restart and check the bus.
- **Firefox**: enable media-key controls. If necessary, inspect `about:config`
  and ensure `media.hardwaremediakeys.enabled` is true, then restart Firefox.
  See [Mozilla's media-control setting discussion](https://support.mozilla.org/en-US/questions/1309968).
- Flatpak/browser isolation may affect session bus access. Check the browser's
  documented MPRIS permissions. LYRA cannot create metadata a website omits.

Run `lyra --doctor` while music is playing for a one-shot report of session-bus
access, discovered players, title, artist, playback position, and player-read errors.
It runs without the terminal UI and makes no lyrics requests.

Additional diagnostics (playerctl is optional and is never used to scrape a browser):

```bash
playerctl -l
playerctl --all-players metadata
playerctl --player=spotify status
playerctl --player=spotify position
printf '%s\n' "$DBUS_SESSION_BUS_ADDRESS"
```

Prefer a desktop terminal over a root shell, container, or unrelated SSH session.
Do not start a separate D-Bus session for LYRA: it would not contain the music
player. With no session bus, LYRA reports the failure and retries every three
seconds. Player discovery reconciles every two seconds and responds to name and
property signals between polls. Position is separately queried because MPRIS
Position usually does not emit property changes. Between samples, a monotonic
clock interpolates according to playback state and rate. Seeked signals correct
immediately; polling catches players that omit signals. No position ever sampled
for a track means LYRA explicitly refuses to claim synchronized playback.

## Configuration

Preferences are created/saved on clean exit at
`~/.config/lyra/config.toml` (or `$XDG_CONFIG_HOME/lyra/config.toml`). CLI overrides
and keyboard changes are saved too. Saving rewrites known options and shortcuts;
comments/custom formatting are not retained. Unknown options and invalid values
produce an error naming the file. A `--config` path changes both load and save.

```toml
theme = "white"                  # white | violet | green | cyan | amber | neon
accent = ""                      # optional #RRGGBB; T clears this override
provider = "lrclib"               # lrclib | local (requires --lyrics)
mode = "duo"                     # word | duo
compact = false
ascii_art = false                # large ASCII words; A toggles
show_context = true              # retain small lyric text, including compact view
animation_intensity = 0.65        # 0 disables glow, through 1
refresh_rate = 30                 # 5–60 FPS
preferred_player = ""
sync_offset_ms = 0
estimate_words = true
cache_enabled = true
cache_ttl_days = 7                # 1–365
cache_max_entries = 500           # 1–10000
user_agent = "LYRA/0.1.0 (local Linux terminal lyrics client)"
```

An optional `[shortcuts]` table **replaces** the default map. Action names and all
bindings are listed in `examples/config.toml`. Keep `q = "quit"` and a help key
for convenience; Ctrl+C is always available. The player chooser reserves arrows
and Enter while open. Theme colors are quantized automatically by Textual/Rich
for terminals without true-color support. A Unicode-capable monospace font is
recommended. Short terminals hide secondary context; use compact mode for very
small windows. An intensity of zero keeps words and progress responsive without
color animation. Render rate never controls the underlying playback clock.

Successful lyric records live under `~/.cache/lyra/lyrics/` (respects
`$XDG_CACHE_HOME`). Writes are atomic, entries expire, and oldest entries are
pruned to the configured limit. Unavailable/unwritable caches do not stop playback.
Cached lyrics remain usable offline; new songs require network or local files.
Remove cache JSON files to clear stored lyrics. The `--debug` option creates
bounded rotating `debug.log` files in the same cache root; they can contain song
metadata and request URLs.

## Development and verification

```bash
python -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python scripts/verify.py
.venv/bin/python -m ruff check src tests scripts
.venv/bin/python -m ruff format --check src tests scripts
.venv/bin/python -m compileall -q src tests
.venv/bin/lyra --demo
```

The unittest suite also runs under pytest. HTTP tests use HTTPX MockTransport
with original sample text; they do not contact LRCLIB. Textual Pilot tests cover
controls, player/help modals, missing players, and resizing. Signal tests use
actual dbus-next message types. Tests explicitly skip unavailable optional test
runtimes rather than pretending integration was exercised. RapidFuzz is the
installed matching engine; a standard-library fallback supports bootstrap use.

In a socket-restricted sandbox whose asyncio self-pipe cannot wake worker
completions, use `scripts/verify.py --sandbox-poll`. This bounds selector waits
**only in the test runner**, while exercising real worker threads and production
code. See [VERIFICATION.md](../VERIFICATION.md) for this checkout's actual results
and remaining live checks. Do not treat unit tests as proof of Spotify/browser
compatibility or of a visually inspected terminal session.

Architecture: `mpris/` handles bus/player state, `lyrics/` handles parsing,
matching/providers/cache, `sync/` handles monotonic time and indexed timelines,
`ui/` holds modal screens, and `app.py` binds these to Textual. Network and file
parsing run asynchronously/off the UI loop. New providers implement the small
`LyricsProvider` protocol. Lyrics text and player metadata are rendered without
Rich markup and stripped of terminal control characters.

## Troubleshooting

| Symptom | Check / recovery |
| --- | --- |
| Waiting for a player | Start playback; inspect `playerctl -l` in the same session |
| Title or artist missing | Browser/site is not exposing sufficient metadata; try desktop player or local LRC |
| Position unavailable | This player cannot provide synchronization; try another MPRIS implementation |
| Wrong song/no confident match | Use the matching recording and local `--lyrics`; LYRA rejects low-confidence matches |
| Words drift | Confirm recording/version, playback rate, and timing label; adjust Up/Down |
| Words seem badly spaced | `≈` timing is only a word-length estimate; obtain enhanced LRC |
| Network error / rate limited | Existing cache/local files work; wait for cooldown, then R |
| Invalid LRC | Check UTF-8 encoding, ordered enhanced tags, and valid timestamp seconds |
| Cannot seek/pause | Player capability flags disable unsupported operations |
| Session D-Bus unavailable | Run in your desktop session, without sudo; verify bus environment |
| Missing Python dependency | Reinstall with pipx or the project venv; see installation above |
| Tiny terminal | Press C; restore full view to inspect errors or plain lyrics |

## License

LYRA is released under the [MIT license](../LICENSE), copyright © 2026 Es1xx.
The root license covers the original code, documentation, and demo assets.
No third-party song lyrics are bundled. Retrieved lyrics remain subject to their
respective rights and service terms.
