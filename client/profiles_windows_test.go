//go:build windows

package main

import (
	"path/filepath"
	"testing"
)

func TestConcurrentWindowsHaveSeparatePersistentProfiles(t *testing.T) {
	root := t.TempDir()
	first, firstAccounts, releaseFirst, err := reserveClientProfile(root, "server-hash")
	if err != nil {
		t.Fatal(err)
	}
	if first != filepath.Join(root, "Mogobe", "webview-server-hash") || firstAccounts != filepath.Join(root, "Mogobe", "accounts-server-hash.dat") {
		t.Fatal("The first window must retain the existing profile and saved accounts")
	}
	second, secondAccounts, releaseSecond, err := reserveClientProfile(root, "server-hash")
	if err != nil {
		releaseFirst()
		t.Fatal(err)
	}
	defer releaseSecond()
	if second == first || secondAccounts == firstAccounts {
		t.Fatal("Concurrent windows share cookies or saved accounts")
	}
	releaseFirst()
	reopened, reopenedAccounts, releaseReopened, err := reserveClientProfile(root, "server-hash")
	if err != nil {
		t.Fatal(err)
	}
	defer releaseReopened()
	if reopened != first || reopenedAccounts != firstAccounts {
		t.Fatal("Restart must reuse the saved primary profile")
	}
}
