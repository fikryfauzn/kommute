package server

import (
	"net/http"

	"github.com/fikryfauzn/kommute/internal/db"
	"github.com/fikryfauzn/kommute/internal/model"
)

func (s *Server) handleStations(
	w http.ResponseWriter,
	r *http.Request,
) error {
	lines, err := db.GetStationsByLine(
		r.Context(),
		s.pool,
	)
	if err != nil {
		return err
	}

	w.Header().Set(
		"Cache-Control",
		"public, max-age=300",
	)

	writeJSON(
		w,
		http.StatusOK,
		model.StationsResponse{
			Lines: lines,
		},
	)

	return nil
}
