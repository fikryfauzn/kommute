package server

import (
	"net/http"

	"github.com/fikryfauzn/kommute/internal/db"
	"github.com/fikryfauzn/kommute/internal/model"
)

func (s *Server) handleArrivals(w http.ResponseWriter, r *http.Request) error {
	stationID := r.PathValue("id")
	if !validStationCode(stationID) {
		return &apiError{Status: http.StatusBadRequest, Message: "invalid station code"}
	}

	if match := r.Header.Get("If-None-Match"); match == s.dataVersion {
		w.WriteHeader(http.StatusNotModified)
		return nil
	}

	sort := currentSort()
	grouped := r.URL.Query().Get("group") == "true"

	if grouped {
		groups, err := db.GetArrivalsGrouped(r.Context(), s.pool, stationID, sort)
		if err != nil {
			return err
		}

		w.Header().Set("Cache-Control", "public, max-age=60")
		w.Header().Set("ETag", s.dataVersion)
		writeJSON(w, http.StatusOK, model.GroupedArrivalsResponse{
			Station: stationID,
			Groups:  groups,
		})
		return nil
	}

	arrivals, err := db.GetArrivals(r.Context(), s.pool, stationID, sort)
	if err != nil {
		return err
	}

	w.Header().Set("Cache-Control", "public, max-age=60")
	w.Header().Set("ETag", s.dataVersion)
	writeJSON(w, http.StatusOK, model.ArrivalsResponse{
		Station:  stationID,
		Arrivals: arrivals,
	})
	return nil
}
