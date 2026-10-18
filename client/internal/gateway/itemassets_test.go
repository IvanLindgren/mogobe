package gateway

import (
	"bytes"
	"compress/zlib"
	"encoding/binary"
	"io"
	"net/http"
	"net/http/httptest"
	"strconv"
	"strings"
	"sync"
	"sync/atomic"
	"testing"
	"testing/fstest"
	"time"
)

func TestItemGraphicsAreLocalIncludingConcurrentLoadsAndMissingIDs(t *testing.T) {
	var calls atomic.Int32
	backend := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		calls.Add(1)
		t.Error("item request reached backend: " + r.URL.Path)
		http.Error(w, "graphics disabled on backend", 503)
	}))
	defer backend.Close()
	g := New(backend.URL, time.Second)
	g.ItemAssets = fstest.MapFS{
		"Display/100.swf": {Data: []byte("original-swf")},
		"InUse/100.swf":   {Data: []byte("standing-and-walking")},
		"Cats/4.swf":      {Data: categoryTemplate()},
	}
	handler := g.Middleware(http.NotFoundHandler())
	var wg sync.WaitGroup
	for i := 0; i < 8; i++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			w := httptest.NewRecorder()
			handler.ServeHTTP(w, httptest.NewRequest("GET", "http://wails.localhost/Swf/Items/Display/100.swf?appVer=2", nil))
			if w.Code != 200 || w.Body.String() != "original-swf" {
				t.Errorf("bad asset: %d %q", w.Code, w.Body.String())
			}
		}()
	}
	wg.Wait()
	for _, path := range []string{"Display/999.swf", "InUse/999.swf", "Cats/103.swf", "Cats/4.swf", "raw/100.swf", "Display/../100.swf", "Display/-1.swf", "Display/4294967296.swf"} {
		w := httptest.NewRecorder()
		g.ServeHTTP(w, httptest.NewRequest("GET", "http://wails.localhost/api/shop-assets/"+path, nil))
		if w.Code != 404 {
			t.Errorf("%s: status %d", path, w.Code)
		}
	}
	for _, path := range []string{"InUse/100.swf", "Cats/104.swf", "Cats/9000104.swf"} {
		w := httptest.NewRecorder()
		g.ServeHTTP(w, httptest.NewRequest("GET", "http://wails.localhost/api/shop-assets/"+path, nil))
		if w.Code != 200 {
			t.Errorf("%s: status %d", path, w.Code)
		}
	}
	first := httptest.NewRecorder()
	g.ServeHTTP(first, httptest.NewRequest("GET", "http://wails.localhost/api/shop-assets/Display/100.swf", nil))
	request := httptest.NewRequest("GET", "http://wails.localhost/api/shop-assets/Display/100.swf", nil)
	request.Header.Set("If-None-Match", first.Header().Get("ETag"))
	cached := httptest.NewRecorder()
	g.ServeHTTP(cached, request)
	if cached.Code != 304 || calls.Load() != 0 {
		t.Fatalf("conditional cache: %d, backend loads %d", cached.Code, calls.Load())
	}
	head := httptest.NewRecorder()
	g.ServeHTTP(head, httptest.NewRequest("HEAD", request.URL.String(), nil))
	if head.Code != 200 || head.Body.Len() != 0 || head.Header().Get("Content-Length") != "12" {
		t.Fatalf("HEAD: %+v", head)
	}
	post := httptest.NewRecorder()
	g.ServeHTTP(post, httptest.NewRequest("POST", request.URL.String(), nil))
	if post.Code != 405 || calls.Load() != 0 {
		t.Fatalf("POST: %d, backend loads %d", post.Code, calls.Load())
	}
}

func categoryTemplate() []byte {
	body := bytes.NewBuffer([]byte{8, 0, 0, 15, 1, 0})
	for _, tag := range []struct {
		kind uint16
		data []byte
	}{
		{82, []byte("\x00\x00\x00\x00loading-compat\x00\x07btnCat0")},
		{76, []byte("\x01\x00\x01\x00btnCat0\x00")},
		{1, nil}, {0, nil},
	} {
		binary.Write(body, binary.LittleEndian, uint16(tag.kind<<6|63))
		binary.Write(body, binary.LittleEndian, uint32(len(tag.data)))
		body.Write(tag.data)
	}
	result := bytes.NewBuffer([]byte("CWS\x0a\x00\x00\x00\x00"))
	binary.LittleEndian.PutUint32(result.Bytes()[4:], uint32(body.Len()+8))
	compressor := zlib.NewWriter(result)
	compressor.Write(body.Bytes())
	compressor.Close()
	return result.Bytes()
}

func TestNewServerCategoriesUseLocalIconsWithCorrectAS3ClassNames(t *testing.T) {
	for _, ident := range []uint64{104, 88004, 4294967204} {
		movie, err := categoryMovie(categoryTemplate(), ident)
		if err != nil {
			t.Fatal(err)
		}
		reader, err := zlib.NewReader(bytes.NewReader(movie[8:]))
		if err != nil {
			t.Fatal(err)
		}
		body, err := io.ReadAll(reader)
		reader.Close()
		if err != nil {
			t.Fatal(err)
		}
		name := []byte("btnCat" + strconv.FormatUint(ident, 10))
		if !bytes.Contains(body, append([]byte{byte(len(name))}, name...)) || !bytes.Contains(body, append(append([]byte(nil), name...), 0)) || bytes.Contains(body, []byte("btnCat0")) || int(binary.LittleEndian.Uint32(movie[4:8])) != len(body)+8 {
			t.Fatalf("incorrect category export for %d", ident)
		}
	}
	for _, bad := range [][]byte{nil, []byte("CWS"), []byte(strings.Repeat("0", 100)), append([]byte("CWS\x0a\x00\x00\x00\x00"), []byte("bad zlib")...)} {
		if _, err := categoryMovie(bad, 104); err == nil {
			t.Fatal("corrupt template accepted")
		}
	}
}
