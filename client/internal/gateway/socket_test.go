package gateway

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/gorilla/websocket"
)

func TestWorldSocketUsesPrivateSessionAndClosesOnLogout(t *testing.T) {
	backend := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/api/auth/register" {
			http.SetCookie(w, &http.Cookie{Name: "mogobe_session", Value: "private-session", Path: "/", HttpOnly: true})
			w.WriteHeader(201)
			return
		}
		if r.URL.Path != "/legacy/socket" || r.URL.RawQuery != "" || r.Header.Get("Authorization") != "Bearer private-session" {
			http.Error(w, "Invalid backend request", 403)
			return
		}
		upstream, err := (&websocket.Upgrader{}).Upgrade(w, r, nil)
		if err != nil {
			return
		}
		defer upstream.Close()
		for {
			kind, packet, err := upstream.ReadMessage()
			if err != nil {
				return
			}
			if upstream.WriteMessage(kind, packet) != nil {
				return
			}
		}
	}))
	defer backend.Close()
	g := New(backend.URL, time.Second)
	closeBridge, err := g.StartWorldSocket("")
	if err != nil {
		t.Fatal(err)
	}
	defer closeBridge()
	origin := http.Header{"Origin": {"http://wails.localhost"}}
	if connection, _, err := websocket.DefaultDialer.Dial(g.world.url, origin); err == nil {
		connection.Close()
		t.Fatal("Unauthenticated connection accepted")
	}
	// Registration establishes the private Go session without exposing it in runtime JSON.
	request := httptest.NewRequest("POST", "http://wails.localhost/api/auth/register", nil)
	response := httptest.NewRecorder()
	g.ServeHTTP(response, request)
	if response.Code != 201 {
		t.Fatalf("Register: %d", response.Code)
	}
	if connection, _, err := websocket.DefaultDialer.Dial(g.world.url, http.Header{"Origin": {"https://other.test"}}); err == nil {
		connection.Close()
		t.Fatal("Foreign origin accepted")
	}
	downstream, _, err := websocket.DefaultDialer.Dial(g.world.url, origin)
	if err != nil {
		t.Fatal(err)
	}
	defer downstream.Close()
	downstream.SetReadDeadline(time.Now().Add(3 * time.Second))
	packet := []byte("<msg/>\x00")
	if err := downstream.WriteMessage(websocket.BinaryMessage, packet); err != nil {
		t.Fatal(err)
	}
	kind, echoed, err := downstream.ReadMessage()
	if err != nil || kind != websocket.BinaryMessage || string(echoed) != string(packet) {
		t.Fatalf("Echo: %q %v", echoed, err)
	}
	// A social packet can span multiple WebSocket messages, or share a
	// message with another NUL-delimited packet. Forward every byte intact.
	revision := func() uint64 {
		t.Helper()
		response := httptest.NewRecorder()
		g.ServeHTTP(response, httptest.NewRequest("GET", "http://wails.localhost/client/world/status", nil))
		var status struct {
			Revision uint64 `json:"social_revision"`
		}
		if err := json.Unmarshal(response.Body.Bytes(), &status); err != nil {
			t.Fatal(err)
		}
		return status.Revision
	}
	fragments := [][]byte{
		[]byte(`{"t":"xt","b":{"o":{"_cmd":"buddyList__get`),
		[]byte("UserBuddies\",\"buddies\":[]}}}\x00<msg/>\x00"),
		[]byte("{\"t\":\"xt\",\"b\":{\"o\":{\"_cmd\":\"buddyList__deleteBuddy\"}}}\x00"),
		[]byte("{\"t\":\"xt\",\"b\":{\"o\":{\"_cmd\":\"user__getMyMoney\",\"text\":\"buddyList__\"}}}\x00{bad json}\x00"),
	}
	expected := []uint64{0, 1, 2, 2}
	for i, fragment := range fragments {
		if err := downstream.WriteMessage(websocket.BinaryMessage, fragment); err != nil {
			t.Fatal(err)
		}
		kind, forwarded, err := downstream.ReadMessage()
		if err != nil || kind != websocket.BinaryMessage || string(forwarded) != string(fragment) {
			t.Fatalf("Social stream changed: %q %v", forwarded, err)
		}
		if actual := revision(); actual != expected[i] {
			t.Fatalf("Fragment %d revision = %d, want %d", i, actual, expected[i])
		}
	}
	g.observeSocialPacket("other-session", g.world.generation, []byte(`{"t":"xt","b":{"o":{"_cmd":"buddyList__deleteBuddy"}}}`))
	g.observeSocialPacket("private-session", g.world.generation-1, []byte(`{"t":"xt","b":{"o":{"_cmd":"buddyList__deleteBuddy"}}}`))
	if revision() != 2 {
		t.Fatal("Stale world connection changed social state")
	}
	leave := httptest.NewRecorder()
	g.ServeHTTP(leave, httptest.NewRequest("POST", "http://wails.localhost/client/world/leave", nil))
	if leave.Code != http.StatusNoContent || len(leave.Result().Cookies()) != 0 {
		t.Fatalf("Leave must preserve the login cookie: status=%d", leave.Code)
	}
	if _, _, err = downstream.ReadMessage(); err == nil {
		t.Fatal("World connection survived return to picker")
	}
}

func TestDuplicateWorldConnectionReportsErrorWithoutRevokingSession(t *testing.T) {
	backend := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		connection, err := (&websocket.Upgrader{}).Upgrade(w, r, nil)
		if err != nil {
			return
		}
		defer connection.Close()
		connection.WriteMessage(websocket.CloseMessage, websocket.FormatCloseMessage(4009, "Account already in game"))
	}))
	defer backend.Close()
	g := New(backend.URL, time.Second)
	closeBridge, err := g.StartWorldSocket("")
	if err != nil {
		t.Fatal(err)
	}
	defer closeBridge()
	g.setWorldSession("still-valid")
	socket, _, err := websocket.DefaultDialer.Dial(g.world.url, http.Header{"Origin": {"http://wails.localhost"}})
	if err != nil {
		t.Fatal(err)
	}
	defer socket.Close()
	socket.SetReadDeadline(time.Now().Add(3 * time.Second))
	socket.ReadMessage()
	g.world.mu.Lock()
	message, token := g.world.error, g.world.token
	g.world.mu.Unlock()
	if message == "" || token != "still-valid" {
		t.Fatal("Duplicate login must report error and preserve session")
	}
}
