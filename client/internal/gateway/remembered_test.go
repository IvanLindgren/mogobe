package gateway

import (
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"net/url"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/firocore/mogobe/client/internal/accounts"
)

func savedRequest(username string, remember bool) *http.Request {
	r := httptest.NewRequest("GET", "http://local/Servises/Login.aspx?user="+url.QueryEscape(username)+"&pass="+url.QueryEscape(accounts.SavedSessionMarker), nil)
	prefs, _ := json.Marshal(loginPreferences{Username: username, RememberName: true, RememberSession: remember, Attempt: "test-attempt"})
	r.AddCookie(&http.Cookie{Name: "mogobe_login_preferences", Value: url.QueryEscape(string(prefs))})
	r.AddCookie(&http.Cookie{Name: "mogobe_session", Value: "token-b"})
	return r
}

func TestSavedPickerUsesSelectedTokenAndCanStopRemembering(t *testing.T) {
	revoked := make(chan string, 10)
	remote := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path == "/api/auth/logout" {
			revoked <- r.Header.Get("Authorization")
			w.WriteHeader(204)
			return
		}
		if r.URL.Path != "/legacy/resume" || r.Method != "POST" || r.URL.RawQuery != "" {
			t.Error("saved login used password endpoint", r.URL)
		}
		if r.Header.Get("Authorization") != "Bearer token-a" {
			t.Error("resumed current cookie instead of selected mogobe")
		}
		var body map[string]any
		json.NewDecoder(r.Body).Decode(&body)
		if body["username"] != "MogoA" || body["password"] != nil {
			t.Error("unexpected resume body", body)
		}
		io.WriteString(w, `<Response><Login status="1" username="MogoA" colorId="3"/></Response>`)
	}))
	defer remote.Close()
	store, err := accounts.Open(filepath.Join(t.TempDir(), "accounts.dat"), remote.URL)
	if err != nil {
		t.Fatal(err)
	}
	store.Remember("MogoA", 3, "token-a", true, true)
	store.Remember("MogoB", 4, "token-b", true, true)
	g := New(remote.URL, time.Second)
	g.Accounts = store
	w := httptest.NewRecorder()
	g.ServeHTTP(w, savedRequest("MogoA", true))
	if w.Code != 200 || !strings.Contains(w.Body.String(), `status="1"`) {
		t.Fatal(w.Code, w.Body.String())
	}
	if len(w.Result().Cookies()) != 1 || w.Result().Cookies()[0].Value != "token-a" || !w.Result().Cookies()[0].HttpOnly {
		t.Fatal("selected session not applied")
	}
	if store.Token("MogoB") != "token-b" || store.List()[0].Username != "MogoA" {
		t.Fatal("other account lost or selection order wrong")
	}
	w = httptest.NewRecorder()
	g.ServeHTTP(w, savedRequest("MogoA", false))
	if store.Token("MogoA") != "" || store.Token("MogoB") != "token-b" {
		t.Fatal("unchecked remember affected another mogobe")
	}
	select {
	case token := <-revoked:
		t.Fatal("revoked the selected active session", token)
	case <-time.After(50 * time.Millisecond):
	}
	list := httptest.NewRecorder()
	g.ServeHTTP(list, httptest.NewRequest("GET", "http://local/client/accounts", nil))
	if strings.Contains(list.Body.String(), "token-a") || strings.Contains(list.Body.String(), "token-b") {
		t.Fatal("token exposed to JavaScript")
	}
}

func TestExpiredSavedSessionClearsOnlyItsTokenAndOfflineKeepsIt(t *testing.T) {
	remote := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		io.WriteString(w, `<Response><Login status="2"/></Response>`)
	}))
	store, err := accounts.Open(filepath.Join(t.TempDir(), "accounts.dat"), remote.URL)
	if err != nil {
		t.Fatal(err)
	}
	store.Remember("MogoA", 3, "token-a", true, true)
	store.Remember("MogoB", 4, "token-b", true, true)
	g := New(remote.URL, time.Second)
	g.Accounts = store
	w := httptest.NewRecorder()
	g.ServeHTTP(w, savedRequest("MogoA", true))
	if !strings.Contains(w.Body.String(), `status="2"`) || store.Token("MogoA") != "" || store.Token("MogoB") != "token-b" {
		t.Fatal("expired session affected wrong account")
	}
	store.Remember("MogoA", 3, "replacement", true, true)
	remote.Close()
	w = httptest.NewRecorder()
	g.ServeHTTP(w, savedRequest("MogoA", true))
	if !strings.Contains(w.Body.String(), `status="4"`) || store.Token("MogoA") != "replacement" {
		t.Fatal("network failure erased remembered login")
	}
}

func TestRegistrationUsesCurrentSessionWithoutRememberedToken(t *testing.T) {
	calls := 0
	remote := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		calls++
		if r.URL.Path != "/legacy/resume" || r.Method != "POST" || r.URL.RawQuery != "" {
			t.Error("registration must resume, not submit another password")
		}
		if r.Header.Get("Authorization") != "Bearer registration-session" {
			t.Error("did not use the current HttpOnly registration session")
		}
		var body map[string]any
		json.NewDecoder(r.Body).Decode(&body)
		if body["username"] != "NewMogo" || body["password"] != nil {
			t.Error("unexpected resume body", body)
		}
		io.WriteString(w, `<Response><Login status="1" username="NewMogo" colorId="7"/></Response>`)
	}))
	defer remote.Close()
	store, err := accounts.Open(filepath.Join(t.TempDir(), "accounts.dat"), remote.URL)
	if err != nil {
		t.Fatal(err)
	}
	store.Remember("OtherMogo", 3, "other-session", true, true)
	g := New(remote.URL, time.Second)
	g.Accounts = store
	request := func(withCookie bool) *http.Request {
		r := httptest.NewRequest("GET", "http://local/Servises/Login.aspx?user=NewMogo&pass="+url.QueryEscape(currentSessionMarker), nil)
		if withCookie {
			r.AddCookie(&http.Cookie{Name: "mogobe_session", Value: "registration-session"})
		}
		return r
	}
	w := httptest.NewRecorder()
	g.ServeHTTP(w, request(true))
	if w.Code != 200 || !strings.Contains(w.Body.String(), `status="1"`) {
		t.Fatal(w.Code, w.Body.String())
	}
	if store.List()[0].Username != "NewMogo" || store.List()[0].HasSession || store.List()[0].ColorID != 7 {
		t.Fatal("new mogobe should remember its name/color, without implicitly saving authorization")
	}
	if store.Token("OtherMogo") != "other-session" {
		t.Fatal("registration changed another mogobe's authorization")
	}
	store.Remember("NewMogo", 7, "saved-session", true, true)
	w = httptest.NewRecorder()
	g.ServeHTTP(w, request(false))
	if !strings.Contains(w.Body.String(), `status="2"`) || calls != 1 || store.Token("NewMogo") != "saved-session" {
		t.Fatal("missing registration cookie must not select a stored session")
	}
}
