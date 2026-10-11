package server

import (
	"net/http"
	"regexp"

	"github.com/fikryfauzn/kommute/internal/db"
)

var trainCodePattern = regexp.MustCompile(`^[A-Za-z0-9-]{1,10}$`)

func (s *Server) handleTrainRoute(w http.ResponseWriter, r *http.Request) error {
	station := r.PathValue("id")
	train := r.PathValue("train")
	if !validStationCode(station) || !trainCodePattern.MatchString(train) {
		return &apiError{Status: http.StatusBadRequest, Message: "invalid station or train code"}
	}
	stops, err := db.GetTrainRoute(r.Context(), s.pool, station, train)
	if err != nil {
		return err
	}
	if len(stops) == 0 {
		return &apiError{Status: http.StatusNotFound, Message: "train route not found"}
	}
	w.Header().Set("Cache-Control", "public, max-age=600")
	writeJSON(w, http.StatusOK, map[string]any{
		"train_id": train,
		"station":  station,
		"stops":    stops,
	})
	return nil
}
