import click
import spotipy

from .bpm import _get_db, get_all_cached, match_to_zone
from .garmin import load_zones
from .spotify import create_or_update_playlist, get_user_id

PLAYLIST_PREFIX = "Run"
ATTRIBUTION = "BPM data from GetSongBPM.com"


def generate_playlists(sp: spotipy.Spotify):
    """Load zones and cached BPMs, match songs to zones, create Spotify playlists."""
    zones = load_zones()
    click.echo("Cadence zones:")
    for name, (low, high) in zones.items():
        click.echo(f"  {name}: {low}-{high} spm")

    conn = _get_db()
    cached_songs = get_all_cached(conn)
    conn.close()

    if not cached_songs:
        raise click.ClickException(
            "No songs with BPM data found. Run 'cadence-beats scan-library' first."
        )

    click.echo(f"\nSongs with BPM data: {len(cached_songs)}")

    # Group songs by zone
    zone_tracks: dict[str, list[dict]] = {name: [] for name in zones}
    unmatched = []

    for song in cached_songs:
        matched_zones = match_to_zone(song["bpm"], zones)
        if matched_zones:
            for zone_name in matched_zones:
                zone_tracks[zone_name].append(song)
        else:
            unmatched.append(song)

    click.echo("\nPlaylist breakdown:")
    for zone_name, tracks in zone_tracks.items():
        low, high = zones[zone_name]
        click.echo(f"  {PLAYLIST_PREFIX}: {zone_name} Pace ({low}-{high} BPM) - {len(tracks)} songs")
    click.echo(f"  Unmatched: {len(unmatched)} songs")

    # Create Spotify playlists
    user_id = get_user_id(sp)

    for zone_name, tracks in zone_tracks.items():
        if not tracks:
            click.echo(f"\nSkipping {zone_name} (no matching songs)")
            continue

        low, high = zones[zone_name]
        playlist_name = f"{PLAYLIST_PREFIX}: {zone_name} Pace ({low}-{high} BPM)"
        description = (
            f"Songs matching your {zone_name.lower()} running cadence "
            f"({low}-{high} steps per minute). {ATTRIBUTION}"
        )

        # Build URIs from track IDs
        track_uris = [f"spotify:track:{t['track_id']}" for t in tracks]

        playlist_id = create_or_update_playlist(
            sp, user_id, playlist_name, description, track_uris
        )
        click.echo(f"\nCreated/updated: {playlist_name}")
        click.echo(f"  {len(tracks)} songs, playlist ID: {playlist_id}")
