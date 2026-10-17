package main

import (
	"encoding/binary"
	"fmt"
	"golang.org/x/sys/windows"
	"image"
	"runtime"
	"time"
	"unsafe"
)

var clipboardUser32 = windows.NewLazySystemDLL("user32.dll")
var clipboardKernel32 = windows.NewLazySystemDLL("kernel32.dll")

func avatarDIB(picture image.Image) []byte {
	bounds := picture.Bounds()
	width, height := bounds.Dx(), bounds.Dy()
	dib := make([]byte, 40+width*height*4)
	binary.LittleEndian.PutUint32(dib[0:], 40)
	binary.LittleEndian.PutUint32(dib[4:], uint32(width))
	binary.LittleEndian.PutUint32(dib[8:], uint32(height))
	binary.LittleEndian.PutUint16(dib[12:], 1)
	binary.LittleEndian.PutUint16(dib[14:], 32)
	binary.LittleEndian.PutUint32(dib[20:], uint32(width*height*4))
	for y := 0; y < height; y++ {
		for x := 0; x < width; x++ {
			r, g, b, _ := picture.At(bounds.Min.X+x, bounds.Min.Y+y).RGBA()
			pos := 40 + ((height-1-y)*width+x)*4
			dib[pos], dib[pos+1], dib[pos+2], dib[pos+3] = byte(b>>8), byte(g>>8), byte(r>>8), 255
		}
	}
	return dib
}

func copyAvatarImage(picture image.Image) error {
	runtime.LockOSThread()
	defer runtime.UnlockOSThread()
	open := clipboardUser32.NewProc("OpenClipboard")
	var opened uintptr
	for i := 0; i < 20; i++ {
		opened, _, _ = open.Call(0)
		if opened != 0 {
			break
		}
		time.Sleep(10 * time.Millisecond)
	}
	if opened == 0 {
		return fmt.Errorf("clipboard is busy")
	}
	defer clipboardUser32.NewProc("CloseClipboard").Call()
	dib := avatarDIB(picture)
	handle, _, err := clipboardKernel32.NewProc("GlobalAlloc").Call(2, uintptr(len(dib)))
	if handle == 0 {
		return err
	}
	transferred := false
	defer func() {
		if !transferred {
			clipboardKernel32.NewProc("GlobalFree").Call(handle)
		}
	}()
	pointer, _, err := clipboardKernel32.NewProc("GlobalLock").Call(handle)
	if pointer == 0 {
		return err
	}
	copy(unsafe.Slice((*byte)(unsafe.Pointer(pointer)), len(dib)), dib)
	clipboardKernel32.NewProc("GlobalUnlock").Call(handle)
	ok, _, err := clipboardUser32.NewProc("EmptyClipboard").Call()
	if ok == 0 {
		return err
	}
	ok, _, err = clipboardUser32.NewProc("SetClipboardData").Call(8, handle) // CF_DIB
	if ok == 0 {
		return err
	}
	transferred = true
	return nil
}
