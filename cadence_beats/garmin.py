import json
import statistics
from datetime import datetime, timedelta
from pathlib import Path

import click
from fitparse import FitFile
from garminconnect import Garmin

from .config import CADENCE_ZONES_FILE, FIT_DIR, ensure_data_dirs, get_garmin_email, get_garmin_password

FIXED_ZONES = {
    "Easy": [150, 165],
    "Moderate": [165, 175],
    "Tempo": [175, 185],
    "Speed": [185, 200],
}


def authenticate_garmin() -> Garmin:
    email = get_garmin_email()
    password = get_garmin_password()
    client = Garmin(email, password)
    client.login()
    return client


def download_fit_files(client: Garmin, days: int) -> list[Path]:
    ensure_data_dirs()
    start = datetime.now() - timedelta(days=days)
    end = datetime.now()

    activities = client.get_activities_by_date(
        start.strftime("%Y-%m-%d"),
        end.strftime("%Y-%m-%d"),
        "running",
    )

    if not activities:
        click.echo(f"No running activities found in the last {days} days.")
        return []

    click.echo(f"Found {len(activities)} running activities.")
    fit_paths = []

    for activity in activities:
        activity_id = activity["activityId"]
        fit_path = FIT_DIR / f"{activity_id}.fit"

        if fit_path.exists():
            fit_paths.append(fit_path)
            continue

        try:
            fit_data = client.download_activity(activity_id, dl_fmt=Garmin.ActivityDownloadFormat.ORIGINAL)
            fit_path.write_bytes(fit_data)
            fit_paths.append(fit_path)
            click.echo(f"  Downloaded activity {activity_id}")
        except Exception as e:
            click.echo(f"  Failed to download activity {activity_id}: {e}")

    return fit_paths


def load_local_fit_files(fit_dir: Path) -> list[Path]:
    fits = sorted(fit_dir.glob("*.fit"))
    if not fits:
        click.echo(f"No .fit files found in {fit_dir}")
    else:
        click.echo(f"Found {len(fits)} local FIT files.")
    return fits


def parse_cadence_from_fit(fit_path: Path) -> list[int]:
    """Extract cadence values from a FIT file. Returns list of cadence (spm) readings."""
    cadence_values = []
    try:
        fit = FitFile(str(fit_path))
        for record in fit.get_messages("record"):
            for field in record.fields:
                if field.name == "cadence" and field.value is not None and field.value > 0:
                    # Garmin stores cadence as half-cycles (steps per foot),
                    # multiply by 2 for full steps per minute
                    cadence_values.append(field.value * 2)
    except Exception as e:
        click.echo(f"  Error parsing {fit_path.name}: {e}")
    return cadence_values


def calculate_zones(all_cadence: list[int]) -> dict[str, list[int]]:
    """Calculate percentile-based cadence zones from raw cadence data."""
    if len(all_cadence) < 100:
        click.echo("Warning: very little cadence data, zones may not be meaningful.")

    sorted_cadence = sorted(all_cadence)
    n = len(sorted_cadence)

    def percentile(p: float) -> int:
        idx = int(p / 100 * n)
        idx = min(idx, n - 1)
        return sorted_cadence[idx]

    p25 = percentile(25)
    p50 = percentile(50)
    p75 = percentile(75)
    p90 = percentile(90)

    zones = {
        "Easy": [p25, p50],
        "Moderate": [p50, p75],
        "Tempo": [p75, p90],
        "Speed": [p90, max(sorted_cadence[-1], p90 + 10)],
    }
    return zones


def save_zones(zones: dict[str, list[int]]):
    ensure_data_dirs()
    CADENCE_ZONES_FILE.write_text(json.dumps(zones, indent=2))
    click.echo(f"Zones saved to {CADENCE_ZONES_FILE}")


def load_zones() -> dict[str, list[int]]:
    if not CADENCE_ZONES_FILE.exists():
        raise click.ClickException(
            f"No cadence zones found. Run 'cadence-beats analyze-runs' first."
        )
    return json.loads(CADENCE_ZONES_FILE.read_text())


def analyze_runs(days: int, fit_dir: str | None):
    """Main flow for analyze-runs command."""
    if fit_dir:
        fit_paths = load_local_fit_files(Path(fit_dir))
    else:
        click.echo("Authenticating with Garmin Connect...")
        try:
            client = authenticate_garmin()
            click.echo("Authenticated.")
            fit_paths = download_fit_files(client, days)
        except Exception as e:
            click.echo(f"Garmin auth failed: {e}")
            click.echo(f"Falling back to local FIT files in {FIT_DIR}")
            fit_paths = load_local_fit_files(FIT_DIR)

    if not fit_paths:
        raise click.ClickException("No FIT files to analyze.")

    all_cadence = []
    for fp in fit_paths:
        cadence = parse_cadence_from_fit(fp)
        if cadence:
            click.echo(f"  {fp.name}: {len(cadence)} samples, avg {statistics.mean(cadence):.0f} spm")
            all_cadence.extend(cadence)

    if not all_cadence:
        raise click.ClickException("No cadence data found in any FIT file.")

    num_runs = len(fit_paths)
    if num_runs < 10:
        click.echo(
            f"\nWarning: only {num_runs} runs found (recommend 10+). "
            f"Using fixed fallback zones."
        )
        zones = FIXED_ZONES
    else:
        zones = calculate_zones(all_cadence)

    click.echo("\nCadence zones (steps per minute):")
    for name, (low, high) in zones.items():
        click.echo(f"  {name}: {low}-{high} spm")

    save_zones(zones)
