package db

import (
	"testing"
)

func TestOnlyNamedJunctionsGetDirections(t *testing.T) {
	want := map[string]int{"MRI": 4, "KPB": 4, "JNG": 3, "CTA": 3, "DU": 3, "THB": 3}
	for station, expected := range want {
		got := deriveForkDirections(station, nil, 600)
		if len(got) != expected {
			t.Errorf("%s: got %d directions, want %d", station, len(got), expected)
		}
	}
	for _, station := range []string{"AK", "BKST", "JAKK", "AC", "BKS", "BOO", "TEB", "CKR"} {
		if got := deriveForkDirections(station, nil, 600); len(got) != 0 {
			t.Errorf("%s incorrectly has %d direction chips", station, len(got))
		}
	}
}

func TestForkClassificationUsesPhysicalNextStop(t *testing.T) {
	cases := []struct{ station, line, next, want string }{
		{"MRI", lineCikarang, "MTR", "CKR"},
		{"MRI", lineCikarang, "SUD", "KPB"},
		{"MRI", lineBogor, "CKI", "JAKK"},
		{"KPB", lineCikarang, "AK", "CKR-MRI"},
		{"KPB", lineCikarang, "RJW", "CKR-PSE"},
		{"KPB", linePriuk, "AC", "TPK"},
		{"JNG", lineCikarang, "MTR", "KPB-MRI"},
		{"JNG", lineCikarang, "POK", "KPB-PSE"},
		{"JNG", lineCikarang, "KLD", "CKR"},
		{"CTA", lineBogor, "PDRG", "NMO"},
		{"DU", lineTangerang, "GGL", "TNG"},
		{"DU", lineCikarang, "THB", "CKR"},
		{"THB", lineRangkas, "PLM", "RK"},
		{"THB", lineCikarang, "DU", "KPB"},
		{"THB", lineCikarang, "SUDB", "CKR"},
		{"AK", lineCikarang, "DU", ""},
		{"JAKK", lineCikarang, "KPB", ""},
	}
	for _, c := range cases {
		service := cueService{line: c.line, nextStation: c.next, terminalName: "BEKASI"}
		got := classifyForkService(c.station, service)
		if got != c.want {
			t.Errorf("%s %s -> %s: got %q want %q", c.station, c.line, c.next, got, c.want)
		}
	}
}

func TestForkDirectionsIncludeShortTurnAndCapAtFive(t *testing.T) {
	var services []cueService
	for i := 0; i < 8; i++ {
		services = append(services, cueService{
			trainID: string(rune('A' + i)), line: lineCikarang, color: "#0084D8",
			nextStation: "MTR", terminalName: "BEKASI", terminalCode: "BKS",
			departureTime: "07:00:00", departureSort: 240 + i,
		})
	}
	dirs := deriveForkDirections("MRI", services, 243)
	if len(dirs) != 4 {
		t.Fatalf("got %d directions", len(dirs))
	}
	c := dirs[3]
	if c.Key != "CKR" || len(c.Arrivals) != 5 {
		t.Fatalf("got %+v", c)
	}
	if c.Arrivals[0].Destination != "BEKASI" {
		t.Fatalf("short turn lost actual destination: %+v", c.Arrivals[0])
	}
	if c.LastSort != 247 {
		t.Fatalf("last service sort got %d want 247", c.LastSort)
	}
}

// TestForkDirectionVisualOrder protects the two-column chip composition.
// For three directions, the third chip spans the second row. On mixed-line
// junctions, that third chip must not split a same-line pair.
func TestForkDirectionVisualOrder(t *testing.T) {
	cases := map[string][]string{
		"MRI": {"JAKK", "BOO", "KPB", "CKR"},         // B B / C C
		"KPB": {"TPK", "JAKK", "CKR-MRI", "CKR-PSE"}, // P P / C C
		"JNG": {"KPB-MRI", "KPB-PSE", "CKR"},         // C C / C
		"CTA": {"JAKK", "BOO", "NMO"},                // B B / B
		"DU":  {"KPB", "CKR", "TNG"},                 // C C / T
		"THB": {"KPB", "CKR", "RK"},                  // C C / R
	}
	for station, expected := range cases {
		t.Run(station, func(t *testing.T) {
			got := deriveForkDirections(station, nil, 600)
			if len(got) != len(expected) {
				t.Fatalf("got %d chips, want %d", len(got), len(expected))
			}
			for i, key := range expected {
				if got[i].Key != key {
					t.Errorf("position %d: got %q, want %q", i, got[i].Key, key)
				}
			}
		})
	}
}
