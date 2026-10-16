//go:build windows

package main

import (
	"errors"
	"fmt"
	"os"
	"path/filepath"

	"golang.org/x/sys/windows"
)

// Each running window owns a persistent slot. Slot zero retains the original
// paths; extra windows get separate cookies, Flash storage and saved accounts.
// Windows releases the byte lock even if the process crashes.
func reserveClientProfile(cacheRoot, key string) (string, string, func(), error) {
	root := filepath.Join(cacheRoot, "Mogobe")
	if err := os.MkdirAll(root, 0700); err != nil {
		return "", "", nil, err
	}
	for slot := 0; slot < 32; slot++ {
		suffix := ""
		if slot > 0 {
			suffix = fmt.Sprintf("-%d", slot)
		}
		path := filepath.Join(root, "instance-"+key+suffix+".lock")
		name, err := windows.UTF16PtrFromString(path)
		if err != nil {
			return "", "", nil, err
		}
		handle, err := windows.CreateFile(name, windows.GENERIC_READ|windows.GENERIC_WRITE, windows.FILE_SHARE_READ|windows.FILE_SHARE_WRITE, nil, windows.OPEN_ALWAYS, windows.FILE_ATTRIBUTE_NORMAL, 0)
		if err != nil {
			return "", "", nil, err
		}
		overlapped := &windows.Overlapped{}
		err = windows.LockFileEx(handle, windows.LOCKFILE_EXCLUSIVE_LOCK|windows.LOCKFILE_FAIL_IMMEDIATELY, 0, 1, 0, overlapped)
		if err != nil {
			windows.CloseHandle(handle)
			if errors.Is(err, windows.ERROR_LOCK_VIOLATION) {
				continue
			}
			return "", "", nil, err
		}
		release := func() {
			windows.UnlockFileEx(handle, 0, 1, 0, overlapped)
			windows.CloseHandle(handle)
		}
		return filepath.Join(root, "webview-"+key+suffix), filepath.Join(root, "accounts-"+key+suffix+".dat"), release, nil
	}
	return "", "", nil, errors.New("too many client windows")
}
