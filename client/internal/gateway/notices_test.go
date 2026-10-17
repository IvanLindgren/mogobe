package gateway

import (
	"encoding/json"
	"net/http/httptest"
	"testing"
	"time"
)

func TestGlobalNoticesQueueInOrderAndStayWithinSession(t *testing.T) {
	g := New("http://127.0.0.1:1", time.Second)
	g.setWorldSession("session")
	packet := func(text string) []byte {
		b, _ := json.Marshal(map[string]any{"t": "xt", "b": map[string]any{"o": map[string]string{"_cmd": "msg__sendPublicMsg", "messageType": "alert", "text": text, "sender": "Admin"}}})
		return b
	}
	g.observeSocialPacket("other", g.world.generation, packet("foreign"))
	g.observeSocialPacket("session", g.world.generation-1, packet("stale"))
	g.observeSocialPacket("session", g.world.generation, packet("first"))
	g.observeSocialPacket("session", g.world.generation, packet("second"))
	read := func() []worldNotice {
		rec := httptest.NewRecorder()
		g.ServeHTTP(rec, httptest.NewRequest("GET", "http://wails.localhost/client/world/status", nil))
		var data struct {
			Notices []worldNotice `json:"notices"`
		}
		if json.Unmarshal(rec.Body.Bytes(), &data) != nil {
			t.Fatal(rec.Body)
		}
		return data.Notices
	}
	notices := read()
	if len(notices) != 2 || notices[0].Text != "first" || notices[1].Text != "second" || notices[0].Sender != "Admin" {
		t.Fatal(notices)
	}
	if len(read()) != 0 {
		t.Fatal("notices repeated")
	}
	g.observeSocialPacket("session", g.world.generation, packet("old login"))
	g.setWorldSession("new")
	if len(read()) != 0 {
		t.Fatal("notice crossed session")
	}
}
