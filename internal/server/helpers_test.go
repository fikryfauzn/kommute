package server

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestValidStationCode(t *testing.T) {
	tests := []struct {
		code string
		want bool
	}{
		{"MRI", true},
		{"JAKK", true},
		{"UI", true},
		{"PSMB", true},
		{"ABCDEF", true},
		{"ABCDEFG", false},
		{"A", false},
		{"mri", false},
		{"MR1", false},
		{"", false},
		{"MR I", false},
	}

	for _, tt := range tests {
		t.Run(tt.code, func(t *testing.T) {
			got := validStationCode(tt.code)
			if got != tt.want {
				t.Errorf("validStationCode(%q) = %v, want %v", tt.code, got, tt.want)
			}
		})
	}
}

func TestToArrivalSort(t *testing.T) {
	tests := []struct {
		hour, min int
		want      int
	}{
		{3, 0, 0},
		{5, 30, 150},
		{14, 0, 660},
		{23, 58, 1258},
		{0, 15, 1275},
		{2, 59, 1439},
	}

	for _, tt := range tests {
		got := toArrivalSort(tt.hour, tt.min)
		if got != tt.want {
			t.Errorf("toArrivalSort(%d, %d) = %d, want %d", tt.hour, tt.min, got, tt.want)
		}
	}
}

func TestWriteJSON(t *testing.T) {
	w := httptest.NewRecorder()
	data := map[string]string{"hello": "world"}
	writeJSON(w, http.StatusOK, data)

	if w.Code != http.StatusOK {
		t.Errorf("status = %d, want %d", w.Code, http.StatusOK)
	}
	if ct := w.Header().Get("Content-Type"); ct != "application/json" {
		t.Errorf("Content-Type = %q, want %q", ct, "application/json")
	}
	if nosniff := w.Header().Get("X-Content-Type-Options"); nosniff != "nosniff" {
		t.Errorf("X-Content-Type-Options = %q, want %q", nosniff, "nosniff")
	}

	var got map[string]string
	if err := json.NewDecoder(w.Body).Decode(&got); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if got["hello"] != "world" {
		t.Errorf("body = %v, want hello=world", got)
	}
}

func TestWriteError(t *testing.T) {
	w := httptest.NewRecorder()
	writeError(w, http.StatusBadRequest, "bad input")

	if w.Code != http.StatusBadRequest {
		t.Errorf("status = %d, want %d", w.Code, http.StatusBadRequest)
	}

	var got map[string]any
	if err := json.NewDecoder(w.Body).Decode(&got); err != nil {
		t.Fatalf("decode: %v", err)
	}
	if got["error"] != "bad input" {
		t.Errorf("error = %v, want %q", got["error"], "bad input")
	}
	if got["status"] != float64(400) {
		t.Errorf("status = %v, want 400", got["status"])
	}
}
