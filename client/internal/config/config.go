package config

import (
	"encoding/json"
	"fmt"
	"io"
	"net/url"
	"os"
	"path/filepath"
	"strings"
)

type Config struct {
	ServerURL             string `json:"server_url"`
	RequestTimeoutSeconds int    `json:"request_timeout_seconds"`
}

func Load(path, override string) (Config, error) {
	cfg := Config{ServerURL: "http://localhost:8000", RequestTimeoutSeconds: 15}
	f, err := os.Open(path)
	if err == nil {
		defer f.Close()
		decoder := json.NewDecoder(io.LimitReader(f, 64*1024))
		decoder.DisallowUnknownFields()
		if err = decoder.Decode(&cfg); err != nil {
			return cfg, fmt.Errorf("client.json: %w", err)
		}
		var trailing any
		if err = decoder.Decode(&trailing); err != io.EOF {
			return cfg, fmt.Errorf("client.json: unexpected trailing content")
		}
	} else if !os.IsNotExist(err) {
		return cfg, err
	}
	if override != "" {
		cfg.ServerURL = override
	}
	cfg.ServerURL = strings.TrimRight(cfg.ServerURL, "/")
	u, err := url.Parse(cfg.ServerURL)
	if err != nil || u == nil || u.Hostname() == "" || (u.Scheme != "http" && u.Scheme != "https") || u.User != nil || u.RawQuery != "" || u.Fragment != "" {
		return cfg, fmt.Errorf("server_url must be an http:// or https:// URL without credentials, query or fragment")
	}
	if cfg.RequestTimeoutSeconds < 1 || cfg.RequestTimeoutSeconds > 120 {
		return cfg, fmt.Errorf("request_timeout_seconds must be 1..120")
	}
	return cfg, nil
}

func DefaultPath() string {
	// Portable builds look next to the EXE, independent of the working directory.
	exe, err := os.Executable()
	if err == nil {
		return filepath.Join(filepath.Dir(exe), "client.json")
	}
	return "client.json"
}
