package db

import (
	"context"
	"fmt"
	"sort"

	"github.com/fikryfauzn/kommute/internal/model"
	"github.com/jackc/pgx/v5/pgxpool"
)

const nextCueMinimumGap = 30 // minutes, matching the reference's long-wait cues

type cueService struct {
	trainID       string
	departureTime string
	departureSort int
	line          string
	color         string
	nextStation   string
	terminalCode  string
	terminalName  string
	viaName       string
	reachable     []string // terminal station codes this train reaches *after* departure
}

// GetStationCues reads the full operational-day schedule. The five-row
// arrival APIs cannot determine whether a train is the last usable service.
func GetStationCues(ctx context.Context, pool *pgxpool.Pool, stationID string, nowSort int) (model.StationCuesResponse, error) {
	result := model.StationCuesResponse{
		Station:    stationID,
		Cues:       []model.DepartureCue{},
		Directions: []model.DirectionHistory{},
		Forks:      []model.ForkDirection{},
	}

	// Only use regularly served lines, consistent with the existing board APIs.
	// Include downstream physical stops (board_visible may be false there),
	// otherwise a train passing through a destination would be misclassified.
	const query = `
		WITH active_lines AS (
			SELECT line_id
			FROM stop_times
			WHERE station_id = $1 AND board_visible = TRUE
			GROUP BY line_id
			HAVING COUNT(DISTINCT train_id) >= 4
		), station_services AS (
			SELECT st.train_id, st.arrival_sort,
				TO_CHAR(st.arrival_time, 'HH24:MI:SS') AS departure_time,
				l.ka_name AS line_name,
                l.color AS line_color,
                COALESCE((
                    SELECT next_stop.station_id
                    FROM stop_times next_stop
                    WHERE next_stop.train_id = st.train_id
                      AND next_stop.arrival_sort > st.arrival_sort
                    ORDER BY next_stop.arrival_sort
                    LIMIT 1
                ), '') AS next_station,
				dm.terminal_station_id AS terminal_code,
				ts.name AS terminal_name,
				COALESCE(vs.name, '') AS via_name
			FROM stop_times st
			JOIN active_lines al ON al.line_id = st.line_id
			JOIN lines l ON l.id = st.line_id
			JOIN dest_map dm ON dm.raw_dest = st.raw_dest
			JOIN stations ts ON ts.code = dm.terminal_station_id
			LEFT JOIN stations vs ON vs.code = dm.via_station_id
			WHERE st.station_id = $1 AND st.board_visible = TRUE
		), targets AS (
			SELECT DISTINCT terminal_code FROM station_services
		)
		SELECT s.train_id, s.departure_time, s.arrival_sort,
			s.line_name, s.line_color, s.next_station,
            s.terminal_code, s.terminal_name, s.via_name,
			COALESCE(
				ARRAY_AGG(DISTINCT downstream.station_id)
					FILTER (WHERE downstream.station_id IS NOT NULL),
				ARRAY[]::varchar[]
			) AS reachable
		FROM station_services s
		LEFT JOIN stop_times downstream
			ON downstream.train_id = s.train_id
			AND downstream.arrival_sort > s.arrival_sort
			AND downstream.station_id IN (SELECT terminal_code FROM targets)
		GROUP BY s.train_id, s.departure_time, s.arrival_sort,
			s.line_name, s.line_color, s.next_station,
            s.terminal_code, s.terminal_name, s.via_name
		ORDER BY s.arrival_sort, s.train_id
	`

	rows, err := pool.Query(ctx, query, stationID)
	if err != nil {
		return result, fmt.Errorf("query full-day station cues: %w", err)
	}
	defer rows.Close()

	var services []cueService
	for rows.Next() {
		var s cueService
		if err := rows.Scan(&s.trainID, &s.departureTime, &s.departureSort,
			&s.line, &s.color, &s.nextStation,
			&s.terminalCode, &s.terminalName, &s.viaName, &s.reachable); err != nil {
			return result, fmt.Errorf("scan station cue: %w", err)
		}
		services = append(services, s)
	}
	if err := rows.Err(); err != nil {
		return result, fmt.Errorf("iterate station cues: %w", err)
	}

	result.Cues, result.Directions = deriveStationCues(services)
	result.Forks = deriveForkDirections(stationID, services, nowSort)
	return result, nil
}

type nextService struct {
	trainID string
	sort    int
	time    string
}

// deriveStationCues works backwards through the whole service day. A later
// service counts only if its physical stop list includes the earlier train's
// destination terminal *after* leaving this station.
func deriveStationCues(services []cueService) ([]model.DepartureCue, []model.DirectionHistory) {
	cues := make([]model.DepartureCue, 0)
	histories := make(map[string]model.DirectionHistory)

	for _, s := range services {
		key := s.line + "\x00" + s.terminalCode + "\x00" + s.viaName
		last, exists := histories[key]
		if !exists || s.departureSort > last.LastSort {
			histories[key] = model.DirectionHistory{
				Line: s.line, Terminal: s.terminalName, Via: s.viaName,
				LastDeparture: s.departureTime, LastSort: s.departureSort,
			}
		}
	}

	nextByTerminal := make(map[string]nextService)
	for end := len(services); end > 0; {
		start := end - 1
		for start > 0 && services[start-1].departureSort == services[end-1].departureSort {
			start--
		}

		// Examine the equal-time group before adding any of its services.
		for i := start; i < end; i++ {
			s := services[i]
			if !containsTerminal(s.reachable, s.terminalCode) {
				continue // not verified as a direct service to its stated terminal
			}

			cue := model.DepartureCue{
				TrainID: s.trainID, DepartureTime: s.departureTime,
			}
			if next, ok := nextByTerminal[s.terminalCode]; ok {
				if next.sort-s.departureSort >= nextCueMinimumGap {
					t := next.time
					cue.NextTime = &t
					cue.NextTrainID = next.trainID
				}
			} else {
				cue.LastTrain = true
			}
			if cue.LastTrain || cue.NextTime != nil {
				cues = append(cues, cue)
			}
		}

		for i := start; i < end; i++ {
			s := services[i]
			for _, terminal := range s.reachable {
				nextByTerminal[terminal] = nextService{
					sort: s.departureSort, time: s.departureTime, trainID: s.trainID,
				}
			}
		}
		end = start
	}

	directions := make([]model.DirectionHistory, 0, len(histories))
	for _, history := range histories {
		directions = append(directions, history)
	}
	sort.Slice(directions, func(i, j int) bool {
		if directions[i].LastSort != directions[j].LastSort {
			return directions[i].LastSort > directions[j].LastSort
		}
		if directions[i].Terminal != directions[j].Terminal {
			return directions[i].Terminal < directions[j].Terminal
		}
		return directions[i].Line < directions[j].Line
	})
	return cues, directions
}

func containsTerminal(reachable []string, destination string) bool {
	for _, code := range reachable {
		if code == destination {
			return true
		}
	}
	return false
}
