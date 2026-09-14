from dataclasses import replace
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np

from oline_hri.config import load_config
from oline_hri.speech import (
    AlsaPcmStream,
    CapturedUtterance,
    EndpointingCapture,
    NoSpeechDetected,
    OfflineSpeechRecognizer,
    SILERO_CHUNK_SAMPLES,
    SILERO_STATE_SHAPE,
    SileroOnnxVad,
    SpeechCaptureError,
    SpeechRuntimeError,
    SpeechTranscriptionError,
    Transcription,
    TranscriptionRejected,
    WhisperCppTranscriber,
    _bounded_whisper_run,
    speech_runtime_status,
)


def pcm_chunk(value: int = 100) -> bytes:
    return np.full(SILERO_CHUNK_SAMPLES, value, dtype="<i2").tobytes()


class FakeVad:
    def __init__(self, probabilities) -> None:
        self.probabilities = iter(probabilities)
        self.reset_count = 0
        self.frames = []

    def reset(self) -> None:
        self.reset_count += 1

    def probability(self, samples) -> float:
        self.frames.append(np.asarray(samples).copy())
        return next(self.probabilities)


class FakeStream:
    def __init__(self, chunks) -> None:
        self.chunks = iter(chunks)
        self.entered = False
        self.exited = False
        self.timeouts = []

    def __enter__(self):
        self.entered = True
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.exited = True

    def read_chunk(self, timeout_seconds=None) -> bytes:
        self.timeouts.append(timeout_seconds)
        return next(self.chunks)


def whisper_payload(text=" Hello world!", probabilities=(0.9, 0.8)):
    return {
        "systeminfo": "not trusted",
        "model": {"type": "small.en"},
        "params": {},
        "result": {"language": "en"},
        "transcription": [
            {
                "timestamps": {"from": "00:00:00,000", "to": "00:00:01,000"},
                "offsets": {"from": 0, "to": 1000},
                "text": text,
                "tokens": [
                    {"text": " Hello", "id": 1, "p": probabilities[0]},
                    {"text": " world", "id": 2, "p": probabilities[-1]},
                    {"text": "!", "id": 3, "p": 0.01},
                ],
            }
        ],
    }


def utterance() -> CapturedUtterance:
    return CapturedUtterance(
        pcm_s16le=pcm_chunk() * 12,
        sample_rate_hz=16_000,
        duration_seconds=0.384,
        voiced_seconds=0.32,
        peak_vad_probability=0.95,
        mean_vad_probability=0.75,
    )


class EndpointingCaptureTests(unittest.TestCase):
    def test_endpointing_keeps_preroll_and_stops_after_silence(self) -> None:
        config = load_config().speech
        probabilities = [0.0, 0.0] + [0.9] * 10 + [0.0] * 32
        chunks = [pcm_chunk(index + 1) for index in range(len(probabilities))]
        stream = FakeStream(chunks)
        vad = FakeVad(probabilities)
        capture = EndpointingCapture(
            config,
            vad,
            stream_factory=lambda: stream,
        )

        result, elapsed = capture.capture()

        self.assertTrue(stream.entered)
        self.assertTrue(stream.exited)
        self.assertEqual(vad.reset_count, 1)
        self.assertEqual(len(vad.frames), len(probabilities))
        self.assertEqual(vad.frames[0].shape, (512,))
        self.assertAlmostEqual(float(vad.frames[0][0]), 1.0 / 32768.0)
        self.assertEqual(result.pcm_s16le, b"".join(chunks))
        self.assertAlmostEqual(result.voiced_seconds, 0.32)
        self.assertAlmostEqual(result.peak_vad_probability, 0.9)
        self.assertGreaterEqual(elapsed, 0.0)

    def test_start_timeout_discards_noise_without_transcription(self) -> None:
        config = load_config().speech
        config = replace(
            config,
            silero=replace(config.silero, start_timeout_seconds=1.0),
        )
        timeout_chunks = 32
        stream = FakeStream([pcm_chunk()] * timeout_chunks)
        capture = EndpointingCapture(
            config,
            FakeVad([0.0] * timeout_chunks),
            stream_factory=lambda: stream,
        )

        with self.assertRaises(NoSpeechDetected):
            capture.capture()

        self.assertTrue(stream.exited)

    def test_start_timeout_is_also_an_absolute_wall_clock_bound(self) -> None:
        config = load_config().speech
        clock_value = -10.0

        def slow_clock():
            nonlocal clock_value
            clock_value += 10.0
            return clock_value

        stream = FakeStream([pcm_chunk()] * 10)
        capture = EndpointingCapture(
            config,
            FakeVad([0.0] * 10),
            stream_factory=lambda: stream,
            clock=slow_clock,
        )

        with self.assertRaises(NoSpeechDetected):
            capture.capture()

        self.assertTrue(stream.exited)

    def test_onset_at_the_absolute_deadline_is_not_accepted(self) -> None:
        config = load_config().speech
        config = replace(
            config,
            silero=replace(config.silero, start_timeout_seconds=1.0),
        )
        clock = iter(
            (0.0, 0.0, 0.2, 0.2, 0.2, 0.6, 0.6, 0.6, 1.0)
        ).__next__
        stream = FakeStream([pcm_chunk()] * 3)
        vad = FakeVad([0.9] * 3)
        capture = EndpointingCapture(
            config,
            vad,
            stream_factory=lambda: stream,
            clock=clock,
        )

        with self.assertRaises(NoSpeechDetected):
            capture.capture()

        self.assertEqual(len(vad.frames), 2)
        self.assertEqual(stream.timeouts, [1.0, 0.8, 0.4])

    def test_vad_processing_time_counts_toward_the_start_deadline(self) -> None:
        config = load_config().speech
        config = replace(
            config,
            silero=replace(
                config.silero,
                start_timeout_seconds=1.0,
                start_trigger_seconds=0.128,
            ),
        )

        class Clock:
            value = 0.0

            def __call__(self):
                return self.value

        class SlowVad(FakeVad):
            def probability(inner_self, samples):
                probability = super().probability(samples)
                clock.value += 0.3
                return probability

        clock = Clock()
        stream = FakeStream([pcm_chunk()] * 4)
        capture = EndpointingCapture(
            config,
            SlowVad([0.9] * 4),
            stream_factory=lambda: stream,
            clock=clock,
        )

        with self.assertRaises(NoSpeechDetected):
            capture.capture()

        self.assertEqual(len(stream.timeouts), 4)

    def test_short_false_start_is_rejected(self) -> None:
        config = load_config().speech
        probabilities = [0.9] * 3 + [0.0] * 32
        capture = EndpointingCapture(
            config,
            FakeVad(probabilities),
            stream_factory=lambda: FakeStream([pcm_chunk()] * len(probabilities)),
        )

        with self.assertRaises(TranscriptionRejected):
            capture.capture()

    def test_hysteresis_does_not_end_during_soft_speech(self) -> None:
        config = load_config().speech
        probabilities = [0.9] * 10 + [0.0] + [0.4] * 30 + [0.9] + [0.0] * 32
        capture = EndpointingCapture(
            config,
            FakeVad(probabilities),
            stream_factory=lambda: FakeStream([pcm_chunk()] * len(probabilities)),
        )

        result, _ = capture.capture()

        self.assertGreater(result.duration_seconds, 2.0)

    def test_continuous_speech_stops_at_the_maximum_chunk_bound(self) -> None:
        config = load_config().speech
        config = replace(
            config,
            silero=replace(config.silero, max_utterance_seconds=1.0),
        )
        probabilities = [0.9] * 32
        stream = FakeStream([pcm_chunk()] * len(probabilities))
        capture = EndpointingCapture(
            config,
            FakeVad(probabilities),
            stream_factory=lambda: stream,
        )

        result, _ = capture.capture()

        self.assertLessEqual(result.duration_seconds, 1.0)
        self.assertEqual(len(stream.timeouts), 31)

    def test_preroll_is_included_in_the_maximum_duration(self) -> None:
        config = load_config().speech
        config = replace(
            config,
            silero=replace(config.silero, max_utterance_seconds=1.0),
        )
        probabilities = [0.0] * 10 + [0.9] * 31
        stream = FakeStream([pcm_chunk()] * len(probabilities))
        capture = EndpointingCapture(
            config,
            FakeVad(probabilities),
            stream_factory=lambda: stream,
        )

        result, _ = capture.capture()

        self.assertLessEqual(result.duration_seconds, 1.0)
        self.assertEqual(len(result.pcm_s16le), 31 * 512 * 2)

    def test_invalid_oversized_preroll_is_defensively_trimmed(self) -> None:
        config = load_config().speech
        config = replace(
            config,
            silero=replace(
                config.silero,
                pre_roll_seconds=5.0,
                start_trigger_seconds=0.128,
                min_utterance_seconds=0.128,
                max_utterance_seconds=1.0,
            ),
        )
        probabilities = [0.0] * 160 + [0.9] * 4
        stream = FakeStream([pcm_chunk()] * len(probabilities))
        capture = EndpointingCapture(
            config,
            FakeVad(probabilities),
            stream_factory=lambda: stream,
        )

        result, _ = capture.capture()

        self.assertLessEqual(result.duration_seconds, 1.0)

    def test_vad_is_reset_for_every_utterance(self) -> None:
        config = load_config().speech
        one_turn = [0.9] * 10 + [0.0] * 32
        vad = FakeVad(one_turn * 2)
        streams = iter(
            (
                FakeStream([pcm_chunk()] * len(one_turn)),
                FakeStream([pcm_chunk()] * len(one_turn)),
            )
        )
        capture = EndpointingCapture(
            config,
            vad,
            stream_factory=lambda: next(streams),
        )

        capture.capture()
        capture.capture()

        self.assertEqual(vad.reset_count, 2)


class SileroOnnxVadTests(unittest.TestCase):
    class Session:
        def __init__(self) -> None:
            self.calls = []

        def get_inputs(self):
            return [SimpleNamespace(name=name) for name in ("input", "state", "sr")]

        def get_outputs(self):
            return [SimpleNamespace(name=name) for name in ("output", "stateN")]

        def run(self, names, inputs):
            self.calls.append((names, inputs))
            return (
                np.asarray([[0.75]], dtype=np.float32),
                np.ones(SILERO_STATE_SHAPE, dtype=np.float32),
            )

    def test_adapter_supplies_context_state_and_scalar_sample_rate(self) -> None:
        model = b"test silero model"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "silero.onnx"
            path.write_bytes(model)
            session = self.Session()
            vad = SileroOnnxVad(
                str(path),
                session_factory=lambda unused: session,
                expected_sha256=sha256(model).hexdigest(),
            )

            first = vad.probability(np.ones(512, dtype=np.float32))
            second = vad.probability(np.full(512, 0.5, dtype=np.float32))

        self.assertAlmostEqual(first, 0.75)
        self.assertAlmostEqual(second, 0.75)
        first_inputs = session.calls[0][1]
        second_inputs = session.calls[1][1]
        self.assertEqual(first_inputs["input"].shape, (1, 576))
        self.assertEqual(first_inputs["state"].shape, SILERO_STATE_SHAPE)
        self.assertEqual(first_inputs["sr"].shape, ())
        self.assertTrue(np.all(first_inputs["input"][:, :64] == 0.0))
        self.assertTrue(np.all(second_inputs["input"][:, :64] == 1.0))
        self.assertTrue(np.all(second_inputs["state"] == 1.0))

    def test_hash_and_session_contract_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "silero.onnx"
            path.write_bytes(b"wrong")
            with self.assertRaises(SpeechRuntimeError):
                SileroOnnxVad(str(path), session_factory=lambda unused: self.Session())

            with self.assertRaises(SpeechRuntimeError):
                SileroOnnxVad(
                    str(path),
                    session_factory=lambda unused: SimpleNamespace(
                        get_inputs=lambda: [], get_outputs=lambda: []
                    ),
                    expected_sha256=sha256(b"wrong").hexdigest(),
                )

            with self.assertRaisesRegex(SpeechRuntimeError, "could not be loaded"):
                SileroOnnxVad(
                    str(path),
                    session_factory=lambda unused: (_ for _ in ()).throw(
                        RuntimeError("private")
                    ),
                    expected_sha256=sha256(b"wrong").hexdigest(),
                )

    def test_invalid_frame_and_model_output_are_rejected(self) -> None:
        model = b"test model"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "silero.onnx"
            path.write_bytes(model)
            session = self.Session()
            vad = SileroOnnxVad(
                str(path),
                session_factory=lambda unused: session,
                expected_sha256=sha256(model).hexdigest(),
            )
            with self.assertRaises(SpeechCaptureError):
                vad.probability(np.zeros(511, dtype=np.float32))

            session.run = lambda names, inputs: (
                np.asarray([[float("nan")]], dtype=np.float32),
                np.zeros(SILERO_STATE_SHAPE, dtype=np.float32),
            )
            with self.assertRaises(SpeechRuntimeError):
                vad.probability(np.zeros(512, dtype=np.float32))

            session.run = lambda names, inputs: (object(), object())
            with self.assertRaisesRegex(SpeechRuntimeError, "invalid output"):
                vad.probability(np.zeros(512, dtype=np.float32))

    def test_session_metadata_failures_are_sanitized(self) -> None:
        model = b"test model"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "silero.onnx"
            path.write_bytes(model)
            session = self.Session()
            session.get_inputs = lambda: (_ for _ in ()).throw(RuntimeError("private"))

            with self.assertRaisesRegex(SpeechRuntimeError, "incompatible"):
                SileroOnnxVad(
                    str(path),
                    session_factory=lambda unused: session,
                    expected_sha256=sha256(model).hexdigest(),
                )


class AlsaPcmStreamTests(unittest.TestCase):
    class Process:
        def __init__(self, audio=b"") -> None:
            self.stdout = io.BytesIO(audio)
            self.returncode = None
            self.terminated = False

        def poll(self):
            return self.returncode

        def terminate(self):
            self.terminated = True
            self.returncode = 0

        def kill(self):
            self.returncode = -9

        def wait(self, timeout=None):
            return self.returncode

    def test_capture_uses_argv_and_exact_16khz_mono_contract(self) -> None:
        config = load_config().speech
        process = self.Process(pcm_chunk())
        calls = []

        def popen(command, **kwargs):
            calls.append((command, kwargs))
            return process

        with AlsaPcmStream(config, popen=popen) as stream:
            self.assertEqual(stream.read_chunk(), pcm_chunk())

        command, kwargs = calls[0]
        self.assertEqual(command[0], "/usr/bin/arecord")
        self.assertIn("plughw:CARD=Microphone,DEV=0", command)
        self.assertEqual(command[command.index("-r") + 1], "16000")
        self.assertEqual(command[command.index("-c") + 1], "1")
        self.assertFalse(kwargs["shell"])
        self.assertTrue(process.terminated)

    def test_early_capture_eof_is_sanitized(self) -> None:
        config = load_config().speech
        process = self.Process(b"short")
        with AlsaPcmStream(config, popen=lambda *args, **kwargs: process) as stream:
            with self.assertRaisesRegex(SpeechCaptureError, "ended unexpectedly"):
                stream.read_chunk()

    def test_stalled_capture_pipe_has_a_wall_clock_timeout(self) -> None:
        config = load_config().speech
        read_fd, write_fd = os.pipe()
        process = self.Process()
        process.stdout = os.fdopen(read_fd, "rb", buffering=0)
        try:
            with AlsaPcmStream(
                config,
                popen=lambda *args, **kwargs: process,
                read_timeout_seconds=0.01,
            ) as stream:
                with self.assertRaisesRegex(SpeechCaptureError, "stalled"):
                    stream.read_chunk()
        finally:
            os.close(write_fd)


class WhisperCppTranscriberTests(unittest.TestCase):
    def runtime(self, directory, *, runner, quality=None):
        root = Path(directory)
        executable = root / "whisper-cli"
        executable.write_text("test", encoding="utf-8")
        executable.chmod(0o700)
        primary = root / "ggml-small.en-q5_0.bin"
        fallback = root / "ggml-base.en-q5_0.bin"
        primary.write_bytes(b"primary")
        fallback.write_bytes(b"fallback")
        defaults = load_config().speech
        whisper = replace(
            defaults.whisper,
            executable_path=str(executable),
            primary_model_path=str(primary),
            fallback_model_path=str(fallback),
        )
        return WhisperCppTranscriber(
            whisper,
            defaults.quality if quality is None else quality,
            runner=runner,
            clock=iter((20.0, 21.25)).__next__,
        )

    def test_valid_full_json_is_normalized_and_preserves_quality(self) -> None:
        calls = []

        def runner(command, **kwargs):
            calls.append((command, kwargs))
            payload = whisper_payload("  Hello   world!  ")
            return subprocess.CompletedProcess(command, 0, json.dumps(payload).encode())

        with tempfile.TemporaryDirectory() as directory:
            transcriber = self.runtime(directory, runner=runner)
            result = transcriber.transcribe(Path(directory) / "audio.wav", utterance())

        self.assertEqual(result.text, "Hello world!")
        self.assertEqual(result.raw_text, "  Hello   world!  ")
        self.assertEqual(result.language, "en")
        self.assertEqual(result.model_name, "ggml-small.en-q5_0.bin")
        self.assertFalse(result.used_fallback)
        self.assertAlmostEqual(result.mean_token_probability, 0.85)
        self.assertEqual(result.inference_seconds, 1.25)
        command, kwargs = calls[0]
        self.assertIn("-ojf", command)
        self.assertEqual(command[command.index("-of") + 1], "-")
        self.assertEqual(command[command.index("-t") + 1], "4")
        self.assertFalse(kwargs["shell"])
        self.assertIs(kwargs["stderr"], subprocess.DEVNULL)
        self.assertIs(kwargs["stdout"], subprocess.PIPE)

    def test_backend_failure_uses_configured_fallback_once(self) -> None:
        calls = []

        def runner(command, **kwargs):
            calls.append(command)
            if "ggml-small.en-q5_0.bin" in " ".join(command):
                return subprocess.CompletedProcess(command, 1, b"private failure")
            return subprocess.CompletedProcess(
                command, 0, json.dumps(whisper_payload()).encode()
            )

        with tempfile.TemporaryDirectory() as directory:
            transcriber = self.runtime(directory, runner=runner)
            result = transcriber.transcribe(Path(directory) / "audio.wav", utterance())

        self.assertTrue(result.used_fallback)
        self.assertEqual(result.model_name, "ggml-base.en-q5_0.bin")
        self.assertEqual(len(calls), 2)

    def test_low_probability_and_noise_markers_are_rejected_without_retry(self) -> None:
        payloads = [whisper_payload(probabilities=(0.01, 0.02))]
        payloads.extend(
            whisper_payload(marker)
            for marker in (
                "[BLANK_AUDIO]",
                "[music playing]",
                "[laughter]",
                "[applause]",
                "(background noise)",
                "[silence]",
                "[music] [music]",
                "[noise] (background noise)",
            )
        )
        for payload in payloads:
            with self.subTest(text=payload["transcription"][0]["text"]):
                calls = []

                def runner(command, **kwargs):
                    calls.append(command)
                    return subprocess.CompletedProcess(
                        command, 0, json.dumps(payload).encode()
                    )

                with tempfile.TemporaryDirectory() as directory:
                    transcriber = self.runtime(directory, runner=runner)
                    with self.assertRaises(TranscriptionRejected):
                        transcriber.transcribe(
                            Path(directory) / "audio.wav", utterance()
                        )
                self.assertEqual(len(calls), 1)

    def test_invalid_json_from_both_models_is_a_sanitized_error(self) -> None:
        for invalid_json in (
            b'{"duplicate":1,"duplicate":2}',
            b'{"value":NaN}',
        ):
            def runner(command, **kwargs):
                return subprocess.CompletedProcess(command, 0, invalid_json)

            with self.subTest(payload=invalid_json), tempfile.TemporaryDirectory() as directory:
                transcriber = self.runtime(directory, runner=runner)
                with self.assertRaisesRegex(
                    SpeechTranscriptionError, "could not transcribe"
                ):
                    transcriber.transcribe(
                        Path(directory) / "audio.wav", utterance()
                    )

    def test_deep_json_and_oversized_integer_are_sanitized(self) -> None:
        nested_json = (b'{"x":' * 2_000) + b"0" + (b"}" * 2_000)
        large_probability = whisper_payload()
        large_probability["transcription"][0]["tokens"][0]["p"] = 10**400
        responses = (
            nested_json,
            json.dumps(large_probability).encode("utf-8"),
        )
        for response in responses:
            with self.subTest(size=len(response)):
                def runner(command, **kwargs):
                    return subprocess.CompletedProcess(command, 0, response)

                with tempfile.TemporaryDirectory() as directory:
                    transcriber = self.runtime(directory, runner=runner)
                    with self.assertRaises(SpeechTranscriptionError):
                        transcriber.transcribe(
                            Path(directory) / "audio.wav", utterance()
                        )

    def test_unsafe_unicode_transcripts_are_recoverably_rejected(self) -> None:
        for unsafe in ("\x00", "\u200b", "\u202e", "\u2028", "\ud800"):
            payload = whisper_payload(f"hello{unsafe}world")
            calls = []

            def runner(command, **kwargs):
                calls.append(command)
                return subprocess.CompletedProcess(
                    command, 0, json.dumps(payload).encode("utf-8")
                )

            with self.subTest(unsafe=repr(unsafe)), tempfile.TemporaryDirectory() as directory:
                transcriber = self.runtime(directory, runner=runner)
                with self.assertRaisesRegex(TranscriptionRejected, "unsafe"):
                    transcriber.transcribe(Path(directory) / "audio.wav", utterance())
            self.assertEqual(len(calls), 1)

    def test_language_mismatch_and_runaway_stdout_fail_closed(self) -> None:
        mismatch = whisper_payload()
        mismatch["result"]["language"] = "fr"

        def mismatched_runner(command, **kwargs):
            return subprocess.CompletedProcess(command, 0, json.dumps(mismatch).encode())

        with tempfile.TemporaryDirectory() as directory:
            transcriber = self.runtime(directory, runner=mismatched_runner)
            with self.assertRaises(SpeechTranscriptionError):
                transcriber.transcribe(Path(directory) / "audio.wav", utterance())

        def oversized_runner(command, **kwargs):
            return subprocess.CompletedProcess(
                command, 0, b"x" * (4 * 1024 * 1024 + 1)
            )

        with tempfile.TemporaryDirectory() as directory:
            transcriber = self.runtime(directory, runner=oversized_runner)
            with self.assertRaises(SpeechTranscriptionError):
                transcriber.transcribe(Path(directory) / "audio.wav", utterance())

    def test_default_runner_caps_stdout_while_the_process_is_running(self) -> None:
        result = _bounded_whisper_run(
            [
                sys.executable,
                "-c",
                "import os\nwhile True: os.write(1, b'x' * 65536)",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            shell=False,
            timeout=5,
            check=False,
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, b"")

    def test_default_runner_recomputes_timeout_after_early_stdout_eof(self) -> None:
        with self.assertRaises(subprocess.TimeoutExpired):
            _bounded_whisper_run(
                [
                    sys.executable,
                    "-c",
                    (
                        "import os,time;time.sleep(.2);os.close(1);"
                        "time.sleep(.2)"
                    ),
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                shell=False,
                timeout=0.3,
                check=False,
            )

    def test_empty_and_special_token_only_results_are_recoverably_rejected(
        self,
    ) -> None:
        empty = whisper_payload()
        empty["transcription"] = []
        special_only = whisper_payload(" hello")
        special_only["transcription"][0]["tokens"] = [
            {"text": "[_BEG_]", "id": 50_364, "p": 0.99}
        ]
        for payload in (empty, special_only):
            with self.subTest(segments=len(payload["transcription"])):
                calls = []

                def runner(command, **kwargs):
                    calls.append(command)
                    return subprocess.CompletedProcess(
                        command, 0, json.dumps(payload).encode()
                    )

                with tempfile.TemporaryDirectory() as directory:
                    transcriber = self.runtime(directory, runner=runner)
                    with self.assertRaises(TranscriptionRejected):
                        transcriber.transcribe(
                            Path(directory) / "audio.wav", utterance()
                        )
                self.assertEqual(len(calls), 1)

    def test_missing_models_fails_before_backend_execution(self) -> None:
        calls = []
        with tempfile.TemporaryDirectory() as directory:
            transcriber = self.runtime(
                directory,
                runner=lambda *args, **kwargs: calls.append(args),
            )
            Path(directory, "ggml-small.en-q5_0.bin").unlink()
            Path(directory, "ggml-base.en-q5_0.bin").unlink()
            with self.assertRaises(SpeechRuntimeError):
                transcriber.transcribe(Path(directory) / "audio.wav", utterance())
        self.assertEqual(calls, [])

    def test_runtime_preflight_uses_a_non_transcribing_help_probe(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            transcriber = self.runtime(
                directory,
                runner=lambda *args, **kwargs: self.fail("transcription ran"),
            )
            executable = root / "whisper-cli"
            executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            executable.chmod(0o700)

            transcriber.check_runtime()


class OfflineSpeechRecognizerTests(unittest.TestCase):
    class Capture:
        def capture(self):
            return utterance(), 2.5

    class Transcriber:
        def __init__(self) -> None:
            self.path = None

        def check_runtime(self):
            return None

        def transcribe(self, path, captured):
            self.path = path
            self.asserted_wav = path.read_bytes()
            return Transcription(
                raw_text=" hello",
                text="hello",
                language="en",
                audio_duration_seconds=captured.duration_seconds,
                capture_seconds=0.0,
                inference_seconds=1.0,
                mean_token_probability=0.9,
                peak_vad_probability=0.95,
                model_name="small.bin",
                used_fallback=False,
            )

    def test_temporary_wav_is_deleted_and_capture_time_is_preserved(self) -> None:
        transcriber = self.Transcriber()
        recognizer = OfflineSpeechRecognizer(
            load_config().speech,
            capture=self.Capture(),
            transcriber=transcriber,
        )

        result = recognizer.listen()

        self.assertEqual(result.text, "hello")
        self.assertEqual(result.capture_seconds, 2.5)
        self.assertIsNotNone(transcriber.path)
        self.assertFalse(transcriber.path.exists())
        self.assertTrue(transcriber.asserted_wav.startswith(b"RIFF"))

    def test_transcription_failure_also_deletes_temporary_audio(self) -> None:
        class FailingTranscriber(self.Transcriber):
            def transcribe(inner_self, path, captured):
                inner_self.path = path
                raise SpeechTranscriptionError("private")

        transcriber = FailingTranscriber()
        recognizer = OfflineSpeechRecognizer(
            load_config().speech,
            capture=self.Capture(),
            transcriber=transcriber,
        )

        with self.assertRaises(SpeechTranscriptionError):
            recognizer.listen()

        self.assertIsNotNone(transcriber.path)
        self.assertFalse(transcriber.path.exists())

    def test_runtime_preflight_happens_before_capture(self) -> None:
        class Capture:
            called = False

            def capture(inner_self):
                inner_self.called = True
                return utterance(), 1.0

        class MissingRuntime:
            def check_runtime(self):
                raise SpeechRuntimeError("missing")

        capture = Capture()
        with self.assertRaises(SpeechRuntimeError):
            OfflineSpeechRecognizer(
                load_config().speech,
                capture=capture,
                transcriber=MissingRuntime(),
            )
        self.assertFalse(capture.called)

    def test_runtime_status_requires_pinned_silero_hash(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "tool"
            executable.write_text("x", encoding="utf-8")
            executable.chmod(0o700)
            silero = root / "silero.onnx"
            silero.write_bytes(b"not the pinned model")
            model = root / "model.bin"
            model.write_bytes(b"model")
            config = load_config().speech
            config = replace(
                config,
                capture_executable_path=str(executable),
                silero=replace(config.silero, model_path=str(silero)),
                whisper=replace(
                    config.whisper,
                    executable_path=str(executable),
                    primary_model_path=str(model),
                    fallback_model_path=str(root / "missing.bin"),
                ),
            )

            status = speech_runtime_status(config)

        self.assertFalse(status.ready)
        self.assertTrue(status.capture_executable)
        self.assertFalse(status.silero_model)
        self.assertFalse(status.whisper_executable)
        self.assertFalse(status.primary_model)
        self.assertFalse(status.fallback_model)

    def test_runtime_status_requires_a_verified_install_and_runnable_binary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "whisper-cli"
            executable.write_text("test", encoding="utf-8")
            executable.chmod(0o700)
            config = load_config().speech
            config = replace(
                config,
                whisper=replace(config.whisper, executable_path=str(executable)),
            )
            verified = {
                "whisper_executable": True,
                "primary_model": True,
                "fallback_model": True,
                "silero_model": True,
            }
            calls = []

            def runner(command, **kwargs):
                calls.append((command, kwargs))
                return subprocess.CompletedProcess(command, 0)

            with patch(
                "oline_hri.speech._verified_stt_artifacts",
                return_value=verified,
            ), patch("oline_hri.speech.SileroOnnxVad"):
                status = speech_runtime_status(config, runner=runner)

        self.assertTrue(status.ready)
        self.assertEqual(calls[0][0], [str(executable), "-h"])
        self.assertFalse(calls[0][1]["shell"])


if __name__ == "__main__":
    unittest.main()
