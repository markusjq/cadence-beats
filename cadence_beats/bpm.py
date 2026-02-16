import re
import sqlite3
import time
from pathlib import Path

import click
import requests

from .config import BPM_CACHE_DB, ensure_data_dirs, get_getsongbpm_api_key

GETSONGBPM_BASE = "https://api.getsongbpm.com"


# --- SQLite cache ---

def _get_db(db_path: Path | None = None) -> sqlite3.Connection:
    ensure_data_dirs()
    path = db_path or BPM_CACHE_DB
    conn = sqlite3.connect(str(path))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bpm_cache (
            track_id TEXT PRIMARY KEY,
            track_name TEXT,
            artist TEXT,
            bpm REAL,
            source TEXT DEFAULT 'getsongbpm',
            fetched_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    return conn


def get_cached_bpm(conn: sqlite3.Connection, track_id: str) -> float | None:
    row = conn.execute(
        "SELECT bpm FROM bpm_cache WHERE track_id = ?", (track_id,)
    ).fetchone()
    return row[0] if row else None


def set_cached_bpm(
    conn: sqlite3.Connection,
    track_id: str,
    track_name: str,
    artist: str,
    bpm: float | None,
):
    conn.execute(
        """INSERT OR REPLACE INTO bpm_cache (track_id, track_name, artist, bpm)
           VALUES (?, ?, ?, ?)""",
        (track_id, track_name, artist, bpm),
    )
    conn.commit()


def get_all_cached(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT track_id, track_name, artist, bpm FROM bpm_cache WHERE bpm IS NOT NULL"
    ).fetchall()
    return [
        {"track_id": r[0], "track_name": r[1], "artist": r[2], "bpm": r[3]}
        for r in rows
    ]


# --- String normalization ---

def normalize_track_name(name: str) -> str:
    """Strip noise from track names for better BPM API matching.

    Removes parentheticals, "feat." tags, "Remastered" suffixes, version info.
    """
    # Remove parenthetical content: (feat. X), (Remastered 2023), (Radio Edit), etc.
    name = re.sub(r"\s*\([^)]*\)", "", name)
    # Remove bracket content: [Deluxe Edition], etc.
    name = re.sub(r"\s*\[[^\]]*\]", "", name)
    # Remove "feat." / "ft." and everything after
    name = re.sub(r"\s*[-–]\s*(feat|ft)\.?\s+.*$", "", name, flags=re.IGNORECASE)
    # Remove trailing " - Remastered", " - Radio Edit", etc.
    name = re.sub(
        r"\s*[-–]\s*(remaster(ed)?|radio edit|single version|bonus track|live).*$",
        "",
        name,
        flags=re.IGNORECASE,
    )
    return name.strip()


def normalize_artist(artist: str) -> str:
    """Take the first artist from a comma-separated list."""
    return artist.split(",")[0].strip()


# --- GetSongBPM API ---

def search_bpm(track_name: str, artist: str, api_key: str) -> float | None:
    """Search GetSongBPM for a track's BPM. Returns BPM or None if not found."""
    clean_name = normalize_track_name(track_name)
    clean_artist = normalize_artist(artist)
    query = f"{clean_artist} {clean_name}"

    try:
        resp = requests.get(
            f"{GETSONGBPM_BASE}/search/",
            params={"api_key": api_key, "type": "both", "lookup": query},
            timeout=10,
        )

        if resp.status_code == 429:
            return "RATE_LIMITED"

        if resp.status_code != 200:
            return None

        data = resp.json()
        results = data.get("search", [])
        if not results:
            return None

        # Take the first result's tempo
        song_id = results[0].get("id")
        if not song_id:
            return None

        # Fetch full song details for BPM
        detail_resp = requests.get(
            f"{GETSONGBPM_BASE}/song/",
            params={"api_key": api_key, "id": song_id},
            timeout=10,
        )

        if detail_resp.status_code == 429:
            return "RATE_LIMITED"

        if detail_resp.status_code != 200:
            return None

        detail = detail_resp.json()
        tempo = detail.get("song", {}).get("tempo")
        if tempo:
            return float(tempo)
        return None

    except (requests.RequestException, ValueError, KeyError):
        return None


def scan_for_bpms(tracks: list, progress: bool = True) -> dict:
    """Look up BPMs for tracks, using cache and API.

    Args:
        tracks: list of Track objects (with id, name, artist attributes)

    Returns:
        dict with keys: found, not_found, cached, rate_limited
    """
    api_key = get_getsongbpm_api_key()
    conn = _get_db()

    stats = {"found": 0, "not_found": 0, "cached": 0, "rate_limited": False}
    missing_songs = []
    api_calls = 0

    for i, track in enumerate(tracks):
        cached = get_cached_bpm(conn, track.id)
        if cached is not None:
            stats["cached"] += 1
            continue

        # Check if we already cached it as "not found" (bpm = None)
        row = conn.execute(
            "SELECT bpm FROM bpm_cache WHERE track_id = ?", (track.id,)
        ).fetchone()
        if row is not None:
            stats["not_found"] += 1
            missing_songs.append(f"  {track.artist} - {track.name}")
            continue

        # Need to fetch from API
        bpm = search_bpm(track.name, track.artist, api_key)

        if bpm == "RATE_LIMITED":
            click.echo(
                "\nDaily API limit reached (2000 requests/day). "
                "Run again tomorrow to continue scanning."
            )
            stats["rate_limited"] = True
            break

        if bpm is not None:
            set_cached_bpm(conn, track.id, track.name, track.artist, bpm)
            stats["found"] += 1
        else:
            # Cache the miss so we don't re-query
            set_cached_bpm(conn, track.id, track.name, track.artist, None)
            stats["not_found"] += 1
            missing_songs.append(f"  {track.artist} - {track.name}")

        api_calls += 1

        if progress and api_calls % 50 == 0:
            click.echo(f"  Looked up {api_calls} songs...")

        # Rate limit: ~1 req/sec, but search + detail = 2 calls per song
        time.sleep(1)

    conn.close()

    if missing_songs:
        click.echo(f"\nSongs with no BPM found ({len(missing_songs)}):")
        for s in missing_songs[:20]:
            click.echo(s)
        if len(missing_songs) > 20:
            click.echo(f"  ... and {len(missing_songs) - 20} more")

    return stats


# --- BPM-to-zone matching ---

def match_to_zone(bpm: float, zones: dict[str, list[int]]) -> list[str]:
    """Match a song BPM to cadence zones, including double/half-time.

    Returns list of zone names the song matches (can match multiple).
    """
    matched = []
    candidates = [bpm, bpm * 2, bpm / 2]

    for zone_name, (low, high) in zones.items():
        for candidate in candidates:
            if low <= candidate <= high:
                matched.append(zone_name)
                break

    return matched
