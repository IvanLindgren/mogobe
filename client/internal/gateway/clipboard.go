package gateway

import (
	"bytes"
	"encoding/base64"
	"encoding/json"
	"image"
	"image/jpeg"
	"net/http"
)

// avatarClipboard stays in the native gateway; image data never leaves the PC.
func (g *Gateway) avatarClipboard(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.Error(w, "Method not allowed", 405)
		return
	}
	var body struct {
		JPEG string `json:"jpeg"`
	}
	decoder := json.NewDecoder(http.MaxBytesReader(w, r.Body, 4<<20))
	decoder.DisallowUnknownFields()
	if decoder.Decode(&body) != nil {
		http.Error(w, "Invalid image", 400)
		return
	}
	data, err := base64.StdEncoding.Strict().DecodeString(body.JPEG)
	if err != nil {
		http.Error(w, "Invalid image", 400)
		return
	}
	config, err := jpeg.DecodeConfig(bytes.NewReader(data))
	if err != nil || config.Width < 1 || config.Height < 1 || config.Width > 2048 || config.Height > 2048 {
		http.Error(w, "Invalid image dimensions", 400)
		return
	}
	picture, err := jpeg.Decode(bytes.NewReader(data))
	if err != nil {
		http.Error(w, "Invalid image", 400)
		return
	}
	if g.CopyAvatarImage == nil || g.CopyAvatarImage(picture) != nil {
		http.Error(w, "Clipboard unavailable", 503)
		return
	}
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(map[string]int{"width": config.Width, "height": config.Height})
}

// ImageCopier is injected by the desktop host, so HTTP tests need no clipboard.
type ImageCopier func(image.Image) error
