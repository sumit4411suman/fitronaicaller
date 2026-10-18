"""PC speaker/microphone I/O for the acoustic AI bridge.

The bridge never touches the phone's call audio through any API. The phone sits next to the PC on
speakerphone: the PC speaker plays the AI's voice (the phone's microphone picks it up) and the PC microphone
hears the prospect through the phone's loudspeaker. Audio is processed in memory and never written to disk.

Half duplex: the microphone is opened only while listening, so the AI does not hear (and transcribe) itself.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import numpy as np

SAMPLE_RATE = 16000
FRAME_MS = 30
FRAME = SAMPLE_RATE * FRAME_MS // 1000


class AudioUnavailable(RuntimeError):
    pass


class Speaker(Protocol):
    def speak(self, text: str, language: str) -> float:
        """Say ``text`` and block until playback finished. Returns seconds of audio played."""


class Listener(Protocol):
    def listen(self, *, timeout_s: float, max_utterance_s: float, language: str | None, should_stop: Callable[[], bool]) -> str | None:
        """Wait up to ``timeout_s`` for speech, record until the speaker pauses, transcribe. None = nothing heard."""


@dataclass
class DeviceChoice:
    input_device: int | str | None = None
    output_device: int | str | None = None


def _sd():  # type: ignore[no-untyped-def]
    try:
        import sounddevice as sd
    except (ImportError, OSError) as exc:
        raise AudioUnavailable(f"PC audio needs the 'sounddevice' package with PortAudio ({exc}). Install requirements-speech.txt.") from exc
    if not hasattr(sd, "InputStream"):
        raise AudioUnavailable("sounddevice is installed but PortAudio could not be loaded")
    return sd


def _device(v: int | str | None) -> int | str | None:
    if v in (None, ""):
        return None
    try:
        return int(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return v


class PiperSpeaker:
    """Piper TTS -> PC speaker."""

    def __init__(self, tts: object, voices: dict[str, str], devices: DeviceChoice | None = None) -> None:
        self.tts = tts
        self.voices = voices
        self.devices = devices or DeviceChoice()

    def speak(self, text: str, language: str) -> float:
        voice = self.voices.get(language) or self.voices.get("en")
        if not voice:
            raise AudioUnavailable(f"no Piper voice configured for {language!r} (Settings: ai.piper_voice_{language})")
        res = self.tts.synthesize(text, voice)  # type: ignore[attr-defined]
        sd = _sd()
        sd.play(res.audio, res.sample_rate, device=_device(self.devices.output_device))
        sd.wait()
        return len(res.audio) / res.sample_rate


class MicListener:
    """PC microphone -> energy VAD endpointing -> faster-whisper."""

    def __init__(self, stt: object, *, allow_download: bool = False, devices: DeviceChoice | None = None, energy_threshold_db: float = -42.0) -> None:
        self.stt = stt
        self.allow_download = allow_download
        self.devices = devices or DeviceChoice()
        self.energy_threshold_db = energy_threshold_db

    def record_utterance(self, *, timeout_s: float, max_utterance_s: float, should_stop: Callable[[], bool]) -> np.ndarray | None:
        from sellagent_speech.vad import EnergyVAD, VadConfig

        sd = _sd()
        vad = EnergyVAD(VadConfig(sample_rate=SAMPLE_RATE, frame_ms=FRAME_MS, energy_threshold_db=self.energy_threshold_db, min_speech_ms=240, hangover_ms=900))
        try:
            stream = sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="float32", blocksize=FRAME, device=_device(self.devices.input_device))
        except Exception as exc:  # noqa: BLE001 - no device, permission denied
            raise AudioUnavailable(f"cannot open the PC microphone: {exc}. Check Windows Settings > Privacy > Microphone.") from exc
        frames: list[np.ndarray] = []
        pre: list[np.ndarray] = []  # keep ~300 ms before onset so first syllables are not cut
        started = False
        t0 = time.monotonic()
        with stream:
            time.sleep(0.15)  # let the speaker tail die out before listening
            while not should_stop():
                data, _ = stream.read(FRAME)
                frame = data[:, 0].copy()
                onset = vad.feed(frame)
                if not started:
                    pre = (pre + [frame])[-10:]
                    if onset:
                        started = True
                        frames.extend(pre)
                    elif time.monotonic() - t0 > timeout_s:
                        return None
                    continue
                frames.append(frame)
                if not vad.in_speech or len(frames) * FRAME_MS / 1000 >= max_utterance_s:
                    break
        return np.concatenate(frames) if frames else None

    def listen(self, *, timeout_s: float, max_utterance_s: float, language: str | None, should_stop: Callable[[], bool]) -> str | None:
        audio = self.record_utterance(timeout_s=timeout_s, max_utterance_s=max_utterance_s, should_stop=should_stop)
        if audio is None or len(audio) < SAMPLE_RATE * 0.3:
            return None
        res = self.stt.transcribe(audio, language=language if language in ("hi", "en") else None, allow_download=self.allow_download)  # type: ignore[attr-defined]
        text = (res.text or "").strip()
        return text or None
