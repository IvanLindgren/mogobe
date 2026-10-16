package accounts

import (
	"golang.org/x/sys/windows"
	"unsafe"
)

func blob(data []byte) windows.DataBlob {
	if len(data) == 0 {
		return windows.DataBlob{}
	}
	return windows.DataBlob{Size: uint32(len(data)), Data: &data[0]}
}

func protect(data, entropy []byte) ([]byte, error) {
	input, extra := blob(data), blob(entropy)
	var output windows.DataBlob
	if err := windows.CryptProtectData(&input, nil, &extra, 0, nil, windows.CRYPTPROTECT_UI_FORBIDDEN, &output); err != nil {
		return nil, err
	}
	defer windows.LocalFree(windows.Handle(uintptr(unsafe.Pointer(output.Data))))
	return append([]byte(nil), unsafe.Slice(output.Data, int(output.Size))...), nil
}

func unprotect(data, entropy []byte) ([]byte, error) {
	input, extra := blob(data), blob(entropy)
	var output windows.DataBlob
	if err := windows.CryptUnprotectData(&input, nil, &extra, 0, nil, windows.CRYPTPROTECT_UI_FORBIDDEN, &output); err != nil {
		return nil, err
	}
	defer windows.LocalFree(windows.Handle(uintptr(unsafe.Pointer(output.Data))))
	return append([]byte(nil), unsafe.Slice(output.Data, int(output.Size))...), nil
}
