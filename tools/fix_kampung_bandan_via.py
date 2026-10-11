#!/usr/bin/env python3
"""Repair the compiled KCI route label and preserve the fix in future compiles.

Run from the Kommute repository after extracting the correction ZIP.
No database credentials are used here; run the accompanying SQL separately.
"""

import json
import os
import stat
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATASET = ROOT / "data" / "kommute.json"
COMPILER = ROOT / "tools" / "compile_schedule.py"
BARE_LABEL = "KAMPUNGBANDAN"

METADATA_ANCHOR = '''            metadata = {
                "line": line,
'''
METADATA_PATCH = '''            # All unqualified KAMPUNGBANDAN services in the current
            # verified timetable run through Manggarai. Preserve the
            # routing label when the KCI board omits the VIA suffix.
            if raw_dest == "KAMPUNGBANDAN" and via_code is None:
                via_code = "MRI"

''' + METADATA_ANCHOR

ROUTE_ANCHOR = '''        trains[
            train_id
        ] = {
            **metadata,
            "stops": stops,
        }
'''
ROUTE_PATCH = '''        # Don't silently mislabel a future KCI timetable if the
        # unqualified route ever stops running through Manggarai.
        if metadata["destination"] == "KAMPUNGBANDAN":
            via_stops = {stop["station"] for stop in stops}
            if "MRI" not in via_stops or "PSE" in via_stops:
                raise RuntimeError(
                    f"{train_id}: unqualified Kampung Bandan route "
                    "is no longer exclusively via Manggarai; "
                    "review destination normalization"
                )

''' + ROUTE_ANCHOR


def corrected_compiler(source):
    if METADATA_PATCH not in source:
        if source.count(METADATA_ANCHOR) != 1:
            raise RuntimeError("Compiler metadata section differs from expected version; no changes made")
        source = source.replace(METADATA_ANCHOR, METADATA_PATCH, 1)

    if ROUTE_PATCH not in source:
        if source.count(ROUTE_ANCHOR) != 1:
            raise RuntimeError("Compiler route section differs from expected version; no changes made")
        source = source.replace(ROUTE_ANCHOR, ROUTE_PATCH, 1)

    compile(source, str(COMPILER), "exec")
    return source


def corrected_dataset(data):
    destinations = data.get("destinations")
    trains = data.get("trains")
    if not isinstance(destinations, dict) or not isinstance(trains, dict):
        raise RuntimeError("Invalid compiled dataset: missing destinations or trains")
    mapping = destinations.get(BARE_LABEL)
    if not isinstance(mapping, dict) or mapping.get("terminal") != "KPB":
        raise RuntimeError("KAMPUNGBANDAN destination mapping is missing or not KPB")
    if mapping.get("via") not in (None, "MRI"):
        raise RuntimeError("KAMPUNGBANDAN has unexpected VIA mapping; not overwriting")
    if (destinations.get("KAMPUNGBANDAN VIA PSE") or {}).get("via") != "PSE":
        raise RuntimeError("Pasar Senen mapping differs from expected; not overwriting")

    bare_trains = [(train_id, train) for train_id, train in trains.items()
                   if train.get("destination") == BARE_LABEL]
    if not bare_trains:
        raise RuntimeError("No unqualified Kampung Bandan trains; not changing anything")

    for train_id, train in bare_trains:
        stops = [stop.get("station") for stop in train.get("stops", [])]
        if not stops or stops[-1] != "KPB" or "MRI" not in stops or "PSE" in stops:
            raise RuntimeError(
                f"Train {train_id} no longer matches the verified Manggarai route; "
                "investigate before changing destination labels"
            )
        if train.get("via") not in (None, "MRI"):
            raise RuntimeError(f"Train {train_id} has an unexpected existing VIA value")

    mapping["via"] = "MRI"
    for _, train in bare_trains:
        train["via"] = "MRI"

    return data, len(bare_trains)


def atomic_write(path, content):
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", newline="\n", dir=path.parent,
        prefix=".kommute-via-", suffix=".tmp", delete=False
    ) as tmp:
        tmp.write(content)
        temp_path = Path(tmp.name)
    try:
        os.chmod(temp_path, stat.S_IMODE(path.stat().st_mode))
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def main():
    compiler_original = COMPILER.read_text(encoding="utf-8")
    compiler_fixed = corrected_compiler(compiler_original)

    data_original = DATASET.read_text(encoding="utf-8")
    data, train_count = corrected_dataset(json.loads(data_original))
    data_fixed = json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n"

    # Preflight is complete. Only now modify project files.
    if compiler_fixed != compiler_original:
        atomic_write(COMPILER, compiler_fixed)
        print("Updated future compiler: tools/compile_schedule.py")
    else:
        print("Compiler already contains the normalization")

    if data_fixed != data_original:
        atomic_write(DATASET, data_fixed)
        print("Updated compiled dataset: data/kommute.json")
    else:
        print("Compiled dataset already normalized")

    print(f"Validated {train_count} unqualified Kampung Bandan trains via MRI.")
    print("Next: apply sql/fix_kampung_bandan_via.sql using psql and DB_DSN.")


if __name__ == "__main__":
    main()
