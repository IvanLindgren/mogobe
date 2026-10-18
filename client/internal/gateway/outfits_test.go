package gateway

import (
	"io"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"reflect"
	"strings"
	"testing"
	"time"

	"github.com/firocore/mogobe/client/internal/accounts"
)

func TestSavedOutfitRefreshUsesPrivateCredentialsAndPreservesSnapshotsOnErrors(t *testing.T) {
	backend := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.URL.Path != "/api/social/profiles/by-name/МоГо_Ё" || r.Header.Get("Authorization") != "Bearer private-token" || r.URL.RawQuery != "" {
			t.Errorf("unexpected refresh request: %s", r.URL.Path)
		}
		io.WriteString(w, `{"userName":"МоГо_Ё","items":[{"typeId":100},{"typeId":16}]}`)
	}))
	store, err := accounts.Open(filepath.Join(t.TempDir(), "accounts.dat"), backend.URL)
	if err != nil {
		t.Fatal(err)
	}
	store.Remember("МоГо_Ё", 3, "private-token", true, true)
	store.Remember("NameOnly", 4, "", true, false)
	store.UpdateOutfit("NameOnly", []int{20})
	g := New(backend.URL, time.Second)
	g.Accounts = store
	refresh := func() string {
		w := httptest.NewRecorder()
		g.ServeHTTP(w, httptest.NewRequest("POST", "http://local/client/accounts/refresh", nil))
		if w.Code != 200 {
			t.Fatal(w.Code, w.Body.String())
		}
		if strings.Contains(w.Body.String(), "private-token") {
			t.Fatal("token exposed")
		}
		return w.Body.String()
	}
	first := refresh()
	if !reflect.DeepEqual(store.List()[1].ItemIDs, []int{100, 16}) || !reflect.DeepEqual(store.List()[0].ItemIDs, []int{20}) {
		t.Fatal(store.List())
	}
	backend.Close()
	if second := refresh(); first != second || store.Token("МоГо_Ё") != "private-token" {
		t.Fatal("network error erased cached appearance or session")
	}
}

func TestOwnOutfitSnapshotsIgnoreOtherPlayersAndStaleConnections(t *testing.T) {
	store, err := accounts.Open(filepath.Join(t.TempDir(), "accounts.dat"), "http://localhost")
	if err != nil {
		t.Fatal(err)
	}
	store.Remember("MogoA", 3, "", true, false)
	g := New("http://localhost", time.Second)
	g.Accounts = store
	g.setWorldSession("active-session")
	generation := g.world.generation
	packet := func(s string) { g.observeOutfitPacket("active-session", generation, []byte(s)) }
	packet(`{"t":"xt","b":{"o":{"_cmd":"login","uSFSId":7,"userName":"MogoA"}}}`)
	packet(`<msg t="sys"><body action="joinOK"><uLs><u i="9"><vars><var n="items">[{"typeId":101}]</var></vars></u><u i="7"><vars><var n="items">[{"typeId":100}]</var></vars></u></uLs></body></msg>`)
	if !reflect.DeepEqual(store.List()[0].ItemIDs, []int{100}) {
		t.Fatal("initial outfit missing", store.List())
	}
	update := func(id int, items string) string {
		if id == 9 {
			return `<msg t="sys"><body action="uVarsUpdate"><user id="9"/><vars><var n="items">[{"typeId":101}]</var></vars></body></msg>`
		}
		return `<msg t="sys"><body action="uVarsUpdate"><user id="7"/><vars><var n="items">` + items + `</var></vars></body></msg>`
	}
	packet(update(9, `[{"typeId":101}]`))
	g.observeOutfitPacket("another-session", generation, []byte(update(7, `[]`)))
	g.observeOutfitPacket("active-session", generation-1, []byte(update(7, `[]`)))
	packet(update(7, `null`))
	packet(update(7, `[{"typeId":-1}]`))
	packet(update(7, `[{"typeId":100},{"typeId":100}]`))
	if !reflect.DeepEqual(store.List()[0].ItemIDs, []int{100}) {
		t.Fatal("another player, stale connection or bad payload changed appearance")
	}
	packet(update(7, `[]`))
	if len(store.List()[0].ItemIDs) != 0 {
		t.Fatal("unequip did not remove the last garment")
	}
}
