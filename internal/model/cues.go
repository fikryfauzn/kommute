package model

// DepartureCue describes the next usable service toward the actual terminal
// of a train, not just the next train with an identical destination label.
// The schedule is daily; these values are not live vehicle positions.
type DepartureCue struct {
	TrainID       string  `json:"train_id"`
	DepartureTime string  `json:"departure_time"`
	LastTrain     bool    `json:"last_train"`
	NextTime      *string `json:"next_time,omitempty"`
	NextTrainID   string  `json:"next_train_id,omitempty"`
}

// DirectionHistory keeps the last scheduled departure available even when
// there are no longer any upcoming trains in a grouped-departures response.
type DirectionHistory struct {
	Line          string `json:"line"`
	Terminal      string `json:"terminal"`
	Via           string `json:"via"`
	LastDeparture string `json:"last_departure"`
	LastSort      int    `json:"last_sort"`
}

// ForkDirection is a stable outward branch available only at the six
// recognized junction stations. Arrivals retain each service's real terminal.
type ForkDirection struct {
	Key           string    `json:"key"`
	Label         string    `json:"label"`
	Via           string    `json:"via,omitempty"`
	Line          string    `json:"line"`
	Color         string    `json:"color"`
	Arrivals      []Arrival `json:"arrivals"`
	LastDeparture string    `json:"last_departure,omitempty"`
	LastSort      int       `json:"last_sort"`
}

type StationCuesResponse struct {
	Station    string             `json:"station"`
	Cues       []DepartureCue     `json:"cues"`
	Directions []DirectionHistory `json:"directions"`
	Forks      []ForkDirection    `json:"forks"`
}
