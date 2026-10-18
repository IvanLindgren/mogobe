package gateway

import (
	"bytes"
	"io"
	"net/http"
	"net/http/httptest"
	"testing"
	"testing/fstest"
	"time"
)

func TestShopGraphicOverOneMegabyteIsNotTruncated(t *testing.T) {
	payload := bytes.Repeat([]byte{0x43, 0x57, 0x53}, 700000)
	gateway := New("http://127.0.0.1:1", time.Millisecond)
	gateway.ItemAssets = fstest.MapFS{"Display/1.swf": {Data: payload}}
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
	for _, path := range []string{"/admin", "/admin/", "/admin/app.js", "/api/admin/login", "/api/admin/accounts", "/api/admin/items", "/api/admin/overview", "/admin/shops", "/admin/runtime/ruffle.js", "/api/admin/shops", "/api/admin/shops/login"} {
		recorder := httptest.NewRecorder()
		gateway.Middleware(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { t.Fatal("admin request reached embedded assets") })).ServeHTTP(recorder, httptest.NewRequest("GET", "http://wails.localhost"+path, nil))
		if recorder.Code != http.StatusNotFound {
			t.Fatalf("%s: status %d", path, recorder.Code)
		}
	}
}
