package accounts

import (
	"os"
	"path/filepath"
	"reflect"
	"testing"
)

func TestOutfitPersistsForNamesOnlyAccountsAndDoesNotChangeCredentialsOrOrder(t *testing.T) {
	path := filepath.Join(t.TempDir(), "accounts.dat")
	s, err := Open(path, "http://localhost")
	if err != nil {
		t.Fatal(err)
	}
	s.Remember("MiXeD", 7, "", true, false)
	s.Remember("Other", 4, "private-token", true, true)
	items := []int{100, 16}
	if err = s.UpdateOutfit("mixed", items); err != nil {
		t.Fatal(err)
	}
	items[0] = 101
	list := s.List()
	list[1].ItemIDs[0] = 20
	if !reflect.DeepEqual(s.List()[1].ItemIDs, []int{100, 16}) {
		t.Fatal("caller mutated saved outfit")
	}
	s, err = Open(path, "http://localhost")
	if err != nil {
		t.Fatal(err)
	}
	if s.List()[0].Username != "Other" || s.Token("Other") != "private-token" || s.List()[1].HasSession || !reflect.DeepEqual(s.List()[1].ItemIDs, []int{100, 16}) {
		t.Fatal(s.List())
	}
	s.Remember("MiXeD", 7, "new-token", true, true)
	if !reflect.DeepEqual(s.List()[0].ItemIDs, []int{100, 16}) {
		t.Fatal("login discarded outfit")
	}
	s.ClearToken("new-token")
	if !reflect.DeepEqual(s.List()[0].ItemIDs, []int{100, 16}) {
		t.Fatal("expired session discarded outfit")
	}
	if err = s.UpdateOutfit("MiXeD", []int{}); err != nil || len(s.List()[0].ItemIDs) != 0 {
		t.Fatal("removing clothes failed", err)
	}
}

func TestPreOutfitSavedAccountFilesRemainReadable(t *testing.T) {
	path := filepath.Join(t.TempDir(), "accounts.dat")
	data, err := protect([]byte(`{"version":1,"accounts":[{"username":"MogoA","color_id":3,"token":"private-token"}]}`), []byte("http://localhost"))
	if err != nil {
		t.Fatal(err)
	}
	if err = os.WriteFile(path, data, 0600); err != nil {
		t.Fatal(err)
	}
	s, err := Open(path, "http://localhost")
	if err != nil {
		t.Fatal(err)
	}
	if s.Token("MogoA") != "private-token" || len(s.List()[0].ItemIDs) != 0 {
		t.Fatal(s.List())
	}
}
