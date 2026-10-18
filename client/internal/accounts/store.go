// Package accounts stores up to six remembered mogobes for one configured server.
package accounts

import (
	"encoding/json"
	"errors"
	"os"
	"path/filepath"
	"slices"
	"strings"
	"sync"
)

const MaxAccounts = 6
const SavedSessionMarker = "__MOGOBE_SAVED_SESSION__"

type PublicAccount struct {
	ItemIDs    []int  `json:"item_ids"`
	Username   string `json:"username"`
	ColorID    int    `json:"color_id"`
	HasSession bool   `json:"has_session"`
}

type entry struct {
	ItemIDs  []int  `json:"item_ids,omitempty"`
	Username string `json:"username"`
	ColorID  int    `json:"color_id"`
	Token    string `json:"token,omitempty"`
}

type Store struct {
	mu      sync.Mutex
	path    string
	server  string
	entries []entry
}

func Open(path, server string) (*Store, error) {
	s := &Store{path: path, server: server}
	data, err := os.ReadFile(path)
	if errors.Is(err, os.ErrNotExist) {
		return s, nil
	}
	if err != nil {
		return nil, err
	}
	plain, err := unprotect(data, []byte(server))
	if err != nil {
		return nil, errors.New("не удалось расшифровать сохранённые сессии Windows")
	}
	var disk struct {
		Version  int     `json:"version"`
		Accounts []entry `json:"accounts"`
	}
	if err := json.Unmarshal(plain, &disk); err != nil {
		return nil, err
	}
	if disk.Version != 1 || len(disk.Accounts) > MaxAccounts {
		return nil, errors.New("неизвестный формат списка могоби")
	}
	s.entries = disk.Accounts
	return s, nil
}

func (s *Store) List() []PublicAccount {
	s.mu.Lock()
	defer s.mu.Unlock()
	result := make([]PublicAccount, 0, len(s.entries))
	for _, e := range s.entries {
		result = append(result, PublicAccount{Username: e.Username, ColorID: e.ColorID, HasSession: e.Token != "", ItemIDs: append([]int{}, e.ItemIDs...)})
	}
	return result
}

func (s *Store) Token(username string) string {
	s.mu.Lock()
	defer s.mu.Unlock()
	for _, e := range s.entries {
		if strings.EqualFold(e.Username, username) {
			return e.Token
		}
	}
	return ""
}

// Remember returns superseded/evicted tokens so the gateway can revoke them.
func (s *Store) Remember(username string, color int, token string, rememberName, rememberSession bool) ([]string, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	previous := s.entries
	next := make([]entry, 0, MaxAccounts+1)
	if rememberName || rememberSession {
		if !rememberSession {
			token = ""
		}
		var items []int
		for _, e := range previous {
			if strings.EqualFold(e.Username, username) {
				items = e.ItemIDs
				break
			}
		}
		next = append(next, entry{Username: username, ColorID: color, Token: token, ItemIDs: items})
	}
	var removed []string
	for _, e := range previous {
		if strings.EqualFold(e.Username, username) || len(next) >= MaxAccounts {
			if e.Token != "" && e.Token != token {
				removed = append(removed, e.Token)
			}
		} else {
			next = append(next, e)
		}
	}
	s.entries = next
	if err := s.save(); err != nil {
		s.entries = previous
		return nil, err
	}
	return removed, nil
}

// UpdateOutfit stores a display-only snapshot, never ownership or permissions.
// Existing version-1 files without item_ids remain readable.
func (s *Store) UpdateOutfit(username string, items []int) error {
	if len(items) > 24 {
		return errors.New("invalid outfit")
	}
	seen := make(map[int]bool)
	for _, id := range items {
		if id <= 0 || id > 2147483647 || seen[id] {
			return errors.New("invalid outfit")
		}
		seen[id] = true
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	for i, e := range s.entries {
		if !strings.EqualFold(e.Username, username) || slices.Equal(e.ItemIDs, items) {
			continue
		}
		s.entries[i].ItemIDs = append([]int(nil), items...)
		if err := s.save(); err != nil {
			s.entries[i] = e
			return err
		}
		break
	}
	return nil
}

func (s *Store) KeepNames(names []string) ([]string, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	previous := s.entries
	next := make([]entry, 0, len(previous))
	var removed []string
	for _, e := range previous {
		keep := false
		for _, name := range names {
			if strings.EqualFold(name, e.Username) {
				keep = true
				break
			}
		}
		if keep {
			next = append(next, e)
		} else if e.Token != "" {
			removed = append(removed, e.Token)
		}
	}
	s.entries = next
	if err := s.save(); err != nil {
		s.entries = previous
		return nil, err
	}
	return removed, nil
}

func (s *Store) ClearToken(token string) error {
	if token == "" {
		return nil
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	previous := append([]entry(nil), s.entries...)
	changed := false
	for i := range s.entries {
		if s.entries[i].Token == token {
			s.entries[i].Token = ""
			changed = true
		}
	}
	if !changed {
		return nil
	}
	if err := s.save(); err != nil {
		s.entries = previous
		return err
	}
	return nil
}

func (s *Store) save() error {
	data, err := json.Marshal(struct {
		Version  int     `json:"version"`
		Accounts []entry `json:"accounts"`
	}{1, s.entries})
	if err != nil {
		return err
	}
	encrypted, err := protect(data, []byte(s.server))
	if err != nil {
		return err
	}
	if err = os.MkdirAll(filepath.Dir(s.path), 0700); err != nil {
		return err
	}
	f, err := os.CreateTemp(filepath.Dir(s.path), "accounts-*.tmp")
	if err != nil {
		return err
	}
	defer os.Remove(f.Name())
	if _, err = f.Write(encrypted); err != nil {
		f.Close()
		return err
	}
	if err = f.Sync(); err != nil {
		f.Close()
		return err
	}
	if err = f.Close(); err != nil {
		return err
	}
	return os.Rename(f.Name(), s.path)
}
