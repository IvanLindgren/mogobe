package gateway

import (
	"bytes"
	"encoding/base64"
	"image"
	"image/jpeg"
	"net/http/httptest"
	"strings"
	"testing"
	"time"
)

func TestAvatarClipboardIsLocalAndChecksImage(t *testing.T) {
	g := New("http://127.0.0.1:1", time.Millisecond)
	calls := 0
	g.CopyAvatarImage = func(p image.Image) error {
		calls++
		if p.Bounds().Dx() != 12 {
			t.Fatal(p.Bounds())
		}
		return nil
	}
	var encoded bytes.Buffer
	jpeg.Encode(&encoded, image.NewRGBA(image.Rect(0, 0, 12, 16)), nil)
	good := `{"jpeg":"` + base64.StdEncoding.EncodeToString(encoded.Bytes()) + `"}`
	for _, tc := range []struct {
		body string
		code int
	}{{good, 200}, {`{"jpeg":"invalid"}`, 400}, {`{"jpeg":""}`, 400}} {
		rec := httptest.NewRecorder()
		req := httptest.NewRequest("POST", "http://wails.localhost/client/clipboard/avatar", strings.NewReader(tc.body))
		g.ServeHTTP(rec, req)
		if rec.Code != tc.code {
			t.Fatalf("%d: %s", rec.Code, rec.Body)
		}
	}
	if calls != 1 {
		t.Fatal(calls)
	}
	rec := httptest.NewRecorder()
	req := httptest.NewRequest("POST", "http://wails.localhost/client/clipboard/avatar", strings.NewReader(good))
	req.Header.Set("Origin", "https://elsewhere.invalid")
	g.ServeHTTP(rec, req)
	if rec.Code != 403 || calls != 1 {
		t.Fatal(rec.Code, calls)
	}
}
