#!/usr/bin/env python3

import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


RAW_DIR = Path("data/kci/raw")
SCHEDULE_DIR = RAW_DIR / "schedules"
TRAIN_ROUTE_DIR = RAW_DIR / "train-schedules"

OUTPUT = Path("data/kommute.json")


SUPPORTED_LINES = {
    "COMMUTER LINE BOGOR",
    "COMMUTER LINE CIKARANG",
    "COMMUTER LINE RANGKASBITUNG",
    "COMMUTER LINE TANGERANG",
    "COMMUTER LINE TANJUNGPRIUK",
}


LINE_LETTERS = {
    "COMMUTER LINE BOGOR": "B",
    "COMMUTER LINE CIKARANG": "C",
    "COMMUTER LINE RANGKASBITUNG": "R",
    "COMMUTER LINE TANGERANG": "T",
    "COMMUTER LINE TANJUNGPRIUK": "P",
}


STATION_NAME_ALIASES = {
    "TANJUNGPRIUK": "TPK",
}


STATION_CODE_RE = re.compile(
    r"^[A-Z0-9]{2,10}$"
)


def read_json(path):
    with path.open(
        "r",
        encoding="utf-8",
    ) as f:
        return json.load(f)


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
            ensure_ascii=False,
            separators=(",", ":"),
        )
        f.write("\n")


def normalize_station_name(value):
    return re.sub(
        r"[^A-Z0-9]",
        "",
        value.upper(),
    )


def arrival_sort(time_string):
    """
    Operational day begins at 03:00.

        03:00 -> 0
        23:59 -> 1259
        00:00 -> 1260
        02:59 -> 1439
    """
    parts = time_string.split(":")

    if len(parts) < 2:
        raise ValueError(
            f"invalid time: {time_string!r}"
        )

    hour = int(parts[0])
    minute = int(parts[1])

    if not 0 <= hour <= 23:
        raise ValueError(
            f"invalid hour: {time_string!r}"
        )

    if not 0 <= minute <= 59:
        raise ValueError(
            f"invalid minute: {time_string!r}"
        )

    if hour >= 3:
        return (
            (hour - 3) * 60
            + minute
        )

    return (
        (hour + 21) * 60
        + minute
    )


def parse_destination(raw_dest):
    marker = " VIA "

    if marker not in raw_dest:
        return (
            raw_dest.strip(),
            None,
        )

    terminal, via = raw_dest.split(
        marker,
        1,
    )

    return (
        terminal.strip(),
        via.strip(),
    )


def resolve_station(
    value,
    stations_by_code,
    station_name_index,
):
    """
    Resolve station references used by destination strings.

    These must resolve to selectable/current stations.
    """
    if not value:
        return None

    value = value.upper()

    if value in stations_by_code:
        return value

    normalized = normalize_station_name(
        value
    )

    alias = STATION_NAME_ALIASES.get(
        normalized
    )

    if alias is not None:
        if alias not in stations_by_code:
            raise RuntimeError(
                "station-name alias points "
                "to missing station: "
                f"{normalized} -> {alias}"
            )

        return alias

    return station_name_index.get(
        normalized
    )


def build_station_indexes(
    raw_stations,
):
    stations_by_code = {}
    station_name_index = {}

    for station in raw_stations:
        code = station["sta_id"]
        name = station["sta_name"]

        if code in stations_by_code:
            raise RuntimeError(
                f"duplicate station code: "
                f"{code}"
            )

        stations_by_code[code] = {
            "code": code,
            "name": name,
        }

        normalized = (
            normalize_station_name(
                name
            )
        )

        existing = (
            station_name_index.get(
                normalized
            )
        )

        if (
            existing is not None
            and existing != code
        ):
            raise RuntimeError(
                "station-name collision: "
                f"{normalized}: "
                f"{existing} vs {code}"
            )

        station_name_index[
            normalized
        ] = code

    return (
        stations_by_code,
        station_name_index,
    )


def load_station_schedules(
    raw_stations,
):
    schedules = {}

    for station in raw_stations:
        code = station["sta_id"]

        path = (
            SCHEDULE_DIR
            / f"{code}.json"
        )

        if not path.exists():
            raise RuntimeError(
                f"missing station schedule: "
                f"{path}"
            )

        payload = read_json(path)

        rows = payload.get("data")

        if not isinstance(rows, list):
            raise RuntimeError(
                f"{code}: schedule data "
                "is not an array"
            )

        schedules[code] = rows

    return schedules


def determine_line_colors(
    schedules,
):
    counts = {
        line: Counter()
        for line in SUPPORTED_LINES
    }

    for rows in schedules.values():
        for row in rows:
            line = row.get("ka_name")

            if line not in SUPPORTED_LINES:
                continue

            color = row.get("color")

            if not color:
                raise RuntimeError(
                    f"{line}: missing color"
                )

            counts[line][color] += 1

    canonical = {}

    for line in sorted(
        SUPPORTED_LINES
    ):
        if not counts[line]:
            raise RuntimeError(
                "supported line has no rows: "
                f"{line}"
            )

        canonical[
            line
        ] = counts[
            line
        ].most_common(1)[0][0]

    return canonical, counts


def resolve_route_station(
    row,
    stations_by_code,
    station_name_index,
    route_only_stations,
):
    """
    Resolve station references from /train-schedule.

    There are three cases.

    1. Normal current station:

        station_id = MRI
        -> MRI

    2. KCI internal ID mismatch:

        station_id   = GRG
        station_name = GROGOL

        current station list contains:
        GGL / GROGOL

        -> canonical GGL

    3. Route-only / non-selectable station:

        station_id   = KAT
        station_name = KARET

        KAT is absent from the current station-list endpoint but still
        appears in physical train paths.

        -> preserve KAT in the train route
        -> do NOT expose it as a selectable Kommute station.
    """
    source_code = str(
        row.get("station_id", "")
    ).upper()

    station_name = str(
        row.get("station_name", "")
    ).strip()

    if not source_code:
        raise RuntimeError(
            "route row missing station_id"
        )

    # Case 1:
    # canonical station ID already exists.
    if source_code in stations_by_code:
        return (
            source_code,
            False,
        )

    # Case 2:
    # try resolving by station name.
    if station_name:
        normalized = (
            normalize_station_name(
                station_name
            )
        )

        canonical = (
            station_name_index.get(
                normalized
            )
        )

        if canonical is not None:
            return (
                canonical,
                False,
            )

    # Case 3:
    # route-only station.
    if not STATION_CODE_RE.fullmatch(
        source_code
    ):
        raise RuntimeError(
            "invalid route-only station "
            f"code: {source_code!r}"
        )

    if not station_name:
        raise RuntimeError(
            "route-only station has no "
            f"name: {source_code}"
        )

    existing = (
        route_only_stations.get(
            source_code
        )
    )

    candidate = {
        "code": source_code,
        "name": station_name,
    }

    if (
        existing is not None
        and existing != candidate
    ):
        raise RuntimeError(
            "route-only station "
            "conflict for "
            f"{source_code}: "
            f"{existing} vs {candidate}"
        )

    route_only_stations[
        source_code
    ] = candidate

    return (
        source_code,
        True,
    )


def main():
    manifest_path = (
        RAW_DIR / "manifest.json"
    )

    stations_path = (
        RAW_DIR / "stations.json"
    )

    for required in (
        manifest_path,
        stations_path,
        SCHEDULE_DIR,
        TRAIN_ROUTE_DIR,
    ):
        if not required.exists():
            raise RuntimeError(
                f"missing input: "
                f"{required}"
            )

    raw_manifest = read_json(
        manifest_path
    )

    raw_stations = read_json(
        stations_path
    )

    print(
        "Compiling Kommute schedule..."
    )

    print(
        f"Raw stations: "
        f"{len(raw_stations)}"
    )

    (
        stations_by_code,
        station_name_index,
    ) = build_station_indexes(
        raw_stations
    )

    schedules = (
        load_station_schedules(
            raw_stations
        )
    )

    (
        canonical_colors,
        observed_colors,
    ) = determine_line_colors(
        schedules
    )

    print()
    print(
        "Canonical line colors:"
    )

    for line in sorted(
        SUPPORTED_LINES
    ):
        print(
            f"  {line:<32} "
            f"{canonical_colors[line]}"
        )

    # ---------------------------------------------------------
    # Station-board pass
    # ---------------------------------------------------------

    train_metadata = {}

    arrivals_by_station = (
        defaultdict(list)
    )

    station_lines = (
        defaultdict(set)
    )

    destinations = {}

    ignored_services = (
        defaultdict(int)
    )

    normalized_color_rows = (
        defaultdict(int)
    )

    unresolved_destinations = set()
    unresolved_via = set()

    seen_station_arrivals = set()

    supported_board_rows = 0
    ignored_rows = 0

    for station in raw_stations:
        station_code = (
            station["sta_id"]
        )

        for row in schedules[
            station_code
        ]:
            line = row["ka_name"]

            if line not in SUPPORTED_LINES:
                ignored_services[
                    line
                ] += 1

                ignored_rows += 1
                continue

            supported_board_rows += 1

            train_id = row["train_id"]
            route = row["route_name"]
            raw_dest = row["dest"]
            time_est = row["time_est"]
            dest_time = row["dest_time"]

            source_color = row["color"]

            canonical_color = (
                canonical_colors[
                    line
                ]
            )

            if (
                source_color
                != canonical_color
            ):
                normalized_color_rows[
                    line
                ] += 1

            (
                terminal_raw,
                via_raw,
            ) = parse_destination(
                raw_dest
            )

            terminal_code = (
                resolve_station(
                    terminal_raw,
                    stations_by_code,
                    station_name_index,
                )
            )

            if terminal_code is None:
                unresolved_destinations.add(
                    raw_dest
                )

            via_code = None

            if via_raw:
                via_code = (
                    resolve_station(
                        via_raw,
                        stations_by_code,
                        station_name_index,
                    )
                )

                if via_code is None:
                    unresolved_via.add(
                        via_raw
                    )

            metadata = {
                "line": line,
                "color": canonical_color,
                "route": route,
                "destination": raw_dest,
                "terminal": terminal_code,
                "via": via_code,
                "destination_time": (
                    dest_time
                ),
            }

            existing = (
                train_metadata.get(
                    train_id
                )
            )

            if existing is None:
                train_metadata[
                    train_id
                ] = metadata

            elif existing != metadata:
                raise RuntimeError(
                    "inconsistent metadata for "
                    f"train {train_id}:\n"
                    f"  first: {existing}\n"
                    f"  later: {metadata}"
                )

            arrival_key = (
                station_code,
                train_id,
                time_est,
            )

            if (
                arrival_key
                in seen_station_arrivals
            ):
                raise RuntimeError(
                    "duplicate station arrival: "
                    f"{arrival_key}"
                )

            seen_station_arrivals.add(
                arrival_key
            )

            arrivals_by_station[
                station_code
            ].append(
                {
                    "train_id": train_id,
                    "arrival_time": (
                        time_est
                    ),
                    "arrival_sort": (
                        arrival_sort(
                            time_est
                        )
                    ),
                }
            )

            station_lines[
                station_code
            ].add(line)

            destinations[
                raw_dest
            ] = {
                "raw": raw_dest,
                "terminal": terminal_code,
                "via": via_code,
            }

    # ---------------------------------------------------------
    # Destination validation
    # ---------------------------------------------------------

    if unresolved_destinations:
        print()
        print(
            "ERROR: unresolved "
            "destinations:"
        )

        for value in sorted(
            unresolved_destinations
        ):
            print(
                f"  {value}"
            )

        raise RuntimeError(
            "destination normalization "
            "is incomplete"
        )

    if unresolved_via:
        print()
        print(
            "ERROR: unresolved "
            "VIA stations:"
        )

        for value in sorted(
            unresolved_via
        ):
            print(
                f"  {value}"
            )

        raise RuntimeError(
            "VIA normalization "
            "is incomplete"
        )

    # ---------------------------------------------------------
    # Sort station-board arrivals
    # ---------------------------------------------------------

    for rows in (
        arrivals_by_station.values()
    ):
        rows.sort(
            key=lambda row: (
                row["arrival_sort"],
                row["train_id"],
            )
        )

    # ---------------------------------------------------------
    # Complete train-route pass
    # ---------------------------------------------------------

    trains = {}

    route_station_aliases = {}

    route_only_stations = {}

    route_stop_count = 0

    for train_id in sorted(
        train_metadata
    ):
        path = (
            TRAIN_ROUTE_DIR
            / f"{train_id}.json"
        )

        if not path.exists():
            raise RuntimeError(
                "missing train route: "
                f"{train_id}"
            )

        payload = read_json(
            path
        )

        route_rows = payload.get(
            "data"
        )

        if (
            not isinstance(
                route_rows,
                list,
            )
            or not route_rows
        ):
            raise RuntimeError(
                f"{train_id}: "
                "invalid train route"
            )

        metadata = train_metadata[
            train_id
        ]

        stops = []

        previous_sort = None

        for (
            route_index,
            row,
        ) in enumerate(
            route_rows
        ):
            if (
                row.get("train_id")
                != train_id
            ):
                raise RuntimeError(
                    f"{train_id}: route row "
                    f"{route_index} belongs "
                    "to another train"
                )

            route_line = row.get(
                "ka_name"
            )

            if (
                route_line
                != metadata["line"]
            ):
                raise RuntimeError(
                    f"{train_id}: line mismatch: "
                    f"{metadata['line']!r} vs "
                    f"{route_line!r}"
                )

            (
                canonical_station,
                is_route_only,
            ) = resolve_route_station(
                row,
                stations_by_code,
                station_name_index,
                route_only_stations,
            )

            source_station = str(
                row["station_id"]
            ).upper()

            # If KCI used another station ID but the station name
            # resolved to a canonical active station, record it.
            if (
                not is_route_only
                and source_station
                != canonical_station
            ):
                previous_alias = (
                    route_station_aliases.get(
                        source_station
                    )
                )

                if (
                    previous_alias
                    is not None
                    and previous_alias
                    != canonical_station
                ):
                    raise RuntimeError(
                        "route station alias "
                        "collision: "
                        f"{source_station} -> "
                        f"{previous_alias} / "
                        f"{canonical_station}"
                    )

                route_station_aliases[
                    source_station
                ] = canonical_station

            time_est = row["time_est"]

            sort_value = arrival_sort(
                time_est
            )

            # /train-schedule is already ordered.
            #
            # This verifies our 03:00 operational-day transform
            # preserves that order across midnight.
            if (
                previous_sort is not None
                and sort_value
                < previous_sort
            ):
                raise RuntimeError(
                    f"{train_id}: operational "
                    "time ordering broke between "
                    f"{stops[-1]['station']} "
                    f"({stops[-1]['arrival_time']}) "
                    f"and {canonical_station} "
                    f"({time_est})"
                )

            previous_sort = sort_value

            stop = {
                "station": (
                    canonical_station
                ),
                "arrival_time": (
                    time_est
                ),
                "arrival_sort": (
                    sort_value
                ),
            }

            if is_route_only:
                stop[
                    "route_only"
                ] = True

            if row.get(
                "transit_station"
            ):
                stop[
                    "transit_station"
                ] = True

            stops.append(
                stop
            )

            route_stop_count += 1

        terminal = metadata[
            "terminal"
        ]

        if terminal is None:
            raise RuntimeError(
                f"{train_id}: "
                "missing terminal"
            )

        last_stop = stops[-1]

        if (
            last_stop["station"]
            != terminal
        ):
            raise RuntimeError(
                f"{train_id}: route terminal "
                "does not match destination: "
                f"route ends at "
                f"{last_stop['station']} "
                f"but destination resolves to "
                f"{terminal}"
            )

        if (
            last_stop["arrival_time"]
            != metadata[
                "destination_time"
            ]
        ):
            raise RuntimeError(
                f"{train_id}: destination "
                "time mismatch: "
                f"route says "
                f"{last_stop['arrival_time']} "
                f"but station schedules say "
                f"{metadata['destination_time']}"
            )

        trains[
            train_id
        ] = {
            **metadata,
            "stops": stops,
        }

    # ---------------------------------------------------------
    # Selectable Kommute stations
    #
    # IMPORTANT:
    # Route-only stations do NOT enter this collection.
    # ---------------------------------------------------------

    compiled_stations = {}

    for (
        code,
        station,
    ) in stations_by_code.items():

        lines = sorted(
            station_lines.get(
                code,
                set(),
            )
        )

        if not lines:
            continue

        compiled_stations[
            code
        ] = {
            "code": code,
            "name": station["name"],
            "lines": lines,
        }

    # ---------------------------------------------------------
    # Lines
    # ---------------------------------------------------------

    compiled_lines = {}

    for line in sorted(
        SUPPORTED_LINES
    ):
        compiled_lines[
            line
        ] = {
            "name": line,
            "letter": (
                LINE_LETTERS[line]
            ),
            "color": (
                canonical_colors[
                    line
                ]
            ),
            "stations": sorted(
                code
                for code, lines
                in station_lines.items()
                if line in lines
            ),
        }

    # ---------------------------------------------------------
    # Diagnostics
    # ---------------------------------------------------------

    color_diagnostics = {}

    for line in sorted(
        SUPPORTED_LINES
    ):
        counts = (
            observed_colors[
                line
            ]
        )

        color_diagnostics[
            line
        ] = {
            "canonical": (
                canonical_colors[
                    line
                ]
            ),
            "observed": {
                color: count
                for color, count
                in counts.most_common()
            },
            "normalized_rows": (
                normalized_color_rows[
                    line
                ]
            ),
        }

    # ---------------------------------------------------------
    # Final dataset
    # ---------------------------------------------------------

    output = {
        "schema_version": 2,

        "generated_at": (
            datetime.now(
                ZoneInfo(
                    "Asia/Jakarta"
                )
            ).isoformat()
        ),

        "source": {
            "name": (
                "KAI Commuter"
            ),
            "snapshot_fetched_at": (
                raw_manifest.get(
                    "fetched_at"
                )
            ),
        },

        "operational_day": {
            "starts_at": "03:00",
            "timezone": (
                "Asia/Jakarta"
            ),
        },

        "stats": {
            "stations": len(
                compiled_stations
            ),
            "route_only_stations": len(
                route_only_stations
            ),
            "lines": len(
                compiled_lines
            ),
            "trains": len(
                trains
            ),
            "station_board_rows": (
                supported_board_rows
            ),
            "route_stops": (
                route_stop_count
            ),
            "ignored_rows": (
                ignored_rows
            ),
            "destinations": len(
                destinations
            ),
        },

        "lines": (
            compiled_lines
        ),

        "stations": (
            compiled_stations
        ),

        "destinations": (
            destinations
        ),

        "arrivals_by_station": dict(
            arrivals_by_station
        ),

        "trains": trains,

        "diagnostics": {
            "station_name_aliases": (
                STATION_NAME_ALIASES
            ),

            "route_station_aliases": (
                route_station_aliases
            ),

            "route_only_stations": (
                route_only_stations
            ),

            "line_colors": (
                color_diagnostics
            ),

            "ignored_services": {
                line: count
                for line, count
                in sorted(
                    ignored_services.items()
                )
            },
        },
    }

    write_json(
        OUTPUT,
        output,
    )

    # ---------------------------------------------------------
    # Report
    # ---------------------------------------------------------

    print()
    print(
        "Kommute schedule compiled"
    )

    print(
        f"  stations:           "
        f"{len(compiled_stations)}"
    )

    print(
        f"  route-only stations:"
        f" {len(route_only_stations)}"
    )

    print(
        f"  lines:              "
        f"{len(compiled_lines)}"
    )

    print(
        f"  trains:             "
        f"{len(trains)}"
    )

    print(
        f"  station-board rows: "
        f"{supported_board_rows}"
    )

    print(
        f"  route stops:        "
        f"{route_stop_count}"
    )

    print(
        f"  ignored rows:       "
        f"{ignored_rows}"
    )

    print(
        f"  destinations:       "
        f"{len(destinations)}"
    )

    print(
        f"  output:             "
        f"{OUTPUT}"
    )

    if route_station_aliases:
        print()
        print(
            "Route station-ID aliases:"
        )

        for (
            source,
            canonical,
        ) in sorted(
            route_station_aliases.items()
        ):
            print(
                f"  {source:<10} "
                f"-> {canonical}"
            )

    if route_only_stations:
        print()
        print(
            "Route-only stations:"
        )

        for (
            code,
            station,
        ) in sorted(
            route_only_stations.items()
        ):
            print(
                f"  {code:<10} "
                f"{station['name']}"
            )

    if normalized_color_rows:
        print()
        print(
            "Normalized KCI "
            "line-color anomalies:"
        )

        for line in sorted(
            normalized_color_rows
        ):
            count = (
                normalized_color_rows[
                    line
                ]
            )

            if count == 0:
                continue

            print(
                f"  {line:<32} "
                f"{count:5d} rows "
                f"-> "
                f"{canonical_colors[line]}"
            )

    if ignored_services:
        print()
        print(
            "Ignored KCI services:"
        )

        for (
            line,
            count,
        ) in sorted(
            ignored_services.items()
        ):
            print(
                f"  {line:<32} "
                f"{count:5d} rows"
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
