BEGIN;

-- ============================================================
-- STATIONS
--
-- The current KCI station-list endpoint contains the stations
-- users can actively select/search.
--
-- The complete train-route endpoint can additionally contain
-- physical route stations that are not currently selectable.
--
-- Example:
--
--   KAT / KARET
--
-- Karet appears in train paths but does not appear in KCI's
-- current selectable station list.
--
-- Keep it relationally valid while excluding it from the
-- public station picker.
-- ============================================================

ALTER TABLE stations
    ADD COLUMN selectable BOOLEAN NOT NULL DEFAULT TRUE;


-- Karet is still referenced by complete train routes, so it
-- belongs in the stations table even though users should not
-- currently be able to select it.
INSERT INTO stations (
    code,
    name,
    selectable
)
VALUES (
    'KAT',
    'KARET',
    FALSE
)
ON CONFLICT (code) DO UPDATE
SET
    name = EXCLUDED.name,
    selectable = EXCLUDED.selectable;


-- ============================================================
-- STOP_TIMES
--
-- /api/krl/schedules and /api/krl/train-schedule do not expose
-- exactly the same set of stops.
--
-- stop_times will now represent the COMPLETE physical train
-- route from /train-schedule.
--
-- board_visible tells us whether the same train/stop also
-- appears in the station-board /schedules feed.
--
-- This lets one table support both:
--
--   1. arrival board
--   2. complete direct-trip lookup
-- ============================================================

ALTER TABLE stop_times
    ADD COLUMN board_visible BOOLEAN NOT NULL DEFAULT TRUE;


-- stop_times_staging was created using:
--
--   CREATE TABLE ... (LIKE stop_times INCLUDING ALL)
--
-- in migration 001, before board_visible existed.
--
-- Therefore it must be altered separately.
ALTER TABLE stop_times_staging
    ADD COLUMN board_visible BOOLEAN NOT NULL DEFAULT TRUE;


-- ============================================================
-- INDEXES
-- ============================================================

-- Replace the previous arrival-board index with a partial index.
--
-- Arrival requests only care about board-visible rows, so this
-- keeps that query path small even though stop_times now holds
-- complete route data.
DROP INDEX IF EXISTS idx_arrivals;

CREATE INDEX idx_arrivals
    ON stop_times (
        station_id,
        arrival_sort
    )
    INCLUDE (
        train_id,
        line_id,
        raw_dest,
        dest_time,
        arrival_time,
        route_name
    )
    WHERE board_visible = TRUE;


-- The existing trip lookup index remains valid:
--
--   idx_train_lookup (train_id, station_id)
--
-- Trip lookup MUST be able to see route-only stops, so no
-- board_visible predicate belongs there.


-- ============================================================
-- SANITY CHECKS
-- ============================================================

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM stations
        WHERE code = 'KAT'
          AND name = 'KARET'
          AND selectable = FALSE
    ) THEN
        RAISE EXCEPTION
            'KAT / KARET route-only station was not configured correctly';
    END IF;
END
$$;


COMMIT;
