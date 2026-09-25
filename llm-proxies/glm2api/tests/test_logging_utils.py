from glm2api.logging_utils import redact_sensitive_text




def test_signed_url_query_secrets_are_redacted():
    """C-17: signierte URLs tragen ihre berechtigung im Query-String. Die
    feld-/header-redaktion greift dort nicht — der token landete
    vollstaendig im Debug-Log."""
    redacted = redact_sensitive_text(
        "https://cdn.example/x.png?X-Amz-Signature=AWS4SIGN&X-Amz-Credential=AKIA123&filePath=/a"
    )
    assert "AWS4SIGN" not in redacted
    assert "AKIA123" not in redacted
    # harmlose parameter bleiben lesbar — das log soll nutzbar bleiben
    assert "filePath=/a" in redacted


def test_query_redaction_keeps_plain_urls_usable():
    text = "https://opendata.baidu.com/api.php?query=1.1.1.1&resource_id=6006&oe=utf8"
    assert redact_sensitive_text(text) == text


def test_query_redaction_covers_token_and_secret_keys():
    for url in (
        "https://x/y?token=SEKRET1&expires=99",
        "https://x/y?secret=SEKRET2",
        "https://x/y?password=SEKRET3",
        "https://x/y?access_token=SEKRET4",
    ):
        redacted = redact_sensitive_text(url)
        assert "SEKRET" not in redacted, url


# --- C-17: signatur und session-cookie waren im klartext ----------------


def test_signature_and_session_cookie_are_redacted():
    """C-17: `X-Sign` ist die HMAC-Signatur ueber die anfrage und wurde
    mit dem geheimen schluessel gebildet — im debug-log lag sie im
    klartext. `set-cookie` traegt die upstream-session."""
    from glm2api.logging_utils import redact_sensitive_data

    out = redact_sensitive_data({
        "Authorization": "Bearer eyJhbGciOi.SECRET",
        "X-Sign": "deadbeefsignature",
        "set-cookie": "session=abc123",
    })

    assert out["Authorization"] == "[REDACTED]"
    assert out["X-Sign"] == "[REDACTED]"
    assert out["set-cookie"] == "[REDACTED]"


def test_non_secret_request_metadata_stays_readable():
    """Gegenprobe: nonce und timestamp sind keine Zugangsdaten. Sie zu
    redigieren wuerde die Nachvollziehbarkeit des Protokolls zerstoeren, ohne
    etwas zu schuetzen."""
    from glm2api.logging_utils import redact_sensitive_data

    out = redact_sensitive_data({"x-nonce": "abc123", "X-Timestamp": "1700000000"})

    assert out["x-nonce"] == "abc123"
    assert out["X-Timestamp"] == "1700000000"


def test_content_stays_complete_after_signature_redaction():
    """Das debug-log bleibt bewusst 1:1 fuer den inhalt — die
    Redaktion betrifft nur Zugangsdaten."""
    from glm2api.logging_utils import redact_sensitive_data

    out = redact_sensitive_data({
        "X-Sign": "deadbeef",
        "messages": [{"role": "user", "content": "VOLLER PROMPT INKL. ALLES"}],
    })

    assert "VOLLER PROMPT INKL. ALLES" in str(out["messages"])
