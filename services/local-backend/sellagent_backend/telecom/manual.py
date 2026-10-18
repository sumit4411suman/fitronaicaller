"""Human-assisted route: the operator dials on their own phone and logs the outcome in the live console.
Always available; this is the default and the only route usable while the audio release gate is closed."""

from __future__ import annotations

from sellagent_backend.telecom.base import RouteCapabilities


class ManualAdapter:
    route = "manual"

    def capabilities(self) -> RouteCapabilities:
        return RouteCapabilities(
            route="manual", can_dial=False, reports_call_state=False, remote_audio_capture=False, audio_injection=False,
            autonomous_supported=False, notes=["Operator dials and speaks; SELL AGENT provides script, approved facts, transcript capture and outcome logging."],
        )

    async def dial(self, **_: object) -> tuple[bool, str]:
        return True, "human-assisted: operator dials manually; backend marks the job in progress"

    async def cancel(self, **_: object) -> bool:
        return True
