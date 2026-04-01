package server

import (
	"net/http"

	"github.com/fikryfauzn/kommute/internal/db"
	"github.com/fikryfauzn/kommute/internal/model"
)

func (s *Server) handleStations(w http.ResponseWriter, r *http.Request) error {
	if match := r.Header.Get("If-None-Match"); match == s.dataVersion {
		w.WriteHeader(http.StatusNotModified)
		return nil
	}

	lines, err := db.GetStationsByLine(r.Context(), s.pool)
	if err != nil {
		return err
	}

	w.Header().Set("Cache-Control", "public, max-age=86400")
	w.Header().Set("ETag", s.dataVersion)
	writeJSON(w, http.StatusOK, model.StationsResponse{Lines: lines})
	return nil
}
