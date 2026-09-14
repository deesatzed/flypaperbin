from flypaper.classify import classify_for_storage, detect_secret, guess_category


def test_secret_sk():
    g = guess_category("sk-abcdefghijklmnopqrstuvwxyz0123456789ABCD")
    assert g["category"] == "Secret"
    assert g["secret"]["last4"]
    assert g["secret"]["fingerprint"]


def test_secret_ghp():
    g = guess_category("ghp_abcdefghijklmnopqrstuvwx1234567890")
    assert g["category"] == "Secret"
    assert g["secret"]["kind"] == "github_pat"


def test_secret_akia():
    g = guess_category("AKIAIOSFODNN7EXAMPLE")
    assert g["category"] == "Secret"


def test_cli():
    g = guess_category("git status -sb && git diff")
    assert g["category"] == "CLI"


def test_prompt():
    g = guess_category("You are a helpful assistant. Please summarize the following document carefully.")
    assert g["category"] == "Prompt"


def test_file_path():
    g = guess_category("/Users/allen/Desktop/IMG_4291.png")
    assert g["category"] == "File"
    assert g["needs_description"] is True
    assert g["file"]["filename"] == "IMG_4291.png"


def test_file_url():
    g = guess_category("file:///tmp/notes/report.pdf")
    assert g["category"] == "File"
    assert g["file"]["filename"] == "report.pdf"


def test_url():
    g = guess_category("https://example.com/ticket/123")
    assert g["category"] == "URL"


def test_classify_redacts_secret_body():
    raw = "sk-abcdefghijklmnopqrstuvwxyz0123456789ABCD"
    fields = classify_for_storage(raw)
    assert fields["category"] == "Secret"
    assert raw not in fields["body"]
    assert fields["fingerprint"]
    assert fields["last4"] == raw[-4:]
    assert detect_secret(raw) is not None
