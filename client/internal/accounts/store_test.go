package accounts

import (
	"bytes"
	"fmt"
	"os"
	"path/filepath"
	"testing"
)

func TestEncryptedPersistenceAndServerBinding(t *testing.T) {
	path := filepath.Join(t.TempDir(), "accounts.dat")
	s, err := Open(path, "https://one.example")
	if err != nil {
		t.Fatal(err)
	}
	if _, err = s.Remember("Могобик12", 12, "long-private-session-token", true, true); err != nil {
		t.Fatal(err)
	}
	data, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	if bytes.Contains(data, []byte("long-private-session-token")) || bytes.Contains(data, []byte("Могобик12")) {
		t.Fatal("unencrypted account file")
	}
	s, err = Open(path, "https://one.example")
	if err != nil {
		t.Fatal(err)
	}
	if s.Token("могобик12") != "long-private-session-token" || s.List()[0].ColorID != 12 {
		t.Fatal("account did not survive restart")
	}
	if _, err = Open(path, "https://other.example"); err == nil {
		t.Fatal("session can be moved to another server")
	}
}

func TestSixAccountsMRUForgetAndNamesOnly(t *testing.T) {
	s, err := Open(filepath.Join(t.TempDir(), "accounts.dat"), "http://localhost:8000")
	if err != nil {
		t.Fatal(err)
	}
	for i := 1; i <= 7; i++ {
		removed, err := s.Remember(fmt.Sprintf("Mogo%d", i), i, fmt.Sprintf("token-%d", i), true, true)
		if err != nil {
			t.Fatal(err)
		}
		if i == 7 && (len(removed) != 1 || removed[0] != "token-1") {
			t.Fatal("oldest token not evicted", removed)
		}
	}
	if len(s.List()) != 6 || s.List()[0].Username != "Mogo7" {
		t.Fatal(s.List())
	}
	removed, err := s.Remember("mogo3", 3, "replacement-token", true, true)
	if err != nil || len(removed) != 1 || removed[0] != "token-3" || s.List()[0].Username != "mogo3" || len(s.List()) != 6 {
		t.Fatal("duplicate account or wrong ordering", removed, err)
	}
	if err = s.ClearToken("replacement-token"); err != nil {
		t.Fatal(err)
	}
	if s.List()[0].HasSession || s.Token("Mogo7") != "token-7" {
		t.Fatal("logout affected another account")
	}
	removed, err = s.KeepNames([]string{"Mogo7", "Mogo6"})
	if err != nil || len(s.List()) != 2 || len(removed) != 3 {
		t.Fatal("forget failed", removed, err)
	}
	if _, err = s.Remember("Mogo7", 7, "new-token", true, false); err != nil {
		t.Fatal(err)
	}
	if s.List()[0].HasSession || s.List()[0].Username != "Mogo7" {
		t.Fatal("remember name stored a session")
	}
	if _, err = s.Remember("Mogo7", 7, "new-token", false, false); err != nil {
		t.Fatal(err)
	}
	if len(s.List()) != 1 || s.List()[0].Username != "Mogo6" {
		t.Fatal("unchecked remember flags not honored")
	}
}
