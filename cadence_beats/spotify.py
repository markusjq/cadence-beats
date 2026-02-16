from dataclasses import dataclass

import click
import spotipy
from spotipy.oauth2 import SpotifyPKCE

from .config import SPOTIFY_CACHE_PATH, SPOTIFY_REDIRECT_URI, ensure_data_dirs, get_spotify_client_id

SCOPES = "user-library-read playlist-modify-public playlist-modify-private"


@dataclass
class Track:
    id: str
    name: str
    artist: str
    uri: str


def authenticate_spotify() -> spotipy.Spotify:
    ensure_data_dirs()
    auth_manager = SpotifyPKCE(
        client_id=get_spotify_client_id(),
        redirect_uri=SPOTIFY_REDIRECT_URI,
        scope=SCOPES,
        cache_path=str(SPOTIFY_CACHE_PATH),
    )
    return spotipy.Spotify(auth_manager=auth_manager)


def fetch_liked_songs(sp: spotipy.Spotify) -> list[Track]:
    """Fetch all liked songs from the user's Spotify library."""
    tracks = []
    offset = 0
    limit = 50

    click.echo("Fetching liked songs...")
    while True:
        results = sp.current_user_saved_tracks(limit=limit, offset=offset)
        items = results.get("items", [])
        if not items:
            break

        for item in items:
            t = item["track"]
            if t is None:
                continue
            artists = ", ".join(a["name"] for a in t["artists"])
            tracks.append(Track(
                id=t["id"],
                name=t["name"],
                artist=artists,
                uri=t["uri"],
            ))

        offset += limit
        if offset % 200 == 0:
            click.echo(f"  Fetched {offset} songs...")

        if not results.get("next"):
            break

    click.echo(f"Total liked songs: {len(tracks)}")
    return tracks


def get_user_id(sp: spotipy.Spotify) -> str:
    return sp.current_user()["id"]


def find_existing_playlist(sp: spotipy.Spotify, user_id: str, name: str) -> str | None:
    """Find a playlist by name owned by the current user. Returns playlist ID or None."""
    offset = 0
    while True:
        results = sp.current_user_playlists(limit=50, offset=offset)
        items = results.get("items", [])
        if not items:
            break
        for pl in items:
            if pl["name"] == name and pl["owner"]["id"] == user_id:
                return pl["id"]
        offset += 50
        if not results.get("next"):
            break
    return None


def create_or_update_playlist(
    sp: spotipy.Spotify,
    user_id: str,
    name: str,
    description: str,
    track_uris: list[str],
) -> str:
    """Create a new playlist or overwrite an existing one. Returns playlist ID."""
    playlist_id = find_existing_playlist(sp, user_id, name)

    if playlist_id:
        sp.playlist_change_details(playlist_id, description=description)
        sp.playlist_replace_items(playlist_id, [])
    else:
        result = sp.user_playlist_create(
            user_id, name, public=False, description=description
        )
        playlist_id = result["id"]

    # Spotify API allows max 100 tracks per request
    for i in range(0, len(track_uris), 100):
        batch = track_uris[i : i + 100]
        sp.playlist_add_items(playlist_id, batch)

    return playlist_id
