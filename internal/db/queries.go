package db

import (
	"context"
	"encoding/json"
	"fmt"

	"github.com/fikryfauzn/kommute/internal/model"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

// GetStationsByLine lists only lines operating at least four distinct
// board-visible trains at the station during the loaded service day.
func GetStationsByLine(
	ctx context.Context,
	pool *pgxpool.Pool,
) ([]model.Line, error) {
	query := `
		SELECT
			l.ka_name,
			l.color,
			json_agg(
				json_build_object(
					'code', s.code,
					'name', s.name
				)
				ORDER BY s.name
			) AS stations
		FROM lines l
		JOIN station_lines sl
			ON sl.line_id = l.id
		JOIN stations s
			ON s.code = sl.station_id
		-- Only advertise regular station-line services. A line with
		-- 1 to 3 distinct board-visible trains in the service day
		-- remains in the timetable, but is not a selectable line.
		JOIN (
			SELECT station_id, line_id
			FROM stop_times
			WHERE board_visible = TRUE
			GROUP BY station_id, line_id
			HAVING COUNT(DISTINCT train_id) >= 4
		) active_lines
			ON active_lines.station_id = sl.station_id
			AND active_lines.line_id = sl.line_id
		WHERE s.selectable = TRUE
		GROUP BY
			l.id,
			l.ka_name,
			l.color
		ORDER BY l.ka_name
	`

	rows, err := pool.Query(
		ctx,
		query,
	)
	if err != nil {
		return nil, fmt.Errorf(
			"query stations by line: %w",
			err,
		)
	}
	defer rows.Close()

	var lines []model.Line

	for rows.Next() {
		var row model.LineRow

		if err := rows.Scan(
			&row.Name,
			&row.Color,
			&row.Stations,
		); err != nil {
			return nil, fmt.Errorf(
				"scan station line row: %w",
				err,
			)
		}

		var stations []model.StationInfo

		if err := json.Unmarshal(
			row.Stations,
			&stations,
		); err != nil {
			return nil, fmt.Errorf(
				"unmarshal stations json: %w",
				err,
			)
		}

		lines = append(
			lines,
			model.Line{
				Name:     row.Name,
				Color:    row.Color,
				Stations: stations,
			},
		)
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf(
			"iterate station rows: %w",
			err,
		)
	}

	return lines, nil
}

// GetArrivals returns the 5 nearest departures at a station. When line is
// non-empty (a lines.ka_name) only that line is considered, so the 5 rows
// are the 5 nearest of that line rather than a slice of the mixed board.
// Irregular station-line pairs with fewer than four daily services are hidden.
func GetArrivals(
	ctx context.Context,
	pool *pgxpool.Pool,
	stationID string,
	currentSort int,
	line string,
) ([]model.Arrival, error) {
	query := `
		SELECT
			st.train_id,
			TO_CHAR(
				st.arrival_time,
				'HH24:MI:SS'
			),
			TO_CHAR(
				st.dest_time,
				'HH24:MI:SS'
			),
			l.ka_name,
			l.color,
			ts.name AS dest_name,
			vs.code AS via_name
		FROM stop_times st
		JOIN (
			SELECT line_id
			FROM stop_times
			WHERE station_id = $1
			  AND board_visible = TRUE
			GROUP BY line_id
			HAVING COUNT(DISTINCT train_id) >= 4
		) active_lines
			ON active_lines.line_id = st.line_id
		JOIN lines l
			ON l.id = st.line_id
		JOIN dest_map dm
			ON dm.raw_dest = st.raw_dest
		JOIN stations ts
			ON ts.code = dm.terminal_station_id
		LEFT JOIN stations vs
			ON vs.code = dm.via_station_id
		WHERE st.station_id = $1
		  AND st.board_visible = TRUE
		  AND st.arrival_sort > $2
		  AND ($3::text = '' OR l.ka_name = $3::text)
		ORDER BY st.arrival_sort
		LIMIT 5
	`

	rows, err := pool.Query(
		ctx,
		query,
		stationID,
		currentSort,
		line,
	)
	if err != nil {
		return nil, fmt.Errorf(
			"query arrivals: %w",
			err,
		)
	}
	defer rows.Close()

	return pgx.CollectRows(
		rows,
		func(
			row pgx.CollectableRow,
		) (model.Arrival, error) {
			var a model.Arrival

			err := row.Scan(
				&a.TrainID,
				&a.ArrivalTime,
				&a.DestTime,
				&a.Line,
				&a.Color,
				&a.Destination,
				&a.Via,
			)

			return a, err
		},
	)
}

// GetArrivalsGrouped returns up to five upcoming trains per line/destination.
// Line/destination ranking is separate so routes sharing a terminal do not
// consume each other's five slots. Irregular station-line pairs are hidden.
func GetArrivalsGrouped(
	ctx context.Context,
	pool *pgxpool.Pool,
	stationID string,
	currentSort int,
) ([]model.ArrivalGroup, error) {
	query := `
		WITH active_lines AS (
			SELECT line_id
			FROM stop_times
			WHERE station_id = $1
			  AND board_visible = TRUE
			GROUP BY line_id
			HAVING COUNT(DISTINCT train_id) >= 4
		)
		SELECT
			st.raw_dest,
			ts.name AS dest_name,
			vs.name AS via_name,
			json_agg(
				json_build_object(
					'train_id', st.train_id,
					'line', l.ka_name,
					'color', l.color,
					'arrival_time', st.arrival_time,
					'dest_time', st.dest_time,
					'route_name', st.route_name
				)
				ORDER BY st.arrival_sort
			) AS next_trains
		FROM (
			SELECT
				st.*,
				ROW_NUMBER() OVER (
					PARTITION BY st.line_id, st.raw_dest
					ORDER BY st.arrival_sort
				) AS rn
			FROM stop_times st
			JOIN active_lines
				ON active_lines.line_id = st.line_id
			WHERE st.station_id = $1
			  AND st.board_visible = TRUE
			  AND st.arrival_sort > $2
		) st
		JOIN lines l
			ON l.id = st.line_id
		JOIN dest_map dm
			ON dm.raw_dest = st.raw_dest
		JOIN stations ts
			ON ts.code = dm.terminal_station_id
		LEFT JOIN stations vs
			ON vs.code = dm.via_station_id
		WHERE st.rn <= 5
		GROUP BY
			st.raw_dest,
			dm.terminal_station_id,
			ts.name,
			dm.via_station_id,
			vs.name
		ORDER BY MIN(st.arrival_sort)
	`

	rows, err := pool.Query(
		ctx,
		query,
		stationID,
		currentSort,
	)
	if err != nil {
		return nil, fmt.Errorf(
			"query grouped arrivals: %w",
			err,
		)
	}
	defer rows.Close()

	var groups []model.ArrivalGroup

	for rows.Next() {
		var row model.GroupedArrivalRow

		if err := rows.Scan(
			&row.RawDest,
			&row.DestName,
			&row.ViaName,
			&row.NextTrains,
		); err != nil {
			return nil, fmt.Errorf(
				"scan grouped arrival row: %w",
				err,
			)
		}

		var trains []model.GroupedTrainJSON

		if err := json.Unmarshal(
			row.NextTrains,
			&trains,
		); err != nil {
			return nil, fmt.Errorf(
				"unmarshal next_trains json: %w",
				err,
			)
		}

		arrivals := make(
			[]model.GroupArrival,
			len(trains),
		)

		for i, t := range trains {
			arrivals[i] = model.GroupArrival{
				TrainID:     t.TrainID,
				Line:        t.Line,
				Color:       t.Color,
				ArrivalTime: t.ArrivalTime,
				DestTime:    t.DestTime,
			}
		}

		groups = append(
			groups,
			model.ArrivalGroup{
				Destination: row.RawDest,
				Terminal:    row.DestName,
				Via:         row.ViaName,
				Arrivals:    arrivals,
			},
		)
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf(
			"iterate grouped arrival rows: %w",
			err,
		)
	}

	return groups, nil
}

func GetTrips(
	ctx context.Context,
	pool *pgxpool.Pool,
	fromID string,
	toID string,
	currentSort int,
) ([]model.Trip, error) {
	/*
		Trip lookup intentionally does NOT filter board_visible.

		stop_times now contains the complete physical train route
		from KCI /train-schedule.

		That includes terminal and route-only stops that can be
		absent from the station-board /schedules feed.
	*/
	query := `
		SELECT
			a.train_id,
			TO_CHAR(
				a.arrival_time,
				'HH24:MI:SS'
			) AS depart_time,
			TO_CHAR(
				b.arrival_time,
				'HH24:MI:SS'
			) AS arrive_time,
			b.arrival_sort
				- a.arrival_sort
				AS travel_minutes,
			l.ka_name,
			l.color,
			ds.name AS destination
		FROM stop_times a
		JOIN stop_times b
			ON a.train_id = b.train_id
		JOIN lines l
			ON l.id = a.line_id
		JOIN dest_map dm
			ON dm.raw_dest = a.raw_dest
		JOIN stations ds
			ON ds.code = dm.terminal_station_id
		WHERE a.station_id = $1
		  AND b.station_id = $2
		  AND a.arrival_sort > $3
		  AND b.arrival_sort > a.arrival_sort
		ORDER BY a.arrival_sort
		LIMIT 5
	`

	rows, err := pool.Query(
		ctx,
		query,
		fromID,
		toID,
		currentSort,
	)
	if err != nil {
		return nil, fmt.Errorf(
			"query trips: %w",
			err,
		)
	}
	defer rows.Close()

	return pgx.CollectRows(
		rows,
		func(
			row pgx.CollectableRow,
		) (model.Trip, error) {
			var t model.Trip

			err := row.Scan(
				&t.TrainID,
				&t.DepartTime,
				&t.ArriveTime,
				&t.TravelMinutes,
				&t.Line,
				&t.Color,
				&t.Destination,
			)

			return t, err
		},
	)
}
