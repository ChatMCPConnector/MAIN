# Changelog

This project follows [Semantic Versioning](https://semver.org/).

## 4.20.0

### Added

- **Cookie pool flags dead accounts in red** (issue #18). When an account's auth has failed
  (`fail_count>0`, i.e. 401/403), the panel's status column marks it red as "suspected dead",
  the whole row gets a red background with a left red bar, and a header summary shows
  "N suspected dead" — you can see at a glance which ones to re-export from Firefox.
  A manual "check" that finds it dead turns it red immediately; passing the check or a
  successful use turns it back to normal automatically. (The embedded mini browser also
  proposed in #18 won't be done — it conflicts with the single-binary design.)

## 4.19.0

### Added

- **Automatic cookie renewal** (issue #6, merges @s1oz's #25). Previously the 10-minute
  `RotateCookies` keepalive used the browser iframe path `[658, session_id]`, which only
  refreshes `SIDCC` / `*PSIDCC` and **cannot mint** a new `__Secure-1PSIDTS` — that's the
  short-lived ticket expiring in ~30 minutes, which is why signed-in accounts looked like
  they died after half an hour and the keepalive button couldn't save them. Now the sentinel
  payload `[000,"-0000000000000000000"]` is sent first (carrying only the
  `__Secure-1PSID` + `__Secure-1PSIDTS` subset — more entries cause a 401) to mint a fresh
  `*PSIDTS`, then the original SIDCC keepalive runs; the first refresh fires 15 seconds
  after import, and the same account is not pinged twice within 60 seconds (to avoid 429).
- Measured (pure HTTP, no browser at any point): a static cookie without the sentinel dies
  in 20-30 minutes; with the sentinel it stayed alive for 3 hours straight. **Cookies exported
  from Firefox can be renewed indefinitely**; Chrome's new device-bound sessions (DBSC) fail
  the renewal with 401 — if you see repeated 401s, re-login in Firefox and export again.

## 4.18.0

### Added

- **Anonymous-first switch `anon_first`** (issue #20). Off by default. When on, requests that
  don't need a signed-in session (plain text, no thinking, no tools, no images) go out
  anonymously without consuming a cookie account, maximally saving account quota; only
  3.1 Pro / 3.8 Flash / extended thinking / image·music·video·canvas / file upload etc.
  pick an account. Toggle it on the Settings page.

### Fixed

- **Concurrent account picks could select the same account.** Picking is two steps —
  "SELECT the least-recently-used account + UPDATE to mark it just used" — which previously
  weren't serialized: concurrent requests would SELECT the same account and each UPDATE it,
  using it simultaneously and breaking the rotation. A lock now makes the two steps atomic.

## 4.17.0

### Added

- **Settings page gains the "server-side multi-turn continuation" (`multi_turn`) switch**
  (issue #27). This runtime switch had existed all along, but could previously only be
  enabled by hand-writing `config.json` — it wasn't on the panel and no environment variable
  was read, which was especially awkward on docker/Synology-style deployments. Now it's a
  checkbox on the Settings page. When on, one continuous conversation reuses the same Gemini
  web session (continuation is recognised by history prefix; on a hit only the newest message
  is sent while history stays server-side), instead of opening a new session per message.

### Fixed

- **`multi_turn` was silently reset to `false` after clicking "save and apply" in the panel.**
  It was the only runtime field missing from the panel's config form, and saving went through
  full deserialisation — fields not carried by the form decoded to zero values, so saving once
  in the panel would also wipe a `multi_turn` set in `config.json`. Listed in the form and
  fixed.

## 4.16.0

### Added

- **`gemini-3.8-flash` (+ `-thinking`)** (issue #26). Google bumped the original 3.7 Flash
  hex (`56fdd199312815e2`) to 3.8 in place — same hex, the server-side display name changed
  from `"3.7 Flash"` to `"3.8 Flash"` (confirmed via paid-account HAR response frames).
  **Paid Gemini accounts only** (not a gradual rollout): free accounts still get downgraded
  to 3.5 Flash-Lite. `gemini-3.7-flash` / `gemini-3.7-flash-thinking` remain as aliases
  (same hex), so old clients are unaffected.

## 4.15.0

### Added

- **`/v1/videos` endpoint** (issue #24). OpenAI (Sora)-shaped async video generation:
  `POST /v1/videos` {model, prompt} creates a job and immediately returns `{id, status}`;
  `GET /v1/videos/{id}` polls the status; `GET /v1/videos/{id}/content` downloads the MP4
  once finished. Under the hood it reuses the `gemini-video` generation chain (needs a
  signed-in Pro account). Video takes tens of seconds to minutes, so async fits better than
  the blocking chat/completions style. The original `/v1/chat/completions` +
  `model=gemini-video` (returns a base64 data URL) remains available.

## 4.14.0

### Added

- **MySQL / PostgreSQL support** (issue #22). Just set the `SQL_DSN` environment variable;
  unset still defaults to SQLite, nothing to change. `SQL_DSN=mysql://user:pass@host:3306/db`
  or `postgres://user:pass@host:5432/db?sslmode=disable`. Tables are created automatically;
  all three backends share one schema; dialect differences (`?`/`$N` placeholders, upsert,
  auto-increment primary keys, TEXT key columns, `IFNULL`/`COALESCE`) are all confined to
  `dbdialect.go` — the ~70 queries in the business layer are untouched. Verified against real
  mysql8 and pg16 instances.

### Fixed

- SSE responses now carry `X-Accel-Buffering: no`, so streaming through reverse proxies like
  nginx is no longer buffered into a single flush (clients connecting directly were already
  streaming; only deployments "with their own reverse proxy in front" need this). Note: the
  one-shot output seen with Dify in issue #21 is NOT this — testing showed Dify's squid
  (ssrf_proxy) passes streams through transparently; that problem is on Dify's side.

## 4.13.0

### Added

- **Video input.** Clients pass `video_url` / `input_video` (data URL) in the content and
  the model can analyse the video — same upload path as image input (file tuple type marker
  2 = video). Needs a cookie (anonymous references are refused upstream). Tested with a
  red→green→blue test clip, asking which three colours appear in order; the model answered
  "red, green, blue" — it really watched it frame by frame.
- **Video generation** (`gemini-video`). `inner[49]=11` submits an async job; polling hNvQHb
  yields the `contribution.usercontent.google.com` download link, and the MP4 is fetched back
  (base64 data URL). Tested with "sunset ocean waves" — produced a real 10-second 720p
  H.264+AAC video. **Needs a Pro/paid account** (self-reports 3.7 Flash); free accounts get
  an explicit error when Google's video content policy refuses. Generation takes tens of
  seconds to minutes, so clients should set a long timeout.
- **Auto-delete conversation** (issue #19, config `auto_delete_conversation`, off by default).
  After a result is produced, the conversation it left on gemini.google.com is deleted
  automatically (rpc GzXR5e), so accounts don't pile them up. Signed-in only; async
  best-effort, doesn't affect the response.

## 4.12.0

### Fixed

- **Agentic client tool loops now converge** (follow-up to #15). Command success results from
  clients like Codex arrive as a wrapped text "Process exited with code 0 / Output: (empty)";
  commands like writing a file or setting a value have no stdout, and weak models (especially
  anonymous 3.6 Flash) read "no output" as "didn't work", then retry with a different
  formulation over and over — measured: the task "write hello to a.txt" tried 26 different
  commands over 90 seconds without converging (the file was actually correct the first time).
  Tool results are now condensed into a one-line clean success/failure signal (✅ exit 0 with
  a note that no output is normal — don't re-run; ❌ exit N), plus a termination clause in the
  instructions (stop on success; don't retry the same thing). Measured: the same task dropped
  from 26-27 rounds to 2-4 rounds, with a normal final answer. The termination clause alone
  without the clean signal does nothing — the two must go together.

## 4.11.0

### Fixed

- **Requests with tools giving off-topic replies** (issue #15). Requests from agentic clients
  (Codex etc.) carry tens of KB of the client's own developer prompt in the middle, containing
  native-tool phrasing like "emit function calls to run terminal commands", which buried our
  ```tool_call``` format instructions at the very top — the model then answered "I have no
  tools / cannot access the filesystem" or answered the wrong question. `buildPrompt` now
  re-anchors the tool format after all messages (right next to the user's question, with a
  behavioural example making clear that the only execution channel is ```tool_call```, no
  ```powershell blocks shown to the user, one call at a time), and the fence regex is loosened
  to tolerate the model's inline variants (no newlines). Verified with the real Codex client:
  tools invoke correctly; plain chat with tools attached doesn't mis-trigger.
- **Pure-code-artifact responses no longer come back empty and cause a 502.** On math /
  expression questions the model runs code directly and the whole reply is just the execution
  artifact; after scrubbing the `?code_reference/stdout` markers it was empty, which was
  treated as "no content frame" and reported as 502. Now, if the scrubbed result is empty,
  the code and its result are kept and returned as a normal code block.

## 4.10.0

### Added

- **`gemini-canvas` (canvas).** Generates an immersive interactive HTML document. Unlike
  image/music generation, the artifact is HTML and **inlined in the response** (a ```html
  block), no extra download needed. Needs a cookie; not exposed without one. Measured: returns
  a complete `<!DOCTYPE html>…</html>` interactive page (with scripts); clients can extract
  and render it.

## 4.9.0

### Added

- **Admin panel language toggle (Chinese/English)** (issue #13). A language button was added
  to the top bar — Chinese by default, click once to switch to English (remembered in
  localStorage). About 190 strings covering navigation, KPIs, table headers, buttons,
  dropdowns, status badges, runtime config fields and hints, error categories, connectivity
  diagnostics, dialogs, and the deployment table. Interpolated sentences with numeric
  variables (e.g. "roughly N more requests before the block") stay Chinese.

## 4.8.0

### Fixed

- **Image generation fetches the original image** (issue #14). The plain gg-dl link
  downloads a ~500px (512×279) thumbnail by default; appending `=s0` to the link fetches
  the original resolution (measured: 1408×768). Format is still PNG.
- **Media models no longer lose their artifacts to the multi-turn path.** Since 4.5.0, when
  the multi-turn gate was widened to requests with tools, media models (image/music) also
  entered the multi-turn path — but multi-turn only handles text, so with `multi_turn` on,
  calling `gemini-image` / `gemini-music` returned just a placeholder sentence with no
  image/music. Media models now always take the artifact-retrieval path, regardless of the
  `multi_turn` switch.

## 4.7.0

### Added

- **`gemini-3.7-flash` (including the `-thinking` variant).** Gemini's web app rolls out
  3.7 Flash per account; wired it in. Needs a cookie, and **the account must be enrolled in
  the 3.7 rollout**, otherwise it degrades to 3.5 Flash-Lite (same as 3.1 Pro — no cookie /
  no rollout means no fake success).

  The hex is the 3.7 entry's primary hex `56fdd199312815e2` (it appears in the otAQ7b lists
  of two independently enrolled accounts, and users with 3.7 tested that sending it reports
  "3.7 Flash"). Not the compat list's `797f3d0293f288ad` — that's a "current Flash" generic
  pointer; older accounts sending it get 3.6, which would pass 3.6 off as 3.7.

## 4.6.0

### Fixed

- **Streaming `tool_calls` now carry the `index` field** (issue #10). Each tool_call in a
  streaming delta was missing `index`, which the OpenAI streaming spec says clients use to
  stitch sharded tool_calls together; without it some clients couldn't reassemble them. It's
  now assigned in order to each one.

## 4.5.0

### Fixed

- **`/v1/responses` streaming completes the item lifecycle events.** Previously it emitted
  `response.created` and went straight to `output_text.delta`, skipping the
  `response.output_item.added` + `content_part.added` declarations. Strict Responses clients
  (Codex, zcode, etc.) abort mid-stream on a non-compliant event sequence ("OutputTextDelta
  without active item" / "Turn execution failed"), while the HTTP request itself returns 200
  and chat mode is unaffected — so the panel looks fine and it's very hard to locate. The
  full lifecycle for both message and function_call items is now emitted: added →
  content_part → done.

### Added

- **Optional multi-turn (`multi_turn`, off by default).** When on, requests use Gemini's
  native conversation_id server-side continuation: the client resends the full history each
  turn, the server fingerprints "history minus the last message" to detect a continuation,
  and on a hit sends only the newest message while history stays on Google's servers —
  bypassing the ~130KB single-request wall. Works signed-in or anonymous (anonymously, the
  first turn does an in-place GET /app to grab a session cookie as the conversation carrier —
  no account needed). Agentic clients with tools also take this path.

  Measured: two 110KB turns that would hit the byte wall with full resend and get 400 —
  with continuation only the new message is sent → 200; long conversations no longer hit the
  wall. Note that multi-turn does **not** enlarge the model's context window — content past
  the window is still evicted (a sliding window keeps the recent part). It solves "long
  conversation without hitting the single-request wall + keeping recent context", not
  "feeding a huge document".

## 4.4.0

### Added

- **Image / music generation.** Two new models, `gemini-image` (Nano Banana) and
  `gemini-music` (Lyria, ~30 seconds), via `/v1/chat/completions`. The artifact bytes are
  placed directly into the returned `content` as a **base64 data URL** (image `![]`, audio
  `[]`) — no external link, since links need the cookie to download and clients couldn't
  fetch them. Both need a signed-in session; not listed in `/v1/models` without a cookie.

  Artifact retrieval was stuck for a long time on a download 403; three root causes
  (confirmed via packet capture + testing): the download host only accepts the 18 cookies
  from `.google.com` domains (sending the whole string, including the accounts-host-only
  ones, gets a 403); the image link cross-domain 302 means clients don't carry the Cookie to
  the new domain by default (solved by following manually and re-sending per hop); the image
  response returns a `gg-dl` plain link whose GET only yields a text/plain pointer — the real
  image requires switching to the `rd-gg-dl` prefix.

  base64 is not counted in output tokens — a single image is millions of characters; billing
  by it would charge users for binary data.

  Measured: `gemini-image` → 512×279 PNG (106KB, decodable); `gemini-music` → 744KB valid
  MP3.

## 4.3.0

### Added

- **MCP server (web_search).** Besides the OpenAI API, the same process and port now also
  serves an MCP server at `/mcp`, exposing Gemini's web-grounded search as a `web_search`
  tool, letting MCP clients (Claude Desktop / Claude Code / Cursor) "search the web through
  Gemini" and get a synthesized answer plus source links back.

  The transport is HTTP (Streamable HTTP); once deployed as a server, remote clients just
  point at the URL, reusing the backend's account pool / proxy pool / rate limiting; search
  works anonymously, no cookie required. Authenticated with the same API key
  (`Authorization: Bearer <key>`). Hand-written JSON-RPC 2.0, no third-party SDK.

  Client configuration is in the README's "MCP" section. `web_search(query)` returns the
  answer with a `Sources:` list appended.

- **Grounded search sources are parsed out.** Previously only the answer text was returned
  and the grounding sources were dropped; now each source's url / title / snippet is
  extracted from the response frames, with the `#:~:text=` fragment anchor stripped from the
  URL tail. Currently used by the MCP `web_search` tool; OpenAI API responses are unaffected.

## 4.2.0

### Added

- **Extended thinking: available on all three models.** Added
  `gemini-3.6-flash-thinking` / `gemini-3.5-flash-lite-thinking` /
  `gemini-3.1-pro-thinking`. The model name the backend reports carries `Extended`, and the
  reasoning chain measured 2467 / 1059 / 583 characters (versus 0 / 0 / 268 for the plain
  versions). Like 3.1 Pro, only exposed when a cookie is attached — anonymous requests
  carrying the toggle are silently ignored by the server (re-verified with the complete
  header; it's not us failing to send it).

  It's the web UI's "extended thinking" toggle, orthogonal to the model — not three
  additional models.

  **The switch lives in the model header, not the payload.** We originally sent only the
  5-element minimal form `[1,null,null,null,"<hex>"]`; the browser sends 18 elements, where
  index 14 = model MODE and index 15 = the thinking bit. Setting only `inner[80]=2` in the
  payload left all three models' reasoning chains at 0 characters; adding the header is what
  makes it work — the same rule as model selection itself, where "the header overrides
  inner[79]".

  Alongside: `inner` was widened from 80 to 97 slots (the browser sends 97-98 slots; in an
  80-length array `inner[80]` has no position at all); `x-goog-ext-525005358-jspb` plus the
  fixed-value `x-goog-ext-73010989-jspb` / `-73010990-jspb` are now sent; `inner[91]` /
  `inner[96]` were added. After all that, a slot-by-slot comparison with the browser differs
  only in `[3,4]` — the botguard token and its paired nonce: the server doesn't accept ours
  for those two, so they are deliberately not sent.

### Fixed

- **Dead accounts are auto-disabled**: after 3 consecutive auth failures (only 401/403
  counts), the account is switched to disabled. Previously `fail_count` only ever grew and
  was never acted on, and picking uses `ORDER BY fail_count ASC` — bad accounts sort last,
  but when only bad accounts remain they still get picked, so every request had to pay one
  XSRF round-trip for it before erroring. Disabling doesn't delete: cookies are
  user-imported data, the judgement can be wrong, and they're left for the user to decide.
- **Identity is verified before refreshing a cookie**: after merging Set-Cookie, if
  `SAPISID` or `__Secure-1PSID` changed, the whole merge is discarded. Without the check, an
  upstream that swapped the entire session in a response would silently write account A's
  credentials into account B's row — the panel would still show the original label while the
  session actually sent out is someone else's.
- **One rescue attempt before declaring a cookie dead**: when the XSRF token can't be
  fetched, a forced rotation runs first and the fetch is retried; only if that fails does it
  move to the next account. Previously it switched accounts immediately, giving up on one
  that might merely be stale.

## 4.1.1

### Fixed

- **Panel couldn't open when reverse-proxied under a sub-path** (e.g.
  `example.com/gemini/admin`). The 30 URLs in `index.html` were absolute; the browser
  resolved them against the site root, so they all landed on `example.com/admin/api/…` and
  the prefix was lost. They are now relative.

  One pitfall worth spelling out: **making them relative alone is not enough**. Relative
  URLs resolve against the document URL's *directory*, and the directories of `/admin` and
  `/admin/` differ by one level — `api/stats` under `/gemini/admin/` resolves to
  `/gemini/admin/api/stats` (right), but under `/gemini/admin` it resolves to
  `/gemini/api/stats` (wrong). So the server 301s `/admin` to `admin/`, normalising the
  document URL to the trailing-slash form. The Location uses a **relative value** — an
  absolute `/admin/` would send the browser to the site root and lose the prefix again.

  No extra configuration is needed for the reverse proxy: just forward `/prefix/` to this
  service's `/`.

## 4.1.0

### ⚠️ Breaking changes

- **Proxies and cookies each have exactly one entrance left**: proxies only via the
  "Proxy pool" page, cookies only via the "Cookie pool" page. The Settings page's "static
  proxy" input, the cookie card's single-cookie input, and the `/admin/api/cookie` endpoint
  have been removed.

  Why removal instead of "one more simple option": both singleton paths went through the
  "ID=0" branch, sharing the rate-limit slot with the direct connection, and the health
  writeback function starts with `id<=0 return`, skipping it entirely. The result:
  fail_count permanently 0, last_ok_at permanently empty, no rotation, no circuit-breaker
  cooldown — and the panel couldn't tell whether traffic went through the proxy or direct
  (measured: pre-migration requests using the static proxy were recorded in the requests
  table as `proxy_id=0`, indistinguishable from a real direct connection). One entry in the
  pool is strictly better everywhere.

  **Upgrading migrates automatically and leaves your original values untouched**: the
  static proxy and single cookie stored in kv are moved into their pools on first startup,
  with the originals left as-is (so rolling back to 4.0.0 still works). Migration is only
  marked "done" **after the entry lands in the pool successfully**; on failure it retries on
  the next startup — 4.0.0 applied zero validation to the static-proxy field and the stored
  value might be a scheme-less `1.2.3.4:8080`; clearing the value before pooling would make
  it vanish into thin air.

- **`--proxy` / `--cookie-file` became declarative followers**: when the value changes it
  replaces the corresponding pool entry instead of adding another one. When the value is
  unchanged the pool is left completely alone; your adds/removes/edits/disables in the panel
  are authoritative. Deployments that rotate `cookie.txt` should pay special attention —
  without dedup-by-value, dead cookies would pile up in the pool over and over, still
  enabled and still taking part in rotation.

- **`--proxy` / `--cookie-file` / `config.json` demoted to seed parameters.** They are no
  longer "a second config layer"; they only import their values into the pools at startup
  (deduplicated by URL / cookie contents), and the pools are authoritative afterwards.
  Change and restart to take effect. The original `--proxy` semantics were "fallback when
  the proxy pool is empty", and **once you saved settings in the panel, kv held a complete
  record and `--proxy` never took effect again** — editing compose and finding it did
  nothing. That pit is gone.

### Added

- **Over-long requests no longer let the upstream eat your newest question.** The upstream
  caps a single request at about **130,000 UTF-8 bytes** and **silently truncates from the
  tail** with no error; we assemble the prompt in order with the newest message last — so
  exactly the user's just-asked question gets cut, the model sees only the system preamble
  and replies with a generic opener, answering nothing and calling no tools. It looks like
  "the model got dumber" or "tool support is broken".

  Now there are two cases:

  - **With a cookie**: an over-long conversation is automatically converted to a
    `message.txt` attachment and uploaded, leaving only a short instruction in the request
    body — that wall is bypassed. **But the attachment has a cap too** — the model can see
    about 160,000 bytes of content in total; anything past that is uploaded but never read.
    So this path raises the usable length from 130K to about 160K, a bounded improvement;
    genuinely long conversations still have to be compacted by the client. (On upload
    failure it does **not** silently fall back to inline: the upstream would truncate the
    newest question and the client would get a 200 answering something else with no visible
    sign — better to fail loudly.)
  - **Without a cookie**: returns 400 + `context_length_exceeded` immediately, with the
    error message hinting that importing a cookie buys a higher limit. Anonymous mode CAN
    upload the file, but referencing it in a conversation is refused server-side, so there
    is no other way anonymously.

  **We don't drop history ourselves**: that would still be silent data loss, just in a
  different place — the client thinks the whole thing was sent while the model has already
  forgotten. `context_length_exceeded` is a signal OpenAI-compatible clients understand;
  agentic clients compact their context and retry on their own, far smarter than us blindly
  dropping segments.

  The cap `max_prompt_bytes` defaults to 128000, editable in the panel; 0 = check disabled.
  **The unit is UTF-8 bytes, not tokens**: measured, the upstream's wall is byte-based and
  language-independent — Chinese and English padded to the same byte count each sent 3
  times, ~129,950 bytes passed 3/3, ~135,990 bytes 1/3, while the token counts of those same
  requests differed by 1.9×. With a token threshold, the same number is too loose for
  English and pins Chinese at roughly a third of real capacity.

- **Image input (with a cookie)**: `image_url` in `/v1/chat/completions` and `input_image`
  in `/v1/responses` are now actually passed to the model. `data:` URLs and http(s) links
  are both supported (the latter is downloaded first — handing the link to the upstream
  directly doesn't work; it only accepts attachments in its own storage), 12MB per image
  max. Remote images go through the same exit as the conversation, otherwise it would
  expose an extra IP. Not supported anonymously, for the same reason.

- **Automatic cookie renewal.** Nearly every upstream response refreshes `SIDCC` /
  `__Secure-1PSIDCC` / `__Secure-3PSIDCC` via `Set-Cookie`; the browser accepts them and
  stays alive forever; we previously sent but never received, so the stored copy stayed at
  the import-time values. The refreshed entries are now merged back into the account on
  every request, matching browser behaviour.

  **But this didn't extend account lifetime**: cookies from the same source lived 86 minutes
  with renewal+keepalive versus 114 minutes with neither (n=3, and both shared the same
  session with a real browser — quite possibly the two sides each rotating SIDCC collided).
  So this only claims "behaves like a browser", not "accounts live longer" — why accounts
  still die within an hour or two remains unresolved.

- **Session keepalive.** The browser hits `accounts.google.com/RotateCookies` every 10
  minutes; the interval is dictated by the server in the page (the 600 seconds in the
  response body `[["identity.hfcr",600],…]`). This call **also** returns Set-Cookie,
  refreshing the same three entries as above (in two captures: 9 of 12 and 14 of 15), so
  they must be merged back too. Across the full capture, no response ever reset
  `__Secure-1PSIDTS`. Failures **don't count against cookie health**: the target is
  `accounts.google.com`, which is unrelated to whether conversations work; a network blip
  marking an account bad would sink it to the bottom of the pick order and hurt
  availability instead.

- **"Check" button in the cookie pool** — one click tells whether the account still works,
  without spending a real conversation. It distinguishes "still signed in" from
  "expired/invalid" — the upstream doesn't refuse the latter, it just treats you as
  anonymous, which you can't tell from a successful request.

- **The import-cookie dialog now has two input modes**, defaulting to "paste the whole
  string": just paste the `name=value; name=value; …` copied from the browser — also the
  form closest to what a real browser sends. Switch tabs for field-by-field entry.

- **Expired cookies now fall through to the next account** instead of killing the whole
  request. Previously the picked account going bad failed that request outright while
  other healthy accounts in the pool never got a chance — the bigger the pool, the more
  ways to hit a bad one.

- **Each cookie account is pinned to its own exit.** Previously the cookie pool and proxy
  pool rotated independently, so one Google account would emit requests from dozens of
  different IPs — exactly what account sharing looks like to Google. Now an account binds
  to the first exit it uses and stays on it, switching only when that exit becomes
  unusable.

- **Request records now include the cookie account used** (failed records too), so the
  panel shows directly which account is misbehaving — no more guessing by timestamp.
  Requests without a cookie show "anonymous".

- **Real streaming completed for the last two paths**: `/v1/responses` now emits
  `response.output_text.delta`, and `/v1/chat/completions` with `tools` streams as content
  arrives. Both were previously buffered because the ```` ```tool_call ```` fence needs the
  complete text to parse. The body now passes through an incremental gate that lets through
  only what is **certainly not inside a fence** — a tail holding half an opening fence
  (`` `` `` or `` ```tool_c ``) is held back for the next frame; sending it first and
  discovering it's a fence afterwards would be too late. Measured: streaming and
  non-streaming results are byte-identical.
- **Proxy circuit breaker switches to cooldown**: after 5 consecutive failures trip it, the
  proxy rests for 120 minutes by default and returns to the pool automatically; the duration
  is configurable on the Settings page, 0 = revert to the old permanent removal. The 120
  comes from measurement — exits blocked by Google recover after 106-121 minutes. Previously
  a tripped breaker meant permanent removal, never a success to reset the counter, only a
  manual reset.
- **Two fallback switches, both off by default** (old behaviour preserved; enabling is an
  explicit choice):
  - `fallback_direct`: fall back to a direct connection when the proxy pool can't serve a
    request. Off returns 429 and the host IP is never exposed upstream; on, a log line notes
    the direct connection.
  - `fallback_anon`: degrade to anonymous when a cookie expires. Off fails loudly — an
    expired cookie isn't refused upstream, you're just treated as anonymous: `3.1 Pro`
    silently degrades to `3.5 Flash-Lite`, the reasoning chain vanishes, and the client
    can't tell at all — so failing explicitly is the safer default.
- **`bl` version auto-follows the upstream**: fetched from the `/app` page every 6 hours;
  on a shape mismatch or fetch failure the pinned configured value stays in use. Can be
  turned off on the Settings page.

### Fixed

- **Container failing to start with `unable to open database file (14)`**. The image runs
  as nonroot (uid 65532), but a bind mount overwrites `/data`'s ownership with the host
  directory's; when the directory doesn't exist on the host Docker creates it owned by
  root, and the container can't write. Compose now defaults to a named volume, with the
  bind mount kept as a comment noting to run `sudo chown -R 65532:65532 ./data` first.
  The error message now prints the current uid, the directory, and both fixes — 14 is
  SQLITE_CANTOPEN, and nobody would guess permissions from the literal text.

- **`HTTP_PROXY` / `ALL_PROXY` set but not taking effect, with no hint at all.** The program
  deliberately ignores these environment variables (a stray export on the host would
  silently change the exit IP while the panel still shows direct), but "not reading them"
  and "staying silent" are different things. Startup now detects them and, with an empty
  proxy pool, prints an explanatory line.

- **Occasional bypassing of the proxy for a direct connection.** In `loadProxies`, a `Scan`
  error went to `continue` and `rows.Err()` was never checked, so an interrupted iteration
  was treated as a normal end and the proxy list got overwritten with a partial or empty
  result; and "is a proxy pool configured" is judged exactly by that list's length — empty
  meant falling back to direct, exposing the deployer's real IP to the upstream, with only
  a few ordinary requests in the log. The trigger: the proxy table was fully re-read after
  every request, colliding with our own just-issued UPDATE on WAL with SQLITE_BUSY. Read
  failures now keep the previous pool, and the result writeback modifies only the one
  in-memory row instead of re-reading the whole table.
- **Empty responses are retried.** The upstream occasionally returns HTTP 200 with no
  content frame at all (a transient refusal); the old code only retried on non-200 or
  network errors, so a self-healing blip became a visible 502. The criterion is **whether a
  content frame exists**, not `BardErrorInfo` — normal responses' closing frames also carry
  an error code.
- **`inner[41]` didn't match the browser**: we sent `[2]`; browser captures across three
  scenarios all show `[1]`. The value was copied early on and has since been disproven at
  the protocol layer.

### Documentation corrections

- **"Slowing down doesn't help" was wrong.** The old judgement was based on residential
  exits where the burst arm (103-177) and slow arm (81-166) overlapped almost completely.
  The observation was right, the attribution wrong — residential exits degrade over long
  runs (of 8 pre-screened exits running the slow pace, 6 exceeded a 40% failure rate
  partway through), and that variance swamped pacing. After switching to a static IP to
  remove the confound: the same IP bursting was blocked at **188 requests**, while
  **10 requests/minute ran 800 requests over 110 minutes without a single block**. So
  `per_ip_rph=80` is a conservative floor for the burst regime; deployments pacing
  themselves can raise it a lot.
- **Recovery time after a block** updated from "untested" to a measured **106-121 minutes**.
- All remaining "about 85 requests" mentions in the panel and code comments were replaced
  with the measured range.

## 4.0.0

### ⚠️ Breaking changes

- **5 old model aliases removed**: `gemini-3.5-flash`,
  `gemini-3.5-flash-thinking`, `gemini-3.5-flash-thinking-lite`, `gemini-auto`,
  `gemini-flash-lite` now return **400**. The backend has no entries for them — they all
  fell through to the same backend anyway, and keeping them only suggested there were five
  distinct models to choose from. Only the three that actually exist in the server-side list
  are exposed now: `gemini-3.6-flash`, `gemini-3.5-flash-lite`, `gemini-3.1-pro`.
  **Check the model names your clients use before upgrading.**

No database migration needed — all CREATE TABLE statements are `IF NOT EXISTS`; old
databases work as-is.

### Added

- **Cookie pool**: import multiple signed-in Google accounts; requests rotate through them
  least-recently-used first, falling back to the Settings page's single cookie only when
  the pool is empty. The list shows redacted summaries only (cookie count / whether key
  entries are present / last 4 of SAPISID / failure count); the full cookie never leaves
  the server.
- **Reasoning chain (`reasoning_content`)**: `gemini-3.1-pro`'s reasoning process before
  each answer is now exposed. Non-streaming puts it in `message.reasoning_content`;
  streaming emits `delta.reasoning_content`, with the whole reasoning chain streamed before
  any answer text (matching the upstream order). Tokens are listed separately in
  `usage.reasoning_tokens` and **not counted in `completion_tokens`** — clients collapse it
  by default, so counting it would charge users for output they never see.
- **Admin panel redesign**: light theme using Gemini's design language, fixed-height lists
  filling the viewport + pagination, errors categorised by "what to do about it", and the
  hero stat is now "requests left before the block line".
- **Multi-arch container images**: built and pushed to ghcr automatically on push to main
  or on tag.

### Fixed

- **A valid cookie made every request fail with 400.** Requests with a cookie must carry an
  extra XSRF token (form field `at`), and we only sent `f.req`. Anonymous requests don't
  require that field, so the defect stayed hidden for a long time — with a **valid** cookie,
  the cookie feature was 100% broken; an **expired** cookie, ironically, "worked" (treated
  as anonymous), which covered the problem up perfectly. The token is now fetched from the
  Gemini page automatically, cached per cookie, and re-fetched on expiry.
- **Cookie pool health was never written back.** `markAccountResult` was dead code;
  `fail_count` was permanently 0 and `last_ok_at` permanently empty — while the panel
  displayed both columns, an ops fake report of "everything healthy, forever". Results are
  written back now, and **only 401/403 counts as the cookie's fault**: network errors,
  proxy failures and Google blocks (302) are all excluded — otherwise residential proxies'
  high failure rates would turn the number into proxy noise and make healthy cookies look
  like the worst offenders.
- Several admin panel display bugs: trend chart growing without bound, login card stretched
  to full height, buttons overflowing their cards, clicking the current page re-rendering
  the whole page.
- Settings page compressed from 2234px to 1075px: 12 config items grouped semantically into
  four sections with adaptive multi-column layout inside each.

### Documentation corrections (all old conclusions overturned by measurement)

- **`gemini-3.1-pro` really works with a valid cookie.** The old docs said "free accounts
  only get 3.6 Flash even when signed in" — that observation was made with the XSRF token
  missing, when cookie requests couldn't be sent at all. With it fixed, six consecutive
  calls all reported `3.1 Pro`, each with a reasoning chain.
- **Per-IP limit** changed from "about 85" to the measured range **80-180 requests**, with
  the clarification that it's mainly determined by **connection strategy and exit quality**,
  not request pace: at the same concurrency of 10, a reused connection pool reached
  172/177 versus 106/109 for a fresh connection per request.
- **Through a proxy Google sees our own TLS fingerprint**, not the exit node's (JA3
  measurement: stdlib direct and stdlib via proxy share a fingerprint; swapping in
  tls-client through the same proxy yields a different one). The code comment had it
  backwards. Measured, it doesn't change the blocking threshold, so the implementation
  stayed as-is.

## 3.0.0

Single-binary OpenAI-compatible reverse proxy + admin panel.