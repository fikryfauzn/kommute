package server

import (
	"context"
	"net/http"
	"time"

	"github.com/fikryfauzn/kommute/internal/model"
)

func (s *Server) handleHealth(w http.ResponseWriter, r *http.Request) error {
	ctx, cancel := context.WithTimeout(r.Context(), 2*time.Second)
	defer cancel()

	if err := s.pool.Ping(ctx); err != nil {
		writeJSON(w, http.StatusServiceUnavailable, model.HealthResponse{Status: "unhealthy"})
		return nil
	}

	writeJSON(w, http.StatusOK, model.HealthResponse{Status: "ok"})
	return nil
}
