"""Offline microphone capture, endpointing, and speech transcription."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from hashlib import sha256
import json
from math import ceil, isfinite
import os
from pathlib import Path
import selectors
import stat
import subprocess
import tempfile
from threading import Lock
import time
from typing import Any, BinaryIO, Callable, Mapping, Optional, Protocol, Sequence
import unicodedata
import wave

import numpy as np

from .config import SpeechConfig, TranscriptionQualityConfig, WhisperConfig


SILERO_SAMPLE_RATE_HZ = 16_000
SILERO_CHUNK_SAMPLES = 512
SILERO_CONTEXT_SAMPLES = 64
SILERO_STATE_SHAPE = (2, 1, 128)
SILERO_VAD_SHA256 = (
    "1a153a22f4509e292a94e67d6f9b85e8deb25b4988682b7e174c65279d8788e3"
)
PCM_SAMPLE_WIDTH_BYTES = 2
MAX_WHISPER_JSON_BYTES = 4 * 1024 * 1024
MAX_WHISPER_SEGMENTS = 1_000
MAX_TOKENS_PER_SEGMENT = 4_096
AUDIO_READ_TIMEOUT_SECONDS = 5.0
WHISPER_RUNTIME_CHECK_TIMEOUT_SECONDS = 10.0
_UNSAFE_TRANSCRIPT_CATEGORIES = frozenset({"Cc", "Cf", "Cs", "Zl", "Zp"})
_PINNED_STT_MANIFEST_LINES = frozenset(
    {
        "format=1",
        "whisper_cpp_version=v1.9.2",
        "whisper_cpp_commit=306c88f4d1286aec1bf96e544632897886af5501",
        (
            "whisper_cpp_source_url=https://github.com/ggml-org/whisper.cpp/"
            "archive/refs/tags/v1.9.2.tar.gz"
        ),
        (
            "whisper_cpp_source_sha256="
            "a6abd064fcca8b85e794d205abf328c522e9451db43a3eadc178b883b7d0e9cd"
        ),
        "whisper_model_revision=5359861c739e955e79d9a303bcbc70fb988958b1",
        (
            "small_en_source_sha256="
            "c6138d6d58ecc8322097e0f987c32f1be8bb0a18532a3f88f734d1bbf9c41e5d"
        ),
        (
            "base_en_source_sha256="
            "a03779c86df3323075f5e796cb2ce5029f00ec8869eee3fdfb897afe36c6d002"
        ),
        "quantization=q5_0",
        "silero_vad_version=v6.2.1",
        "silero_vad_commit=7e30209a3e901f9842f81b225f3e93d8199902b1",
        f"silero_vad_sha256={SILERO_VAD_SHA256}",
        "cuda_compiler=/usr/local/cuda/bin/nvcc",
        "cuda_architectures=87",
        "cmake_ggml_cuda=ON",
    }
)
_PINNED_STT_PATHS = {
    "whisper_executable": "bin/whisper-cli",
    "primary_model": "models/ggml-small.en-q5_0.bin",
    "fallback_model": "models/ggml-base.en-q5_0.bin",
    "silero_model": "models/silero_vad-v6.2.1.onnx",
}


class SpeechRecognitionError(RuntimeError):
    """Base class for sanitized local speech-recognition failures."""


class SpeechRuntimeError(SpeechRecognitionError):
    """Raised when a required local executable or model is unavailable."""


class SpeechCaptureError(SpeechRecognitionError):
    """Raised when microphone audio cannot be captured safely."""


class SpeechTranscriptionError(SpeechRecognitionError):
    """Raised when whisper.cpp cannot return a valid result."""


class NoSpeechDetected(SpeechRecognitionError):
    """Raised when the listening window expires without an utterance."""


class TranscriptionRejected(SpeechRecognitionError):
    """Raised when a transcript does not pass the local quality gate."""


@dataclass(frozen=True)
class CapturedUtterance:
    """One endpointed in-memory PCM utterance and its VAD measurements."""

    pcm_s16le: bytes = field(repr=False)
    sample_rate_hz: int
    duration_seconds: float
    voiced_seconds: float
    peak_vad_probability: float
    mean_vad_probability: float


@dataclass(frozen=True)
class Transcription:
    """Accepted whisper.cpp output passed to the text conversation boundary."""

    raw_text: str = field(repr=False)
    text: str
    language: str
    audio_duration_seconds: float
    capture_seconds: float
    inference_seconds: float
    mean_token_probability: float
    peak_vad_probability: float
    model_name: str
    used_fallback: bool


@dataclass(frozen=True)
class SpeechRuntimeStatus:
    """Validation results for native components needed by voice mode."""

    capture_executable: bool
    silero_model: bool
    whisper_executable: bool
    primary_model: bool
    fallback_model: bool

    @property
    def ready(self) -> bool:
        return (
            self.capture_executable
            and self.silero_model
            and self.whisper_executable
            and self.primary_model
            and self.fallback_model
        )

    def to_dict(self) -> dict[str, bool]:
        return {
            "capture_executable": self.capture_executable,
            "silero_model": self.silero_model,
            "whisper_executable": self.whisper_executable,
            "primary_model": self.primary_model,
            "fallback_model": self.fallback_model,
        }


class VoiceActivityDetector(Protocol):
    """Minimal stateful VAD contract used by the endpoint detector."""

    def reset(self) -> None:
        ...

    def probability(self, samples: np.ndarray) -> float:
        ...


class ChunkStream(Protocol):
    """One context-managed source of fixed-width PCM chunks."""

    def __enter__(self) -> "ChunkStream":
        ...

    def __exit__(self, exc_type, exc, traceback) -> None:
        ...

    def read_chunk(self, timeout_seconds: Optional[float] = None) -> bytes:
        ...


class SileroOnnxVad:
    """Pinned Silero VAD v6.2.1 ONNX streaming adapter."""

    def __init__(
        self,
        model_path: str,
        *,
        session_factory: Optional[Callable[[Path], Any]] = None,
        expected_sha256: str = SILERO_VAD_SHA256,
    ) -> None:
        path = _regular_file(model_path)
        if _sha256_file(path) != expected_sha256:
            raise SpeechRuntimeError("the configured Silero model is not supported")
        try:
            self._session = (
                session_factory(path)
                if session_factory is not None
                else _silero_session(path)
            )
        except SpeechRecognitionError:
            raise
        except Exception:
            raise SpeechRuntimeError("the Silero runtime could not be loaded") from None
        self._validate_session_contract()
        self._state = np.zeros(SILERO_STATE_SHAPE, dtype=np.float32)
        self._context = np.zeros((1, SILERO_CONTEXT_SAMPLES), dtype=np.float32)

    def _validate_session_contract(self) -> None:
        try:
            input_names = {item.name for item in self._session.get_inputs()}
            output_names = {item.name for item in self._session.get_outputs()}
        except Exception:
            raise SpeechRuntimeError("the Silero runtime is incompatible") from None
        if input_names != {"input", "state", "sr"}:
            raise SpeechRuntimeError("the Silero model input contract is unsupported")
        if not {"output", "stateN"}.issubset(output_names):
            raise SpeechRuntimeError("the Silero model output contract is unsupported")

    def reset(self) -> None:
        self._state.fill(0.0)
        self._context.fill(0.0)

    def probability(self, samples: np.ndarray) -> float:
        try:
            frame = np.asarray(samples, dtype=np.float32)
        except (TypeError, ValueError):
            raise SpeechCaptureError("microphone chunks have an invalid shape") from None
        if frame.shape != (SILERO_CHUNK_SAMPLES,):
            raise SpeechCaptureError("microphone chunks have an invalid shape")
        if not np.all(np.isfinite(frame)):
            raise SpeechCaptureError("microphone audio contains invalid samples")

        model_input = np.concatenate((self._context, frame.reshape(1, -1)), axis=1)
        try:
            output, next_state = self._session.run(
                ["output", "stateN"],
                {
                    "input": model_input,
                    "state": self._state,
                    "sr": np.asarray(SILERO_SAMPLE_RATE_HZ, dtype=np.int64),
                },
            )
        except Exception:
            raise SpeechRuntimeError("Silero VAD inference failed") from None

        try:
            probability_values = np.asarray(output, dtype=np.float32).reshape(-1)
            state = np.asarray(next_state, dtype=np.float32)
        except (TypeError, ValueError, OverflowError):
            raise SpeechRuntimeError("Silero VAD returned invalid output") from None
        if (
            probability_values.size != 1
            or state.shape != SILERO_STATE_SHAPE
            or not np.all(np.isfinite(probability_values))
            or not np.all(np.isfinite(state))
        ):
            raise SpeechRuntimeError("Silero VAD returned invalid output")
        probability = float(probability_values[0])
        if not 0.0 <= probability <= 1.0:
            raise SpeechRuntimeError("Silero VAD returned an invalid probability")

        self._state = state.copy()
        self._context = frame[-SILERO_CONTEXT_SAMPLES:].reshape(1, -1).copy()
        return probability


class AlsaPcmStream:
    """Stream converted mono PCM from one ALSA capture device."""

    def __init__(
        self,
        config: SpeechConfig,
        *,
        popen: Callable[..., Any] = subprocess.Popen,
        read_timeout_seconds: float = AUDIO_READ_TIMEOUT_SECONDS,
    ) -> None:
        if not isfinite(read_timeout_seconds) or read_timeout_seconds <= 0.0:
            raise ValueError("audio read timeout must be positive")
        self._config = config
        self._popen = popen
        self._read_timeout_seconds = read_timeout_seconds
        self._process: Optional[Any] = None
        self._stdout: Optional[BinaryIO] = None
        self._chunk_bytes = config.chunk_samples * PCM_SAMPLE_WIDTH_BYTES

    def __enter__(self) -> "AlsaPcmStream":
        executable = _executable_file(self._config.capture_executable_path)
        command = [
            str(executable),
            "-q",
            "-D",
            self._config.capture_device,
            "-t",
            "raw",
            "-f",
            "S16_LE",
            "-r",
            str(self._config.sample_rate_hz),
            "-c",
            "1",
        ]
        try:
            process = self._popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                shell=False,
                bufsize=0,
            )
        except (OSError, ValueError):
            raise SpeechCaptureError("microphone capture could not start") from None
        if process.stdout is None:
            _stop_process(process)
            raise SpeechCaptureError("microphone capture did not provide audio")
        self._process = process
        self._stdout = process.stdout
        return self

    def read_chunk(self, timeout_seconds: Optional[float] = None) -> bytes:
        if self._process is None or self._stdout is None:
            raise SpeechCaptureError("microphone capture is not running")
        timeout = self._read_timeout_seconds
        if timeout_seconds is not None:
            if not isfinite(timeout_seconds) or timeout_seconds <= 0.0:
                raise SpeechCaptureError("microphone capture deadline expired")
            timeout = min(timeout, timeout_seconds)
        chunk = _read_exact(
            self._stdout,
            self._chunk_bytes,
            timeout_seconds=timeout,
        )
        if len(chunk) != self._chunk_bytes:
            raise SpeechCaptureError("microphone capture ended unexpectedly")
        return chunk

    def __exit__(self, exc_type, exc, traceback) -> None:
        process = self._process
        stream = self._stdout
        self._process = None
        self._stdout = None
        if stream is not None:
            try:
                stream.close()
            except OSError:
                pass
        if process is not None:
            _stop_process(process)


class EndpointingCapture:
    """Collect one utterance using Silero probabilities and bounded silence."""

    def __init__(
        self,
        config: SpeechConfig,
        vad: VoiceActivityDetector,
        *,
        stream_factory: Optional[Callable[[], ChunkStream]] = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._config = config
        self._vad = vad
        self._stream_factory = (
            stream_factory
            if stream_factory is not None
            else lambda: AlsaPcmStream(config)
        )
        self._clock = clock

    def capture(self) -> tuple[CapturedUtterance, float]:
        self._vad.reset()
        started_at = self._clock()
        utterance = self._capture_stream(started_at)
        elapsed = _safe_elapsed(self._clock(), started_at)
        return utterance, elapsed

    def _capture_stream(self, listen_started_at: float) -> CapturedUtterance:
        config = self._config
        chunk_seconds = config.chunk_samples / config.sample_rate_hz
        pre_roll_chunks = ceil(config.silero.pre_roll_seconds / chunk_seconds)
        start_chunks = ceil(config.silero.start_trigger_seconds / chunk_seconds)
        end_chunks = ceil(config.silero.end_silence_seconds / chunk_seconds)
        min_voice_chunks = ceil(config.silero.min_utterance_seconds / chunk_seconds)
        start_timeout_chunks = max(
            1,
            ceil(config.silero.start_timeout_seconds / chunk_seconds) - 1,
        )
        max_utterance_chunks = max(
            1,
            int(config.silero.max_utterance_seconds / chunk_seconds),
        )
        pending: deque[tuple[bytes, float]] = deque(
            maxlen=max(1, pre_roll_chunks + start_chunks)
        )
        probabilities: list[float] = []
        audio_chunks: list[bytes] = []
        consecutive_start = 0
        consecutive_silence = 0
        voiced_chunks = 0
        chunks_before_start = 0
        captured_chunks = 0
        speech_started = False
        utterance_started_at: Optional[float] = None

        with self._stream_factory() as stream:
            while True:
                before_read = self._clock()
                if not speech_started:
                    remaining = _remaining_time(
                        before_read,
                        listen_started_at,
                        config.silero.start_timeout_seconds,
                    )
                    if remaining <= 0.0:
                        raise NoSpeechDetected("no speech was detected")
                else:
                    if utterance_started_at is None:
                        raise SpeechCaptureError("microphone endpoint timing failed")
                    remaining = _remaining_time(
                        before_read,
                        utterance_started_at,
                        config.silero.max_utterance_seconds,
                    )
                    if remaining <= 0.0:
                        return _finish_utterance(
                            audio_chunks,
                            probabilities,
                            voiced_chunks=voiced_chunks,
                            min_voice_chunks=min_voice_chunks,
                            config=config,
                        )

                raw_chunk = stream.read_chunk(timeout_seconds=remaining)
                now = self._clock()
                if not speech_started and _safe_elapsed(now, listen_started_at) >= (
                    config.silero.start_timeout_seconds
                ):
                    raise NoSpeechDetected("no speech was detected")
                if speech_started:
                    if utterance_started_at is None:
                        raise SpeechCaptureError("microphone endpoint timing failed")
                    if _safe_elapsed(now, utterance_started_at) >= (
                        config.silero.max_utterance_seconds
                    ):
                        return _finish_utterance(
                            audio_chunks,
                            probabilities,
                            voiced_chunks=voiced_chunks,
                            min_voice_chunks=min_voice_chunks,
                            config=config,
                        )
                samples = np.frombuffer(raw_chunk, dtype="<i2").astype(np.float32)
                samples *= 1.0 / 32768.0
                probability = self._vad.probability(samples)
                now = self._clock()
                if not speech_started and _safe_elapsed(now, listen_started_at) >= (
                    config.silero.start_timeout_seconds
                ):
                    raise NoSpeechDetected("no speech was detected")
                if speech_started:
                    if utterance_started_at is None:
                        raise SpeechCaptureError("microphone endpoint timing failed")
                    if _safe_elapsed(now, utterance_started_at) >= (
                        config.silero.max_utterance_seconds
                    ):
                        return _finish_utterance(
                            audio_chunks,
                            probabilities,
                            voiced_chunks=voiced_chunks,
                            min_voice_chunks=min_voice_chunks,
                            config=config,
                        )

                if not speech_started:
                    chunks_before_start += 1
                    pending.append((raw_chunk, probability))
                    if probability >= config.silero.threshold:
                        consecutive_start += 1
                    else:
                        consecutive_start = 0
                    if consecutive_start >= start_chunks:
                        speech_started = True
                        utterance_started_at = now
                        bounded_pending = tuple(pending)[-max_utterance_chunks:]
                        audio_chunks.extend(chunk for chunk, _ in bounded_pending)
                        probabilities.extend(value for _, value in bounded_pending)
                        voiced_chunks = sum(
                            value >= config.silero.threshold
                            for _, value in bounded_pending
                        )
                        captured_chunks = len(audio_chunks)
                        if captured_chunks >= max_utterance_chunks:
                            return _finish_utterance(
                                audio_chunks,
                                probabilities,
                                voiced_chunks=voiced_chunks,
                                min_voice_chunks=min_voice_chunks,
                                config=config,
                            )
                    elif (
                        chunks_before_start >= start_timeout_chunks
                        or _safe_elapsed(now, listen_started_at)
                        >= config.silero.start_timeout_seconds
                    ):
                        raise NoSpeechDetected("no speech was detected")
                    continue

                audio_chunks.append(raw_chunk)
                probabilities.append(probability)
                captured_chunks += 1
                if probability >= config.silero.threshold:
                    voiced_chunks += 1
                    consecutive_silence = 0
                elif probability <= config.silero.silence_threshold:
                    consecutive_silence += 1
                elif consecutive_silence:
                    consecutive_silence += 1

                if consecutive_silence >= end_chunks:
                    return _finish_utterance(
                        audio_chunks,
                        probabilities,
                        voiced_chunks=voiced_chunks,
                        min_voice_chunks=min_voice_chunks,
                        config=config,
                    )
                if utterance_started_at is None:
                    raise SpeechCaptureError("microphone endpoint timing failed")
                if (
                    captured_chunks >= max_utterance_chunks
                    or _safe_elapsed(now, utterance_started_at)
                    >= config.silero.max_utterance_seconds
                ):
                    return _finish_utterance(
                        audio_chunks,
                        probabilities,
                        voiced_chunks=voiced_chunks,
                        min_voice_chunks=min_voice_chunks,
                        config=config,
                    )


class WhisperCppTranscriber:
    """Invoke the pinned first-party whisper.cpp CLI once per utterance."""

    def __init__(
        self,
        whisper: WhisperConfig,
        quality: TranscriptionQualityConfig,
        *,
        runner: Optional[Callable[..., Any]] = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._config = whisper
        self._quality = quality
        self._runner = _bounded_whisper_run if runner is None else runner
        self._clock = clock

    def check_runtime(self) -> None:
        """Fail before capture when no configured transcription backend exists."""

        executable = _executable_file(self._config.executable_path)
        # The full recognizer verifies this executable against the pinned
        # installer checksum before reaching this probe.
        if not _whisper_runtime_is_runnable(executable, runner=subprocess.run):
            raise SpeechRuntimeError("the configured whisper runtime is not runnable")
        if not any(
            _optional_regular_file(path) is not None
            for path in (
                self._config.primary_model_path,
                self._config.fallback_model_path,
            )
        ):
            raise SpeechRuntimeError("no configured whisper model is available")

    def transcribe(
        self, wav_path: Path, utterance: CapturedUtterance
    ) -> Transcription:
        executable = _executable_file(self._config.executable_path)
        model_paths = (
            _optional_regular_file(self._config.primary_model_path),
            _optional_regular_file(self._config.fallback_model_path),
        )
        attempted = False
        started_at = self._clock()
        for index, model_path in enumerate(model_paths):
            if model_path is None:
                continue
            attempted = True
            payload = self._run(executable, model_path, wav_path)
            if payload is None:
                continue
            try:
                raw_text, language, probabilities = _whisper_result(payload)
            except SpeechTranscriptionError:
                continue
            if language != self._config.language:
                continue
            normalized = _normalize_transcript(raw_text, self._quality)
            if not probabilities:
                raise TranscriptionRejected(
                    "the transcription has no usable word probabilities"
                )
            mean_probability = sum(probabilities) / len(probabilities)
            if mean_probability < self._quality.min_mean_token_probability:
                raise TranscriptionRejected(
                    "the transcription did not pass the quality gate"
                )
            inference_seconds = self._clock() - started_at
            if not isfinite(inference_seconds) or inference_seconds < 0.0:
                raise SpeechTranscriptionError("transcription timing failed")
            return Transcription(
                raw_text=raw_text,
                text=normalized,
                language=language,
                audio_duration_seconds=utterance.duration_seconds,
                capture_seconds=0.0,
                inference_seconds=inference_seconds,
                mean_token_probability=mean_probability,
                peak_vad_probability=utterance.peak_vad_probability,
                model_name=model_path.name,
                used_fallback=index == 1,
            )
        if not attempted:
            raise SpeechRuntimeError("no configured whisper model is available")
        raise SpeechTranscriptionError("whisper.cpp could not transcribe the utterance")

    def _run(
        self, executable: Path, model_path: Path, wav_path: Path
    ) -> Optional[Mapping[str, Any]]:
        command = [
            str(executable),
            "-m",
            str(model_path),
            "-f",
            str(wav_path),
            "-l",
            self._config.language,
            "-t",
            str(self._config.threads),
            "-ojf",
            "-of",
            "-",
            "-np",
        ]
        try:
            result = self._runner(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                shell=False,
                timeout=self._config.timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired, ValueError):
            return None
        if result.returncode != 0 or not isinstance(result.stdout, bytes):
            return None
        encoded = result.stdout
        if not encoded or len(encoded) > MAX_WHISPER_JSON_BYTES:
            return None
        try:
            decoded = encoded.decode("utf-8")
            payload = json.loads(
                decoded,
                object_pairs_hook=_unique_object,
                parse_constant=_reject_nonstandard_constant,
            )
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError):
            return None
        return payload if isinstance(payload, Mapping) else None


class OfflineSpeechRecognizer:
    """Synchronous capture -> VAD -> whisper.cpp -> quality-gate pipeline."""

    def __init__(
        self,
        config: SpeechConfig,
        *,
        capture: Optional[EndpointingCapture] = None,
        transcriber: Optional[WhisperCppTranscriber] = None,
    ) -> None:
        self._config = config
        if capture is None or transcriber is None:
            _require_verified_stt_runtime(config)
        if capture is None:
            vad = SileroOnnxVad(config.silero.model_path)
            capture = EndpointingCapture(config, vad)
        self._capture = capture
        if transcriber is None:
            transcriber = WhisperCppTranscriber(config.whisper, config.quality)
        transcriber.check_runtime()
        self._transcriber = transcriber
        self._lock = Lock()

    def listen(self) -> Transcription:
        """Capture and transcribe one utterance without retaining raw audio."""

        with self._lock:
            utterance, capture_seconds = self._capture.capture()
            try:
                with tempfile.TemporaryDirectory(prefix="oline-hri-stt-") as directory:
                    wav_path = Path(directory) / "utterance.wav"
                    _write_wav(wav_path, utterance)
                    result = self._transcriber.transcribe(wav_path, utterance)
            except SpeechRecognitionError:
                raise
            except (OSError, wave.Error):
                raise SpeechTranscriptionError(
                    "temporary speech processing failed"
                ) from None
            return Transcription(
                raw_text=result.raw_text,
                text=result.text,
                language=result.language,
                audio_duration_seconds=result.audio_duration_seconds,
                capture_seconds=capture_seconds,
                inference_seconds=result.inference_seconds,
                mean_token_probability=result.mean_token_probability,
                peak_vad_probability=result.peak_vad_probability,
                model_name=result.model_name,
                used_fallback=result.used_fallback,
            )


def speech_runtime_status(
    config: SpeechConfig,
    *,
    runner: Callable[..., Any] = subprocess.run,
) -> SpeechRuntimeStatus:
    """Validate pinned runtime assets without opening the microphone."""

    capture = _is_executable(config.capture_executable_path)
    verified = _verified_stt_artifacts(config)
    whisper_path = _existing_regular_path(config.whisper.executable_path)
    whisper = verified["whisper_executable"] and _whisper_runtime_is_runnable(
        whisper_path,
        runner=runner,
    )
    silero = False
    if verified["silero_model"]:
        try:
            SileroOnnxVad(config.silero.model_path)
        except SpeechRecognitionError:
            pass
        else:
            silero = True
    return SpeechRuntimeStatus(
        capture,
        silero,
        whisper,
        verified["primary_model"],
        verified["fallback_model"],
    )


def _finish_utterance(
    chunks: Sequence[bytes],
    probabilities: Sequence[float],
    *,
    voiced_chunks: int,
    min_voice_chunks: int,
    config: SpeechConfig,
) -> CapturedUtterance:
    if voiced_chunks < min_voice_chunks:
        raise TranscriptionRejected("the detected utterance was too short")
    return _captured_utterance(
        chunks,
        probabilities,
        voiced_chunks=voiced_chunks,
        config=config,
    )


def _captured_utterance(
    chunks: Sequence[bytes],
    probabilities: Sequence[float],
    *,
    voiced_chunks: int,
    config: SpeechConfig,
) -> CapturedUtterance:
    pcm = b"".join(chunks)
    if not pcm or len(pcm) % PCM_SAMPLE_WIDTH_BYTES:
        raise SpeechCaptureError("captured audio is invalid")
    duration = len(pcm) / (PCM_SAMPLE_WIDTH_BYTES * config.sample_rate_hz)
    chunk_seconds = config.chunk_samples / config.sample_rate_hz
    if not probabilities:
        raise SpeechCaptureError("voice activity measurements are missing")
    return CapturedUtterance(
        pcm_s16le=pcm,
        sample_rate_hz=config.sample_rate_hz,
        duration_seconds=duration,
        voiced_seconds=voiced_chunks * chunk_seconds,
        peak_vad_probability=max(probabilities),
        mean_vad_probability=sum(probabilities) / len(probabilities),
    )


def _safe_elapsed(now: float, started_at: float) -> float:
    elapsed = now - started_at
    if not isfinite(elapsed) or elapsed < 0.0:
        raise SpeechCaptureError("microphone timing failed")
    return elapsed


def _remaining_time(now: float, started_at: float, limit_seconds: float) -> float:
    return limit_seconds - _safe_elapsed(now, started_at)


def _whisper_result(
    payload: Mapping[str, Any],
) -> tuple[str, str, tuple[float, ...]]:
    result = payload.get("result")
    segments = payload.get("transcription")
    if not isinstance(result, Mapping) or not isinstance(segments, list):
        raise SpeechTranscriptionError("whisper.cpp returned invalid metadata")
    language = result.get("language")
    if not isinstance(language, str) or not language.strip() or len(language) > 16:
        raise SpeechTranscriptionError("whisper.cpp returned invalid language metadata")
    if len(segments) > MAX_WHISPER_SEGMENTS:
        raise SpeechTranscriptionError("whisper.cpp returned invalid segments")

    texts: list[str] = []
    probabilities: list[float] = []
    for segment in segments:
        if not isinstance(segment, Mapping):
            raise SpeechTranscriptionError("whisper.cpp returned an invalid segment")
        text = segment.get("text")
        tokens = segment.get("tokens")
        if not isinstance(text, str) or not isinstance(tokens, list):
            raise SpeechTranscriptionError("whisper.cpp returned an invalid segment")
        if len(tokens) > MAX_TOKENS_PER_SEGMENT:
            raise SpeechTranscriptionError("whisper.cpp returned too many tokens")
        texts.append(text)
        for token in tokens:
            if not isinstance(token, Mapping):
                raise SpeechTranscriptionError("whisper.cpp returned an invalid token")
            token_text = token.get("text")
            token_probability = token.get("p")
            if not isinstance(token_text, str):
                raise SpeechTranscriptionError("whisper.cpp returned an invalid token")
            stripped_token = token_text.strip()
            if (
                not any(character.isalnum() for character in stripped_token)
                or (
                    stripped_token.startswith("[_")
                    and stripped_token.endswith("]")
                )
                or (
                    stripped_token.startswith("<|")
                    and stripped_token.endswith("|>")
                )
            ):
                continue
            if isinstance(token_probability, bool) or not isinstance(
                token_probability, (int, float)
            ):
                raise SpeechTranscriptionError(
                    "whisper.cpp returned an invalid token probability"
                )
            try:
                probability = float(token_probability)
            except (TypeError, ValueError, OverflowError):
                raise SpeechTranscriptionError(
                    "whisper.cpp returned an invalid token probability"
                ) from None
            if not isfinite(probability) or not 0.0 <= probability <= 1.0:
                raise SpeechTranscriptionError(
                    "whisper.cpp returned an invalid token probability"
                )
            probabilities.append(probability)
    return "".join(texts), language.strip().casefold(), tuple(probabilities)


def _normalize_transcript(
    raw_text: str, quality: TranscriptionQualityConfig
) -> str:
    if not isinstance(raw_text, str):
        raise SpeechTranscriptionError("whisper.cpp returned invalid text")
    if any(
        unicodedata.category(character) in _UNSAFE_TRANSCRIPT_CATEGORIES
        for character in raw_text
    ):
        raise TranscriptionRejected("the transcription contains unsafe characters")
    normalized = unicodedata.normalize("NFC", raw_text)
    if any(
        unicodedata.category(character) in _UNSAFE_TRANSCRIPT_CATEGORIES
        for character in normalized
    ):
        raise TranscriptionRejected("the transcription contains unsafe characters")
    normalized = " ".join(normalized.split())
    if not quality.min_text_characters <= len(normalized) <= quality.max_text_characters:
        raise TranscriptionRejected("the transcription length is not usable")
    if not any(character.isalnum() for character in normalized):
        raise TranscriptionRejected("the transcription contains no speech text")

    if _is_only_noise_markers(normalized):
        raise TranscriptionRejected("the transcription contains only a noise marker")
    return normalized


def _is_only_noise_markers(text: str) -> bool:
    punctuation = " .,!?:;-_()[]<>{}"
    words = tuple(
        "".join(
            " " if character in punctuation else character
            for character in text.casefold()
        ).split()
    )
    if not words:
        return False
    phrases = (
        ("background", "music"),
        ("background", "noise"),
        ("blank", "audio"),
        ("music", "playing"),
        ("no", "audio"),
        ("no", "speech"),
        ("applause",),
        ("breathing",),
        ("coughing",),
        ("inaudible",),
        ("laughing",),
        ("laughter",),
        ("music",),
        ("noise",),
        ("silence",),
        ("unintelligible",),
    )
    reachable = {0}
    for index in range(len(words)):
        if index not in reachable:
            continue
        for phrase in phrases:
            if words[index : index + len(phrase)] == phrase:
                reachable.add(index + len(phrase))
    return len(words) in reachable


def _write_wav(path: Path, utterance: CapturedUtterance) -> None:
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(PCM_SAMPLE_WIDTH_BYTES)
        wav_file.setframerate(utterance.sample_rate_hz)
        wav_file.writeframes(utterance.pcm_s16le)


def _silero_session(path: Path) -> Any:
    try:
        import onnxruntime as ort

        options = ort.SessionOptions()
        options.inter_op_num_threads = 1
        options.intra_op_num_threads = 1
        options.log_severity_level = 3
        return ort.InferenceSession(
            str(path),
            sess_options=options,
            providers=["CPUExecutionProvider"],
        )
    except Exception:
        raise SpeechRuntimeError("the Silero runtime could not be loaded") from None


def _read_exact(
    stream: BinaryIO,
    size: int,
    *,
    timeout_seconds: float,
) -> bytes:
    try:
        stream.fileno()
    except (AttributeError, OSError, ValueError):
        return _read_exact_test_stream(stream, size)

    output = bytearray()
    deadline = time.monotonic() + timeout_seconds
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(stream, selectors.EVENT_READ)
            while len(output) < size:
                remaining = deadline - time.monotonic()
                if remaining <= 0.0 or not selector.select(remaining):
                    raise SpeechCaptureError("microphone capture stalled")
                try:
                    block = stream.read(size - len(output))
                except OSError:
                    raise SpeechCaptureError(
                        "microphone audio could not be read"
                    ) from None
                if not block:
                    break
                output.extend(block)
    except (OSError, ValueError):
        raise SpeechCaptureError("microphone audio could not be monitored") from None
    return bytes(output)


def _bounded_whisper_run(
    command: Sequence[str],
    *,
    stdin: Any,
    stdout: Any,
    stderr: Any,
    shell: bool,
    timeout: float,
    check: bool,
) -> subprocess.CompletedProcess:
    """Run whisper.cpp while enforcing its stdout limit during execution."""

    if shell or check or stdout is not subprocess.PIPE:
        raise ValueError("unsupported whisper subprocess options")
    process = subprocess.Popen(
        command,
        stdin=stdin,
        stdout=subprocess.PIPE,
        stderr=stderr,
        shell=False,
        bufsize=0,
    )
    if process.stdout is None:
        _kill_process(process)
        raise OSError("whisper subprocess did not expose stdout")
    output = bytearray()
    deadline = time.monotonic() + timeout
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0.0:
                    raise subprocess.TimeoutExpired(command, timeout)
                if not selector.select(remaining):
                    raise subprocess.TimeoutExpired(command, timeout)
                block = os.read(
                    process.stdout.fileno(),
                    min(64 * 1024, MAX_WHISPER_JSON_BYTES + 1 - len(output)),
                )
                if not block:
                    wait_remaining = deadline - time.monotonic()
                    if wait_remaining <= 0.0:
                        raise subprocess.TimeoutExpired(command, timeout)
                    return_code = process.wait(timeout=wait_remaining)
                    if time.monotonic() > deadline:
                        raise subprocess.TimeoutExpired(command, timeout)
                    return subprocess.CompletedProcess(
                        command,
                        return_code,
                        stdout=bytes(output),
                    )
                output.extend(block)
                if len(output) > MAX_WHISPER_JSON_BYTES:
                    _kill_process(process)
                    return subprocess.CompletedProcess(
                        command,
                        process.returncode if process.returncode else 1,
                        stdout=b"",
                    )
    except BaseException:
        _kill_process(process)
        raise
    finally:
        try:
            process.stdout.close()
        except OSError:
            pass


def _read_exact_test_stream(stream: BinaryIO, size: int) -> bytes:
    """Read file-like unit-test doubles that do not expose a selectable fd."""

    output = bytearray()
    while len(output) < size:
        try:
            block = stream.read(size - len(output))
        except OSError:
            raise SpeechCaptureError("microphone audio could not be read") from None
        if not block:
            break
        output.extend(block)
    return bytes(output)


def _stop_process(process: Any) -> None:
    try:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2.0)
    except (OSError, ProcessLookupError, subprocess.TimeoutExpired):
        pass


def _kill_process(process: Any) -> None:
    try:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=2.0)
    except (OSError, ProcessLookupError, subprocess.TimeoutExpired):
        pass


def _regular_file(configured_path: str) -> Path:
    path = _existing_regular_path(configured_path)
    if path is None:
        raise SpeechRuntimeError("a configured speech model is unavailable")
    return path


def _optional_regular_file(configured_path: str) -> Optional[Path]:
    return _existing_regular_path(configured_path)


def _existing_regular_path(configured_path: str) -> Optional[Path]:
    try:
        path = Path(configured_path).expanduser()
        mode = path.stat().st_mode
    except (OSError, RuntimeError, ValueError):
        return None
    return path if stat.S_ISREG(mode) else None


def _executable_file(configured_path: str) -> Path:
    path = _existing_regular_path(configured_path)
    if path is None or not os.access(path, os.X_OK):
        raise SpeechRuntimeError("a configured speech executable is unavailable")
    return path


def _is_executable(configured_path: str) -> bool:
    path = _existing_regular_path(configured_path)
    return path is not None and os.access(path, os.X_OK)


def _verified_stt_artifacts(config: SpeechConfig) -> dict[str, bool]:
    verified = {name: False for name in _PINNED_STT_PATHS}
    executable = _existing_regular_path(config.whisper.executable_path)
    if executable is None:
        return verified
    root = executable.parent.parent
    manifest = _read_small_text(root / "MANIFEST")
    checksum_text = _read_small_text(root / "SHA256SUMS")
    if manifest is None or checksum_text is None:
        return verified
    manifest_lines = manifest.splitlines()
    if (
        len(manifest_lines) != len(_PINNED_STT_MANIFEST_LINES)
        or set(manifest_lines) != _PINNED_STT_MANIFEST_LINES
    ):
        return verified
    checksums = _parse_checksum_manifest(checksum_text)
    if checksums is None:
        return verified
    if _sha256_file(root / "MANIFEST") != checksums.get("MANIFEST"):
        return verified

    configured = {
        "whisper_executable": config.whisper.executable_path,
        "primary_model": config.whisper.primary_model_path,
        "fallback_model": config.whisper.fallback_model_path,
        "silero_model": config.silero.model_path,
    }
    for name, relative_path in _PINNED_STT_PATHS.items():
        path = _existing_regular_path(configured[name])
        expected_path = root / relative_path
        expected_checksum = checksums.get(relative_path)
        if (
            path is not None
            and not path.is_symlink()
            and path == expected_path
            and expected_checksum is not None
            and _sha256_file(path) == expected_checksum
        ):
            verified[name] = True
    if verified["silero_model"]:
        silero_path = _existing_regular_path(config.silero.model_path)
        verified["silero_model"] = (
            silero_path is not None
            and _sha256_file(silero_path) == SILERO_VAD_SHA256
        )
    return verified


def _require_verified_stt_runtime(config: SpeechConfig) -> None:
    if not _is_executable(config.capture_executable_path):
        raise SpeechRuntimeError("the configured capture executable is unavailable")
    verified = _verified_stt_artifacts(config)
    if not all(verified.values()):
        raise SpeechRuntimeError("the pinned speech runtime is missing or invalid")


def _read_small_text(path: Path, *, maximum_bytes: int = 64 * 1024) -> Optional[str]:
    try:
        if (
            path.is_symlink()
            or not path.is_file()
            or path.stat().st_size > maximum_bytes
        ):
            return None
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError, ValueError):
        return None


def _parse_checksum_manifest(text: str) -> Optional[dict[str, str]]:
    checksums: dict[str, str] = {}
    for line in text.splitlines():
        fields = line.split("  ", 1)
        if len(fields) != 2:
            return None
        checksum, relative_path = fields
        if (
            len(checksum) != 64
            or any(character not in "0123456789abcdef" for character in checksum)
            or relative_path not in {
                *_PINNED_STT_PATHS.values(),
                "bin/whisper-quantize",
                "MANIFEST",
            }
            or relative_path in checksums
        ):
            return None
        checksums[relative_path] = checksum
    required = {
        *_PINNED_STT_PATHS.values(),
        "bin/whisper-quantize",
        "MANIFEST",
    }
    return checksums if set(checksums) == required else None


def _whisper_runtime_is_runnable(
    path: Optional[Path],
    *,
    runner: Callable[..., Any],
) -> bool:
    if path is None or not os.access(path, os.X_OK):
        return False
    try:
        result = runner(
            [str(path), "-h"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
            timeout=WHISPER_RUNTIME_CHECK_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return False
    return getattr(result, "returncode", None) == 0


def _sha256_file(path: Path) -> str:
    digest = sha256()
    try:
        with path.open("rb") as input_file:
            for block in iter(lambda: input_file.read(1024 * 1024), b""):
                digest.update(block)
    except OSError:
        return ""
    return digest.hexdigest()


def _unique_object(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def _reject_nonstandard_constant(value: str) -> None:
    raise ValueError("nonstandard JSON value")
