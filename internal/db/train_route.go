package db

import (
	"context"
	"fmt"

	"github.com/jackc/pgx/v5/pgxpool"
)

// RouteStop is one stop on the selected train, beginning at the station
// whose departure appears on Kommute's board.
type RouteStop struct {
	Code string `json:"code"`
	Name string `json:"name"`
	Time string `json:"time"`
}

// GetTrainRoute returns the remaining physical stops for a board-visible
// train at the given station. It never invents intermediary station times.
func GetTrainRoute(ctx context.Context, pool *pgxpool.Pool, station, train string) ([]RouteStop, error) {
	const sql = `
        SELECT st.station_id, s.name, TO_CHAR(st.arrival_time, 'HH24:MI')
        FROM stop_times st
        JOIN stations s ON s.code = st.station_id
        WHERE st.train_id = $1
          AND st.arrival_sort >= (
              SELECT arrival_sort
              FROM stop_times
              WHERE train_id = $1
                AND station_id = $2
                AND board_visible = TRUE
              ORDER BY arrival_sort
              LIMIT 1
          )
        ORDER BY st.arrival_sort, st.id
    `
	rows, err := pool.Query(ctx, sql, train, station)
	if err != nil {
		return nil, fmt.Errorf("query train route: %w", err)
	}
	defer rows.Close()
	stops := make([]RouteStop, 0, 32)
	for rows.Next() {
		var stop RouteStop
		if err := rows.Scan(&stop.Code, &stop.Name, &stop.Time); err != nil {
			return nil, fmt.Errorf("scan train stop: %w", err)
		}
		stops = append(stops, stop)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate train route: %w", err)
	}
	return stops, nil
}
