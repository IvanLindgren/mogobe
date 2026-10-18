package gateway

import (
	"context"
	"encoding/json"
	"encoding/xml"
	"net/http"
	"strings"
	"sync"
	"time"
)

type outfitItem struct {
	TypeID int `json:"typeId"`
}

func outfitIDs(items []outfitItem) []int {
	ids := make([]int, 0, len(items))
	for _, item := range items {
		ids = append(ids, item.TypeID)
	}
	return ids
}

// Once at the login screen, refresh display snapshots using private Go-held
// credentials. Missing/expired sessions and network errors keep cached outfits.
// No background polling, no login/resume, and no tokens returned to Flash/JS.
func (g *Gateway) refreshSavedOutfits(r *http.Request) {
	ctx, cancel := context.WithTimeout(r.Context(), 3*time.Second)
	defer cancel()
	current := ""
	if cookie, err := r.Cookie("mogobe_session"); err == nil {
		current = cookie.Value
	}
	var wg sync.WaitGroup
	for _, account := range g.Accounts.List() {
		token := g.Accounts.Token(account.Username)
		if token == "" {
			token = current
		}
		if token == "" {
			continue
		}
		wg.Add(1)
		go func(username, token string) {
			defer wg.Done()
			response, data, err := g.remoteJSONContext(ctx, "/api/social/profiles/by-name/"+username, "GET", nil, token)
			if err != nil || response.StatusCode != http.StatusOK {
				return
			}
			var profile struct {
				Username string        `json:"userName"`
				Items    *[]outfitItem `json:"items"`
			}
			if json.Unmarshal(data, &profile) == nil && strings.EqualFold(profile.Username, username) && profile.Items != nil {
				g.Accounts.UpdateOutfit(username, outfitIDs(*profile.Items))
			}
		}(account.Username, token)
	}
	wg.Wait()
}

// Save only authoritative server-to-client appearance changes for this login.
// The snapshot lets names-only entries retain their last outfit across restart.
func (g *Gateway) observeOutfitPacket(token string, generation uint64, packet []byte) {
	if g.Accounts == nil || len(packet) == 0 {
		return
	}
	if packet[0] == '{' {
		var event struct {
			Type string `json:"t"`
			Body struct {
				Object struct {
					Command  string `json:"_cmd"`
					ID       int    `json:"uSFSId"`
					Username string `json:"userName"`
				} `json:"o"`
			} `json:"b"`
		}
		if json.Unmarshal(packet, &event) != nil || event.Type != "xt" || event.Body.Object.Command != "login" || event.Body.Object.ID <= 0 {
			return
		}
		g.world.mu.Lock()
		defer g.world.mu.Unlock()
		if g.world.token == token && g.world.generation == generation {
			g.world.avatarID = event.Body.Object.ID
			g.world.avatarName = event.Body.Object.Username
		}
		return
	}
	if packet[0] != '<' {
		return
	}
	type variable struct {
		Name  string `xml:"n,attr"`
		Value string `xml:",chardata"`
	}
	var event struct {
		Type string `xml:"t,attr"`
		Body struct {
			Action string `xml:"action,attr"`
			User   struct {
				ID int `xml:"id,attr"`
			} `xml:"user"`
			Vars  []variable `xml:"vars>var"`
			Users []struct {
				ID   int        `xml:"i,attr"`
				Vars []variable `xml:"vars>var"`
			} `xml:"uLs>u"`
		} `xml:"body"`
	}
	if xml.Unmarshal(packet, &event) != nil || event.Type != "sys" {
		return
	}
	g.world.mu.Lock()
	defer g.world.mu.Unlock()
	if g.world.token != token || g.world.generation != generation || g.world.avatarID <= 0 {
		return
	}
	var vars []variable
	if event.Body.Action == "uVarsUpdate" && event.Body.User.ID == g.world.avatarID {
		vars = event.Body.Vars
	}
	if event.Body.Action == "joinOK" {
		for _, user := range event.Body.Users {
			if user.ID == g.world.avatarID {
				vars = user.Vars
				break
			}
		}
	}
	for _, v := range vars {
		if v.Name != "items" {
			continue
		}
		var items []outfitItem
		if json.Unmarshal([]byte(v.Value), &items) == nil && items != nil {
			g.Accounts.UpdateOutfit(g.world.avatarName, outfitIDs(items))
		}
		break
	}
}
