# STAVA Player

A desktop audio player written in Python with PyQt6 and the BASS audio engine.

**Free and non-commercial.** No money is charged for this project, now or later.
See [LICENSE](LICENSE).

---

## Features

- **Playback** of MP3, FLAC, WAV, OGG and M4A through the native BASS engine
- **Equalizer** with 10 bands, preamp, and bass/treble controls
- **Effects** — spatial widening, reverb, tempo, limiter, plus VST plugin support
- **Library** with folder, album, artist, most-played and queue views, all backed
  by a local SQLite database
- **Waveform** rendered ahead of time, plus an FFT visualizer
- **Two player modes** — full, with artwork and waveform, or compact beside the
  library
- **Discord Rich Presence**, optional
- **Themes** and adjustable zoom for the whole interface

## Requirements

- Python 3.10 or newer
- Windows (BASS binaries are bundled for Windows; macOS binaries are present in
  `libs/`, but the app is tested on Windows)

## Installation

```bash
git clone https://github.com/InvincibleAlex/stava-player.git
cd stava-player

python -m venv .venv
.venv\Scripts\activate        # on Windows
pip install -r requirements.txt

python main.py
```

On first launch the app creates its own `settings.ini` with default values. Pick
your music folder from **Settings → Playlist**; scanning starts automatically
from there.

## Project layout

| Directory | Purpose |
|---|---|
| `audio/` | playback engine, BASS bindings and the effects chain |
| `core/` | orchestration: session, playback, navigation, events, Discord |
| `playlist/` | library, scanning, database, playlist interface |
| `tabs/` | main screens — Player, EQ, Playlist, Settings |
| `player/` | player widgets and the two layouts |
| `Eq/`, `ui/`, `animations/`, `background/` | visual components and transitions |
| `libs/` | BASS and the VST plugins |

## Notes

**Discord Rich Presence** ships with a default Client ID so the feature works
without any setup. It is not a secret: every application using Rich Presence
sends its Client ID to Discord from each user. You can replace it with your own
Discord application ID under **Settings → Discord**.

**`settings.ini` is not included in the repository.** It holds preferences and
local paths that differ between installations, and it is generated
automatically.

**The interface is in Romanian.**

## Licence

Source code: [MIT](LICENSE). The libraries bundled under `libs/` belong to their
respective authors and carry their own terms — see
[THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md). BASS is free for
non-commercial use.
