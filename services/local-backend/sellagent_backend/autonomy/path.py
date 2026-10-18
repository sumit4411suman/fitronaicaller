"""Call-audio path contract for autonomous conversations.

A path carries the REMOTE party's audio into the PC and the AI's audio into the SAME live call, digitally.
Acoustic relays (speaker -> microphone) are not paths. A telecom adapter only returns a path when that route has
been verified on the real device; the Android companion on a Jio SIM returns none because Android gives third-party
apps no call-audio stream (docs/FEASIBILITY_REPORT.md).
"""

from __future__ import annotations

from typing import Protocol

import numpy as np


class CallAudioPath(Protocol):
    name: str
    sample_rate: int  # PCM rate of read()/write(), mono float32 in [-1, 1]

    def read(self) -> np.ndarray:
        """Non-blocking: caller audio received since the last read (may be empty)."""

    def write(self, chunk: np.ndarray) -> None:
        """Send a short chunk of AI speech into the call; blocks roughly for its real-time duration."""

    def is_open(self) -> bool:
        """False once the call or the path has ended."""

    def close(self) -> None: ...


class NoVerifiedPath(RuntimeError):
    """Raised when autonomous mode is requested but no verified digital call-audio path exists."""
