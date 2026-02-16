import click

from .bpm import scan_for_bpms
from .garmin import analyze_runs
from .generator import generate_playlists
from .spotify import authenticate_spotify, fetch_liked_songs


@click.group()
def cli():
    """Cadence Beats: Generate Spotify playlists matched to your running cadence."""
    pass


@cli.command("analyze-runs")
@click.option("--days", default=30, help="Number of days of run history to analyze.")
@click.option("--fit-dir", default=None, help="Path to local folder of FIT files (skips Garmin API).")
def analyze_runs_cmd(days: int, fit_dir: str | None):
    """Analyze Garmin running data to calculate your personal cadence zones."""
    analyze_runs(days, fit_dir)


@cli.command("scan-library")
def scan_library_cmd():
    """Fetch your Spotify liked songs and look up BPM for each."""
    click.echo("Authenticating with Spotify...")
    sp = authenticate_spotify()
    click.echo("Authenticated.\n")

    tracks = fetch_liked_songs(sp)
    if not tracks:
        click.echo("No liked songs found.")
        return

    click.echo(f"\nLooking up BPM data...")
    stats = scan_for_bpms(tracks)

    click.echo(f"\nSummary:")
    click.echo(f"  Cached (already known): {stats['cached']}")
    click.echo(f"  Found (new lookups):    {stats['found']}")
    click.echo(f"  Not found:              {stats['not_found']}")
    if stats["rate_limited"]:
        click.echo(f"  Note: hit daily API limit, run again tomorrow to finish.")


@cli.command("generate-playlists")
def generate_playlists_cmd():
    """Create Spotify playlists from your cadence zones and BPM-tagged songs."""
    click.echo("Authenticating with Spotify...")
    sp = authenticate_spotify()
    click.echo("Authenticated.\n")

    generate_playlists(sp)
    click.echo("\nDone! Check your Spotify for new playlists.")


if __name__ == "__main__":
    cli()
