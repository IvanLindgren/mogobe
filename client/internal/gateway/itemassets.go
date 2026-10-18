package gateway

import (
	"bytes"
	"compress/zlib"
	"crypto/sha256"
	"encoding/binary"
	"fmt"
	"io"
	"io/fs"
	"net/http"
	"strconv"
	"strings"
	"time"
)

// Ruffle keeps requesting the original URLs. Resolve every item graphic from
// the embedded package, including misses; never fall back to a remote server.
func (g *Gateway) serveGraphic(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodGet && r.Method != http.MethodHead {
		w.Header().Set("Allow", "GET, HEAD")
		w.WriteHeader(http.StatusMethodNotAllowed)
		return
	}
	parts := strings.Split(strings.TrimPrefix(r.URL.Path, "/api/shop-assets/"), "/")
	if len(parts) != 2 || !strings.HasSuffix(parts[1], ".swf") || g.ItemAssets == nil {
		http.NotFound(w, r)
		return
	}
	ident, err := strconv.ParseUint(strings.TrimSuffix(parts[1], ".swf"), 10, 32)
	if err != nil || ident == 0 {
		http.NotFound(w, r)
		return
	}
	role, sourceID := parts[0], ident
	switch role {
	case "Display", "InUse":
	case "Cats":
		if ident < 100 {
			http.NotFound(w, r)
			return
		}
		sourceID = ident % 100
	default:
		http.NotFound(w, r)
		return
	}
	data, err := fs.ReadFile(g.ItemAssets, fmt.Sprintf("%s/%d.swf", role, sourceID))
	if err == nil && role == "Cats" {
		data, err = categoryMovie(data, ident)
	}
	if err != nil {
		http.NotFound(w, r)
		return
	}
	w.Header().Set("Content-Type", "application/x-shockwave-flash")
	// Revalidate after client updates; prices and ownership never use this cache.
	w.Header().Set("Cache-Control", "private, no-cache")
	w.Header().Set("ETag", fmt.Sprintf("\"%x\"", sha256.Sum256(data)))
	http.ServeContent(w, r, parts[1], time.Time{}, bytes.NewReader(data))
}

// The catalog encodes category ID and icon as categoryID*100+iconID. Categories
// can be added on the server without rebuilding the client. Our seven local
// templates export btnCat0; rename only their generated AS3 class and export,
// preserving all original vector shapes. No server category lookup is needed.
func categoryMovie(data []byte, ident uint64) ([]byte, error) {
	invalid := fmt.Errorf("invalid embedded category template")
	if len(data) < 10 || string(data[:3]) != "CWS" {
		return nil, invalid
	}
	reader, err := zlib.NewReader(bytes.NewReader(data[8:]))
	if err != nil {
		return nil, err
	}
	body, err := io.ReadAll(io.LimitReader(reader, 8*1024*1024+1))
	reader.Close()
	if err != nil || len(body) < 6 || len(body) > 8*1024*1024 || len(body)+8 != int(binary.LittleEndian.Uint32(data[4:8])) {
		return nil, invalid
	}
	start := (5+int(body[0]>>3)*4+7)/8 + 4
	if start > len(body) {
		return nil, invalid
	}
	output := bytes.NewBuffer(append([]byte(nil), body[:start]...))
	name := []byte(fmt.Sprintf("btnCat%d", ident))
	old := []byte("btnCat0")
	classes, exports := 0, 0
	for pos := start; pos < len(body); {
		if pos+2 > len(body) {
			return nil, invalid
		}
		header := binary.LittleEndian.Uint16(body[pos:])
		pos += 2
		kind, length := header>>6, int(header&63)
		if length == 63 {
			if pos+4 > len(body) {
				return nil, invalid
			}
			length = int(binary.LittleEndian.Uint32(body[pos:]))
			pos += 4
		}
		if length > len(body)-pos {
			return nil, invalid
		}
		block := body[pos : pos+length]
		pos += length
		switch kind {
		case 82: // DoABC: the generated class's single-byte u30 string length.
			token := append([]byte{byte(len(old))}, old...)
			if bytes.Count(block, token) != 1 {
				return nil, invalid
			}
			block = bytes.Replace(block, token, append([]byte{byte(len(name))}, name...), 1)
			classes++
		case 76: // SymbolClass: one sprite ID and its null-terminated class name.
			if len(block) != 4+len(old)+1 || binary.LittleEndian.Uint16(block) != 1 || !bytes.Equal(block[4:], append(append([]byte(nil), old...), 0)) {
				return nil, invalid
			}
			block = append(append(append([]byte(nil), block[:4]...), name...), 0)
			exports++
		}
		binary.Write(output, binary.LittleEndian, uint16(kind<<6|63))
		binary.Write(output, binary.LittleEndian, uint32(len(block)))
		output.Write(block)
	}
	if classes != 1 || exports != 1 {
		return nil, invalid
	}
	result := bytes.NewBuffer(append([]byte(nil), data[:8]...))
	binary.LittleEndian.PutUint32(result.Bytes()[4:8], uint32(output.Len()+8))
	compressor := zlib.NewWriter(result)
	compressor.Write(output.Bytes())
	compressor.Close()
	return result.Bytes(), nil
}
