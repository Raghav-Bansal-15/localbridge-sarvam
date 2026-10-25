# LocalBridge 🗣️ — speak with locals in their language

**Built at the Sarvam AI Buildathon.** Two people share one laptop or phone and take turns talking: each one speaks their own language, and the other hears and reads it in theirs.

## Problem
Students, travellers and migrant workers in India often can't communicate with auto drivers, shopkeepers or mess staff who speak a different language. Generic translators are built around English and formal text, not quick spoken back-and-forth between two Indian languages.

## How it works
```
🎙️ Tap & speak ──► Saaras (speech-to-text) ──► Sarvam-Translate ──► Bulbul (text-to-speech) ──► 🔊 + 📝
```
- **Two-way intercom**: a blue button for *You* and an orange button for *Local*, so each turn is routed explicitly (no guessing who spoke).
- **11 languages**: Hindi, Tamil, Telugu, Kannada, Malayalam, Bengali, Marathi, Gujarati, Punjabi, Odia, English.
- **Voice + text** for every turn, with a replay button.

## Robustness
- The browser recording (WebM/MP4) is converted to **16 kHz mono WAV** in-browser before upload, matching Sarvam's supported STT formats.
- Recording **auto-stops at 28 s** to stay under Sarvam's 30-second sync limit.
- **Voice failure never loses the text**: TTS falls back across a language-matched `bulbul:v3` speaker → default `bulbul:v3` → `bulbul:v4-flash`, and shows a warning if none works.
- STT falls back from `saaras:v3` to `saaras:v4`.
- **Fix & resend**: correct a misheard transcript and re-translate it.
- Typed input for either person (for noisy places or no mic), plus a swap-languages button.
- Clear errors for a bad API key, missing credits, rate limits and timeouts, with no raw provider errors shown to users.
- The API key stays server-side in `.env` and is never sent to the browser.

## Run it
```bash
pip install -r requirements.txt
echo "SARVAM_API_KEY=your_key" > .env
python3 app.py
```
Open http://127.0.0.1:8000 in Chrome, allow the mic, tap a button and speak.

## Sarvam APIs used
| Step | API | Model |
|---|---|---|
| Speech → text | `speech_to_text.transcribe` | `saaras:v3` (fallback `saaras:v4`) |
| Translation | `text.translate` | `sarvam-translate:v1` |
| Text → speech | `text_to_speech.convert` | `bulbul:v3` (fallback `bulbul:v4-flash`) |

## Limits and next steps
- This is a push-to-talk prototype, not a certified interpreter. Confirm important details (prices, medicine, directions) directly.
- Next: streaming STT/TTS for near-real-time conversation, a mobile build over HTTPS, colloquial/code-mixed translation modes, and an offline phrasebook.
- Audio is sent to Sarvam only for processing and isn't stored by this app.
