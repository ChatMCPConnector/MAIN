package app

import "testing"

// Repeated auth failures must auto-disable the account, otherwise a dead one
// stays at the front of the pick queue and every request pays one XSRF round
// trip before it even gets to fail.
func TestAutoDisableAfterAuthFailures(t *testing.T) {
	id, err := accountAdd("dead", "SAPISID=aaa; __Secure-1PSID=bbb", "")
	if err != nil {
		t.Fatalf("failed to insert account: %v", err)
	}
	t.Cleanup(func() { _ = accountDelete(id) })

	for i := 1; i < maxCookieAuthFailures; i++ {
		markCookieByStatus(id, 401, "no SNlM0e")
		if a := accountByID(id); a == nil || a.Status != "enabled" {
			t.Fatalf("disabled after only %d failures, too early", i)
		}
	}
	markCookieByStatus(id, 401, "no SNlM0e")
	if a := accountByID(id); a == nil || a.Status != "disabled" {
		t.Errorf("should auto-disable after %d consecutive auth failures, got %+v", maxCookieAuthFailures, a)
	}
}

// Non-auth failures must not increment fail_count, let alone disable —
// residential egress degrades often; counting 302/network errors would get
// good cookies wrongly ranked as "most failing".
func TestNonAuthFailureDoesNotDisable(t *testing.T) {
	id, err := accountAdd("noisy", "SAPISID=ccc; __Secure-1PSID=ddd", "")
	if err != nil {
		t.Fatalf("failed to insert account: %v", err)
	}
	t.Cleanup(func() { _ = accountDelete(id) })

	for i := 0; i < maxCookieAuthFailures+2; i++ {
		markCookieByStatus(id, 302, "sorry page")
		markCookieByStatus(id, 0, "network error")
	}
	a := accountByID(id)
	if a == nil || a.Status != "enabled" || a.FailCount != 0 {
		t.Errorf("non-auth failures must not affect health, got %+v", a)
	}
}

// Success resets the counter, otherwise sporadic failures accumulate up to
// the disable threshold.
func TestSuccessResetsFailCount(t *testing.T) {
	id, err := accountAdd("flappy", "SAPISID=eee; __Secure-1PSID=fff", "")
	if err != nil {
		t.Fatalf("failed to insert account: %v", err)
	}
	t.Cleanup(func() { _ = accountDelete(id) })

	markCookieByStatus(id, 401, "x")
	markCookieByStatus(id, 200, "")
	markCookieByStatus(id, 401, "x")
	markCookieByStatus(id, 401, "x")
	if a := accountByID(id); a == nil || a.Status != "enabled" {
		t.Errorf("an intermediate success should reset the count, not disable, got %+v", a)
	}
}

// A refresh result is only written back if its identity matches the stored
// one. Without that check, an upstream that swaps the whole session in its
// response would silently write account A's credentials into account B's
// row — the panel still shows the original label but the requests go out
// with someone else's session.
func TestUpdateAccountCookieIdentityGuard(t *testing.T) {
	orig := "SAPISID=keep; __Secure-1PSID=same; SIDCC=old"
	id, err := accountAdd("guarded", orig, "")
	if err != nil {
		t.Fatalf("failed to insert account: %v", err)
	}
	t.Cleanup(func() { _ = accountDelete(id) })

	// Only SIDCC refreshed: identity unchanged, must be written back
	refreshed := "SAPISID=keep; __Secure-1PSID=same; SIDCC=new"
	updateAccountCookie(id, refreshed)
	if a := accountByID(id); a == nil || a.Cookie != refreshed {
		t.Errorf("a refresh with the same identity should be written back, got %+v", a)
	}

	// SAPISID changed: not the same account anymore, must be discarded
	updateAccountCookie(id, "SAPISID=other; __Secure-1PSID=same; SIDCC=x")
	if a := accountByID(id); a == nil || a.Cookie != refreshed {
		t.Errorf("a changed SAPISID should be discarded, got cookie=%q", a.Cookie)
	}

	// __Secure-1PSID changed: same deal
	updateAccountCookie(id, "SAPISID=keep; __Secure-1PSID=other; SIDCC=x")
	if a := accountByID(id); a == nil || a.Cookie != refreshed {
		t.Errorf("a changed __Secure-1PSID should be discarded, got cookie=%q", a.Cookie)
	}
}
