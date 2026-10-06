#!/usr/bin/env python3

import json
import re
import subprocess
import sys
import time
from pathlib import Path


BASE_URL = "https://www.kci.id/api/krl"
SOURCE_PAGE = "https://www.kci.id/perjalanan-krl/jadwal-kereta"

RAW_DIR = Path("data/kci/raw")
SCHEDULE_DIR = RAW_DIR / "schedules"
OUTPUT_DIR = RAW_DIR / "train-schedules"

SUPPORTED_LINES = {
    "COMMUTER LINE BOGOR",
    "COMMUTER LINE CIKARANG",
    "COMMUTER LINE RANGKASBITUNG",
    "COMMUTER LINE TANGERANG",
    "COMMUTER LINE TANJUNGPRIUK",
}

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

TRAIN_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def read_json(path):
    with path.open(
        "r",
        encoding="utf-8",
    ) as f:
        return json.load(f)


def write_json_atomic(path, data):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    tmp = path.with_suffix(
        path.suffix + ".tmp"
    )

    with tmp.open(
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2,
        )
        f.write("\n")

    tmp.replace(path)


def fetch_train_schedule(train_id):
    cmd = [
        "curl",
        "-fsS",
        "--compressed",
        "--retry",
        "3",
        "--retry-delay",
        "2",
        *HEADERS,
        "-G",
        "--data-urlencode",
        f"trainid={train_id}",
        f"{BASE_URL}/train-schedule",
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            result.stderr.strip()
            or f"curl exited {result.returncode}"
        )

    try:
        payload = json.loads(
            result.stdout
        )
    except json.JSONDecodeError as exc:
        preview = result.stdout[:500]

        raise RuntimeError(
            "non-JSON response: "
            f"{preview!r}"
        ) from exc

    if payload.get("status") != 200:
        raise RuntimeError(
            "KCI returned "
            f"status={payload.get('status')} "
            f"data={payload.get('data')!r}"
        )

    rows = payload.get("data")

    if not isinstance(rows, list):
        raise RuntimeError(
            "data is not an array"
        )

    if not rows:
        raise RuntimeError(
            "empty train schedule"
        )

    for index, row in enumerate(rows):
        returned_train = row.get(
            "train_id"
        )

        if returned_train != train_id:
            raise RuntimeError(
                f"row {index}: requested "
                f"{train_id!r}, got "
                f"{returned_train!r}"
            )

        required = {
            "train_id",
            "ka_name",
            "station_id",
            "station_name",
            "time_est",
            "color",
        }

        missing = (
            required - row.keys()
        )

        if missing:
            raise RuntimeError(
                f"row {index}: missing "
                f"{sorted(missing)}"
            )

    return payload


def collect_supported_train_ids():
    if not SCHEDULE_DIR.exists():
        raise RuntimeError(
            "missing station schedules: "
            f"{SCHEDULE_DIR}"
        )

    train_ids = set()

    schedule_files = sorted(
        SCHEDULE_DIR.glob("*.json")
    )

    if not schedule_files:
        raise RuntimeError(
            "no station schedule files found"
        )

    supported_rows = 0

    for path in schedule_files:
        payload = read_json(path)

        rows = payload.get("data")

        if not isinstance(rows, list):
            raise RuntimeError(
                f"{path}: data is not an array"
            )

        for row in rows:
            if (
                row.get("ka_name")
                not in SUPPORTED_LINES
            ):
                continue

            train_id = row.get(
                "train_id"
            )

            if not train_id:
                raise RuntimeError(
                    f"{path}: row missing train_id"
                )

            if not TRAIN_ID_RE.fullmatch(
                train_id
            ):
                raise RuntimeError(
                    "unsafe train ID: "
                    f"{train_id!r}"
                )

            train_ids.add(train_id)
            supported_rows += 1

    return sorted(train_ids), supported_rows


def existing_file_is_valid(
    path,
    train_id,
):
    if not path.exists():
        return False

    try:
        payload = read_json(path)
    except Exception:
        return False

    if payload.get("status") != 200:
        return False

    rows = payload.get("data")

    if (
        not isinstance(rows, list)
        or not rows
    ):
        return False

    return all(
        row.get("train_id")
        == train_id
        for row in rows
    )


def main():
    train_ids, supported_rows = (
        collect_supported_train_ids()
    )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    print(
        "Fetching complete KCI train routes..."
    )

    print(
        f"Supported station rows: "
        f"{supported_rows}"
    )

    print(
        f"Unique trains: "
        f"{len(train_ids)}"
    )

    print()

    fetched = 0
    reused = 0
    total_stops = 0
    failures = []

    for index, train_id in enumerate(
        train_ids,
        start=1,
    ):
        output_path = (
            OUTPUT_DIR
            / f"{train_id}.json"
        )

        print(
            f"[{index:04d}/"
            f"{len(train_ids):04d}] "
            f"{train_id:<10}",
            end=" ",
            flush=True,
        )

        if existing_file_is_valid(
            output_path,
            train_id,
        ):
            payload = read_json(
                output_path
            )

            stop_count = len(
                payload["data"]
            )

            reused += 1
            total_stops += stop_count

            print(
                f"{stop_count:3d} stops "
                "[cached]"
            )

            continue

        try:
            payload = (
                fetch_train_schedule(
                    train_id
                )
            )

            write_json_atomic(
                output_path,
                payload,
            )

            stop_count = len(
                payload["data"]
            )

            fetched += 1
            total_stops += stop_count

            print(
                f"{stop_count:3d} stops"
            )

        except Exception as exc:
            failures.append(
                (
                    train_id,
                    str(exc),
                )
            )

            print("FAILED")

        # Avoid needlessly hammering KCI.
        time.sleep(0.20)

    print()
    print(
        "Train-route fetch complete"
    )

    print(
        f"  trains:       "
        f"{len(train_ids)}"
    )

    print(
        f"  fetched:      "
        f"{fetched}"
    )

    print(
        f"  cached:       "
        f"{reused}"
    )

    print(
        f"  route stops:  "
        f"{total_stops}"
    )

    print(
        f"  failures:     "
        f"{len(failures)}"
    )

    print(
        f"  output:       "
        f"{OUTPUT_DIR}"
    )

    if failures:
        print()
        print("Failures:")

        for train_id, error in failures:
            print(
                f"  {train_id:<10} "
                f"{error}"
            )

        sys.exit(1)


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
