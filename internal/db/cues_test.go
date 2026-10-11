package db

import "testing"

func TestCuesRespectIntermediateStops(t *testing.T) {
	services := []cueService{
		{trainID: "short", departureTime: "18:15:00", departureSort: 915, line: "C", terminalCode: "TB", terminalName: "TAMBUN", reachable: []string{"TB"}},
		{trainID: "through", departureTime: "18:20:00", departureSort: 920, line: "C", terminalCode: "CKR", terminalName: "CIKARANG", reachable: []string{"TB", "CKR"}},
		{trainID: "late", departureTime: "19:00:00", departureSort: 960, line: "C", terminalCode: "CKR", terminalName: "CIKARANG", reachable: []string{"TB", "CKR"}},
	}
	cues, _ := deriveStationCues(services)
	if len(cues) != 2 {
		t.Fatalf("got %d cues, want 2 (a long wait and a last train): %+v", len(cues), cues)
	}
	if cues[0].TrainID != "late" || !cues[0].LastTrain {
		t.Errorf("final service should be last train: %+v", cues)
	}
	if cues[1].TrainID != "through" || cues[1].NextTime == nil || *cues[1].NextTime != "19:00:00" {
		t.Errorf("through service should have NEXT 19:00: %+v", cues)
	}
	for _, cue := range cues {
		if cue.TrainID == "short" {
			t.Fatal("short terminating service incorrectly labelled last despite through service")
		}
	}
}

func TestCuesDoNotCountTheWrongBranch(t *testing.T) {
	services := []cueService{
		{trainID: "kp", departureTime: "22:29:00", departureSort: 1169, line: "C", terminalCode: "KPB", terminalName: "KAMPUNG BANDAN", reachable: []string{"AK", "KPB"}},
		{trainID: "ak", departureTime: "22:38:00", departureSort: 1178, line: "C", terminalCode: "AK", terminalName: "ANGKE", reachable: []string{"AK"}},
	}
	cues, _ := deriveStationCues(services)
	if len(cues) != 2 || !cues[0].LastTrain || !cues[1].LastTrain {
		t.Errorf("two branches must each have their own last service: %+v", cues)
	}
}

func TestEqualTimeDoesNotCountAsLater(t *testing.T) {
	services := []cueService{
		{trainID: "a", departureTime: "00:15:00", departureSort: 1275, line: "B", terminalCode: "BOO", terminalName: "BOGOR", reachable: []string{"BOO"}},
		{trainID: "b", departureTime: "00:15:00", departureSort: 1275, line: "B", terminalCode: "BOO", terminalName: "BOGOR", reachable: []string{"BOO"}},
	}
	cues, _ := deriveStationCues(services)
	if len(cues) != 2 || !cues[0].LastTrain || !cues[1].LastTrain {
		t.Errorf("simultaneous last trains must not erase each other's cue: %+v", cues)
	}
}

func TestUnverifiedTerminalIsNeverLast(t *testing.T) {
	services := []cueService{{trainID: "unknown", departureTime: "20:00:00", departureSort: 1020, line: "C", terminalCode: "CKR", reachable: []string{"TB"}}}
	cues, _ := deriveStationCues(services)
	if len(cues) != 0 {
		t.Errorf("unverified terminal must not get a false cue: %+v", cues)
	}
}
