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
