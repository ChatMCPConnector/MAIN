package app

import "testing"

// The panel's fill-in template must enter the pool just like a raw cookie string.
// The criterion is "what you fill in is what gets assembled" — a broken normalization
// would store a whole JSON blob in the pool, breaking SAPISID extraction and requests.
func TestNormalizeCookieForms(t *testing.T) {
	want := "SID=a; HSID=b; SSID=c; APISID=d; SAPISID=e; __Secure-1PSID=f; __Secure-1PSIDTS=g"

	cases := []struct{ name, in, want string }{
		{"原始串原样通过", want, want},
		{
			"填好的 JSON 模板",
			`{"SID":"a","HSID":"b","SSID":"c","APISID":"d","SAPISID":"e",
			  "__Secure-1PSID":"f","__Secure-1PSIDTS":"g"}`,
			want,
		},
		{
			// JSON key order must not affect the result, otherwise the same cookie
			// pasted in a different order becomes two distinct accounts and dedup breaks
			"模板字段顺序打乱",
			`{"SAPISID":"e","__Secure-1PSIDTS":"g","HSID":"b","SID":"a",
			  "__Secure-1PSID":"f","APISID":"d","SSID":"c"}`,
			want,
		},
		{
			"留空的项自动跳过",
			`{"SID":"a","HSID":"","SSID":"  ","SAPISID":"e"}`,
			"SID=a; SAPISID=e",
		},
		{
			// extra fields the user copied from DevTools must not be lost; appended
			// after the template fields, sorted by name
			"模板外的字段保留",
			`{"SID":"a","SAPISID":"e","NID":"z","AEC":"y"}`,
			"SID=a; SAPISID=e; AEC=y; NID=z",
		},
		{"旧单 cookie 的 JSON 形态", `{"cookie":"SID=a; SAPISID=e","sapisid":"e"}`, "SID=a; SAPISID=e"},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			got, ok := normalizeCookie(c.in, "test")
			if !ok {
				t.Fatal("parse failed")
			}
			if got != c.want {
				t.Errorf("got %q\nwant %q", got, c.want)
			}
		})
	}
}

// A blank template must be rejected. The field name "SAPISID" is present even in a
// blank template, so the criterion has to be "any non-empty value", not "SAPISID
// appearing anywhere in the string".
func TestAccountAddRejectsBlankTemplate(t *testing.T) {
	resetSeedState(t)
	blank := `{"SID":"","HSID":"","SSID":"","APISID":"","SAPISID":"","__Secure-1PSID":"","__Secure-1PSIDTS":""}`
	if _, err := accountAdd("空模板", blank, ""); err == nil {
		t.Fatal("an empty template was put into the pool")
	}
	if n := len(accountList()); n != 0 {
		t.Errorf("the pool gained %d extra entries", n)
	}
}

// A filled-in template must actually enter the pool, storing the assembled bare string, not JSON.
func TestAccountAddAcceptsTemplate(t *testing.T) {
	resetSeedState(t)
	filled := `{"SID":"a","HSID":"b","SSID":"c","APISID":"d","SAPISID":"e","__Secure-1PSID":"f","__Secure-1PSIDTS":""}`
	if _, err := accountAdd("模板", filled, ""); err != nil {
		t.Fatal(err)
	}
	list := accountList()
	if len(list) != 1 {
		t.Fatalf("should have 1 entry, actually %d", len(list))
	}
	want := "SID=a; HSID=b; SSID=c; APISID=d; SAPISID=e; __Secure-1PSID=f"
	if list[0].Cookie != want {
		t.Errorf("stored %q\nwant %q", list[0].Cookie, want)
	}
	if extractSAPISID(list[0].Cookie) != "e" {
		t.Error("SAPISID not extractable after entering the pool")
	}
}

// Strings copied from DevTools don't necessarily carry spaces. Splitting on "; "
// would treat the whole string as one key, so SAPISID gets no value, no
// Authorization header is sent, the upstream treats the request as anonymous —
// while the user sees "success". Another silent downgrade.
func TestCookiePairsWithoutSpaces(t *testing.T) {
	for _, in := range []string{
		"SID=a; SAPISID=b; HSID=c",
		"SID=a;SAPISID=b;HSID=c",
		"  SID=a ;  SAPISID=b ;HSID=c  ",
		"SID=a;\nSAPISID=b;\nHSID=c",
	} {
		if got := extractSAPISID(in); got != "b" {
			t.Errorf("extractSAPISID(%q) = %q, want \"b\"", in, got)
		}
		if n := len(cookieNames(in)); n != 3 {
			t.Errorf("cookieNames(%q) counted %d items, want 3", in, n)
		}
	}
	// a value containing '=' (base64 padding) must only be split at the first equals sign
	if got := extractSAPISID("SAPISID=ab==; SID=x"); got != "ab==" {
		t.Errorf("the equals sign in the value got cut: %q", got)
	}
}

// Space-less strings used to pass accountAdd's substring check yet were stored broken.
func TestAccountAddAcceptsNoSpaceCookie(t *testing.T) {
	resetSeedState(t)
	if _, err := accountAdd("无空格", "SID=a;SAPISID=b;__Secure-1PSID=c", ""); err != nil {
		t.Fatalf("a string without spaces should be able to enter the pool: %v", err)
	}
	if extractSAPISID(accountList()[0].Cookie) != "b" {
		t.Error("SAPISID not extractable after entering the pool")
	}
}
