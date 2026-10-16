package config

import (
	"os"
	"path/filepath"
	"testing"
)

func TestConfigDefaultsAndOverride(t *testing.T) {
	path := filepath.Join(t.TempDir(), "client.json")
	cfg, err := Load(path, "")
	if err != nil || cfg.ServerURL != "http://localhost:8000" {
		t.Fatalf("default: %+v %v", cfg, err)
	}
	if err := os.WriteFile(path, []byte(`{"server_url":"https://remote.example/mogobe/","request_timeout_seconds":30}`), 0600); err != nil {
		t.Fatal(err)
	}
	cfg, err = Load(path, "")
	if err != nil || cfg.ServerURL != "https://remote.example/mogobe" || cfg.RequestTimeoutSeconds != 30 {
		t.Fatalf("remote: %+v %v", cfg, err)
	}
	cfg, err = Load(path, "http://localhost:9000")
	if err != nil || cfg.ServerURL != "http://localhost:9000" {
		t.Fatalf("override: %+v %v", cfg, err)
	}
}

func TestMalformedConfigIsRejected(t *testing.T) {
	path := filepath.Join(t.TempDir(), "client.json")
	for _, data := range []string{`{`, `{"server_url":"file:///tmp/a"}`, `{"server_url":"https://u:p@example.com"}`, `{"server_url":"https://example.com/?token=s"}`, `{"request_timeout_seconds":0}`, `{"unknown":true}`, `{} {}`} {
		os.WriteFile(path, []byte(data), 0600)
		if _, err := Load(path, ""); err == nil {
			t.Errorf("accepted %s", data)
		}
	}
}
