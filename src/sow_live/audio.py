"""Audio capture, segmentation and local ASR.

Two independent streams, so speaker attribution is free:
  - mic    -> "SA"      (ffmpeg / AVFoundation)
  - system -> "Remote"  (build/bin/syscap, ScreenCaptureKit; everyone else on the call)

Each stream is cut into utterances with a simple energy VAD, and every
utterance is transcribed by a local whisper.cpp server (Metal on Apple Silicon).
"""

from __future__ import annotations

import io
import json
import queue
import re
import shutil
import socket
import subprocess
import threading
import time
import urllib.request
import uuid
import wave
from difflib import SequenceMatcher

import numpy as np

from .config import SYSCAP_BIN, Config

SR = 16_000
FRAME = 480  # 30 ms at 16 kHz

HALLUCINATIONS = {
    "", "you", "thank you", "thank you.", "thanks for watching", "thanks for watching!", "bye", "bye.",
    "[blank_audio]", "(music)", "[music]", "(silence)", "[silence]", "okay.", "so", "uh", "um", ".",
}


# ------------------------------------------------------------------ whisper server
class WhisperServer:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.port = cfg["asr"]["port"]
        self.proc: subprocess.Popen | None = None

    def _up(self) -> bool:
        try:
            with socket.create_connection(("127.0.0.1", self.port), timeout=0.5):
                return True
        except OSError:
            return False

    def start(self) -> None:
        if self._up():
            return  # reuse a server that is already running
        model = self.cfg.asr_model
        if not model.exists():
            raise RuntimeError(f"ASR model missing: {model}. Run: sow-live init")
        if not shutil.which("whisper-server"):
            raise RuntimeError("whisper-server not found. Run: brew install whisper-cpp")
        a = self.cfg["asr"]
        self.proc = subprocess.Popen(
            ["whisper-server", "-m", str(model), "--host", "127.0.0.1", "--port", str(self.port),
             "-l", a["language"], "-t", str(a["threads"]), "-nt"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        for _ in range(120):
            if self._up():
                return
            if self.proc.poll() is not None:
                raise RuntimeError("whisper-server exited during startup")
            time.sleep(0.5)
        raise RuntimeError("whisper-server did not start within 60s")

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(5)
            except subprocess.TimeoutExpired:
                self.proc.kill()

    def transcribe(self, pcm16: np.ndarray) -> str:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SR)
            w.writeframes(pcm16.tobytes())
        fields = {"response_format": "json", "temperature": "0", "prompt": self.cfg["asr"]["vocabulary"]}
        boundary = uuid.uuid4().hex
        body = io.BytesIO()
        for k, v in fields.items():
            body.write(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
        body.write(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="a.wav"\r\n'
                   f"Content-Type: audio/wav\r\n\r\n".encode())
        body.write(buf.getvalue())
        body.write(f"\r\n--{boundary}--\r\n".encode())
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/inference", data=body.getvalue(),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        )
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read()).get("text", "")


def clean_text(text: str) -> str:
    text = re.sub(r"\[[^\]]*\]|\([^)]*(music|silence|inaudible)[^)]*\)", " ", text, flags=re.I)
    text = re.sub(r"\s+", " ", text).strip()
    return "" if text.lower().strip(" .!") in {h.strip(" .!") for h in HALLUCINATIONS} else text


# ------------------------------------------------------------------ segmentation
class Segmenter:
    """Energy VAD with an adaptive noise floor. Emits (start_seconds, int16 array)."""

    def __init__(self, cfg: Config, on_segment, clock_offset: float):
        a = cfg["audio"]
        self.silence_frames = int(a["silence_ms_to_cut"] / 30)
        self.max_frames = int(a["max_segment_seconds"] * 1000 / 30)
        self.min_speech_frames = int(a["min_speech_seconds"] * 1000 / 30)
        self.on_segment = on_segment
        self.offset = clock_offset          # session-relative time of sample 0
        self.noise = 0.003
        self.frames: list[np.ndarray] = []
        self.speech = 0
        self.silence = 0
        self.preroll: list[np.ndarray] = []
        self.pos = 0                        # samples consumed
        self.seg_start = 0
        self.level = 0.0                    # for the UI meter
        self.rest = np.zeros(0, dtype=np.float32)

    def feed(self, samples: np.ndarray) -> None:
        """samples: float32 mono 16 kHz in [-1, 1]."""
        samples = np.concatenate([self.rest, samples]) if len(self.rest) else samples
        usable = len(samples) - (len(samples) % FRAME)
        self.rest = samples[usable:]
        samples = samples[:usable]
        for i in range(0, usable, FRAME):
            f = samples[i : i + FRAME]
            rms = float(np.sqrt(np.mean(f * f)) + 1e-9)
            self.level = rms
            voiced = rms > max(self.noise * 3.0, 0.006)
            if not voiced:
                self.noise = 0.995 * self.noise + 0.005 * rms
            if self.frames:
                self.frames.append(f)
                if voiced:
                    self.speech += 1
                    self.silence = 0
                else:
                    self.silence += 1
                if self.silence >= self.silence_frames:
                    self._emit()
                elif len(self.frames) >= self.max_frames:
                    self._emit_at_quietest()
            elif voiced:
                self.seg_start = self.pos + i - FRAME * len(self.preroll)
                self.frames = self.preroll + [f]
                self.speech, self.silence = 1, 0
            else:
                self.preroll = (self.preroll + [f])[-10:]  # 300 ms lead-in
        self.pos += usable

    def flush(self) -> None:
        if self.frames:
            self._emit()

    def _emit_at_quietest(self) -> None:
        """Long monologue: cut at the quietest frame in the last 2 s, carry the rest over."""
        window = min(len(self.frames) - 1, 66)
        tail = self.frames[-window:]
        cut = len(self.frames) - window + int(np.argmin([float(np.mean(f * f)) for f in tail])) + 1
        carry = self.frames[cut:]
        self.frames = self.frames[:cut]
        start_next = self.seg_start + cut * FRAME
        self._emit()
        if carry:
            self.frames, self.speech, self.silence = carry, len(carry), 0
            self.seg_start = start_next

    def _emit(self) -> None:
        frames, speech = self.frames, self.speech
        self.frames, self.speech, self.silence, self.preroll = [], 0, 0, []
        if speech < self.min_speech_frames:
            return
        audio = np.concatenate(frames)
        pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
        self.on_segment(self.offset + self.seg_start / SR, pcm)


# ------------------------------------------------------------------ sources
class Source(threading.Thread):
    """Reads raw audio from a subprocess and feeds a Segmenter."""

    def __init__(self, name: str, cmd: list[str], fmt: str, rate: int, segmenter: Segmenter, status: dict,
                 realtime_file: bool = False):
        super().__init__(name=f"src-{name}", daemon=True)
        self.label, self.cmd, self.fmt, self.rate = name, cmd, fmt, rate
        self.seg, self.status = segmenter, status
        self.proc: subprocess.Popen | None = None
        self.stopped = threading.Event()
        self.realtime_file = realtime_file

    def run(self) -> None:
        try:
            self.proc = subprocess.Popen(self.cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except FileNotFoundError as e:
            self.status[self.label] = f"error: {e}"
            return
        threading.Thread(target=self._watch_stderr, daemon=True).start()
        bytes_per = 2 if self.fmt == "s16" else 4
        chunk = int(self.rate * 0.1) * bytes_per  # 100 ms
        leftover = np.zeros(0, dtype=np.float32)
        started = time.time()
        consumed = 0.0
        while not self.stopped.is_set():
            data = self.proc.stdout.read(chunk)
            if not data:
                break
            if self.fmt == "s16":
                x = np.frombuffer(data[: len(data) // 2 * 2], dtype="<i2").astype(np.float32) / 32768
            else:
                x = np.frombuffer(data[: len(data) // 4 * 4], dtype="<f4").astype(np.float32)
            if self.rate != SR:  # 48k -> 16k: average groups of 3 (cheap low-pass + decimate)
                x = np.concatenate([leftover, x])
                n = len(x) // 3 * 3
                leftover = x[n:]
                x = x[:n].reshape(-1, 3).mean(axis=1)
            self.seg.feed(x)
            if self.status.get(self.label, "").startswith(("starting", "waiting")):
                self.status[self.label] = "live"
            self.status[f"{self.label}_level"] = self.seg.level
            if self.realtime_file:  # replay at real-time speed
                consumed += len(data) / bytes_per / self.rate
                lag = consumed - (time.time() - started)
                if lag > 0:
                    time.sleep(lag)
        self.seg.flush()
        if not self.stopped.is_set() and self.status.get(self.label) == "live":
            self.status[self.label] = "ended"

    def _watch_stderr(self) -> None:
        for raw in self.proc.stderr:
            line = raw.decode(errors="ignore").strip()
            if line.startswith("ERROR"):
                self.status[self.label] = line[:120]
            elif line == "READY":
                self.status[self.label] = "waiting for audio"

    def stop(self) -> None:
        self.stopped.set()
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()


# ------------------------------------------------------------------ capture orchestration
class Capture:
    def __init__(self, cfg: Config, session, status: dict, on_utterance):
        self.cfg, self.s, self.status = cfg, session, status
        self.on_utterance = on_utterance
        self.asr = WhisperServer(cfg)
        self.q: queue.Queue = queue.Queue()
        self.sources: list[Source] = []
        self.recent_remote: list[tuple[float, str]] = []
        self.worker = threading.Thread(target=self._asr_loop, name="asr", daemon=True)
        self.stopping = False

    def _enqueue(self, speaker):
        return lambda start, pcm: self.q.put((speaker, start, pcm))

    def start_live(self) -> None:
        self.status["asr"] = "starting"
        self.asr.start()
        self.status["asr"] = "ready"
        self.worker.start()
        offset = self.s.elapsed()
        a = self.cfg["audio"]
        if a.get("system_audio", True):
            if not SYSCAP_BIN.exists():
                self.status["Remote"] = "error: system-audio helper missing (run sow-live init)"
            else:
                self.status["Remote"] = "starting"
                src = Source("Remote", [str(SYSCAP_BIN)], "f32", 48_000,
                             Segmenter(self.cfg, self._enqueue("Remote"), offset), self.status)
                self.sources.append(src)
                src.start()
        mic = a.get("mic_device", "default")
        if mic:
            self.status["SA"] = "starting"
            src = Source("SA", ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "avfoundation",
                                "-i", f":{mic}", "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"],
                         "s16", SR, Segmenter(self.cfg, self._enqueue("SA"), offset), self.status)
            self.sources.append(src)
            src.start()

    def start_replay(self, audio_file: str, speaker: str = "Remote", realtime: bool = True) -> None:
        """Feed a recorded call (any format ffmpeg reads) through the same path."""
        self.status["asr"] = "starting"
        self.asr.start()
        self.status["asr"] = "ready"
        self.worker.start()
        self.status[speaker] = "starting (replay)"
        src = Source(speaker, ["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", audio_file,
                               "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"],
                     "s16", SR, Segmenter(self.cfg, self._enqueue(speaker), self.s.elapsed()), self.status,
                     realtime_file=realtime)
        self.sources.append(src)
        src.start()

    def _is_echo(self, start: float, text: str) -> bool:
        """Drop mic segments that are just the speakers leaking into the mic."""
        for t, other in self.recent_remote:
            if abs(t - start) < 8 and SequenceMatcher(None, other.lower(), text.lower()).ratio() > 0.6:
                return True
        return False

    def _asr_loop(self) -> None:
        while True:
            item = self.q.get()
            if item is None:
                return
            speaker, start, pcm = item
            self.status["asr_queue"] = self.q.qsize()
            try:
                text = clean_text(self.asr.transcribe(pcm))
            except Exception as e:  # keep going on transient errors
                self.status["asr"] = f"error: {e}"[:120]
                continue
            self.status["asr"] = "ready"
            if not text:
                continue
            if speaker == "Remote":
                self.recent_remote = [(t, x) for t, x in self.recent_remote if start - t < 30] + [(start, text)]
            elif self._is_echo(start, text):
                continue
            self.on_utterance(speaker, start, text)

    def wait_replay_done(self) -> None:
        for s in self.sources:
            s.join()

    def stop(self, drain: bool = True) -> None:
        for s in self.sources:
            s.stop()
        for s in self.sources:
            s.join(timeout=3)
        if self.worker.is_alive():
            self.q.put(None)
            if drain:
                self.worker.join(timeout=120)
        self.asr.stop()
