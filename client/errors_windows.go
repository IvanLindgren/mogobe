package main

import (
	"fmt"
	"os"
	"syscall"
	"unsafe"
)

func fatal(message string, err error) {
	text := message + "\n\n" + err.Error()
	fmt.Fprintln(os.Stderr, text)
	caption, _ := syscall.UTF16PtrFromString("Могоби")
	body, _ := syscall.UTF16PtrFromString(text)
	messageBox := syscall.NewLazyDLL("user32.dll").NewProc("MessageBoxW")
	messageBox.Call(0, uintptr(unsafe.Pointer(body)), uintptr(unsafe.Pointer(caption)), 0x10)
	os.Exit(1)
}
