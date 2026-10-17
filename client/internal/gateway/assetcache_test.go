package gateway

import (
	"io"
	"net/http"
	"net/http/httptest"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

func TestConcurrentOriginalGraphicRequestsShareOneBackendLoad(t *testing.T) {
	var calls atomic.Int32
	backend := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		calls.Add(1)
		time.Sleep(20 * time.Millisecond)
		w.Header().Set("Content-Type", "application/x-shockwave-flash")
		io.WriteString(w, "original-swf")
	}))
	defer backend.Close()
	g := New(backend.URL, time.Second)
	var wg sync.WaitGroup
	for i := 0; i < 8; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			w := httptest.NewRecorder()
			g.ServeHTTP(w, httptest.NewRequest("GET", "http://wails.localhost/api/shop-assets/Display/100.swf", nil))
			if w.Code != 200 || w.Body.String() != "original-swf" {
				t.Errorf("bad asset: %d %q", w.Code, w.Body.String())
			}
		}()
	}
	wg.Wait()
	if calls.Load() != 1 {
		t.Fatalf("backend loads: %d", calls.Load())
	}
	first := httptest.NewRecorder()
	g.ServeHTTP(first, httptest.NewRequest("GET", "http://wails.localhost/api/shop-assets/Display/100.swf?appVer=2", nil))
	request := httptest.NewRequest("GET", "http://wails.localhost/api/shop-assets/Display/100.swf", nil)
	request.Header.Set("If-None-Match", first.Header().Get("ETag"))
	cached := httptest.NewRecorder()
	g.ServeHTTP(cached, request)
	if cached.Code != 304 || calls.Load() != 1 {
		t.Fatalf("conditional cache: %d, loads %d", cached.Code, calls.Load())
	}
}

func TestMissingGraphicDoesNotPoisonTheCache(t *testing.T) {
	var calls atomic.Int32
	backend := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if calls.Add(1) == 1 {
			http.NotFound(w, r)
			return
		}
		io.WriteString(w, "ready")
	}))
	defer backend.Close()
	g := New(backend.URL, time.Second)
	for _, status := range []int{404, 200, 200} {
		w := httptest.NewRecorder()
		g.ServeHTTP(w, httptest.NewRequest("GET", "http://wails.localhost/api/shop-assets/Display/100.swf", nil))
		if w.Code != status {
			t.Fatalf("status: %d", w.Code)
		}
	}
	if calls.Load() != 2 {
		t.Fatal(calls.Load())
	}
}
