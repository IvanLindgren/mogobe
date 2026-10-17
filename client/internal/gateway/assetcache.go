package gateway

import (
	"crypto/sha256"
	"fmt"
	"io"
	"net/http"
	"strings"
	"sync"
	"time"
)

const graphicCacheBytes = 32 * 1024 * 1024

type graphicEntry struct {
	ready       chan struct{}
	data        []byte
	status      int
	contentType string
	etag        string
	expires     time.Time
	used        uint64
}

type graphicCache struct {
	mu      sync.Mutex
	entries map[string]*graphicEntry
	bytes   int
	clock   uint64
}

// Original graphics are public and fixed by role/ID. Cache per selected backend,
// coalesce concurrent Ruffle thumbnail/preview loads, and never cache errors.
func (g *Gateway) serveGraphic(w http.ResponseWriter, r *http.Request) {
	key := r.URL.Path
	c := &g.graphics
	c.mu.Lock()
	if c.entries == nil {
		c.entries = make(map[string]*graphicEntry)
	}
	c.clock++
	entry := c.entries[key]
	if entry != nil && !entry.expires.IsZero() && time.Now().After(entry.expires) {
		delete(c.entries, key)
		c.bytes -= len(entry.data)
		entry = nil
	}
	if entry != nil {
		entry.used = c.clock
		c.mu.Unlock()
		select {
		case <-entry.ready:
		case <-r.Context().Done():
			return
		}
		writeGraphic(w, r, entry)
		return
	}
	entry = &graphicEntry{ready: make(chan struct{}), used: c.clock}
	c.entries[key] = entry
	c.mu.Unlock()

	target := *g.target
	target.Path = strings.TrimRight(target.Path, "/") + key
	target.RawQuery = ""
	request, err := http.NewRequest(http.MethodGet, target.String(), nil)
	entry.status = http.StatusBadGateway
	if err == nil {
		response, failure := g.client.Do(request)
		if failure == nil {
			data, readErr := io.ReadAll(io.LimitReader(response.Body, 8*1024*1024+1))
			response.Body.Close()
			if readErr == nil && len(data) <= 8*1024*1024 {
				entry.status, entry.data = response.StatusCode, data
				entry.contentType = response.Header.Get("Content-Type")
				entry.etag = fmt.Sprintf("\"%x\"", sha256.Sum256(data))
			}
		}
	}
	c.mu.Lock()
	if entry.status == http.StatusOK {
		entry.expires = time.Now().Add(30 * time.Minute)
		c.bytes += len(entry.data)
		for c.bytes > graphicCacheBytes || len(c.entries) > 256 {
			var oldest string
			var candidate *graphicEntry
			for name, value := range c.entries {
				if value.expires.IsZero() {
					continue
				}
				if candidate == nil || value.used < candidate.used {
					oldest, candidate = name, value
				}
			}
			if candidate == nil {
				break
			}
			delete(c.entries, oldest)
			c.bytes -= len(candidate.data)
		}
	} else {
		delete(c.entries, key)
	}
	close(entry.ready)
	c.mu.Unlock()
	writeGraphic(w, r, entry)
}

func writeGraphic(w http.ResponseWriter, r *http.Request, entry *graphicEntry) {
	w.Header().Set("Content-Type", entry.contentType)
	if entry.status == http.StatusOK {
		w.Header().Set("Cache-Control", "private, no-cache")
		w.Header().Set("ETag", entry.etag)
		if r.Header.Get("If-None-Match") == entry.etag {
			w.WriteHeader(http.StatusNotModified)
			return
		}
	}
	w.WriteHeader(entry.status)
	w.Write(entry.data)
}
