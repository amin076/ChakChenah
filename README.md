# ChakChenah — Pronunciation MVP

A **free/open-source local pronunciation experiment**. Record an English sentence, send the actual audio to [OpenPronounce](https://github.com/Halleck45/OpenPronounce), see an acoustic/phoneme-derived score and feedback, and review your attempts. No commercial speech API and **no simulated scores**.

## Local setup (Windows PowerShell)

Prerequisites: Python 3.10+, **ffmpeg** and **espeak-ng** available on your PATH (restart the shell after installing them). First inference downloads two Wav2Vec2 checkpoints (~2.4 GB in total) plus a Piper voice (~60 MB). Subsequent runs use the local cache. Free software is not the same as zero CPU/disk usage.

```powershell
git clone https://github.com/amin076/ChakChenah.git
cd ChakChenah
git checkout feature/pronunciation-mvp
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
$env:OPENPRONOUNCE_TTS="piper"
uvicorn app:app --host 127.0.0.1 --port 8000
```

Open **http://localhost:8000** in Chrome or Edge. Allow microphone permissions, press Start recording, read the shown sentence, Stop, listen back, then Analyse pronunciation. Audio uploads are also supported.

The microphone runs in your browser, but **the pronunciation model runs on your computer in Python**, not in the browser. On macOS/Linux, use `source .venv/bin/activate` and `export OPENPRONOUNCE_TTS=piper` instead. The selected Piper backend avoids gTTS requests after downloading the voice.

## Real results, known limitations

- Only a successful OpenPronounce model invocation returns a score. If the engine is not installed or fails to run, the API returns **503**, not a pretend score.
- The output includes score 0–100, transcription, flagged words, phonemes and confidence values. It does **not** yet diagnose conversational fluency or grammar.
- Strong accents and noise produce false alarms. The original project's evaluation is preliminary; scores are **experimental and not a validated CEFR or intelligibility score**.
- Temporary recordings are deleted after inference. SQLite stores expected text, transcription, score and flagged errors in `data/attempts.sqlite3`.
- No login or authorization yet: this is a **single-user local-only prototype**, not a public production server.
- OpenPronounce code is MIT; inspect licenses of downloaded model and voice weights separately before redistributing them.
- For a truly offline *first* run, install and cache models/voices beforehand.

## Endpoints

`GET /api/health`, `POST /api/analyze` (multipart: `file`, `expected_text`), `GET /api/history`.

## Acceptance criteria for the first experiment

1. Read a known sentence clearly, repeat 3 times and compare scores.
2. Deliberately omit/change one word; confirm feedback indicates the difference.
3. Test one vowel error, noisy audio and silence; record false positives.
4. Check that failures return errors rather than invented scores.
5. Repeat with Australian-accent speech: assess whether the system incorrectly penalizes valid variants.

**Tests:** `pip install pytest httpx` then `pytest -q`. The automated tests mock the acoustic engine to check the API contract and failure handling; they are **not actual inference validation**. Running speech-model integration tests still requires model weights and audio samples.

**Future phases:** speaking encouragement, structured conversation, vocabulary, error-review memory, spaced repetition, confidence-friendly rewards, weekly matched-prompt comparisons. These are not represented as completed features.
