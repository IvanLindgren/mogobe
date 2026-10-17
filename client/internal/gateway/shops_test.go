package gateway

import (
	"bytes"
	"io"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"
)

func TestShopGraphicOverOneMegabyteIsNotTruncated(t *testing.T) {
	payload := bytes.Repeat([]byte{0x43, 0x57, 0x53}, 700000)
	backend := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/shop-assets/Display/1.swf" {
			t.Errorf("unexpected path %s", r.URL.Path)
		}
		w.Header().Set("Content-Type", "application/x-shockwave-flash")
		w.Write(payload)
	}))
	defer backend.Close()
	gateway := New(backend.URL, time.Second)
	request := httptest.NewRequest("GET", "http://wails.localhost/Swf/Items/Display/1.swf", nil)
	recorder := httptest.NewRecorder()
	gateway.Middleware(http.NotFoundHandler()).ServeHTTP(recorder, request)
	actual, _ := io.ReadAll(recorder.Result().Body)
	if recorder.Code != 200 || !bytes.Equal(actual, payload) {
		t.Fatalf("graphic truncated: %d bytes, status %d", len(actual), recorder.Code)
	}
}

func TestAdministrationIsNotExposedByGameClient(t *testing.T) {
	gateway := New("http://127.0.0.1:1", time.Millisecond)
	for _, path := range []string{"/admin/shops", "/admin/runtime/ruffle.js", "/api/admin/shops", "/api/admin/shops/login"} {
		recorder := httptest.NewRecorder()
		gateway.Middleware(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { t.Fatal("admin request reached embedded assets") })).ServeHTTP(recorder, httptest.NewRequest("GET", "http://wails.localhost"+path, nil))
		if recorder.Code != http.StatusNotFound {
			t.Fatalf("%s: status %d", path, recorder.Code)
		}
	}
}
