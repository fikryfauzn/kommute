package model

import "encoding/json"

// StationInfo is a station code + name pair used in list responses.
type StationInfo struct {
	Code string `json:"code"`
	Name string `json:"name"`
}

// Line is a KRL line with its stations. Used by GET /api/stations.
type Line struct {
	Name     string        `json:"name"`
	Color    string        `json:"color"`
	Stations []StationInfo `json:"stations"`
}

// StationsResponse is the response for GET /api/stations.
type StationsResponse struct {
	Lines []Line `json:"lines"`
}

// Arrival is a single train arrival. Used by GET /api/stations/{id}/arrivals.
type Arrival struct {
	TrainID     string  `json:"train_id"`
	Line        string  `json:"line"`
	Color       string  `json:"color"`
	Destination string  `json:"destination"`
	Via         *string `json:"via"`
	ArrivalTime string  `json:"arrival_time"`
	DestTime    string  `json:"dest_time"`
}

// ArrivalsResponse is the response for GET /api/stations/{id}/arrivals (flat).
type ArrivalsResponse struct {
	Station  string    `json:"station"`
	Arrivals []Arrival `json:"arrivals"`
}

// GroupArrival is a train within a grouped arrival.
type GroupArrival struct {
	TrainID     string `json:"train_id"`
	Line        string `json:"line"`
	Color       string `json:"color"`
	ArrivalTime string `json:"arrival_time"`
	DestTime    string `json:"dest_time"`
}

// ArrivalGroup is a destination group with its next trains.
type ArrivalGroup struct {
	Destination string         `json:"destination"`
	Terminal    string         `json:"terminal"`
	Via         *string        `json:"via"`
	Arrivals    []GroupArrival `json:"arrivals"`
}

// GroupedArrivalsResponse is the response for GET /api/stations/{id}/arrivals?group=true.
type GroupedArrivalsResponse struct {
	Station string         `json:"station"`
	Groups  []ArrivalGroup `json:"groups"`
}

// Trip is a single trip between two stations. Used by GET /api/trip.
type Trip struct {
	TrainID       string `json:"train_id"`
	Line          string `json:"line"`
	Color         string `json:"color"`
	Destination   string `json:"destination"`
	DepartTime    string `json:"depart_time"`
	ArriveTime    string `json:"arrive_time"`
	TravelMinutes int    `json:"travel_minutes"`
}

// TripResponse is the response for GET /api/trip.
type TripResponse struct {
	From  string `json:"from"`
	To    string `json:"to"`
	Trips []Trip `json:"trips"`
}

// HealthResponse is the response for GET /health.
type HealthResponse struct {
	Status string `json:"status"`
}

// LineRow is the DB scan target for the stations-by-line query.
type LineRow struct {
	Name     string          `db:"ka_name"`
	Color    string          `db:"color"`
	Stations json.RawMessage `db:"stations"`
}

// GroupedArrivalRow is the DB scan target for the grouped arrivals query.
type GroupedArrivalRow struct {
	RawDest    string          `db:"raw_dest"`
	DestName   string          `db:"dest_name"`
	ViaName    *string         `db:"via_name"`
	NextTrains json.RawMessage `db:"next_trains"`
}

// GroupedTrainJSON is the shape of each object inside the json_agg next_trains array.
type GroupedTrainJSON struct {
	TrainID     string `json:"train_id"`
	Line        string `json:"line"`
	Color       string `json:"color"`
	ArrivalTime string `json:"arrival_time"`
	DestTime    string `json:"dest_time"`
	RouteName   string `json:"route_name"`
}
