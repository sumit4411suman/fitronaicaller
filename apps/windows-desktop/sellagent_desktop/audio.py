"""Play a WAV (bytes) produced by the backend's TTS diagnostic.

Preference order: QtMultimedia ``QSoundEffect`` (only when the Addons wheel is installed), the Windows
``winsound`` module (always present on Windows), and finally handing the file to the default player.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices

_effects: list[object] = []  # keep QSoundEffect alive while playing


def play_wav_bytes(data: bytes) -> str:
    tmp = Path(tempfile.gettempdir()) / "sellagent_tts_preview.wav"
    tmp.write_bytes(data)
    try:
        from PySide6.QtMultimedia import QSoundEffect  # type: ignore

        eff = QSoundEffect()
        eff.setSource(QUrl.fromLocalFile(str(tmp)))
        eff.setVolume(0.9)
        eff.play()
        _effects.append(eff)
        return "playing via QtMultimedia"
    except ImportError:
        pass
    if sys.platform == "win32":
        import winsound

        winsound.PlaySound(data, winsound.SND_MEMORY | winsound.SND_ASYNC)
        return "playing via winsound"
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(tmp)))
    return f"opened {tmp} with the default player"
