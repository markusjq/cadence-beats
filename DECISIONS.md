# Cadence Beats - Decision Log & Project History

## What this is
A Python CLI tool that analyzes running cadence from Garmin watch data and generates Spotify playlists grouped by BPM to match your pace zones.

## Problem statement
Running to music that matches your cadence feels great. But there's no easy way to take your actual Garmin cadence data and automatically build playlists from your existing Spotify library that match your running speeds.

## Architecture chosen (and why)

### Three approaches were evaluated

| Approach | Description | Verdict |
|----------|-------------|---------|
| **A: Phone app** | Phone reads live cadence via Bluetooth, controls Spotify in real-time | Too complex for MVP |
| **B: Garmin watch app** | Connect IQ AudioContentProviderApp, on-watch cadence + music | Monkey C learning curve, no Spotify streaming |
| **C: Post-run playlist generator** | Pull historical cadence, match to BPM-tagged library, create playlists | **Chosen as MVP** |

**Why C**: Validates the core hypothesis (do BPM-matched playlists improve runs?) with minimal engineering. Can be built in a focused session. If it works, Option A becomes the natural upgrade path.

### Key technical constraints discovered during research
- **Spotify deprecated BPM endpoints** (Nov 2024): `audio-features`, `audio-analysis`, and `recommendations` with `target_tempo` all return 403 for new apps. Cannot query Spotify for "songs at 170 BPM."
- **Garmin apps are sandboxed**: A Connect IQ app reading cadence cannot control the Spotify app. No inter-app communication.
- **GetSongBPM API** is the viable free alternative for BPM lookups. Requires attribution (link to their site).

## Decisions made

### 1. Percentile-based cadence zones (not fixed ranges)
- **Decision**: Calculate zones from the user's actual run data using percentiles (25th/50th/75th/90th)
- **Why**: Runners vary hugely. A beginner runs ~150 spm, an elite runner ~190 spm. Fixed zones would miss the mark for most people.
- **Tradeoff**: Needs ~10+ runs of data to be meaningful.

### 2. Double-time BPM matching
- **Decision**: Match songs at BPM, BPM x 2, and BPM / 2
- **Why**: A hip-hop track at 85 BPM feels like 170 BPM when running (you step on every other beat). Without this, you lose a huge chunk of your library.
- **Tradeoff**: Some songs may end up in zones that feel wrong outside of running context.

### 3. SQLite cache for BPM data
- **Decision**: Use SQLite over a JSON file
- **Why**: 1000+ songs need structured lookups. SQLite handles this cleanly and supports metadata (fetch date, source).

### 4. Separate CLI commands (not one pipeline)
- **Decision**: `analyze-runs`, `scan-library`, `generate-playlists` as independent commands
- **Why**: Each step can take time (scanning 1000+ songs). Separation means you can re-run just playlist generation without re-scanning everything.

### 5. Spotify PKCE auth (no client secret)
- **Decision**: Use `SpotifyPKCE` via spotipy
- **Why**: No client secret needed, ideal for a personal CLI tool.

### 6. GetSongBPM over local audio analysis
- **Decision**: Use GetSongBPM free API for BPM lookups
- **Why**: Faster to build, no need to have audio files locally. Can add local analysis (librosa/essentia) later if accuracy is an issue.

### 7. Flat module structure
- **Decision**: Single-level modules (`garmin.py`, `spotify.py`, `bpm.py`) instead of nested packages
- **Why**: Small CLI tool, no need for deep nesting. Keeps it easy to navigate.

### 8. String normalization for BPM lookups (added after CTO review)
- **Decision**: Strip parentheticals, "feat." tags, "Remastered" suffixes, and other noise from track names before querying GetSongBPM
- **Why**: Spotify metadata is messy. "Song Name (feat. Artist B) - Radio Edit" won't match in GetSongBPM. Without normalization, expect 30-40% unnecessary lookup failures.

### 9. Garmin FIT file fallback (added after CTO review)
- **Decision**: `garmin.py` supports both live download via garminconnect AND reading from a local folder of manually-exported FIT files
- **Why**: The unofficial garminconnect library breaks periodically (MFA changes, CAPTCHAs). A local folder fallback means the tool still works even when the API is broken.

### 10. GetSongBPM daily limit handling (added after CTO review)
- **Decision**: Free tier allows 2000 requests/day. Handle gracefully with a "daily limit reached, run again tomorrow" message.
- **Why**: With 1500+ uncached songs, first scan will hit the cap. Better to stop cleanly than fail silently.

### 11. MVP scope cuts (added after CTO review)
- **Cut**: `list-missing` and `add-bpm` CLI commands (just print missing songs to stdout during scan)
- **Cut**: `--include-playlists` flag (start with liked songs only)
- **Cut**: `--overwrite` flag (always overwrite existing playlists)
- **Why**: Removes ~20% of CLI surface area without losing core functionality. Ship faster, add back later.

## Tech stack
- Python 3.10+
- `garminconnect` - Garmin Connect auth + activity download
- `fitparse` - Parse FIT files for cadence records
- `spotipy` - Spotify Web API (PKCE auth, library read, playlist create)
- `click` - CLI framework
- `requests` - GetSongBPM API calls
- `python-dotenv` - Load .env credentials

## Configuration required
1. Garmin Connect email + password (in .env)
2. Spotify app created at https://developer.spotify.com/dashboard with redirect URI `http://localhost:8888/callback`
3. GetSongBPM API key from https://getsongbpm.com/api

## Implementation steps

### Step 1: Project scaffolding
- [ ] Create directory structure, pyproject.toml, .env.example, .gitignore
- [ ] Set up config.py for loading env vars
- **Status**: Not started

### Step 2: Garmin module (garmin.py)
- [ ] Auth with garminconnect + local FIT folder fallback
- [ ] Download FIT files for recent runs (filter to running activities only)
- [ ] Parse cadence using fitparse
- [ ] Calculate percentile-based zones (warn if < 10 runs, fall back to fixed zones)
- [ ] Wire up `analyze-runs` CLI command
- **Status**: Not started

### Step 3: Spotify module (spotify.py) -- moved before BPM so we have real track data
- [ ] PKCE auth via spotipy (pin cache path in config.py)
- [ ] Fetch liked songs (paginated)
- [ ] Create/update playlists (add GetSongBPM attribution to playlist description)
- [ ] Wire up `scan-library` CLI command
- **Status**: Not started

### Step 4: BPM module (bpm.py) -- needs real Spotify track data from Step 3
- [ ] SQLite cache (create table, get/set BPM, list uncached)
- [ ] String normalization: strip parentheticals, "feat.", "Remastered", etc. before API calls
- [ ] GetSongBPM API client with rate limiting (1 req/sec, handle 2000/day cap gracefully)
- [ ] BPM-to-zone matcher with double/half-time support
- **Status**: Not started

### Step 5: Generator + remaining CLI
- [ ] Orchestrate zones + BPM cache -> matched playlists
- [ ] Wire up `generate-playlists` command (always overwrite for MVP)
- [ ] Print missing songs to stdout (no separate command for MVP)
- [ ] End-to-end test
- **Status**: Not started

## File structure
```
Projects/cadence-beats/
├── cadence_beats/
│   ├── __init__.py
│   ├── cli.py              # Click CLI commands
│   ├── config.py           # .env loading, paths
│   ├── garmin.py           # Auth, download FIT, parse cadence, calc zones
│   ├── spotify.py          # Auth (PKCE), fetch library, create playlists
│   ├── bpm.py              # GetSongBPM API, SQLite cache, BPM-to-zone matching
│   └── generator.py        # Orchestrates: zones + songs + BPMs -> playlists
├── data/                   # FIT files, BPM cache (gitignored)
├── .env.example
├── DECISIONS.md            # This file
├── pyproject.toml
└── .gitignore
```

## Future directions (out of MVP scope)
- **Option A upgrade**: Phone-based app with live cadence reading and real-time Spotify control
- Custom zone adjustment via CLI/config
- Strava integration as Garmin alternative
- Song energy/mood matching alongside BPM
- Web dashboard for cadence trends
