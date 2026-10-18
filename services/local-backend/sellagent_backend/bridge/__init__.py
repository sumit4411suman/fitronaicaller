"""Acoustic AI bridge: the AI talks on a phone call through the PC speaker/microphone next to the phone on speakerphone."""

from sellagent_backend.bridge.manager import BridgeManager, default_audio_factory
from sellagent_backend.bridge.session import BRIDGE_STEP, BridgeError, BridgeSession

__all__ = ["BRIDGE_STEP", "BridgeError", "BridgeManager", "BridgeSession", "default_audio_factory"]
