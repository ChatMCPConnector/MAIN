package app

import (
	"encoding/json"
	"io"
	"net/http"
	"strconv"
	"strings"
)

// keyCookieWants lists the key items checked to judge whether a cookie was "copied in full".
//
// Packet capture showed browsers send 30 cookies to gemini.google.com each time,
// 16 of which are login-state items present on every request. We only surface the
// few that best reflect "fully copied or not" — not that the others don't matter:
// we forward the whole string as-is, and one missing means one not sent.
var keyCookieWants = []string{"SID", "HSID", "SSID", "APISID", "SAPISID",
	"__Secure-1PSID", "__Secure-1PSIDTS", "__Secure-1PAPISID", "__Secure-1PSIDCC"}

// cookieAcctView is a redacted account view: **no full cookie values**, status summary only.
// Credentials have no business being sent back to the browser by the server (same principle as the old handleAdminCookie).
func cookieAcctView(a CookieAccount) map[string]interface{} {
	names := cookieNames(a.Cookie)
	nameSet := map[string]bool{}
	for _, n := range names {
		nameSet[n] = true
	}
	var key []string
	for _, w := range keyCookieWants {
		if nameSet[w] {
			key = append(key, w)
		}
	}
	tail := ""
	if s := extractSAPISID(a.Cookie); len(s) >= 4 {
		tail = s[len(s)-4:]
	}
	// health is a derived health value for coloring the panel red (#18). It uses fail_count:
	// markAccountResult resets it to zero on success and only increments on failure, and only
	// 401/403 count as failures (see markCookieByStatus), so fail_count>0 means "auth currently
	// failing" = most likely an expired cookie — mark red and prompt for re-import.
	//   dead     auth failing (red) — regardless of enabled or auto-disabled, whenever fail_count>0
	//   disabled manually disabled by the user with no failures recorded (grey)
	//   unknown  never used/checked successfully yet (pending check)
	//   ok       in use, no failures (green)
	health := "ok"
	switch {
	case a.FailCount > 0:
		health = "dead"
	case a.Status != "enabled":
		health = "disabled"
	case a.LastOkAt == 0:
		health = "unknown"
	}
	return map[string]interface{}{
		"id":           a.ID,
		"label":        a.Label,
		"status":       a.Status,
		"health":       health,
		"note":         a.Note,
		"created_at":   a.CreatedAt,
		"last_used_at": a.LastUsedAt,
		"last_ok_at":   a.LastOkAt,
		"last_error":   a.LastError,
		"fail_count":   a.FailCount,
		"cookie_count": len(names),
		"key_cookies":  key,
		"sapisid_tail": tail,
		"has_1psidts":  nameSet["__Secure-1PSIDTS"],
		"proxy_id":     a.ProxyID,
		"proxy_name":   proxyNameByID(a.ProxyID),
	}
}

// handleAdminCookies — GET lists the pool / POST adds one entry.
func handleAdminCookies(w http.ResponseWriter, r *http.Request) {
	switch r.Method {
	case http.MethodGet:
		accts := accountList()
		items := make([]map[string]interface{}, 0, len(accts))
		for _, a := range accts {
			items = append(items, cookieAcctView(a))
		}
		total, enabled := accountCount()
		writeJSON(w, 200, map[string]interface{}{
			"items": items, "total": total, "enabled": enabled,
		})
	case http.MethodPost:
		var p struct {
			Label  string `json:"label"`
			Cookie string `json:"cookie"`
			Note   string `json:"note"`
		}
		body, _ := io.ReadAll(r.Body)
		if err := json.Unmarshal(body, &p); err != nil {
			writeJSON(w, 400, map[string]string{"error": "bad json"})
			return
		}
		id, err := accountAdd(p.Label, p.Cookie, p.Note)
		if err != nil {
			writeJSON(w, 400, map[string]string{"error": err.Error()})
			return
		}
		logf("[cookies] account added #%d label=%q", id, strings.TrimSpace(p.Label))
		writeJSON(w, 200, map[string]interface{}{"id": id})
	default:
		writeJSON(w, 405, map[string]string{"error": "method not allowed"})
	}
}

// handleAdminCookieItem — /admin/api/cookies/{id}[/toggle]
//
//	DELETE          delete
//	POST .../toggle flip enabled/disabled
//	PATCH           update label / note / status
func handleAdminCookieItem(w http.ResponseWriter, r *http.Request) {
	rest := strings.TrimPrefix(r.URL.Path, "/admin/api/cookies/")
	parts := strings.Split(rest, "/")
	if len(parts) < 1 || parts[0] == "" {
		writeJSON(w, 404, map[string]string{"error": "missing id"})
		return
	}
	id, err := strconv.ParseInt(parts[0], 10, 64)
	if err != nil {
		writeJSON(w, 400, map[string]string{"error": "bad id"})
		return
	}
	action := ""
	if len(parts) > 1 {
		action = parts[1]
	}

	switch r.Method {
	case http.MethodDelete:
		if err := accountDelete(id); err != nil {
			writeJSON(w, 500, map[string]string{"error": err.Error()})
			return
		}
		logf("[cookies] account deleted #%d", id)
		writeJSON(w, 200, map[string]bool{"ok": true})
	case http.MethodPost:
		if action == "rotate" {
			for _, a := range accountList() {
				if a.ID == id {
					iv, names, err := rotateAccount(a)
					if err != nil {
						writeJSON(w, 200, map[string]interface{}{"ok": false, "detail": err.Error()})
						return
					}
					detail := "keepalive succeeded"
				if len(names) > 0 {
					detail = "keepalive succeeded, refreshed " + strings.Join(names, ", ")
				}
					writeJSON(w, 200, map[string]interface{}{
						"ok": true, "detail": detail, "refreshed": names, "next_sec": int(iv.Seconds())})
					return
				}
			}
			writeJSON(w, 404, map[string]string{"error": "account not found"})
			return
		}
		if action == "check" {
			for _, a := range accountList() {
				if a.ID == id {
					writeJSON(w, 200, checkAccountCookie(a))
					return
				}
			}
			writeJSON(w, 404, map[string]string{"error": "account not found"})
			return
		}
		if action != "toggle" {
			writeJSON(w, 400, map[string]string{"error": "unknown action"})
			return
		}
		cur := ""
		for _, a := range accountList() {
			if a.ID == id {
				cur = a.Status
				break
			}
		}
		next := "enabled"
		if cur == "enabled" {
			next = "disabled"
		}
		if err := accountSetStatus(id, next); err != nil {
			writeJSON(w, 500, map[string]string{"error": err.Error()})
			return
		}
		writeJSON(w, 200, map[string]interface{}{"status": next})
	case http.MethodPatch:
		var p struct {
			Label  *string `json:"label"`
			Note   *string `json:"note"`
			Status *string `json:"status"`
		}
		body, _ := io.ReadAll(r.Body)
		if err := json.Unmarshal(body, &p); err != nil {
			writeJSON(w, 400, map[string]string{"error": "bad json"})
			return
		}
		if p.Status != nil {
			if err := accountSetStatus(id, *p.Status); err != nil {
				writeJSON(w, 400, map[string]string{"error": err.Error()})
				return
			}
		}
		if p.Label != nil || p.Note != nil {
			// only modify fields that were sent: unsent ones keep their current values.
			var curLabel, curNote string
			for _, a := range accountList() {
				if a.ID == id {
					curLabel, curNote = a.Label, a.Note
					break
				}
			}
			if p.Label != nil {
				curLabel = *p.Label
			}
			if p.Note != nil {
				curNote = *p.Note
			}
			if err := accountUpdateMeta(id, curLabel, curNote); err != nil {
				writeJSON(w, 500, map[string]string{"error": err.Error()})
				return
			}
		}
		writeJSON(w, 200, map[string]bool{"ok": true})
	default:
		writeJSON(w, 405, map[string]string{"error": "method not allowed"})
	}
}
