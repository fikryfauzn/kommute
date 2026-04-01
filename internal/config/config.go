package config

import (
	"fmt"
	"os"
)

type Config struct {
	Port string
	DSN  string
	Env  string
}

func Load() (Config, error) {
	dsn := os.Getenv("DB_DSN")
	if dsn == "" {
		return Config{}, fmt.Errorf("DB_DSN is required")
	}

	return Config{
		Port: envOr("PORT", "8080"),
		DSN:  dsn,
		Env:  envOr("ENV", "development"),
	}, nil
}

func envOr(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
