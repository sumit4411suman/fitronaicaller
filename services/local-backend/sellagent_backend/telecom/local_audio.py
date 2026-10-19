"""Local PC audio bridge for the media gateway (Bluetooth HFP / wired / virtual-cable path).

This is the seam for the "Galaxy S25 cellular call <-> Bluetooth HFP <-> Windows audio devices <-> local AI"
architecture SIMVox-AI documents. The idea: the PC captures the caller from one Windows input device and plays
the AI's voice into another Windows output device that is wired back into the call. SELL AGENT's existing local
pipeline (faster-whisper, conversation engine, female Piper TTS, barge-in, opt-out, CRM) then runs over it
through the ordinary ``MediaTransport`` / release-gate path - no cloud STT/LLM/TTS.

HONEST LIMITATION (see docs/BLUETOOTH_AUDIO.md): for the all-wireless Bluetooth case the PC must appear as the
phone's **Hands-Free Unit**, i.e. a Windows input device carrying the live call's downlink and an output device
feeding the uplink. Desktop Windows does **not** provide a Hands-Free Unit role, so that device usually does not
exist; the bridge then has nothing to open and the diagnostic reports it. This module never fabricates audio: if
no real device carries the call, no path is produced and autonomous mode stays blocked.

The pure helpers here (device classification, capture evidence) are unit-tested headless; the live
``LocalAudioTransport`` imports ``sounddevice`` lazily and only runs on a PC with real audio hardware.
"""

from __future__ import annotations

from typing import Any

import numpy as np

# Names that suggest a Windows audio endpoint is a phone/Bluetooth hands-free call channel rather than a normal
# mic/speaker. Matching one is a HINT to check, never proof that it carries live cellular call audio.
# Note: no bare "phone" - it would match "microphone"/"headphone". HFP call channels name themselves plainly.
HFP_HINTS = ("hands-free", "handsfree", "hands free", "headset", "ag audio", "bluetooth", "hfp", "smartphone")
SR = 16_000


def classify_devices(devices: list[dict[str, Any]]) -> dict[str, Any]:
    """Split a sounddevice-style device list into usable inputs, outputs and likely phone/HFP call channels.

    Each device dict is expected to have: name, max_input_channels, max_output_channels, and optionally host_api.
    Pure and side-effect free so it can be unit-tested without audio hardware."""
    inputs, outputs, hfp = [], [], []
    for d in devices:
        name = str(d.get("name", ""))
        low = name.lower()
        entry = {"index": d.get("index"), "name": name, "host_api": d.get("host_api", "")}
        if int(d.get("max_input_channels", 0)) > 0:
            inputs.append(entry)
        if int(d.get("max_output_channels", 0)) > 0:
            outputs.append(entry)
        if any(h in low for h in HFP_HINTS):
            hfp.append({**entry, "input": int(d.get("max_input_channels", 0)) > 0, "output": int(d.get("max_output_channels", 0)) > 0})
    return {
        "inputs": inputs,
        "outputs": outputs,
        "hfp_candidates": hfp,
        "has_hfp_capture": any(c["input"] for c in hfp),
        "has_hfp_playback": any(c["output"] for c in hfp),
    }


def capture_evidence(samples: np.ndarray, sample_rate: int, *, label: str = "capture") -> dict[str, Any]:
    """Summarise a short recording into honest, inspectable numbers. A high RMS and many distinct sample values
    mean *some* signal was present on the device - it does NOT prove the signal was the remote party's call
    audio. The operator still confirms that against what the far end actually said. Pure/testable."""
    a = np.asarray(samples, dtype=np.float32).reshape(-1)
    if a.size == 0:
        return {"label": label, "sample_rate": sample_rate, "duration_s": 0.0, "rms": 0.0, "peak": 0.0, "distinct": 0, "has_signal": False, "note": "no samples captured (device opened but returned nothing)"}
    rms = float(np.sqrt(np.mean(a**2)))
    peak = float(np.max(np.abs(a)))
    distinct = int(np.unique(np.round(a, 4)).size)
    # A real voice channel has non-trivial energy and variety; silence/dead channels are flat near zero.
    has_signal = rms > 0.002 and peak > 0.01 and distinct > 50
    return {
        "label": label, "sample_rate": sample_rate, "duration_s": round(a.size / sample_rate, 3),
        "rms": round(rms, 5), "peak": round(peak, 5), "distinct": distinct, "has_signal": has_signal,
        "note": "signal present on the device (NOT proof it is the remote call audio; confirm against the live call)" if has_signal else "no usable signal: flat/near-silent device",
    }


class LocalAudioTransport:
    """``MediaTransport`` over two Windows audio devices via sounddevice: caller from ``input_device``, AI speech
    to ``output_device``. Imports sounddevice lazily, so the backend and its tests load without audio libraries.
    Used only on a real PC; it opens nothing and reports not-connected if the devices cannot be opened."""

    sample_rate = SR

    def __init__(self, input_device: str | int | None, output_device: str | int | None, *, samplerate: int | None = None, block_ms: int = 20) -> None:
        self.input_device = input_device
        self.output_device = output_device
        self.sample_rate = samplerate or SR  # Bluetooth HFP call audio is often 8 kHz; pass the device's real rate
        self.block = int(self.sample_rate * block_ms / 1_000)
        self._sd: Any = None
        self._in: Any = None
        self._out: Any = None
        self._open = False

    def start(self) -> bool:
        try:
            import sounddevice as sd  # noqa: PLC0415 - optional, PC-only
        except Exception:  # noqa: BLE001
            return False
        self._sd = sd
        try:
            self._in = sd.InputStream(samplerate=self.sample_rate, channels=1, dtype="int16", device=self.input_device, blocksize=self.block)
            self._out = sd.OutputStream(samplerate=self.sample_rate, channels=1, dtype="int16", device=self.output_device, blocksize=self.block)
            self._in.start()
            self._out.start()
            self._open = True
        except Exception:  # noqa: BLE001 - a missing/busy device means no path, never a crash
            self._open = False
        return self._open

    def recv(self) -> bytes | None:
        if not self._open or self._in is None:
            return None
        try:
            data, _ = self._in.read(self.block)
        except Exception:  # noqa: BLE001
            self._open = False
            return None
        return bytes(np.asarray(data, dtype="<i2").tobytes()) or None

    def send(self, frame: bytes) -> None:
        if not self._open or self._out is None:
            return
        try:
            self._out.write(np.frombuffer(frame, dtype="<i2").reshape(-1, 1))
        except Exception:  # noqa: BLE001
            self._open = False

    def is_connected(self) -> bool:
        return self._open

    def close(self) -> None:
        self._open = False
        for s in (self._in, self._out):
            try:
                if s is not None:
                    s.stop()
                    s.close()
            except Exception:  # noqa: BLE001, S110
                pass
