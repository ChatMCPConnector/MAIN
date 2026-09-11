package app

import "testing"

// Repeated auth failures must auto-disable the account, otherwise a dead one
// stays at the front of the pick queue and every request pays one XSRF round
// trip before it even gets to fail.
func TestAutoDisableAfterAuthFailures(t *testing.T) {
	id, err := accountAdd("dead", "SAPISID=aaa; __Secure-1PSID=bbb", "")
	if err != nil {
		t.Fatalf("插账号失败: %v", err)
	}
	t.Cleanup(func() { _ = accountDelete(id) })

	for i := 1; i < maxCookieAuthFailures; i++ {
		markCookieByStatus(id, 401, "no SNlM0e")
		if a := accountByID(id); a == nil || a.Status != "enabled" {
			t.Fatalf("第 %d 次失败就被停用了，太早", i)
		}
	}
	markCookieByStatus(id, 401, "no SNlM0e")
	if a := accountByID(id); a == nil || a.Status != "disabled" {
		t.Errorf("连续 %d 次鉴权失败后应自动停用, got %+v", maxCookieAuthFailures, a)
	}
}

// Non-auth failures must not increment fail_count, let alone disable —
// residential egress degrades often; counting 302/network errors would get
// good cookies wrongly ranked as "most failing".
func TestNonAuthFailureDoesNotDisable(t *testing.T) {
	id, err := accountAdd("noisy", "SAPISID=ccc; __Secure-1PSID=ddd", "")
	if err != nil {
		t.Fatalf("插账号失败: %v", err)
	}
	t.Cleanup(func() { _ = accountDelete(id) })

	for i := 0; i < maxCookieAuthFailures+2; i++ {
		markCookieByStatus(id, 302, "sorry page")
		markCookieByStatus(id, 0, "network error")
	}
	a := accountByID(id)
	if a == nil || a.Status != "enabled" || a.FailCount != 0 {
		t.Errorf("非鉴权失败不该动健康度, got %+v", a)
	}
}

// Success resets the counter, otherwise sporadic failures accumulate up to
// the disable threshold.
func TestSuccessResetsFailCount(t *testing.T) {
	id, err := accountAdd("flappy", "SAPISID=eee; __Secure-1PSID=fff", "")
	if err != nil {
		t.Fatalf("插账号失败: %v", err)
	}
	t.Cleanup(func() { _ = accountDelete(id) })

	markCookieByStatus(id, 401, "x")
	markCookieByStatus(id, 200, "")
	markCookieByStatus(id, 401, "x")
	markCookieByStatus(id, 401, "x")
	if a := accountByID(id); a == nil || a.Status != "enabled" {
		t.Errorf("中间成功过就该清零，不应停用, got %+v", a)
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
		t.Fatalf("插账号失败: %v", err)
	}
	t.Cleanup(func() { _ = accountDelete(id) })

	// Only SIDCC refreshed: identity unchanged, must be written back
	refreshed := "SAPISID=keep; __Secure-1PSID=same; SIDCC=new"
	updateAccountCookie(id, refreshed)
	if a := accountByID(id); a == nil || a.Cookie != refreshed {
		t.Errorf("同身份的刷新应写回, got %+v", a)
	}

	// SAPISID changed: not the same account anymore, must be discarded
	updateAccountCookie(id, "SAPISID=other; __Secure-1PSID=same; SIDCC=x")
	if a := accountByID(id); a == nil || a.Cookie != refreshed {
		t.Errorf("换了 SAPISID 应丢弃不写, got cookie=%q", a.Cookie)
	}

	// __Secure-1PSID changed: same deal
	updateAccountCookie(id, "SAPISID=keep; __Secure-1PSID=other; SIDCC=x")
	if a := accountByID(id); a == nil || a.Cookie != refreshed {
		t.Errorf("换了 __Secure-1PSID 应丢弃不写, got cookie=%q", a.Cookie)
	}
}
