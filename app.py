"""ChakChenah pronunciation experiment. All inference runs on the local machine."""
import json
import os
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("CHAKCHENAH_DATA_DIR", ROOT / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "attempts.sqlite3"
MAX_UPLOAD = 12 * 1024 * 1024

# Prevent OpenPronounce's default gTTS backend from making per-sentence network calls.
# Piper downloads a model once, then works offline. Initial model downloads need internet.
os.environ.setdefault("OPENPRONOUNCE_TTS", "piper")

app = FastAPI(title="ChakChenah | Local pronunciation lab")
app.mount("/static", StaticFiles(directory=str(ROOT / "static")), name="static")


def connect_db():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("""CREATE TABLE IF NOT EXISTS attempts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at TEXT NOT NULL,
        expected_text TEXT NOT NULL,
        score REAL NOT NULL,
        transcript TEXT NOT NULL,
        errors_json TEXT NOT NULL,
        engine TEXT NOT NULL
    )""")
    db.commit()
    return db


def analyze_file(path, expected_text):
    # Lazy import: /health and the interface work without downloading any model.
    from openpronounce import compare_audio_with_text, load_audio
    sound = load_audio(str(path))
    result = compare_audio_with_text(sound, expected_text, lang="en")
    score = result.get("score")
    if not isinstance(score, (int, float)) or isinstance(score, bool) or not (0 <= score <= 100):
        raise ValueError("The engine did not return a valid score")
    differences = result.get("differences") or {}
    errors = differences.get("errors") or []
    return {
        "score": round(float(score), 1),
        "transcript": str(result.get("transcribe") or ""),
        "errors": [
            {
                "word": str(e.get("word") or ""),
                "expected": str(e.get("expected") or ""),
                "actual": str(e.get("actual") or ""),
                "confidence": float(e.get("confidence") or 0),
            }
            for e in errors if isinstance(e, dict)
        ][:30],
        "phoneme_error_rate": differences.get("phoneme_error_rate"),
        "word_error_rate": differences.get("word_error_rate"),
        "engine": "OpenPronounce",
    }


@app.get("/")
def home():
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/api/health")
def health():
    try:
        import importlib.util
        ready = importlib.util.find_spec("openpronounce") is not None
    except Exception:
        ready = False
    return {"server": "ok", "engine_installed": ready, "engine": "OpenPronounce",
            "mode": "local; no paid API", "tts": os.environ.get("OPENPRONOUNCE_TTS")}


@app.get("/api/history")
def history():
    with connect_db() as db:
        rows = db.execute(
            "SELECT id, created_at, expected_text, score, transcript, errors_json, engine "
            "FROM attempts ORDER BY id DESC LIMIT 100"
        ).fetchall()
    return [{"id": r["id"], "created_at": r["created_at"],
             "expected_text": r["expected_text"], "score": r["score"],
             "transcript": r["transcript"], "errors": json.loads(r["errors_json"]),
             "engine": r["engine"]} for r in rows]


@app.post("/api/analyze")
async def analyze(file: UploadFile = File(...), expected_text: str = Form(...)):
    expected_text = expected_text.strip()
    if not 2 <= len(expected_text) <= 200:
        raise HTTPException(422, "Expected sentence must contain 2–200 characters")
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".webm", ".wav", ".ogg", ".mp3", ".m4a", ".mp4"}:
        raise HTTPException(415, "Use a supported audio format (webm, wav, ogg, mp3, m4a)")
    path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as temp:
            path = Path(temp.name)
            size = 0
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD:
                    raise HTTPException(413, "Audio file exceeds 12 MB")
                temp.write(chunk)
        if size < 1024:
            raise HTTPException(422, "Audio recording is too short or empty")
        try:
            result = await run_in_threadpool(analyze_file, path, expected_text)
        except (ImportError, ModuleNotFoundError) as exc:
            raise HTTPException(503, "Install the local speech engine first (see README)") from exc
        except Exception as exc:
            # Never synthesize a score when model setup or inference fails.
            raise HTTPException(503, f"Speech analysis unavailable: {type(exc).__name__}. Check server logs and model setup.") from exc
        with connect_db() as db:
            cur = db.execute(
                "INSERT INTO attempts (created_at, expected_text, score, transcript, errors_json, engine) VALUES (?, ?, ?, ?, ?, ?)",
                (datetime.now(timezone.utc).isoformat(), expected_text, result["score"],
                 result["transcript"], json.dumps(result["errors"]), result["engine"]),
            )
            db.commit()
            result["id"] = cur.lastrowid
        return result
    finally:
        await file.close()
        if path is not None:
            path.unlink(missing_ok=True)
