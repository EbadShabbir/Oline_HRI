# Development Decisions

This file records confirmed implementation decisions for the offline personalized conversational robot.

## Jetson Orin Nano deployment baseline

1. Keep Qwen3-0.6B as the resident small model and router.
2. Run Qwen3-4B in INT4, non-thinking mode.
3. Initially use a dedicated TensorRT vision detector rather than a generative vision-language model.
4. Run only one heavy model at a time.
5. Use headless Linux, NVMe storage, active cooling, batch size 1, and an approximately 2K-token context.
6. Invoke vision periodically or in response to an event, rather than continuously processing the camera at full frame rate.

## Confirmed conversational pipeline

```text
Speech -> STT -> compute-and-memory router
                    |-- no memory + small model -> Qwen3-0.6B
                    |-- memory + small model    -> retrieval + Qwen3-0.6B
                    |-- no memory + large model -> Qwen3-4B
                    `-- memory + large model    -> retrieval + Qwen3-4B
                                                     |
                                                     v
                                        validated speech + action
                                                     |
                                                     v
                                              TTS + gesture
```

The router makes two independent decisions: whether personal-memory retrieval is needed, and whether the request requires Qwen3-0.6B or Qwen3-4B. RAG does not automatically require the larger model. A simple personalized question may use retrieval with Qwen3-0.6B, while a complex non-personal question may use Qwen3-4B without retrieval. Generated speech and action output must be validated before TTS or gesture execution.

## Offline personal-memory embedding and storage

### Core design decision

Embeddings are a searchable index over verified personal memories; they are not the memories themselves and do not train or modify either Qwen model.

For Version 1:

- Use [`BAAI/bge-small-en-v1.5`](https://huggingface.co/BAAI/bge-small-en-v1.5) as the embedding model.
- Run the official [ONNX model](https://huggingface.co/BAAI/bge-small-en-v1.5/tree/main/onnx) through ONNX Runtime on the Jetson CPU so that the GPU remains available for Qwen and vision workloads.
- Keep SQLite as the authoritative memory database.
- Use [SQLite FTS5](https://sqlite.org/fts5.html) for exact words, personal names, dates, locations, medicines, and abbreviations.
- Store normalized 384-dimensional `float32` embeddings as SQLite BLOBs and load only the active user's vectors into a contiguous in-memory matrix.
- Perform exact cosine-similarity search in the application for Version 1.
- Keep memory on the NVMe drive and protect it with device encryption. SQLite is not encrypted by itself.

BGE-small-en-v1.5 has approximately 33 million parameters, produces 384-dimensional embeddings, and is substantially lighter than keeping another Qwen-size model resident. `Qwen3-Embedding-0.6B` is a separate checkpoint from the conversational Qwen3-0.6B; its weights cannot be reused from the resident router/generator. It is therefore deferred unless later multilingual evaluation demonstrates a need for it.

The BGE query instruction `Represent this sentence for searching relevant passages:` is applied to retrieval queries only. Stored memory sentences are embedded without that query prefix. All embeddings must be normalized consistently. Do not mix vectors created by different embedding models or revisions in the same search matrix; a model change requires re-embedding the active records.

### Memory-writing example

```text
User: "Remember that I prefer mint tea without sugar."
                           |
                           v
Robot reads back the normalized fact and requests confirmation
                           |
                           v
Canonical memory: "Preference: user prefers mint tea without sugar."
                           |
              +------------+------------+
              |                         |
              v                         v
     SQLite text + metadata      384-number embedding
              |                         |
              `------------+------------'
                           v
                 persistent local memory
```

Later, a question such as "How do I normally take my tea?" is embedded. Similarity search locates the verified record, and the original readable memory—not an attempted reconstruction of the vector—is supplied to the selected Qwen model.

### Storage schema

The exact schema may evolve during implementation, but it must preserve the following separation:

```text
memory_item
  id
  profile_id
  kind
  canonical_text
  source_turn_id
  event_time
  sensitivity
  consent_status
  confidence
  importance
  status
  supersedes_id
  valid_from
  valid_until
  retention_until
  created_at
  updated_at

memory_embedding
  memory_id
  model_id
  model_revision
  dimension
  normalized
  content_sha256
  vector_f32
```

The content hash detects an embedding that no longer matches its memory text. Memory status includes at least `active`, `superseded`, and `retracted`. The FTS5 index and in-memory vector matrix are derived indexes and can always be rebuilt from the authoritative records.

Exact reminders, scheduled actions, medication schedules, and actuator commands must use separate structured transactional tables and deterministic validation. A retrieved semantic memory is context for conversation; it is never sufficient authorization to perform an action.

### Version 1 write policy

Version 1 does not automatically learn from every conversation. Long-term storage is limited to:

- An explicit instruction such as "remember this."
- A controlled record required by the seven-day case study.
- A fact, preference, routine, relationship, or event that the robot explicitly asks about and the user confirms.

Before writing a memory, convert it into a short canonical statement and read it back when an error would matter, especially for names, relationships, addresses, dates, times, health information, and scheduled activities. Do not embed complete transcripts when a short verified fact is sufficient. Immediate conversation context remains in RAM and expires at the end of the session unless the user deliberately saves something.

Do not place the following in ordinary long-term embedding memory:

- Low-confidence speech-to-text output.
- Raw continuous audio or complete transcripts by default.
- Passwords, PINs, payment-card details, bank information, or security codes.
- Inferred emotion, sadness, stammering, a diagnosis, or another paralinguistic estimate.
- A model guess or unconfirmed model-generated summary presented as a user fact.
- Hot-microphone content, television speech, or another person's private information.
- Medication changes or doses as an executable instruction.

A temporary estimate such as `possible_sadness` may adapt the current conversational tone, but it must not become a permanent statement that the user is sad.

### Retrieval pipeline

```text
Current user request
        |
        v
Does this request require personal memory?
        |
       yes
        |
        v
Embed query with BGE-small
        |
        v
Filter before search: current profile + active + consented + unexpired
        |
        v
Structured SQL lookup + FTS5 search + exact cosine search
        |
        v
Fuse/rank candidates and reject weak or contradictory results
        |
        v
Supply at most the best 3-5 verified records, with IDs and dates,
to the independently selected Qwen3-0.6B or Qwen3-4B model
```

Use structured SQL first when the answer belongs to an exact field. Combine lexical and semantic results for conversational memories so that exact personal names and dates are not lost through semantic matching. Recency and importance may be small ranking signals, but they must not override consent, expiration, profile separation, or contradiction handling.

Do not adopt an arbitrary cosine threshold. Calibrate retrieval and abstention thresholds using project-specific query-memory pairs. When evidence is weak, stale, or conflicting, the robot must ask the user or say it is uncertain rather than selecting the nearest vector blindly. Retrieved text is untrusted contextual data, not a system instruction.

### Scale and deferred vector-index options

One 384-dimensional `float32` vector occupies 1,536 bytes before database overhead. Approximately 10,000 vectors require 14.6 MiB of raw vector memory, and 50,000 require about 73 MiB. The one-week study should be much smaller, so an exact scan is simpler, deterministic, and sufficient for the first implementation.

Do not deploy Chroma, Qdrant, or a separate resident vector-database service in Version 1. Do not add FAISS merely because the system uses embeddings. If measured search latency becomes unacceptable at roughly 50,000-100,000 active memories, evaluate CPU [FAISS](https://github.com/facebookresearch/faiss) or another pinned local index. Any future vector index remains a rebuildable cache; SQLite remains the source of truth.

### Privacy, profile isolation, correction, and deletion

Embeddings are sensitive data, not anonymized data. Research has shown that text and personal information can sometimes be reconstructed from embeddings; see [Text Embeddings Reveal (Almost) As Much As Text](https://aclanthology.org/2023.emnlp-main.765/). Protect memory text, embeddings, full-text indexes, backups, and exported data to the same standard.

- Use Jetson-supported LUKS storage protection as described in the [NVIDIA disk-encryption documentation](https://docs.nvidia.com/jetson/archives/r38.4/DeveloperGuide/SD/Security/DiskEncryption.html).
- Optionally add application-level database encryption with [SQLCipher](https://www.zetetic.net/sqlcipher/) if the deployment threat model requires protection beyond full-disk encryption.
- In Version 1, use one encrypted database for the single active user profile.
- For future multi-user operation, separate user databases/indexes and keys. Select the authenticated profile before retrieval; never search all users and filter afterward.
- Provide a user-visible command such as "What do you remember about me?" together with review, correction, export, and deletion controls.
- Audit memory operations using record IDs, operation type, and time without copying private memory content into ordinary logs.

A correction creates a new record, marks the old record `superseded`, and embeds the corrected canonical text. A "forget that" request retracts or deletes the authoritative record and removes its embedding and FTS entry; the in-memory matrix is then rebuilt. The retention and backup policy must define when deleted records disappear from recoverable backups as well.

### Evaluation before freezing the design

Evaluate the embedding and retrieval subsystem with project-specific query-memory pairs in addition to the planned LoCoMo benchmark and controlled seven-day case study. Report:

- Recall@5 and mean reciprocal rank.
- Precision of the memories actually supplied to Qwen.
- False-retrieval rate and no-memory/abstention accuracy.
- Retrieval of stale, expired, superseded, or contradictory memories.
- `memory_used` record IDs for reproducible analysis.
- Embedding latency, search latency, end-to-end retrieval latency, and p50/p95 values.
- CPU and shared-memory use, NVMe activity, power, temperature, and throttling on the final Jetson.
- Deletion/correction success and zero cross-profile retrieval in any later multi-user test.

## Target-user development scope

1. Build the general personalized robot first.
2. Implement an `older_adult_companion` profile as a configurable use case.
3. Keep `dementia_support` as future work requiring participatory co-design and appropriate ethical evaluation.

## Jetson installation and development reference

### Development arrangement

- Use the complete Jetson Orin Nano Super Developer Kit 8GB rather than the older Jetson Nano or a bare module.
- The Jetson is a separate ARM64 computer running Ubuntu-based Jetson Linux. Windows, macOS, or Linux may be used as the setup and development computer.
- Edit remotely from the development computer with VS Code Remote SSH or transfer code with Git or `scp`. CUDA, TensorRT, camera, GPIO, and robot workloads execute on the Jetson.
- Once SSH access works, operate the Jetson headlessly.

### Additional hardware

- 512GB to 1TB M.2 2280 PCIe NVMe SSD; 1TB is preferred for models, containers, memory, datasets, and logs. Do not use an M.2 SATA drive.
- USB flash drive of at least 16GB for the JetPack installer.
- DisplayPort monitor or DisplayPort-to-HDMI adapter, plus a USB keyboard and mouse for the initial setup.
- Ethernet connection is preferred for installation and development; Wi-Fi may be used afterward.
- Optional data-capable USB-C cable for recovery or USB device mode.
- Add the microphone, speaker, camera, and microcontroller when integrating the robot peripherals.

The developer kit includes the 19V power supply, active cooling, and a Wi-Fi/Bluetooth module. Its USB-C connector is not a display output; use DisplayPort for a monitor.

### Initial operating-system installation

As of September 2026, NVIDIA's current beginner installation path for the Orin Nano Developer Kit is JetPack 7.2.1:

1. On a Windows, macOS, or Linux computer with at least 25GB free, download the Jetson ISO.
2. Use Balena Etcher to create a bootable 16GB-or-larger USB drive; do not merely copy the ISO file onto the drive.
3. Install the NVMe SSD in the Jetson.
4. Connect the monitor, keyboard, mouse, network, installer USB, and included power supply.
5. Boot from the installer USB and install Jetson Linux onto the NVMe SSD.
6. Complete the Ubuntu first-boot configuration and create the Jetson username and password.
7. Check the UEFI/QSPI firmware when required. Firmware older than version 36 needs NVIDIA's JetPack 6.x firmware-update path before installing JetPack 7.2.1.

JetPack 7.2.1 is the current reference, not yet the frozen project version. Verify compatibility with Qwen inference, STT, TTS, camera support, and TensorRT before freezing the software stack. JetPack 6.2.3 remains a fallback if required dependencies do not yet support JetPack 7.

### Post-installation setup

Run on the Jetson:

```bash
sudo apt update
sudo apt install -y nvidia-jetpack git openssh-server python3-venv
sudo systemctl enable --now ssh
hostname -I
```

Connect from Windows PowerShell, macOS Terminal, or a Linux terminal:

```bash
ssh <jetson-username>@<jetson-ip-address>
```

Keep the project source on the Jetson and open it through VS Code Remote SSH. Use only Linux ARM64/Jetson-compatible packages and containers; Windows, macOS, and ordinary x86/AMD64 binaries or containers will not run on the Jetson. Build the TensorRT vision engine against the final frozen JetPack, CUDA, and TensorRT versions.

### Official setup references

- [Jetson Orin Nano Quick Start](https://docs.nvidia.com/jetson/orin-nano-devkit/user-guide/latest/quick_start.html)
- [Jetson Orin Nano hardware layout](https://docs.nvidia.com/jetson/orin-nano-devkit/user-guide/latest/hardware_layout.html)
- [JetPack downloads and release information](https://developer.nvidia.com/embedded/jetpack/downloads)
- [Jetson firmware-update path](https://docs.nvidia.com/jetson/orin-nano-devkit/user-guide/latest/update_firmware.html)
- [JetPack component installation](https://docs.nvidia.com/jetson/orin-nano-devkit/user-guide/latest/setup_jetpack.html)
- [Jetson Docker setup](https://docs.nvidia.com/jetson/orin-nano-devkit/user-guide/latest/setup_docker.html)
- [VS Code Remote SSH](https://code.visualstudio.com/docs/remote/ssh)

## Offline speech-to-text design

### Confirmed STT pipeline

```text
Microphone
   |
   v
16 kHz mono audio cleanup
   |
   v
Silero VAD and end-of-turn detection
   |
   v
whisper.cpp with CUDA and small.en Q5_0
   |
   v
transcription-quality and safety gate
   |
   v
personal-memory and model router
```

### Model and runtime baseline

- Run speech recognition completely offline on the Jetson.
- Use CUDA-enabled `whisper.cpp`, compiled natively for the Jetson's ARM64 platform.
- Use quantized `small.en Q5_0` as the primary English STT candidate.
- Retain `base.en Q5_0` as a lower-latency fallback.
- Use batch size 1 and transcribe one completed user utterance at a time.
- If multilingual recognition is introduced later, replace the English-only `.en` model with the appropriate multilingual Whisper model and evaluate it separately.
- Do not use NVIDIA Riva for the initial 8GB build because its resource requirements would compete with the language models, TTS, vision, and operating system.

This choice supersedes the preliminary Faster-Whisper preference. Faster-Whisper remains a fallback if the project freezes JetPack 6.2.3, but its current documented GPU path targets CUDA 12 and is not yet a confirmed drop-in option for JetPack 7.2.1 with CUDA 13.2.1.

### Conversation and endpoint behavior

1. Activate a conversation session before recognizing speech.
2. Keep a lightweight VAD active and preserve a short audio pre-roll so the first word is not clipped.
3. Treat approximately 0.8 to 1.2 seconds of silence as the initial end-of-turn range and tune it on real recordings.
4. Permit a longer silence threshold in the `older_adult_companion` profile to accommodate natural pauses.
5. Transcribe the completed utterance before invoking Qwen3-4B, preserving the one-heavy-model-at-a-time rule.
6. Begin with half-duplex audio: pause VAD and STT while TTS is playing so the robot does not transcribe itself.
7. Keep full-duplex interruption, barge-in, and acoustic echo cancellation as later work after the basic pipeline is stable and measured.

### Transcription safety and personal vocabulary

- Never send raw STT output directly to a gesture controller or other hardware.
- Ask the user to repeat an ordinary utterance when transcription quality is low.
- Confirm uncertain names or personal facts before writing them to long-term memory.
- Require confirmation of critical slots before any physical or state-changing action.
- Discard silence, noise-only, and rejected transcriptions rather than routing or storing them.
- Use only a short, consented contextual prompt containing relevant names, local places, and the robot's name. Do not inject the complete personal-memory database into Whisper.
- Delete the temporary raw-audio buffer after transcription by default. Retain audio only when recording is explicitly enabled under the applicable evaluation and consent process.

The STT handoff should preserve the raw transcript, normalized text, timing, and available quality signals so the confidence gate can decide whether to accept the utterance or request clarification.

### Device-level STT evaluation before freezing

Compare `base.en Q5_0` and `small.en Q5_0` on the final Jetson, microphone, speaker, and robot enclosure. Select the final model using the combined accuracy, latency, memory, and power trade-off rather than word error rate alone.

Measure:

- Word error rate and sentence exact-match rate.
- Personal-name and critical-term errors.
- Intent and critical action-slot accuracy, including negation, stop, directions, people, and times.
- Quiet, room/fan/TV noise, near-field, and far-field speech.
- Voice-activity false starts, missed speech, and speech truncation.
- End-of-speech-to-final-transcript median and p95 latency, real-time factor, and cold-start latency.
- Peak shared memory, power, temperature, and throttling on the Jetson.
- Silence hallucinations, self-echo transcription, and false or unsafe action activation in dry-run mode.

Low-confidence transcripts must not create personal memories, and the finite test set must observe zero unconfirmed hazardous action activations. This test result is an engineering requirement, not a general safety guarantee.

### STT references

- [OpenAI Whisper models and model sizes](https://github.com/openai/whisper#available-models-and-languages)
- [whisper.cpp CUDA, quantization, and VAD](https://github.com/ggml-org/whisper.cpp)
- [Silero VAD](https://github.com/snakers4/silero-vad)
- [Faster-Whisper requirements and fallback implementation](https://github.com/SYSTRAN/faster-whisper)
- [CTranslate2 installation and CUDA requirements](https://opennmt.net/CTranslate2/installation.html)

## Offline paralinguistic speech analysis

### Confirmed design

Add a speech-only `speech_paralinguistic_analyzer` that estimates how an utterance was delivered. It must distinguish observable vocal features, uncertain perceived affect, and possible speech-disfluency events. It must not claim to identify a person's true emotion or diagnose stuttering, depression, anxiety, dementia, or another clinical condition.

```text
Microphone -> VAD -> completed utterance buffer
                         |-- whisper.cpp -> transcript + timing
                         `-- paralinguistic analyzer
                               |-- pitch, energy, pace, and pauses
                               |-- coarse vocal-affect estimate
                               `-- possible disfluency events
                                          |
                                          v
                              confidence and safety gate
                                          |
                                          v
                         memory/model router -> Qwen -> TTS/gesture
```

Use the same completed utterance buffer for STT and paralinguistic analysis. Preserve interior silence and a short pre-roll because aggressive VAD trimming can remove evidence needed to measure pauses or possible speech blocks.

### Initial vocal-delivery and affect module

- Use openSMILE with the `eGeMAPSv02` feature set as the initial lightweight CPU-side feature extractor.
- Measure observable features such as pitch, pitch variation, energy/loudness, speaking rate, pause ratio, long pauses, and available voice-quality measures.
- Add only a small, calibrated classifier or regressor rather than another speech foundation model for the initial deployment.
- Represent perceived affect coarsely as activation/arousal (`low`, `normal`, or `high`) and valence tendency (`positive`, `neutral`, `negative`, or `unknown`), accompanied by confidence and an abstention result.
- Prefer statements such as `low_energy`, `fast_speech`, or `long_pauses`; never treat `happy`, `sad`, or `angry` as established facts about the user.
- Analyze one completed utterance at a time with batch size 1. The feature extractor is lightweight and does not violate the one-heavy-model-at-a-time rule.
- Keep emotion2vec and comparable learned speech-emotion models as optional research baselines, not the first Jetson deployment, until memory use, latency, target-user accuracy, licensing, and ONNX/TensorRT compatibility have been verified.

openSMILE is suitable for the research prototype because it is implemented in C++, supports incremental processing, and extracts the required acoustic features. Its open-source version permits private, research, and educational use but not use in a commercial product; commercial development requires an appropriate licence.

### Speech-fluency observation

Treat possible stammering or stuttering as a separate speech-disfluency task rather than an emotion class.

- Use the STT transcript and timestamps to observe whole-word or phrase repetitions and fillers such as `um` and `uh`.
- Use raw acoustic features for possible sound/syllable repetitions and prolonged sounds because Whisper may normalize or omit these events.
- Treat silent blocks as low-confidence or unsupported initially because they can resemble thinking pauses, endpoint silence, noise, or microphone loss.
- In a later phase, evaluate a compact MFCC/log-Mel TDNN, ConvLSTM, or comparable classifier for sound repetitions and prolongations. Export the selected small model to ONNX/TensorRT where supported.
- Produce descriptions such as `observed_word_repetition` or `possible_prolongation` with confidence. Never output `user_has_stuttering` or make a clinical diagnosis.
- Do not draw attention to a disfluency unless the user asks. Instead, allow more response time, avoid interrupting or completing the user's words, and collapse unintended repetition before intent parsing when confidence is sufficient.

SEP-28k may be used for noncommercial research and initial model development. It contains annotated three-second clips for blocks, prolongations, sound repetitions, word repetitions, and interjections. It is not a clinical diagnostic dataset, its annotators were not clinicians, its audio remains subject to the original owners' copyright, and the released dataset is licensed CC BY-NC 4.0. Target-user evaluation remains mandatory.

### Allowed conversational adaptation

Paralinguistic results may influence only reversible, low-risk conversational presentation:

- Long pauses or possible repetitions: extend turn-taking time and avoid interruption.
- Fast or high-energy speech: respond more slowly and briefly where appropriate.
- Low-energy speech: use a neutral check-in such as, "Would you like to continue talking?"
- Low confidence or unusable audio: abstain and continue with normal conversation behavior.

An affect or disfluency estimate must never by itself trigger a physical action, emergency escalation, caregiver notification, medical conclusion, or long-term personal-memory update. Critical actions continue to require the existing validation and confirmation gates.

### Privacy and older-adult safeguards

- Make speech-affect analysis an understandable opt-in feature and provide an immediate way to disable it.
- Process audio locally and delete the temporary audio buffer after STT and analysis unless research recording has been explicitly consented to.
- Keep inferred affect transient and do not build a permanent mood history by default.
- Prefer a consented within-person acoustic baseline over universal pitch, speed, or energy thresholds, while recognizing that deviation from a baseline still does not prove an emotion.
- Validate on the intended older-adult population because age, health, medication, fatigue, language, accent, microphone distance, and room noise can change pitch, breathiness, pace, pauses, and model performance.

Before freezing the module, test speaker-disjoint target recordings from the actual robot microphone and environment. Report per-class or per-event precision, recall, and F1; macro-F1 or unweighted average recall for affect; calibration and abstention coverage; false-positive rates on slow but fluent speech; inappropriate adaptation rate; latency; peak memory; power; and subgroup results where the evaluation sample supports them.

### Paper terminology

Describe this capability as:

> **Probabilistic paralinguistic state estimation and observable speech-fluency detection for adaptive conversation.**

Do not describe it as definitive emotion detection or stuttering diagnosis.

### Paralinguistic-analysis references

- [openSMILE capabilities and licensing](https://audeering.github.io/opensmile/about.html)
- [openSMILE Python feature-set documentation](https://audeering.github.io/opensmile-python/index.html)
- [ASHA guidance on fluency disorders and clinical assessment](https://www.asha.org/practice-portal/clinical-topics/fluency-disorders/)
- [Apple SEP-28k stuttering-event dataset](https://github.com/apple/ml-stuttering-events-dataset)
- [SER_AMPEL older-adult speech-emotion dataset](https://arxiv.org/abs/2311.14483)
- [Healthy-ageing voice systematic review](https://pubmed.ncbi.nlm.nih.gov/32083980/)
- [emotion2vec research implementation](https://github.com/ddlBoJack/emotion2vec)

## Offline text-to-speech design

### Confirmed model and runtime baseline

- Run TTS completely offline on the Jetson.
- Use `sherpa-onnx` on the CPU with one audited Piper/VITS medium ONNX voice as the initial TTS implementation.
- Keep the GPU available for Whisper, Qwen, and vision. CPU-side Piper/VITS synthesis is lightweight and does not count as a heavy foundation model, subject to device-level measurement.
- Use `en_US-ljspeech-medium` as the initial research voice candidate. It is approximately 63.5MB, produces 22.05kHz speech, and its model card identifies the source dataset as public domain. Compare it with other properly licensed voices before freezing the robot's voice.
- Record and audit the runtime, model, voice, training-data, and distribution licences separately. `sherpa-onnx` uses Apache-2.0, while voice-model licences vary.
- Keep Kokoro-82M ONNX as a Version 2 naturalness benchmark. Promote it only if the final Jetson tests show acceptable first-audio latency, real-time factor, memory, power, temperature, intelligibility, and user preference.
- Do not use NVIDIA Riva for this 8GB Orin Nano baseline. The current JetPack 7 Riva embedded path targets Jetson Thor, and Magpie TTS lists approximately 8.5GB of unified memory.
- Do not implement voice cloning in the first version.

### Confirmed TTS pipeline

```text
Validated Qwen response and action
                |
                v
Text normalization and pronunciation dictionary
                |
                v
Sentence chunking
                |
                v
sherpa-onnx + resident Piper/VITS voice
                |
                v
Cancellable PCM playback queue
                |
                v
USB speaker or USB DAC + amplifier
```

The complete structured response and any accompanying action must pass the existing validation gate before TTS playback begins. After validation, synthesize and queue speech sentence by sentence to reduce perceived delay without allowing unvalidated content to reach the speaker.

### Runtime decisions

- Load the selected voice once when the robot starts; do not reload it for every sentence.
- Generate speech only after the response and any accompanying action have passed validation.
- Split long responses into sentences and begin playback as soon as the first validated sentence is synthesized.
- During playback, set `tts_active=true` and pause STT under our initial half-duplex design.
- Provide immediate playback cancellation, preferably including a physical stop control.
- Maintain a pronunciation dictionary for personal names, medicines, locations, dates, and abbreviations.
- Expose user-controlled voice, volume, speaking rate, and pause duration. The `older_adult_companion` profile should sound clear and calm, not automatically extremely slow or patronizing.
- Do not implement voice cloning in the first version.

### Playback, personalization, and safety

- Use a persistent TTS service or worker and a bounded, cancellable PCM audio queue.
- Resume VAD and STT only after playback stops and a short device-tested cooldown prevents the robot from transcribing its own trailing audio.
- While the initial half-duplex design is active, provide a physical or software playback-stop control because spoken interruption will not be recognized while STT is paused.
- Normalize numbers, dates, times, abbreviations, units, and punctuation before synthesis. Use an allow-listed pronunciation dictionary rather than accepting arbitrary raw phoneme or markup instructions from generated or user-supplied text.
- Adapt pace, volume, and pauses only within tested limits. Do not make exaggerated emotional performances based on uncertain speech-affect estimates.
- Use a neutral adult stock voice. Voice choice and playback settings are preferences, not facts to infer from age or another user characteristic.
- For critical reminders or safety-related messages, present a visual cue where possible and request acknowledgement rather than relying only on synthesized audio.
- A powered USB speaker is the simplest prototype output. A bare loudspeaker requires an appropriate USB audio interface or I2S codec and amplifier; it must not be driven directly from the Jetson.

### Device-level TTS evaluation before freezing

Evaluate candidate voices on the final Jetson, speaker, amplifier, enclosure, room conditions, and target-user population. Measure:

- Time from validated text to first audible audio, median and p95.
- Real-time factor, total synthesis time, underruns, truncation, and playback-cancellation latency.
- Peak shared memory, CPU and GPU use, power, temperature, and throttling.
- Intelligibility and comprehension of names, medicines, numbers, dates, times, units, directions, and action confirmations.
- Pronunciation-error and critical-word error rates.
- Listening effort, comfort, naturalness, warmth, and voice preference, including evaluation with intended older-adult users.
- Quiet and realistic fan, television, household-noise, near-field, and far-field listening conditions.
- User-adjustable rate, volume, and pause settings, including compatibility with hearing aids where applicable.

Freeze the engine version, voice-model hash, configuration, pronunciation dictionary, and licence record together. Maintain a backend interface so the project can compare or replace Piper/VITS with Kokoro without changing the validated response pipeline.

### TTS references

- [sherpa-onnx offline speech runtime and Jetson support](https://github.com/k2-fsa/sherpa-onnx)
- [sherpa-onnx TTS models and documentation](https://k2-fsa.github.io/sherpa/onnx/tts/index.html)
- [Piper/VITS CPU benchmark examples](https://k2-fsa.github.io/sherpa/onnx/tts/pretrained_models/vits.html)
- [Piper `en_US-ljspeech-medium` model](https://huggingface.co/rhasspy/piper-voices/tree/main/en/en_US/ljspeech/medium)
- [Piper `en_US-ljspeech-medium` model card](https://huggingface.co/rhasspy/piper-voices/blob/main/en/en_US/ljspeech/medium/MODEL_CARD)
- [Kokoro-82M model card](https://huggingface.co/hexgrad/Kokoro-82M)
- [sherpa-onnx Kokoro documentation and CPU benchmarks](https://k2-fsa.github.io/sherpa/onnx/tts/pretrained_models/kokoro.html)
- [NVIDIA Riva support and memory matrix](https://docs.nvidia.com/deeplearning/riva/user-guide/docs/support-matrix/support-matrix.html)
- [NIDCD guidance for communicating with older adults with hearing loss](https://www.nidcd.nih.gov/sites/default/files/hearinglossolderadults-508.pdf)
