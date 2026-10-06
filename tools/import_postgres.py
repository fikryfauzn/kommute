#!/usr/bin/env python3

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


DATA_FILE = Path("data/kommute.json")

DEFAULT_DSN = (
    "postgres://kommute:kommute_dev@localhost:5432/kommute"
)

LINE_ORDER = [
    "COMMUTER LINE BOGOR",
    "COMMUTER LINE CIKARANG",
    "COMMUTER LINE RANGKASBITUNG",
    "COMMUTER LINE TANGERANG",
    "COMMUTER LINE TANJUNGPRIUK",
]


def read_json(path):
    with path.open(
        "r",
        encoding="utf-8",
    ) as f:
        return json.load(f)


def copy_field(value):
    """
    Encode a value for PostgreSQL COPY text format.
    """
    if value is None:
        return r"\N"

    if isinstance(value, bool):
        return "t" if value else "f"

    value = str(value)

    return (
        value
        .replace("\\", "\\\\")
        .replace("\t", "\\t")
        .replace("\n", "\\n")
        .replace("\r", "\\r")
    )


def copy_row(values):
    return "\t".join(
        copy_field(value)
        for value in values
    )


def check_length(
    label,
    value,
    maximum,
):
    if len(value) > maximum:
        raise RuntimeError(
            f"{label} too long "
            f"({len(value)} > {maximum}): "
            f"{value!r}"
        )


def validate_time(value):
    parts = value.split(":")

    if len(parts) != 3:
        raise RuntimeError(
            f"invalid time: {value!r}"
        )

    hour = int(parts[0])
    minute = int(parts[1])
    second = int(parts[2])

    if not 0 <= hour <= 23:
        raise RuntimeError(
            f"invalid hour: {value!r}"
        )

    if not 0 <= minute <= 59:
        raise RuntimeError(
            f"invalid minute: {value!r}"
        )

    if not 0 <= second <= 59:
        raise RuntimeError(
            f"invalid second: {value!r}"
        )


def build_import(data):
    if data.get("schema_version") != 2:
        raise RuntimeError(
            "expected kommute.json "
            "schema_version 2"
        )

    stations = data.get("stations")
    lines = data.get("lines")
    destinations = data.get(
        "destinations"
    )
    arrivals = data.get(
        "arrivals_by_station"
    )
    trains = data.get("trains")

    diagnostics = data.get(
        "diagnostics",
        {},
    )

    route_only = diagnostics.get(
        "route_only_stations",
        {},
    )

    if not all(
        isinstance(value, dict)
        for value in (
            stations,
            lines,
            destinations,
            arrivals,
            trains,
        )
    ):
        raise RuntimeError(
            "compiled dataset is missing "
            "required sections"
        )

    # ---------------------------------------------------------
    # Line IDs
    #
    # Preserve the historical IDs used by migration 001.
    # ---------------------------------------------------------

    line_ids = {
        name: index
        for index, name
        in enumerate(
            LINE_ORDER,
            start=1,
        )
    }

    if set(lines) != set(
        LINE_ORDER
    ):
        raise RuntimeError(
            "compiled line set does not "
            "match Kommute supported lines:\n"
            f"compiled={sorted(lines)}"
        )

    # ---------------------------------------------------------
    # Stations
    # ---------------------------------------------------------

    station_rows = []

    known_station_codes = set()

    for code in sorted(stations):
        station = stations[code]

        name = station["name"]

        check_length(
            "station code",
            code,
            6,
        )

        check_length(
            "station name",
            name,
            50,
        )

        station_rows.append(
            (
                code,
                name,
                True,
            )
        )

        known_station_codes.add(
            code
        )

    for code in sorted(route_only):
        station = route_only[code]

        name = station["name"]

        if code in known_station_codes:
            raise RuntimeError(
                "route-only station also "
                "exists as selectable: "
                f"{code}"
            )

        check_length(
            "route-only station code",
            code,
            6,
        )

        check_length(
            "route-only station name",
            name,
            50,
        )

        station_rows.append(
            (
                code,
                name,
                False,
            )
        )

        known_station_codes.add(
            code
        )

    # ---------------------------------------------------------
    # Lines
    # ---------------------------------------------------------

    line_rows = []

    for name in LINE_ORDER:
        line = lines[name]

        color = line["color"]

        check_length(
            "line name",
            name,
            50,
        )

        if (
            len(color) != 7
            or not color.startswith("#")
        ):
            raise RuntimeError(
                f"invalid line color: "
                f"{name}: {color}"
            )

        line_rows.append(
            (
                line_ids[name],
                name,
                color,
            )
        )

    # ---------------------------------------------------------
    # station_lines
    #
    # Only selectable stations belong here.
    #
    # Route-only stations such as KAT/KARET remain available for
    # stop_times foreign keys, but never enter the station picker.
    # ---------------------------------------------------------

    station_line_rows = []

    seen_station_lines = set()

    for code in sorted(stations):
        station = stations[code]

        for line_name in station["lines"]:
            line_id = line_ids.get(
                line_name
            )

            if line_id is None:
                raise RuntimeError(
                    f"{code}: unsupported line "
                    f"{line_name!r}"
                )

            key = (
                code,
                line_id,
            )

            if key in seen_station_lines:
                raise RuntimeError(
                    "duplicate station_lines row: "
                    f"{key}"
                )

            seen_station_lines.add(
                key
            )

            station_line_rows.append(
                key
            )

    # ---------------------------------------------------------
    # Destination map
    # ---------------------------------------------------------

    destination_rows = []

    for raw_dest in sorted(
        destinations
    ):
        destination = (
            destinations[
                raw_dest
            ]
        )

        terminal = destination[
            "terminal"
        ]

        via = destination.get(
            "via"
        )

        check_length(
            "raw destination",
            raw_dest,
            50,
        )

        if (
            terminal
            not in known_station_codes
        ):
            raise RuntimeError(
                f"{raw_dest}: terminal "
                f"{terminal!r} is not "
                "a known station"
            )

        if (
            via is not None
            and via
            not in known_station_codes
        ):
            raise RuntimeError(
                f"{raw_dest}: VIA station "
                f"{via!r} is not "
                "a known station"
            )

        destination_rows.append(
            (
                raw_dest,
                terminal,
                via,
            )
        )

    # ---------------------------------------------------------
    # Board-visible keys
    #
    # The station-board API is authoritative for whether a stop
    # belongs on the Kommute arrival board.
    # ---------------------------------------------------------

    board_keys = set()

    for (
        station_code,
        board_rows,
    ) in arrivals.items():

        if (
            station_code
            not in stations
        ):
            raise RuntimeError(
                "arrival-board station is "
                "not selectable: "
                f"{station_code}"
            )

        for row in board_rows:
            key = (
                station_code,
                row["train_id"],
                row["arrival_time"],
            )

            if key in board_keys:
                raise RuntimeError(
                    "duplicate board key: "
                    f"{key}"
                )

            board_keys.add(key)

    # ---------------------------------------------------------
    # Complete route stop_times
    # ---------------------------------------------------------

    stop_rows = []

    matched_board_keys = set()

    seen_route_stops = set()

    for train_id in sorted(trains):
        train = trains[train_id]

        line_name = train["line"]

        line_id = line_ids.get(
            line_name
        )

        if line_id is None:
            raise RuntimeError(
                f"{train_id}: unsupported "
                f"line {line_name!r}"
            )

        route_name = train["route"]
        raw_dest = train[
            "destination"
        ]
        dest_time = train[
            "destination_time"
        ]

        check_length(
            "train ID",
            train_id,
            10,
        )

        check_length(
            "route name",
            route_name,
            60,
        )

        check_length(
            "destination",
            raw_dest,
            50,
        )

        if raw_dest not in destinations:
            raise RuntimeError(
                f"{train_id}: destination "
                f"{raw_dest!r} missing "
                "from destinations"
            )

        validate_time(
            dest_time
        )

        stops = train.get(
            "stops"
        )

        if (
            not isinstance(stops, list)
            or not stops
        ):
            raise RuntimeError(
                f"{train_id}: no route stops"
            )

        previous_sort = None

        for stop in stops:
            station_code = stop[
                "station"
            ]

            arrival_time = stop[
                "arrival_time"
            ]

            arrival_sort = stop[
                "arrival_sort"
            ]

            if (
                station_code
                not in known_station_codes
            ):
                raise RuntimeError(
                    f"{train_id}: unknown "
                    f"station {station_code}"
                )

            validate_time(
                arrival_time
            )

            if not isinstance(
                arrival_sort,
                int,
            ):
                raise RuntimeError(
                    f"{train_id} "
                    f"{station_code}: "
                    "arrival_sort is not int"
                )

            if not (
                0
                <= arrival_sort
                <= 1439
            ):
                raise RuntimeError(
                    f"{train_id} "
                    f"{station_code}: "
                    "arrival_sort outside "
                    f"operational day: "
                    f"{arrival_sort}"
                )

            if (
                previous_sort is not None
                and arrival_sort
                < previous_sort
            ):
                raise RuntimeError(
                    f"{train_id}: route "
                    "ordering regressed"
                )

            previous_sort = (
                arrival_sort
            )

            route_key = (
                train_id,
                station_code,
                arrival_time,
            )

            if (
                route_key
                in seen_route_stops
            ):
                raise RuntimeError(
                    "duplicate route stop: "
                    f"{route_key}"
                )

            seen_route_stops.add(
                route_key
            )

            board_key = (
                station_code,
                train_id,
                arrival_time,
            )

            board_visible = (
                board_key
                in board_keys
            )

            if board_visible:
                matched_board_keys.add(
                    board_key
                )

            stop_rows.append(
                (
                    station_code,
                    line_id,
                    train_id,
                    route_name,
                    raw_dest,
                    arrival_time,
                    arrival_sort,
                    dest_time,
                    board_visible,
                )
            )

    # ---------------------------------------------------------
    # Critical cross-source validation
    #
    # Every station-board stop must exist in the complete route
    # dataset. Otherwise the two KCI sources disagree in a way
    # we haven't accounted for.
    # ---------------------------------------------------------

    missing_board_keys = (
        board_keys
        - matched_board_keys
    )

    if missing_board_keys:
        examples = sorted(
            missing_board_keys
        )[:20]

        raise RuntimeError(
            "station-board rows missing "
            "from complete train routes.\n"
            f"count="
            f"{len(missing_board_keys)}\n"
            f"examples={examples}"
        )

    # ---------------------------------------------------------
    # Compare against compiled statistics
    # ---------------------------------------------------------

    stats = data.get(
        "stats",
        {},
    )

    expected_board_rows = (
        stats.get(
            "station_board_rows"
        )
    )

    expected_route_stops = (
        stats.get(
            "route_stops"
        )
    )

    if (
        expected_board_rows
        is not None
        and len(board_keys)
        != expected_board_rows
    ):
        raise RuntimeError(
            "board-row count mismatch: "
            f"{len(board_keys)} != "
            f"{expected_board_rows}"
        )

    if (
        expected_route_stops
        is not None
        and len(stop_rows)
        != expected_route_stops
    ):
        raise RuntimeError(
            "route-stop count mismatch: "
            f"{len(stop_rows)} != "
            f"{expected_route_stops}"
        )

    return {
        "stations": station_rows,
        "lines": line_rows,
        "station_lines": (
            station_line_rows
        ),
        "destinations": (
            destination_rows
        ),
        "stop_times": stop_rows,
        "board_visible": len(
            matched_board_keys
        ),
    }


def append_copy(
    parts,
    table,
    columns,
    rows,
):
    parts.append(
        "COPY "
        f"{table} "
        "("
        + ", ".join(columns)
        + ") "
        "FROM STDIN "
        "WITH (FORMAT text);"
    )

    for row in rows:
        parts.append(
            copy_row(row)
        )

    parts.append(r"\.")


def build_sql(import_data):
    parts = [
        r"\set ON_ERROR_STOP on",
        "",
        "BEGIN;",
        "",
        (
            "SET LOCAL "
            "statement_timeout = '120s';"
        ),
        "",
        # All of these tables contain generated/reference data.
        # Reload them atomically.
        (
            "TRUNCATE TABLE "
            "stop_times, "
            "stop_times_staging, "
            "station_lines, "
            "dest_map, "
            "lines, "
            "stations "
            "RESTART IDENTITY CASCADE;"
        ),
        "",
    ]

    append_copy(
        parts,
        "stations",
        [
            "code",
            "name",
            "selectable",
        ],
        import_data[
            "stations"
        ],
    )

    parts.append("")

    append_copy(
        parts,
        "lines",
        [
            "id",
            "ka_name",
            "color",
        ],
        import_data[
            "lines"
        ],
    )

    parts.append("")

    # COPY with explicit line IDs does not advance the sequence.
    parts.extend(
        [
            (
                "SELECT setval("
                "'lines_id_seq', "
                "(SELECT MAX(id) "
                "FROM lines)"
                ");"
            ),
            "",
        ]
    )

    append_copy(
        parts,
        "station_lines",
        [
            "station_id",
            "line_id",
        ],
        import_data[
            "station_lines"
        ],
    )

    parts.append("")

    append_copy(
        parts,
        "dest_map",
        [
            "raw_dest",
            "terminal_station_id",
            "via_station_id",
        ],
        import_data[
            "destinations"
        ],
    )

    parts.append("")

    append_copy(
        parts,
        "stop_times",
        [
            "station_id",
            "line_id",
            "train_id",
            "route_name",
            "raw_dest",
            "arrival_time",
            "arrival_sort",
            "dest_time",
            "board_visible",
        ],
        import_data[
            "stop_times"
        ],
    )

    parts.extend(
        [
            "",
            "COMMIT;",
            "",
        ]
    )

    return "\n".join(parts)


def run_psql_script(
    dsn,
    sql,
):
    result = subprocess.run(
        [
            "psql",
            dsn,
            "-X",
            "-v",
            "ON_ERROR_STOP=1",
            "-f",
            "-",
        ],
        input=sql,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            "PostgreSQL import failed"
        )


def verify_database(dsn):
    query = """
SELECT
    (SELECT COUNT(*) FROM stations),
    (SELECT COUNT(*) FROM stations WHERE selectable = TRUE),
    (SELECT COUNT(*) FROM stations WHERE selectable = FALSE),
    (SELECT COUNT(*) FROM lines),
    (SELECT COUNT(*) FROM station_lines),
    (SELECT COUNT(*) FROM dest_map),
    (SELECT COUNT(*) FROM stop_times),
    (SELECT COUNT(*) FROM stop_times WHERE board_visible = TRUE),
    (SELECT COUNT(*) FROM stop_times WHERE board_visible = FALSE);
"""

    result = subprocess.run(
        [
            "psql",
            dsn,
            "-X",
            "-A",
            "-t",
            "-F",
            "\t",
            "-v",
            "ON_ERROR_STOP=1",
            "-c",
            query,
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            "database verification failed: "
            f"{result.stderr.strip()}"
        )

    line = result.stdout.strip()

    values = line.split("\t")

    if len(values) != 9:
        raise RuntimeError(
            "unexpected verification "
            f"output: {line!r}"
        )

    (
        station_count,
        selectable_count,
        route_only_count,
        line_count,
        station_line_count,
        destination_count,
        stop_count,
        visible_count,
        hidden_count,
    ) = map(int, values)

    return {
        "stations": station_count,
        "selectable_stations": (
            selectable_count
        ),
        "route_only_stations": (
            route_only_count
        ),
        "lines": line_count,
        "station_lines": (
            station_line_count
        ),
        "destinations": (
            destination_count
        ),
        "stop_times": stop_count,
        "board_visible": (
            visible_count
        ),
        "board_hidden": (
            hidden_count
        ),
    }


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Import compiled Kommute "
            "schedule data into PostgreSQL"
        )
    )

    parser.add_argument(
        "--dsn",
        default=(
            os.environ.get(
                "DB_DSN"
            )
            or DEFAULT_DSN
        ),
        help=(
            "PostgreSQL DSN. "
            "Defaults to DB_DSN or "
            "the local Kommute dev DB."
        ),
    )

    parser.add_argument(
        "--data",
        type=Path,
        default=DATA_FILE,
        help=(
            "Compiled Kommute JSON file"
        ),
    )

    args = parser.parse_args()

    if not args.data.exists():
        raise RuntimeError(
            f"missing compiled dataset: "
            f"{args.data}"
        )

    print(
        f"Reading {args.data}..."
    )

    data = read_json(
        args.data
    )

    print(
        "Validating compiled dataset..."
    )

    import_data = build_import(
        data
    )

    print()
    print(
        "Prepared PostgreSQL import"
    )

    print(
        f"  stations:       "
        f"{len(import_data['stations'])}"
    )

    print(
        f"  lines:          "
        f"{len(import_data['lines'])}"
    )

    print(
        f"  station_lines:  "
        f"{len(import_data['station_lines'])}"
    )

    print(
        f"  destinations:   "
        f"{len(import_data['destinations'])}"
    )

    print(
        f"  route stops:    "
        f"{len(import_data['stop_times'])}"
    )

    print(
        f"  board visible:  "
        f"{import_data['board_visible']}"
    )

    print()

    sql = build_sql(
        import_data
    )

    print(
        "Importing into PostgreSQL..."
    )

    run_psql_script(
        args.dsn,
        sql,
    )

    verification = (
        verify_database(
            args.dsn
        )
    )

    print()
    print(
        "PostgreSQL import complete"
    )

    print(
        f"  stations:            "
        f"{verification['stations']}"
    )

    print(
        f"  selectable stations: "
        f"{verification['selectable_stations']}"
    )

    print(
        f"  route-only stations: "
        f"{verification['route_only_stations']}"
    )

    print(
        f"  lines:               "
        f"{verification['lines']}"
    )

    print(
        f"  station_lines:       "
        f"{verification['station_lines']}"
    )

    print(
        f"  destinations:        "
        f"{verification['destinations']}"
    )

    print(
        f"  stop_times:          "
        f"{verification['stop_times']}"
    )

    print(
        f"  board visible:       "
        f"{verification['board_visible']}"
    )

    print(
        f"  route-only rows:     "
        f"{verification['board_hidden']}"
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
