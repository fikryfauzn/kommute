package server

import (
	"context"
	"encoding/json"
	"errors"
	"log/slog"
	"net/http"
	"regexp"
	"time"
)

var stationCodeRe = regexp.MustCompile(`^[A-Z]{2,6}$`)

type ctxKey int

const (
	ctxKeyLogger    ctxKey = iota
	ctxKeyRequestID
)

type apiError struct {
	Status  int
	Message string
}

func (e *apiError) Error() string { return e.Message }

type appHandler func(w http.ResponseWriter, r *http.Request) error

func (s *Server) wrap(fn appHandler) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if err := fn(w, r); err != nil {
			var ae *apiError
			if errors.As(err, &ae) {
				writeError(w, ae.Status, ae.Message)
			} else {
				logger := loggerFromCtx(r.Context())
				logger.Error("internal error", "error", err)
				writeError(w, http.StatusInternalServerError, "internal error")
			}
		}
	}
}

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.Header().Set("X-Content-Type-Options", "nosniff")
	w.WriteHeader(status)
	json.NewEncoder(w).Encode(v)
}

func writeError(w http.ResponseWriter, status int, msg string) {
	writeJSON(w, status, map[string]any{"error": msg, "status": status})
}

func validStationCode(code string) bool {
	return stationCodeRe.MatchString(code)
}

func toArrivalSort(hour, min int) int {
	if hour >= 3 {
		return (hour-3)*60 + min
	}
	return (hour+21)*60 + min
}

func currentSort() int {
	now := time.Now().Add(-3 * time.Minute)
	return toArrivalSort(now.Hour(), now.Minute())
}

func loggerFromCtx(ctx context.Context) *slog.Logger {
	if l, ok := ctx.Value(ctxKeyLogger).(*slog.Logger); ok {
		return l
	}
	return slog.Default()
}
