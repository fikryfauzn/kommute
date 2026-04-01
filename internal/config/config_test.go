package config

import (
	"os"
	"testing"
)

func TestLoad_AllSet(t *testing.T) {
	t.Setenv("PORT", "9090")
	t.Setenv("DB_DSN", "postgres://test@localhost/test")
	t.Setenv("ENV", "production")

	cfg, err := Load()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if cfg.Port != "9090" {
		t.Errorf("Port = %q, want %q", cfg.Port, "9090")
	}
	if cfg.DSN != "postgres://test@localhost/test" {
		t.Errorf("DSN = %q, want %q", cfg.DSN, "postgres://test@localhost/test")
	}
	if cfg.Env != "production" {
		t.Errorf("Env = %q, want %q", cfg.Env, "production")
	}
}

func TestLoad_Defaults(t *testing.T) {
	t.Setenv("DB_DSN", "postgres://test@localhost/test")
	os.Unsetenv("PORT")
	os.Unsetenv("ENV")

	cfg, err := Load()
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if cfg.Port != "8080" {
		t.Errorf("Port = %q, want %q", cfg.Port, "8080")
	}
	if cfg.Env != "development" {
		t.Errorf("Env = %q, want %q", cfg.Env, "development")
	}
}

func TestLoad_MissingDSN(t *testing.T) {
	os.Unsetenv("DB_DSN")

	_, err := Load()
	if err == nil {
		t.Fatal("expected error for missing DB_DSN, got nil")
	}
}
