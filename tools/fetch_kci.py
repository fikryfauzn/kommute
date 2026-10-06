#!/usr/bin/env python3

import json
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


BASE_URL = "https://www.kci.id/api/krl"
SOURCE_PAGE = "https://www.kci.id/perjalanan-krl/jadwal-kereta"

OUTPUT = Path("data/kci/raw")
STAGING = Path("data/kci/raw.tmp")

HEADERS = [
    "-H",
    "User-Agent: Mozilla/5.0 (X11; Linux x86_64; rv:157.0) Gecko/20100101 Firefox/157.0",
    "-H",
    "Accept: application/json, text/javascript, */*; q=0.01",
    "-H",
    "X-Requested-With: XMLHttpRequest",
    "-H",
    f"Referer: {SOURCE_PAGE}",
]

# KCI inconsistencies between /stations and /schedules.
STATION_ID_ALIASES = {
    "GGL": "GRG",  # GROGOL
}

REQUIRED_SCHEDULE_FIELDS = {
    "train_id",
    "ka_name",
    "route_name",
    "dest",
    "time_est",
    "color",
    "dest_time",
}


def fetch(path, params=None):
    cmd = [
        "curl",
        "-fsS",
        "--compressed",
        "--retry",
        "3",
        "--retry-delay",
        "2",
        *HEADERS,
    ]

    if params:
        cmd.append("-G")

        for key, value in params.items():
            cmd.extend(
                [
                    "--data-urlencode",
                    f"{key}={value}",
                ]
            )

    cmd.append(f"{BASE_URL}/{path}")

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"curl failed for {path}: "
            f"{result.stderr.strip()}"
        )

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        preview = result.stdout[:500]

        raise RuntimeError(
            f"non-JSON response from {path}: "
            f"{preview!r}"
        ) from exc

    if payload.get("status") != 200:
        raise RuntimeError(
            f"{path}: KCI returned "
            f"status={payload.get('status')} "
            f"data={payload.get('data')!r}"
        )

    return payload


def write_json(path, data):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open(
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            data,
            f,
            indent=2,
            ensure_ascii=False,
        )
        f.write("\n")


def get_enabled_stations(data):
    """
    Return every enabled station exposed by KCI.

    We intentionally do NOT use WIL* marker ordering here.

    KCI currently places some useful stations, such as
    RANGKASBITUNG (RK), outside the apparent Jabodetabek marker
    block even though they participate in services Kommute supports.

    Product filtering happens later in compile_schedule.py.
    """
    stations = []

    seen_codes = set()

    for row in data:
        code = row.get("sta_id", "")

        if row.get("fg_enable") != 1:
            continue

        if not code:
            continue

        if code in seen_codes:
            raise RuntimeError(
                f"duplicate station code: {code}"
            )

        seen_codes.add(code)
        stations.append(row)

    if not stations:
        raise RuntimeError(
            "no enabled KCI stations found"
        )

    return stations


def validate_schedule(
    station_code,
    rows,
):
    if not isinstance(rows, list):
        raise RuntimeError(
            f"{station_code}: schedule data "
            "is not an array"
        )

    for index, row in enumerate(rows):
        missing = (
            REQUIRED_SCHEDULE_FIELDS
            - row.keys()
        )

        if missing:
            raise RuntimeError(
                f"{station_code}: row {index} "
                f"missing fields: {sorted(missing)}"
            )


def main():
    print("Fetching KCI station list...")

    stations_response = fetch(
        "stations"
    )

    station_data = stations_response.get(
        "data"
    )

    if not isinstance(
        station_data,
        list,
    ):
        raise RuntimeError(
            "stations API did not return "
            "a data array"
        )

    stations = get_enabled_stations(
        station_data
    )

    print(
        "Enabled KCI stations: "
        f"{len(stations)}"
    )

    if STAGING.exists():
        shutil.rmtree(STAGING)

    STAGING.mkdir(
        parents=True,
        exist_ok=True,
    )

    write_json(
        STAGING / "stations-api.json",
        stations_response,
    )

    write_json(
        STAGING / "stations.json",
        stations,
    )

    schedule_dir = (
        STAGING / "schedules"
    )

    schedule_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    total_rows = 0
    unique_trains = set()
    lines = {}
    aliases_used = {}
    station_stats = []

    for index, station in enumerate(
        stations,
        start=1,
    ):
        canonical_code = (
            station["sta_id"]
        )

        name = station["sta_name"]

        api_code = (
            STATION_ID_ALIASES.get(
                canonical_code,
                canonical_code,
            )
        )

        if api_code != canonical_code:
            aliases_used[
                canonical_code
            ] = api_code

        print(
            f"[{index:03d}/"
            f"{len(stations):03d}] "
            f"{canonical_code:<6} "
            f"{name:<35}",
            end=" ",
            flush=True,
        )

        if api_code != canonical_code:
            print(
                f"[API {api_code}]",
                end=" ",
                flush=True,
            )

        response = fetch(
            "schedules",
            {
                "stationid": api_code,
                "timefrom": "00:00",
                "timeto": "23:59",
            },
        )

        rows = response.get("data")

        validate_schedule(
            canonical_code,
            rows,
        )

        write_json(
            schedule_dir
            / f"{canonical_code}.json",
            response,
        )

        total_rows += len(rows)

        for row in rows:
            unique_trains.add(
                row["train_id"]
            )

            lines[
                row["ka_name"]
            ] = row["color"]

        station_stats.append(
            {
                "code": canonical_code,
                "api_code": api_code,
                "name": name,
                "row_count": len(rows),
            }
        )

        print(
            f"{len(rows):4d} rows"
        )

        time.sleep(0.25)

    fetched_at = datetime.now(
        ZoneInfo("Asia/Jakarta")
    )

    manifest = {
        "schema_version": 2,
        "source": BASE_URL,
        "source_page": SOURCE_PAGE,
        "fetched_at": (
            fetched_at.isoformat()
        ),
        "timezone": "Asia/Jakarta",
        "time_range": {
            "from": "00:00",
            "to": "23:59",
        },
        "station_count": len(
            stations
        ),
        "unique_train_count": len(
            unique_trains
        ),
        "stop_row_count": (
            total_rows
        ),
        "lines": lines,
        "station_id_aliases": (
            aliases_used
        ),
        "stations": station_stats,
    }

    write_json(
        STAGING / "manifest.json",
        manifest,
    )

    # Atomic-ish snapshot replacement:
    # only replace the previous dataset once every request succeeded.
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)

    OUTPUT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    STAGING.rename(
        OUTPUT
    )

    print()
    print("KCI snapshot complete")

    print(
        f"  stations:      "
        f"{len(stations)}"
    )

    print(
        f"  unique trains: "
        f"{len(unique_trains)}"
    )

    print(
        f"  stop rows:     "
        f"{total_rows}"
    )

    print(
        f"  aliases:       "
        f"{len(aliases_used)}"
    )

    print(
        f"  output:        "
        f"{OUTPUT}"
    )

    if aliases_used:
        print()
        print(
            "Station ID aliases used:"
        )

        for (
            canonical,
            api_code,
        ) in aliases_used.items():
            print(
                f"  {canonical} "
                f"-> {api_code}"
            )


if __name__ == "__main__":
    try:
        main()

    except KeyboardInterrupt:
        print(
            "\nInterrupted.",
            file=sys.stderr,
        )
        sys.exit(130)

    except Exception as exc:
        print(
            f"\nERROR: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)
