package main

import (
	"encoding/binary"
	"image"
	"image/color"
	"testing"
)

func TestAvatarDIBUsesBottomUpBGRAPixels(t *testing.T) {
	p := image.NewRGBA(image.Rect(3, 4, 4, 6))
	p.Set(3, 4, color.RGBA{255, 0, 0, 255})
	p.Set(3, 5, color.RGBA{0, 0, 255, 255})
	d := avatarDIB(p)
	if binary.LittleEndian.Uint32(d[4:]) != 1 || binary.LittleEndian.Uint32(d[8:]) != 2 || len(d) != 48 {
		t.Fatal(d)
	}
	if d[40] != 255 || d[42] != 0 || d[44] != 0 || d[46] != 255 {
		t.Fatal(d[40:])
	}
}
