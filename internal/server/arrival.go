package server

import (
	"net/http"

	"github.com/fikryfauzn/kommute/internal/db"
	"github.com/fikryfauzn/kommute/internal/model"
)

// maxLineNameLen bounds the optional ?line= filter. The value is only ever
// used as a bound SQL parameter, so this is hygiene, not injection defence.
const maxLineNameLen = 64

func (s *Server) handleArrivals(
	w http.ResponseWriter,
	r *http.Request,
) error {
	stationID := r.PathValue("id")

	if !validStationCode(stationID) {
		return &apiError{
			Status:  http.StatusBadRequest,
			Message: "invalid station code",
		}
	}

	// Optional: restrict the board to one line, by its ka_name, e.g.
	// /api/stations/{id}/arrivals?line=COMMUTER LINE BOGOR
	line := r.URL.Query().Get("line")

	if len(line) > maxLineNameLen {
		return &apiError{
			Status:  http.StatusBadRequest,
			Message: "invalid line name",
		}
	}

	sort := currentSort()
	grouped := r.URL.Query().Get("group") == "true"

	if grouped {
		groups, err := db.GetArrivalsGrouped(
			r.Context(),
			s.pool,
			stationID,
			sort,
		)
		if err != nil {
			return err
		}

		w.Header().Set(
			"Cache-Control",
			"public, max-age=60",
		)

		writeJSON(
			w,
			http.StatusOK,
			model.GroupedArrivalsResponse{
				Station: stationID,
				Groups:  groups,
			},
		)

		return nil
	}

	arrivals, err := db.GetArrivals(
		r.Context(),
		s.pool,
		stationID,
		sort,
		line,
	)
	if err != nil {
		return err
	}

	w.Header().Set(
		"Cache-Control",
		"public, max-age=60",
	)

	writeJSON(
		w,
		http.StatusOK,
		model.ArrivalsResponse{
			Station:  stationID,
			Arrivals: arrivals,
		},
	)

	return nil
}
