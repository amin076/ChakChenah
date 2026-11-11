import io
import os

os.environ["CHAKCHENAH_DATA_DIR"] = "/tmp/chakchenah-test-db"

from fastapi.testclient import TestClient
import app as module

client = TestClient(module.app)


def test_health_and_home():
    assert client.get("/api/health").status_code == 200
    assert "ChakChenah" in client.get("/").text


def test_rejects_bad_audio_and_empty_sentence():
    assert client.post("/api/analyze", data={"expected_text": "OK"},
        files={"file": ("notes.txt", b"x" * 2000, "text/plain")}).status_code == 415
    assert client.post("/api/analyze", data={"expected_text": " "},
        files={"file": ("recording.wav", b"x" * 2000, "audio/wav")}).status_code == 422
    assert client.post("/api/analyze", data={"expected_text": "Hello"},
        files={"file": ("recording.wav", b"x" * (12 * 1024 * 1024 + 1), "audio/wav")}).status_code == 413


def test_real_engine_contract_and_persistence(monkeypatch, tmp_path):
    monkeypatch.setattr(module, "DB_PATH", tmp_path / "test.sqlite3")
    def fake_engine(path, expected):
        assert path.exists()
        assert expected == "Hello world"
        return {"score": 71.5, "transcript": "HELLO WORLD",
                "errors": [{"word": "world", "expected": "wɜːld",
                            "actual": "wɔːld", "confidence": .65}],
                "phoneme_error_rate": .2, "word_error_rate": 0,
                "engine": "OpenPronounce"}
    monkeypatch.setattr(module, "analyze_file", fake_engine)
    response = client.post("/api/analyze", data={"expected_text": "Hello world"},
        files={"file": ("recording.wav", b"x" * 2000, "audio/wav")})
    assert response.status_code == 200, response.text
    assert response.json()["score"] == 71.5
    assert len(client.get("/api/history").json()) == 1
    # This is explicitly a mocked contract test; NOT evidence of actual acoustic scoring.


def test_engine_failure_never_generates_fake_score(monkeypatch, tmp_path):
    monkeypatch.setattr(module, "DB_PATH", tmp_path / "test.sqlite3")
    def broken(path, expected):
        raise RuntimeError("model unavailable")
    monkeypatch.setattr(module, "analyze_file", broken)
    r = client.post("/api/analyze", data={"expected_text": "Hello world"},
        files={"file": ("recording.wav", b"x" * 2000, "audio/wav")})
    assert r.status_code == 503
    assert client.get("/api/history").json() == []
