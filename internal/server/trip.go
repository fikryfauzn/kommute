package server

import (
	"net/http"

	"github.com/fikryfauzn/kommute/internal/db"
	"github.com/fikryfauzn/kommute/internal/model"
)

func (s *Server) handleTrip(w http.ResponseWriter, r *http.Request) error {
	from := r.URL.Query().Get("from")
	to := r.URL.Query().Get("to")

	if from == "" || to == "" {
		return &apiError{Status: http.StatusBadRequest, Message: "from and to are required"}
	}
	if !validStationCode(from) || !validStationCode(to) {
		return &apiError{Status: http.StatusBadRequest, Message: "invalid station code"}
	}
	if from == to {
		return &apiError{Status: http.StatusBadRequest, Message: "from and to must be different"}
	}

	if match := r.Header.Get("If-None-Match"); match == s.dataVersion {
		w.WriteHeader(http.StatusNotModified)
		return nil
	}

	trips, err := db.GetTrips(r.Context(), s.pool, from, to, currentSort())
	if err != nil {
		return err
	}

	w.Header().Set("Cache-Control", "public, max-age=60")
	w.Header().Set("ETag", s.dataVersion)
	writeJSON(w, http.StatusOK, model.TripResponse{
		From:  from,
		To:    to,
		Trips: trips,
	})
	return nil
}
