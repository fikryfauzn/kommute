\set ON_ERROR_STOP on

BEGIN;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM dest_map
    WHERE raw_dest = 'KAMPUNGBANDAN'
      AND terminal_station_id = 'KPB'
  ) THEN
    RAISE EXCEPTION 'Expected KAMPUNGBANDAN -> KPB mapping not found; no update performed';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM dest_map
    WHERE raw_dest = 'KAMPUNGBANDAN VIA PSE'
      AND terminal_station_id = 'KPB'
      AND via_station_id = 'PSE'
  ) THEN
    RAISE EXCEPTION 'Expected VIA PSE mapping not found; no update performed';
  END IF;
END $$;

UPDATE dest_map
SET via_station_id = 'MRI'
WHERE raw_dest = 'KAMPUNGBANDAN'
  AND terminal_station_id = 'KPB'
  AND via_station_id IS DISTINCT FROM 'MRI';

COMMIT;

SELECT raw_dest, terminal_station_id, via_station_id
FROM dest_map
WHERE raw_dest LIKE 'KAMPUNGBANDAN%'
ORDER BY raw_dest;
