package db

import (
	"strings"

	"github.com/fikryfauzn/kommute/internal/model"
)

// Fork directions describe physical outbound branches, not a train's final
// destination. A short-turn service (e.g. Bekasi) is part of its Cikarang
// corridor, but its actual terminal remains visible in the departure row.
// Only these six junctions present TOWARD chips.
type forkSpec struct {
	key, label, via, line string
	nextStops             []string
}

const (
	lineBogor     = "COMMUTER LINE BOGOR"
	lineCikarang  = "COMMUTER LINE CIKARANG"
	lineRangkas   = "COMMUTER LINE RANGKASBITUNG"
	lineTangerang = "COMMUTER LINE TANGERANG"
	linePriuk     = "COMMUTER LINE TANJUNGPRIUK"
)

var forkStations = map[string][]forkSpec{
	"MRI": {
		// Keep B-line directions together in the first row, then C-line.
		{key: "JAKK", label: "JAKARTA KOTA", line: lineBogor, nextStops: []string{"CKI"}},
		{key: "BOO", label: "BOGOR", line: lineBogor, nextStops: []string{"TEB"}},
		{key: "KPB", label: "KAMPUNG BANDAN", line: lineCikarang, nextStops: []string{"SUD"}},
		{key: "CKR", label: "CIKARANG", line: lineCikarang, nextStops: []string{"MTR"}},
	},
	"KPB": {
		{key: "TPK", label: "TANJUNG PRIOK", line: linePriuk, nextStops: []string{"AC"}},
		{key: "JAKK", label: "JAKARTA KOTA", line: linePriuk, nextStops: []string{"JAKK"}},
		{key: "CKR-MRI", label: "CIKARANG", via: "MANGGARAI", line: lineCikarang, nextStops: []string{"AK"}},
		{key: "CKR-PSE", label: "CIKARANG", via: "PASAR SENEN", line: lineCikarang, nextStops: []string{"RJW"}},
	},
	"JNG": {
		{key: "KPB-MRI", label: "KAMPUNG BANDAN", via: "MANGGARAI", line: lineCikarang, nextStops: []string{"MTR", "MRI"}},
		{key: "KPB-PSE", label: "KAMPUNG BANDAN", via: "PASAR SENEN", line: lineCikarang, nextStops: []string{"POK"}},
		{key: "CKR", label: "CIKARANG", line: lineCikarang, nextStops: []string{"KLD"}},
	},
	"CTA": {
		{key: "JAKK", label: "JAKARTA KOTA", line: lineBogor, nextStops: []string{"DP"}},
		{key: "BOO", label: "BOGOR", line: lineBogor, nextStops: []string{"BJD"}},
		{key: "NMO", label: "NAMBO", line: lineBogor, nextStops: []string{"PDRG"}},
	},
	"DU": {
		// C-line pair on top; T-line spans the bottom row.
		{key: "KPB", label: "KAMPUNG BANDAN", line: lineCikarang, nextStops: []string{"AK"}},
		{key: "CKR", label: "CIKARANG", line: lineCikarang, nextStops: []string{"THB"}},
		{key: "TNG", label: "TANGERANG", line: lineTangerang, nextStops: []string{"GGL"}},
	},
	"THB": {
		// C-line pair on top; R-line spans the bottom row.
		{key: "KPB", label: "KAMPUNG BANDAN", line: lineCikarang, nextStops: []string{"DU"}},
		{key: "CKR", label: "CIKARANG", line: lineCikarang, nextStops: []string{"SUDB"}},
		{key: "RK", label: "RANGKASBITUNG", line: lineRangkas, nextStops: []string{"PLM"}},
	},
}

// classifyForkService maps a departure to a stable outward corridor using
// its *next physical stop*, which remains constant even when the service
// terminates early. Its direction does not depend on the next five rows.
func classifyForkService(station string, service cueService) string {
	for _, spec := range forkStations[station] {
		if service.line != spec.line {
			continue
		}
		for _, next := range spec.nextStops {
			if service.nextStation == next {
				return spec.key
			}
		}
	}
	return ""
}

// deriveForkDirections returns the same chip set throughout the day,
// including after a branch's last scheduled departure. Only the first five
// upcoming services per branch are sent to the phone.
func deriveForkDirections(station string, services []cueService, nowSort int) []model.ForkDirection {
	specs, ok := forkStations[station]
	if !ok {
		return []model.ForkDirection{}
	}
	directions := make([]model.ForkDirection, 0, len(specs))
	for _, spec := range specs {
		directions = append(directions, model.ForkDirection{
			Key: spec.key, Label: spec.label, Via: spec.via, Line: spec.line,
			Arrivals: []model.Arrival{},
		})
	}
	for _, service := range services {
		key := classifyForkService(station, service)
		if key == "" {
			continue
		}
		for i := range directions {
			if directions[i].Key != key {
				continue
			}
			direction := &directions[i]
			if direction.Color == "" {
				direction.Color = service.color
			}
			if service.departureSort > direction.LastSort || direction.LastDeparture == "" {
				direction.LastDeparture = service.departureTime
				direction.LastSort = service.departureSort
			}
			if service.departureSort < nowSort || len(direction.Arrivals) >= 5 {
				break
			}
			var via *string
			if strings.TrimSpace(service.viaName) != "" {
				name := service.viaName
				via = &name
			}
			direction.Arrivals = append(direction.Arrivals, model.Arrival{
				TrainID:     service.trainID,
				Line:        service.line,
				Color:       service.color,
				Destination: service.terminalName,
				Via:         via,
				ArrivalTime: service.departureTime,
			})
			break
		}
	}
	// Colors for branches with no trains in this particular snapshot are
	// resolved from the line identity, so their chip stays recognizable.
	for i := range directions {
		if directions[i].Color != "" {
			continue
		}
		switch directions[i].Line {
		case lineBogor:
			directions[i].Color = "#E30A16"
		case lineCikarang:
			directions[i].Color = "#0084D8"
		case lineRangkas:
			directions[i].Color = "#16812B"
		case lineTangerang:
			directions[i].Color = "#623814"
		case linePriuk:
			directions[i].Color = "#DD0067"
		}
	}
	return directions
}
