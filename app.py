import os
import io
import base64
import logging
from typing import Optional
from dotenv import load_dotenv

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from sarvamai import SarvamAI

load_dotenv()

api_key = os.getenv("SARVAM_API_KEY")
if not api_key:
    raise RuntimeError("SARVAM_API_KEY not found in environment or .env file.")

client = SarvamAI(api_subscription_key=api_key)

app = FastAPI(title="Sarvam LocalBridge", description="Two-way speech-to-speech translator for local communication")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SUPPORTED_LANGUAGES = [
    {"code": "hi-IN", "name": "Hindi (हिन्दी)"},
    {"code": "en-IN", "name": "English (Indian)"},
    {"code": "ta-IN", "name": "Tamil (தமிழ்)"},
    {"code": "te-IN", "name": "Telugu (తెలుగు)"},
    {"code": "kn-IN", "name": "Kannada (ಕನ್ನಡ)"},
    {"code": "bn-IN", "name": "Bengali (বাংলা)"},
    {"code": "mr-IN", "name": "Marathi (मराठी)"},
    {"code": "gu-IN", "name": "Gujarati (ગુજરાતી)"},
    {"code": "ml-IN", "name": "Malayalam (മലയാളം)"},
    {"code": "pa-IN", "name": "Punjabi (ਪੰਜਾਬੀ)"},
    {"code": "od-IN", "name": "Odia (ଓଡ଼ିଆ)"},
]

MAX_TEXT_CHARS = 800

# bulbul:v3 voices per language (verified live in the Boli prototype)
SPEAKERS = {
    "hi-IN": "shubh", "pa-IN": "mani", "bn-IN": "rehan", "gu-IN": "ratan", "mr-IN": "ratan",
    "ta-IN": "ratan", "te-IN": "shubh", "kn-IN": "shubh", "ml-IN": "shubh", "od-IN": "shubh",
}


def friendly_error(e):
    """Map Sarvam/provider failures to messages a user can act on, without leaking details."""
    msg = str(e)
    if "401" in msg or "403" in msg:
        return "Sarvam rejected the API key. Check SARVAM_API_KEY in .env."
    if "402" in msg or "credit" in msg.lower():
        return "Sarvam credits are unavailable. Check the account balance."
    if "429" in msg:
        return "Too many requests to Sarvam. Wait a moment and try again."
    if "timeout" in msg.lower() or "timed out" in msg.lower():
        return "Sarvam took too long. Please try again."
    return "Sarvam could not process this. Keep it short (under 30 sec) and try again."


def transcribe(filename, content, content_type, lang):
    last = None
    for model in ("saaras:v3", "saaras:v4"):
        try:
            r = client.speech_to_text.transcribe(
                file=(filename, content, content_type), model=model, mode="transcribe", language_code=lang
            )
            return (r.transcript or "").strip()
        except Exception as e:
            logging.exception("STT failed with %s", model)
            last = e
    raise last


def translate(text, src, tgt):
    if src == tgt:
        return text
    r = client.text.translate(
        input=text, source_language_code=src, target_language_code=tgt, model="sarvam-translate:v1"
    )
    return (r.translated_text or "").strip()


def synthesize(text, lang):
    """TTS that never kills the response: text still returns if voice fails."""
    attempts = []
    if lang in SPEAKERS:
        attempts.append(dict(model="bulbul:v3", speaker=SPEAKERS[lang]))
    attempts += [dict(model="bulbul:v3"), dict(model="bulbul:v4-flash")]
    for extra in attempts:
        try:
            r = client.text_to_speech.convert(text=text[:2500], language_code=lang, **extra)
            if r.audios:
                return r.audios[0]
        except Exception:
            logging.exception("TTS failed with %s", extra)
    return None


def result(original, translated, src, tgt):
    audio = synthesize(translated, tgt)
    return {
        "success": True,
        "original_transcript": original,
        "translated_text": translated,
        "source_lang": src,
        "target_lang": tgt,
        "audio_base64": audio,
        "warning": None if audio else "Translation is ready, but voice is unavailable right now.",
    }


@app.get("/api/languages")
def get_languages():
    return SUPPORTED_LANGUAGES

@app.post("/api/translate-audio")
async def translate_audio(
    audio: UploadFile = File(...),
    source_lang: str = Form("en-IN"),
    target_lang: str = Form("hi-IN"),
):
    try:
        audio_content = await audio.read()
        filename = audio.filename or "recording.webm"
        content_type = audio.content_type or "audio/webm"

        if not audio_content:
            return JSONResponse({"success": False, "error": "The recording is empty. Please record again."}, status_code=400)
        if len(audio_content) > 8 * 1024 * 1024:
            return JSONResponse({"success": False, "error": "Recording too large. Keep it under 30 seconds."}, status_code=413)

        original_transcript = transcribe(filename, audio_content, content_type, source_lang)
        if not original_transcript:
            return JSONResponse({
                "success": False,
                "error": "No clear speech detected. Please speak closer to the mic."
            }, status_code=400)

        return result(original_transcript, translate(original_transcript, source_lang, target_lang), source_lang, target_lang)
    except Exception as e:
        logging.exception("Error in translate_audio")
        return JSONResponse({"success": False, "error": friendly_error(e)}, status_code=500)

@app.post("/api/translate-text")
async def translate_text(
    text: str = Form(...),
    source_lang: str = Form("en-IN"),
    target_lang: str = Form("hi-IN"),
):
    try:
        clean_text = text.strip()
        if not clean_text:
            return JSONResponse({"success": False, "error": "Type a message first."}, status_code=400)
        if len(clean_text) > MAX_TEXT_CHARS:
            return JSONResponse({"success": False, "error": "Keep each message under 800 characters."}, status_code=400)

        return result(clean_text, translate(clean_text, source_lang, target_lang), source_lang, target_lang)
    except Exception as e:
        logging.exception("Error in translate_text")
        return JSONResponse({"success": False, "error": friendly_error(e)}, status_code=500)

@app.get("/", response_class=HTMLResponse)
def index():
    return HTML_CONTENT

HTML_CONTENT = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Sarvam LocalBridge — Speak with Locals</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <style>
    body { font-family: 'Plus Jakarta Sans', sans-serif; }
    .pulse-ring {
      animation: pulse 1.5s cubic-bezier(0.4, 0, 0.6, 1) infinite;
    }
    @keyframes pulse {
      0%, 100% { opacity: 1; transform: scale(1); }
      50% { opacity: 0.5; transform: scale(1.15); }
    }
  </style>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen flex flex-col items-center p-3 sm:p-6">
  <div class="w-full max-w-3xl flex flex-col gap-4">
    
    <!-- Top Header -->
    <header class="flex items-center justify-between border-b border-slate-800 pb-4 pt-2">
      <div class="flex items-center gap-3">
        <div class="h-10 w-10 rounded-xl bg-gradient-to-tr from-amber-500 to-orange-600 flex items-center justify-center shadow-lg shadow-orange-500/20 font-extrabold text-white text-lg">
          SB
        </div>
        <div>
          <h1 class="text-xl font-bold tracking-tight text-white flex items-center gap-2">
            LocalBridge <span class="text-xs px-2 py-0.5 rounded-full bg-orange-500/10 text-orange-400 font-semibold border border-orange-500/20">Sarvam AI</span>
          </h1>
          <p class="text-xs text-slate-400">Two-way real-time voice & text communicator for Indian languages</p>
        </div>
      </div>
      <div id="statusBadge" class="hidden sm:flex items-center gap-2 text-xs font-medium px-3 py-1.5 rounded-full bg-slate-900 border border-slate-800 text-emerald-400">
        <span class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span> Ready
      </div>
    </header>

    <!-- Language Selector Bar -->
    <div class="relative grid grid-cols-2 gap-3 bg-slate-900/90 border border-slate-800/80 p-3 rounded-2xl backdrop-blur">
      <button id="swapBtn" title="Swap languages" class="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 z-10 h-9 w-9 rounded-full bg-slate-800 border border-slate-600 hover:bg-slate-700 text-white text-sm font-bold">⇄</button>
      <div>
        <label class="block text-xs font-semibold text-slate-400 mb-1 flex items-center gap-1.5">
          <span class="w-2 h-2 rounded-full bg-blue-500"></span> You Speak
        </label>
        <select id="myLang" class="w-full bg-slate-950 border border-slate-700/80 rounded-xl px-3 py-2 text-sm font-medium text-white focus:outline-none focus:border-blue-500 transition">
          <option value="en-IN" selected>English (Indian)</option>
          <option value="hi-IN">Hindi (हिन्दी)</option>
          <option value="ta-IN">Tamil (தமிழ்)</option>
          <option value="te-IN">Telugu (తెలుగు)</option>
          <option value="kn-IN">Kannada (ಕನ್ನಡ)</option>
          <option value="bn-IN">Bengali (বাংলা)</option>
          <option value="mr-IN">Marathi (मराठी)</option>
          <option value="gu-IN">Gujarati (ગુજરાતી)</option>
          <option value="ml-IN">Malayalam (മലയാളം)</option>
          <option value="pa-IN">Punjabi (ਪੰਜਾਬੀ)</option>
          <option value="od-IN">Odia (ଓଡ଼ିଆ)</option>
        </select>
      </div>

      <div>
        <label class="block text-xs font-semibold text-slate-400 mb-1 flex items-center gap-1.5">
          <span class="w-2 h-2 rounded-full bg-orange-500"></span> Local Speaks
        </label>
        <select id="localLang" class="w-full bg-slate-950 border border-slate-700/80 rounded-xl px-3 py-2 text-sm font-medium text-white focus:outline-none focus:border-orange-500 transition">
          <option value="hi-IN" selected>Hindi (हिन्दी)</option>
          <option value="ta-IN">Tamil (தமிழ்)</option>
          <option value="te-IN">Telugu (తెలుగు)</option>
          <option value="kn-IN">Kannada (ಕನ್ನಡ)</option>
          <option value="bn-IN">Bengali (বাংলা)</option>
          <option value="mr-IN">Marathi (मराठी)</option>
          <option value="gu-IN">Gujarati (ગુજરાતી)</option>
          <option value="ml-IN">Malayalam (മലയാളം)</option>
          <option value="pa-IN">Punjabi (ਪੰਜਾਬੀ)</option>
          <option value="od-IN">Odia (ଓଡ଼ିଆ)</option>
          <option value="en-IN">English (Indian)</option>
        </select>
      </div>
    </div>

    <!-- Live Conversation Transcript Box -->
    <div id="chatHistory" class="flex flex-col gap-3 h-80 overflow-y-auto p-4 rounded-2xl bg-slate-900/60 border border-slate-800/80 scroll-smooth shadow-inner">
      <div class="text-center text-xs text-slate-500 my-auto">
        Tap or hold a button below to speak. Voice is transcribed, translated, and automatically spoken in the local tongue.
      </div>
    </div>

    <!-- Active Status Bar -->
    <div id="processingIndicator" class="hidden flex items-center justify-center gap-2 py-2 px-4 rounded-xl bg-orange-500/10 border border-orange-500/30 text-orange-400 text-xs font-semibold">
      <svg class="animate-spin h-4 w-4 text-orange-400" viewBox="0 0 24 24" fill="none">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path>
      </svg>
      <span id="processingText">Processing voice with Sarvam AI...</span>
    </div>

    <div id="errorBar" class="hidden flex items-center justify-between gap-3 py-2.5 px-4 rounded-xl bg-red-500/10 border border-red-500/30 text-red-300 text-xs">
      <span id="errorText"></span>
      <button id="errorClose" class="font-bold text-red-200">✕</button>
    </div>

    <!-- Two Dual Talk Controls -->
    <div class="grid grid-cols-2 gap-4">
      
      <!-- User Talk Button -->
      <button id="userTalkBtn" class="group relative flex flex-col items-center justify-center p-5 rounded-2xl bg-gradient-to-b from-blue-600 to-blue-700 hover:from-blue-500 hover:to-blue-600 active:scale-95 text-white font-semibold transition shadow-lg shadow-blue-600/30 select-none cursor-pointer">
        <div id="userMicIcon" class="w-14 h-14 rounded-full bg-blue-500/30 flex items-center justify-center mb-2 group-hover:scale-105 transition">
          <svg class="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 02-3-3V5a3 3 0 116 0v6a3 3 0 02-3 3z"></path>
          </svg>
        </div>
        <span class="text-sm font-bold">You Speak</span>
        <span class="text-[11px] text-blue-200/90 font-normal mt-0.5">Translate → Local</span>
      </button>

      <!-- Local Person Talk Button -->
      <button id="localTalkBtn" class="group relative flex flex-col items-center justify-center p-5 rounded-2xl bg-gradient-to-b from-orange-600 to-orange-700 hover:from-orange-500 hover:to-orange-600 active:scale-95 text-white font-semibold transition shadow-lg shadow-orange-600/30 select-none cursor-pointer">
        <div id="localMicIcon" class="w-14 h-14 rounded-full bg-orange-500/30 flex items-center justify-center mb-2 group-hover:scale-105 transition">
          <svg class="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 02-3-3V5a3 3 0 116 0v6a3 3 0 02-3 3z"></path>
          </svg>
        </div>
        <span class="text-sm font-bold">Local Speaks</span>
        <span class="text-[11px] text-orange-200/90 font-normal mt-0.5">Translate → You</span>
      </button>

    </div>

    <!-- Quick Text Input Fallback -->
    <div class="flex items-center gap-2 bg-slate-900 border border-slate-800 p-2 rounded-xl">
      <input id="textInput" type="text" maxlength="800" placeholder="Or type a phrase here (e.g. Where is the railway station?)..." class="flex-1 bg-transparent px-3 py-1.5 text-xs text-white placeholder-slate-500 focus:outline-none">
      <button id="sendTextBtn" class="bg-blue-700 hover:bg-blue-600 px-3 py-2 rounded-lg text-xs font-semibold text-white transition">
        Send as You
      </button>
      <button id="sendLocalBtn" class="bg-orange-700 hover:bg-orange-600 px-3 py-2 rounded-lg text-xs font-semibold text-white transition">
        Send as Local
      </button>
    </div>

  </div>

  <script>
    let mediaRecorder = null;
    let audioChunks = [];
    let currentRecordingParty = null; // 'user' or 'local'
    let currentAudio = null;

    const chatHistory = document.getElementById('chatHistory');
    const userTalkBtn = document.getElementById('userTalkBtn');
    const localTalkBtn = document.getElementById('localTalkBtn');
    const userMicIcon = document.getElementById('userMicIcon');
    const localMicIcon = document.getElementById('localMicIcon');
    const processingIndicator = document.getElementById('processingIndicator');
    const processingText = document.getElementById('processingText');
    const myLang = document.getElementById('myLang');
    const localLang = document.getElementById('localLang');
    const textInput = document.getElementById('textInput');
    const sendTextBtn = document.getElementById('sendTextBtn');
    const sendLocalBtn = document.getElementById('sendLocalBtn');

    // Sarvam STT accepts WAV/MP3/AAC/FLAC/OGG — browsers record WebM/MP4, so convert to WAV
    async function toWav(blob) {
      const ctx = new (window.AudioContext || window.webkitAudioContext)();
      const decoded = await ctx.decodeAudioData(await blob.arrayBuffer());
      ctx.close();
      const rate = 16000;
      const offline = new OfflineAudioContext(1, Math.ceil(decoded.duration * rate), rate);
      const src = offline.createBufferSource();
      src.buffer = decoded; src.connect(offline.destination); src.start();
      const pcm = (await offline.startRendering()).getChannelData(0);
      const view = new DataView(new ArrayBuffer(44 + pcm.length * 2));
      const str = (o, t) => { for (let i = 0; i < t.length; i++) view.setUint8(o + i, t.charCodeAt(i)); };
      str(0, 'RIFF'); view.setUint32(4, 36 + pcm.length * 2, true); str(8, 'WAVE');
      str(12, 'fmt '); view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
      view.setUint32(24, rate, true); view.setUint32(28, rate * 2, true); view.setUint16(32, 2, true); view.setUint16(34, 16, true);
      str(36, 'data'); view.setUint32(40, pcm.length * 2, true);
      for (let i = 0; i < pcm.length; i++) {
        const v = Math.max(-1, Math.min(1, pcm[i]));
        view.setInt16(44 + i * 2, v < 0 ? v * 0x8000 : v * 0x7FFF, true);
      }
      return new Blob([view], { type: 'audio/wav' });
    }

    function esc(t) {
      const d = document.createElement('div'); d.textContent = t ?? ''; return d.innerHTML;
    }

    // Setup Audio Recording
    async function startRecording(party) {
      if (mediaRecorder && mediaRecorder.state === "recording") {
        return;
      }
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        mediaRecorder = new MediaRecorder(stream);
        audioChunks = [];
        currentRecordingParty = party;

        mediaRecorder.ondataavailable = e => {
          if (e.data.size > 0) audioChunks.push(e.data);
        };

        mediaRecorder.onstop = async () => {
          const audioBlob = new Blob(audioChunks, { type: mediaRecorder.mimeType || 'audio/webm' });
          stream.getTracks().forEach(track => track.stop());
          await processRecordedAudio(audioBlob, party);
        };

        mediaRecorder.start(250);
        updateRecordingUI(party, true);
        recStart = Date.now();
        recTimer = setInterval(() => {
          const btn = party === 'user' ? userTalkBtn : localTalkBtn;
          btn.querySelector('span').innerText = "Listening… " + Math.floor((Date.now() - recStart) / 1000) + "s (tap to stop)";
        }, 250);
        autoStop = setTimeout(() => stopRecording(), 28000); // Sarvam sync STT limit is 30 s
      } catch (err) {
        showError("Microphone blocked or not found. Allow mic access, or type your message below.");
      }
    }

    let recTimer = null, autoStop = null, recStart = 0;
    function stopRecording() {
      clearInterval(recTimer); clearTimeout(autoStop);
      if (mediaRecorder && mediaRecorder.state === "recording") {
        mediaRecorder.stop();
        updateRecordingUI(currentRecordingParty, false);
      }
    }

    function updateRecordingUI(party, isRecording) {
      if (party === 'user') {
        if (isRecording) {
          userMicIcon.classList.add('pulse-ring', 'bg-red-500/60');
          userTalkBtn.querySelector('span').innerText = "Listening...";
        } else {
          userMicIcon.classList.remove('pulse-ring', 'bg-red-500/60');
          userTalkBtn.querySelector('span').innerText = "You Speak";
        }
      } else if (party === 'local') {
        if (isRecording) {
          localMicIcon.classList.add('pulse-ring', 'bg-red-500/60');
          localTalkBtn.querySelector('span').innerText = "Listening...";
        } else {
          localMicIcon.classList.remove('pulse-ring', 'bg-red-500/60');
          localTalkBtn.querySelector('span').innerText = "Local Speaks";
        }
      }
    }

    // Toggle on Click/Tap
    userTalkBtn.addEventListener('click', () => {
      if (mediaRecorder && mediaRecorder.state === "recording") {
        stopRecording();
      } else {
        startRecording('user');
      }
    });

    localTalkBtn.addEventListener('click', () => {
      if (mediaRecorder && mediaRecorder.state === "recording") {
        stopRecording();
      } else {
        startRecording('local');
      }
    });

    async function processRecordedAudio(audioBlob, party) {
      const source_lang = party === 'user' ? myLang.value : localLang.value;
      const target_lang = party === 'user' ? localLang.value : myLang.value;

      hideError();
      showProcessing(true, "Transcribing & Translating with Sarvam AI...");

      let uploadBlob = audioBlob, uploadName = "recording.webm";
      try {
        uploadBlob = await toWav(audioBlob);
        uploadName = "recording.wav";
      } catch (e) {
        console.log("WAV conversion failed, sending original", e);
      }
      const formData = new FormData();
      formData.append("audio", uploadBlob, uploadName);
      formData.append("source_lang", source_lang);
      formData.append("target_lang", target_lang);

      try {
        const res = await fetch("/api/translate-audio", {
          method: "POST",
          body: formData
        });
        const data = await res.json();
        showProcessing(false);

        if (data.success) {
          appendMessageCard(party, data);
          if (data.audio_base64) {
            playAudio(data.audio_base64);
          }
        } else {
          showError(data.error || "Failed to process audio. Please try again.");
        }
      } catch (err) {
        showProcessing(false);
        showError("Could not reach the server. Is app.py still running?");
      }
    }

    async function sendText(text, party) {
      text = (text || "").trim();
      if (!text) return;
      const source_lang = party === 'user' ? myLang.value : localLang.value;
      const target_lang = party === 'user' ? localLang.value : myLang.value;
      hideError();
      showProcessing(true, "Translating & Synthesizing voice...");
      const formData = new FormData();
      formData.append("text", text);
      formData.append("source_lang", source_lang);
      formData.append("target_lang", target_lang);
      try {
        const res = await fetch("/api/translate-text", { method: "POST", body: formData });
        const data = await res.json();
        showProcessing(false);
        if (data.success) {
          appendMessageCard(party, data);
          if (data.audio_base64) playAudio(data.audio_base64);
        } else {
          showError(data.error || "Failed to translate. Please try again.");
        }
      } catch (err) {
        showProcessing(false);
        showError("Could not reach the server. Is app.py still running?");
      }
    }

    sendTextBtn.addEventListener('click', () => { const t = textInput.value; textInput.value = ""; sendText(t, 'user'); });
    sendLocalBtn.addEventListener('click', () => { const t = textInput.value; textInput.value = ""; sendText(t, 'local'); });

    document.getElementById('swapBtn').addEventListener('click', () => {
      const a = myLang.value, b = localLang.value;
      const hasA = [...localLang.options].some(o => o.value === a);
      const hasB = [...myLang.options].some(o => o.value === b);
      if (hasA && hasB) { myLang.value = b; localLang.value = a; }
    });

    const errorBar = document.getElementById('errorBar');
    const errorText = document.getElementById('errorText');
    document.getElementById('errorClose').addEventListener('click', hideError);
    function showError(msg) { errorText.innerText = msg; errorBar.classList.remove('hidden'); }
    function hideError() { errorBar.classList.add('hidden'); }

    textInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') sendTextBtn.click();
    });

    function showProcessing(show, text = "") {
      processingIndicator.classList.toggle('hidden', !show);
      processingText.innerText = text;
    }

    function appendMessageCard(party, data) {
      const isUser = party === 'user';
      const card = document.createElement('div');
      card.className = `flex flex-col gap-1.5 p-3.5 rounded-2xl max-w-[85%] text-xs shadow-md ${
        isUser
          ? 'self-end bg-blue-950/80 border border-blue-800/80 text-blue-100'
          : 'self-start bg-slate-800/90 border border-slate-700/80 text-slate-100'
      }`;

      const speakerLabel = isUser ? "You ➔ Local" : "Local ➔ You";
      const audioBtnHtml = data.audio_base64 
        ? `<button onclick="playAudio('${data.audio_base64}')" class="mt-2 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-orange-500/20 hover:bg-orange-500/30 text-orange-300 font-semibold text-[11px] border border-orange-500/30 transition w-fit">
            <svg class="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 20 20"><path d="M10 18a8 8 0 100-16 8 8 0 000 16zM9.555 7.168A1 1 0 008 8v4a1 1 0 001.555.832l3-2a1 1 0 000-1.664l-3-2z"/></svg>
            Replay Voice
          </button>`
        : '';

      card.innerHTML = `
        <div class="flex items-center justify-between font-semibold text-[10px] tracking-wide text-slate-400 uppercase">
          <span>${speakerLabel}</span>
        </div>
        <div class="text-xs text-slate-300 italic">"${esc(data.original_transcript)}"</div>
        <div class="text-sm font-bold text-white mt-1">${esc(data.translated_text)}</div>
        ${data.warning ? `<div class="text-[11px] text-amber-300">⚠ ${esc(data.warning)}</div>` : ''}
        <div class="flex gap-2 items-center">${audioBtnHtml}
          <button class="edit-btn mt-2 px-3 py-1.5 rounded-xl bg-slate-700/60 hover:bg-slate-700 text-slate-200 text-[11px] font-semibold border border-slate-600 w-fit">✏️ Fix & resend</button>
        </div>
      `;
      card.querySelector('.edit-btn').addEventListener('click', () => {
        const fixed = prompt("Correct what was said:", data.original_transcript);
        if (fixed && fixed.trim()) sendText(fixed, party);
      });

      chatHistory.appendChild(card);
      chatHistory.scrollTop = chatHistory.scrollHeight;
    }

    function playAudio(base64Data) {
      if (currentAudio) {
        currentAudio.pause();
      }
      currentAudio = new Audio("data:audio/wav;base64," + base64Data);
      currentAudio.play().catch(e => console.log("Audio autoplay restricted: ", e));
    }
  </script>
</body>
</html>
"""

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8000)
