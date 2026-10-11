package server

import (
	"net/http"

	"github.com/fikryfauzn/kommute/internal/db"
)

func (s *Server) handleStationCues(w http.ResponseWriter, r *http.Request) error {
	stationID := r.PathValue("id")
	if !validStationCode(stationID) {
		return &apiError{
			Status:  http.StatusBadRequest,
			Message: "invalid station code",
		}
	}

	cues, err := db.GetStationCues(r.Context(), s.pool, stationID, currentSort())
	if err != nil {
		return err
	}

	// Times are scheduled data. Clients refresh for the new service day.
	w.Header().Set("Cache-Control", "public, max-age=60")
	writeJSON(w, http.StatusOK, cues)
	return nil
}
