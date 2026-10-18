# Kotlin protocol mirror

`com/fitron/sellagent/protocol/Protocol.kt` mirrors `sellagent_protocol/messages.py` (protocol v1.0) using
kotlinx.serialization with explicit `@SerialName` annotations.

The two Android Gradle projects are independent, so this file is **copied** (not referenced) into

* `apps/android-companion/app/src/main/java/com/fitron/sellagent/protocol/Protocol.kt`
* `apps/android-audio-diagnostic/app/src/main/java/com/fitron/sellagent/protocol/Protocol.kt`

Keep the three copies byte-identical (`diff` them in CI or before a release). When `messages.py` changes,
update this file first and re-copy.
