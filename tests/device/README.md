# Real-device tests (Samsung Galaxy S25 + Jio SIM + Wi-Fi Calling)

These tests cannot run in CI or in a cloud container. They run on the Windows PC with the phone paired,
and they only **collect and check evidence**; they never simulate a result.

Run: `set SELLAGENT_DEVICE_TESTS=1` then `pytest tests/device -q`.

Each test queries the local backend for operator-confirmed `real_device` results of the 16 steps in
`/api/v1/audio-tests/plan`. A step without a confirmed real-device row is reported as **NOT TESTED**
(pytest `skip` with that reason), never as pass.
