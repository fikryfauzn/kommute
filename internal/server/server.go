package server

import (
	"context"
	"log/slog"
	"net/http"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
)

type Server struct {
	pool        *pgxpool.Pool
	logger      *slog.Logger
	mux         *http.ServeMux
	httpServer  *http.Server
	dataVersion string
}

func New(pool *pgxpool.Pool, logger *slog.Logger, port string) *Server {
	s := &Server{
		pool:        pool,
		logger:      logger,
		mux:         http.NewServeMux(),
		dataVersion: "v1",
	}

	s.routes()

	handler := chain(s.mux,
		recoveryMiddleware(logger),
		requestIDMiddleware(logger),
		loggingMiddleware(),
	)

	s.httpServer = &http.Server{
		Addr:         ":" + port,
		Handler:      handler,
		ReadTimeout:  5 * time.Second,
		WriteTimeout: 10 * time.Second,
		IdleTimeout:  120 * time.Second,
	}

	return s
}

func (s *Server) routes() {
	s.mux.HandleFunc("GET /api/stations", s.wrap(s.handleStations))
	s.mux.HandleFunc("GET /api/stations/{id}/arrivals", s.wrap(s.handleArrivals))
	s.mux.HandleFunc("GET /api/trip", s.wrap(s.handleTrip))
	s.mux.HandleFunc("GET /health", s.wrap(s.handleHealth))
	s.mux.Handle("/", http.FileServer(http.Dir("web/static")))
}

func (s *Server) Start() error {
	s.logger.Info("server starting", "addr", s.httpServer.Addr)
	return s.httpServer.ListenAndServe()
}

func (s *Server) Shutdown(ctx context.Context) error {
	s.logger.Info("server shutting down")
	return s.httpServer.Shutdown(ctx)
}
