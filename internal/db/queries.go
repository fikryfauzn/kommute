package db

import (
	"context"
	"encoding/json"
	"fmt"

	
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/fikryfauzn/kommute/internal/model"
)

func GetStationsByLine(ctx context.Context, pool *pgxpool.Pool) ([]model.Line, error) {
	query := `
		SELECT l.ka_name, l.color,
		       json_agg(
		         json_build_object('code', s.code, 'name', s.name)
		         ORDER BY s.name
		       ) AS stations
		FROM lines l
		JOIN station_lines sl ON sl.line_id = l.id
		JOIN stations s ON s.code = sl.station_id
		GROUP BY l.id, l.ka_name, l.color
		ORDER BY l.ka_name`

	rows, err := pool.Query(ctx, query)
	if err != nil {
		return nil, fmt.Errorf("query stations by line: %w", err)
	}
	defer rows.Close()

	var lines []model.Line
	for rows.Next() {
		var row model.LineRow
		if err := rows.Scan(&row.Name, &row.Color, &row.Stations); err != nil {
			return nil, fmt.Errorf("scan station line row: %w", err)
		}

		var stations []model.StationInfo
		if err := json.Unmarshal(row.Stations, &stations); err != nil {
			return nil, fmt.Errorf("unmarshal stations json: %w", err)
		}

		lines = append(lines, model.Line{
			Name:     row.Name,
			Color:    row.Color,
			Stations: stations,
		})
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate station rows: %w", err)
	}

	return lines, nil
}

func GetArrivals(ctx context.Context, pool *pgxpool.Pool, stationID string, currentSort int) ([]model.Arrival, error) {
	query := `
		SELECT st.train_id,
		       TO_CHAR(st.arrival_time, 'HH24:MI:SS'),
		       TO_CHAR(st.dest_time, 'HH24:MI:SS'),
		       l.ka_name, l.color,
		       ts.name AS dest_name,
		       vs.code AS via_name
		FROM stop_times st
		JOIN lines l ON l.id = st.line_id
		JOIN dest_map dm ON dm.raw_dest = st.raw_dest
		JOIN stations ts ON ts.code = dm.terminal_station_id
		LEFT JOIN stations vs ON vs.code = dm.via_station_id
		WHERE st.station_id = $1
		  AND st.arrival_sort > $2
		ORDER BY st.arrival_sort
		LIMIT 5`

	rows, err := pool.Query(ctx, query, stationID, currentSort)
	if err != nil {
		return nil, fmt.Errorf("query arrivals: %w", err)
	}
	defer rows.Close()

	return pgx.CollectRows(rows, func(row pgx.CollectableRow) (model.Arrival, error) {
		var a model.Arrival
		err := row.Scan(
			&a.TrainID, &a.ArrivalTime, &a.DestTime,
			&a.Line, &a.Color,
			&a.Destination, &a.Via,
		)
		return a, err
	})
}

func GetArrivalsGrouped(ctx context.Context, pool *pgxpool.Pool, stationID string, currentSort int) ([]model.ArrivalGroup, error) {
	query := `
		SELECT st.raw_dest, ts.name AS dest_name,
		       vs.name AS via_name,
		       json_agg(
		         json_build_object(
		           'train_id', st.train_id,
		           'line', l.ka_name,
		           'color', l.color,
		           'arrival_time', st.arrival_time,
		           'dest_time', st.dest_time,
		           'route_name', st.route_name
		         ) ORDER BY st.arrival_sort
		       ) AS next_trains
		FROM (
		  SELECT *, ROW_NUMBER() OVER (
		    PARTITION BY raw_dest ORDER BY arrival_sort
		  ) AS rn
		  FROM stop_times
		  WHERE station_id = $1
		    AND arrival_sort > $2
		) st
		JOIN lines l ON l.id = st.line_id
		JOIN dest_map dm ON dm.raw_dest = st.raw_dest
		JOIN stations ts ON ts.code = dm.terminal_station_id
		LEFT JOIN stations vs ON vs.code = dm.via_station_id
		WHERE rn <= 3
		GROUP BY st.raw_dest, dm.terminal_station_id, ts.name, dm.via_station_id, vs.name
		ORDER BY MIN(st.arrival_sort)`

	rows, err := pool.Query(ctx, query, stationID, currentSort)
	if err != nil {
		return nil, fmt.Errorf("query grouped arrivals: %w", err)
	}
	defer rows.Close()

	var groups []model.ArrivalGroup
	for rows.Next() {
		var row model.GroupedArrivalRow
		if err := rows.Scan(&row.RawDest, &row.DestName, &row.ViaName, &row.NextTrains); err != nil {
			return nil, fmt.Errorf("scan grouped arrival row: %w", err)
		}

		var trains []model.GroupedTrainJSON
		if err := json.Unmarshal(row.NextTrains, &trains); err != nil {
			return nil, fmt.Errorf("unmarshal next_trains json: %w", err)
		}

		arrivals := make([]model.GroupArrival, len(trains))
		for i, t := range trains {
			arrivals[i] = model.GroupArrival{
				TrainID:     t.TrainID,
				Line:        t.Line,
				Color:       t.Color,
				ArrivalTime: t.ArrivalTime,
				DestTime:    t.DestTime,
			}
		}

		groups = append(groups, model.ArrivalGroup{
			Destination: row.RawDest,
			Terminal:    row.DestName,
			Via:         row.ViaName,
			Arrivals:    arrivals,
		})
	}

	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate grouped arrival rows: %w", err)
	}

	return groups, nil
}

func GetTrips(ctx context.Context, pool *pgxpool.Pool, fromID, toID string, currentSort int) ([]model.Trip, error) {
	query := `
		SELECT a.train_id,
		       TO_CHAR(a.arrival_time, 'HH24:MI:SS') AS depart_time,
		       TO_CHAR(b.arrival_time, 'HH24:MI:SS') AS arrive_time,
		       b.arrival_sort - a.arrival_sort AS travel_minutes,
		       l.ka_name, l.color,
		       ds.name AS destination
		FROM stop_times a
		JOIN stop_times b ON a.train_id = b.train_id
		JOIN lines l ON l.id = a.line_id
		JOIN dest_map dm ON dm.raw_dest = a.raw_dest
		JOIN stations ds ON ds.code = dm.terminal_station_id
		WHERE a.station_id = $1
		  AND b.station_id = $2
		  AND a.arrival_sort > $3
		  AND b.arrival_sort > a.arrival_sort
		ORDER BY a.arrival_sort
		LIMIT 5`

	rows, err := pool.Query(ctx, query, fromID, toID, currentSort)
	if err != nil {
		return nil, fmt.Errorf("query trips: %w", err)
	}
	defer rows.Close()

	return pgx.CollectRows(rows, func(row pgx.CollectableRow) (model.Trip, error) {
		var t model.Trip
		err := row.Scan(
			&t.TrainID, &t.DepartTime, &t.ArriveTime,
			&t.TravelMinutes,
			&t.Line, &t.Color,
			&t.Destination,
		)
		return t, err
	})
}
