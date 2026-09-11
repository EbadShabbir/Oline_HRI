#!/usr/bin/env bash

set -Eeuo pipefail
IFS=$'\n\t'
umask 022

readonly WHISPER_CPP_VERSION="v1.9.2"
readonly WHISPER_CPP_COMMIT="306c88f4d1286aec1bf96e544632897886af5501"
readonly WHISPER_CPP_ARCHIVE_URL="https://github.com/ggml-org/whisper.cpp/archive/refs/tags/${WHISPER_CPP_VERSION}.tar.gz"
readonly WHISPER_CPP_ARCHIVE_SHA256="a6abd064fcca8b85e794d205abf328c522e9451db43a3eadc178b883b7d0e9cd"

# Pin the model repository revision as well as each source model checksum. The
# whisper.cpp downloader uses the same official repository but follows `main`.
readonly WHISPER_MODEL_REVISION="5359861c739e955e79d9a303bcbc70fb988958b1"
readonly WHISPER_MODEL_BASE_URL="https://huggingface.co/ggerganov/whisper.cpp/resolve/${WHISPER_MODEL_REVISION}"
readonly SMALL_EN_SOURCE_SHA256="c6138d6d58ecc8322097e0f987c32f1be8bb0a18532a3f88f734d1bbf9c41e5d"
readonly SMALL_EN_SOURCE_SIZE="487614201"
readonly BASE_EN_SOURCE_SHA256="a03779c86df3323075f5e796cb2ce5029f00ec8869eee3fdfb897afe36c6d002"
readonly BASE_EN_SOURCE_SIZE="147964211"

readonly SILERO_VAD_VERSION="v6.2.1"
readonly SILERO_VAD_COMMIT="7e30209a3e901f9842f81b225f3e93d8199902b1"
readonly SILERO_VAD_URL="https://raw.githubusercontent.com/snakers4/silero-vad/${SILERO_VAD_VERSION}/src/silero_vad/data/silero_vad.onnx"
readonly SILERO_VAD_SHA256="1a153a22f4509e292a94e67d6f9b85e8deb25b4988682b7e174c65279d8788e3"
readonly SILERO_VAD_SIZE="2327524"

readonly CUDA_NVCC="/usr/local/cuda/bin/nvcc"
readonly CUDA_ARCHITECTURES="87"

die() {
    printf 'setup_stt.sh: %s\n' "$*" >&2
    exit 1
}

require_command() {
    command -v "$1" >/dev/null 2>&1 || die "required command not found: $1"
}

sha256_of() {
    local checksum_output

    checksum_output="$(sha256sum -- "$1")"
    printf '%s\n' "${checksum_output%% *}"
}

verify_sha256() {
    local file_path="$1"
    local expected="$2"
    local label="$3"
    local actual

    actual="$(sha256_of "$file_path")"
    [[ "$actual" == "$expected" ]] ||
        die "${label} SHA256 mismatch (expected ${expected}, got ${actual})"
}

verify_size() {
    local file_path="$1"
    local expected="$2"
    local label="$3"
    local actual

    actual="$(stat -c '%s' -- "$file_path")"
    [[ "$actual" == "$expected" ]] ||
        die "${label} size mismatch (expected ${expected}, got ${actual})"
}

download_verified() {
    local url="$1"
    local destination="$2"
    local expected_sha256="$3"
    local expected_size="$4"
    local label="$5"
    local temporary

    [[ ! -e "$destination" && ! -L "$destination" ]] ||
        die "refusing to overwrite existing download destination: ${destination}"

    temporary="$(mktemp "${DOWNLOAD_DIR}/.download.XXXXXX")"
    printf 'Downloading %s ...\n' "$label"
    curl \
        --fail \
        --location \
        --proto '=https' \
        --proto-redir '=https' \
        --retry 5 \
        --retry-all-errors \
        --retry-delay 2 \
        --connect-timeout 30 \
        --progress-bar \
        --show-error \
        --output "$temporary" \
        "$url"

    verify_size "$temporary" "$expected_size" "$label"
    verify_sha256 "$temporary" "$expected_sha256" "$label"
    mv -- "$temporary" "$destination"
}

manifest_has_line() {
    local expected_line="$1"

    grep --fixed-strings --line-regexp --quiet -- "$expected_line" "${STT_DIR}/MANIFEST"
}

checksum_from_manifest() {
    local relative_path="$1"
    local checksum_file="${STT_DIR}/SHA256SUMS"
    local count
    local expected

    count="$(awk -v path="$relative_path" '$2 == path { count += 1 } END { print count + 0 }' "$checksum_file")"
    [[ "$count" == "1" ]] ||
        die "installed checksum manifest has ${count} entries for ${relative_path}"

    expected="$(awk -v path="$relative_path" '$2 == path { print $1 }' "$checksum_file")"
    [[ "$expected" =~ ^[0-9a-f]{64}$ ]] ||
        die "installed checksum is malformed for ${relative_path}"
    printf '%s\n' "$expected"
}

validate_existing_install() {
    local relative_path
    local expected
    local line_count
    local -a artifacts=(
        "bin/whisper-cli"
        "bin/whisper-quantize"
        "models/ggml-small.en-q5_0.bin"
        "models/ggml-base.en-q5_0.bin"
        "models/silero_vad-v6.2.1.onnx"
        "MANIFEST"
    )

    [[ -d "$STT_DIR" && ! -L "$STT_DIR" ]] ||
        die "pre-existing STT path is not a regular directory: ${STT_DIR}"

    for relative_path in "${artifacts[@]}" "SHA256SUMS"; do
        [[ -f "${STT_DIR}/${relative_path}" && ! -L "${STT_DIR}/${relative_path}" ]] ||
            die "pre-existing STT installation is incomplete or unsafe: ${STT_DIR}/${relative_path}"
    done
    [[ -x "${STT_DIR}/bin/whisper-cli" ]] ||
        die "pre-existing whisper-cli is not executable"
    [[ -x "${STT_DIR}/bin/whisper-quantize" ]] ||
        die "pre-existing whisper-quantize is not executable"

    manifest_has_line "format=1" || die "pre-existing STT manifest has an unsupported format"
    manifest_has_line "whisper_cpp_version=${WHISPER_CPP_VERSION}" || die "pre-existing whisper.cpp version differs"
    manifest_has_line "whisper_cpp_commit=${WHISPER_CPP_COMMIT}" || die "pre-existing whisper.cpp commit differs"
    manifest_has_line "whisper_cpp_source_sha256=${WHISPER_CPP_ARCHIVE_SHA256}" || die "pre-existing whisper.cpp source differs"
    manifest_has_line "whisper_model_revision=${WHISPER_MODEL_REVISION}" || die "pre-existing Whisper model revision differs"
    manifest_has_line "small_en_source_sha256=${SMALL_EN_SOURCE_SHA256}" || die "pre-existing small.en source differs"
    manifest_has_line "base_en_source_sha256=${BASE_EN_SOURCE_SHA256}" || die "pre-existing base.en source differs"
    manifest_has_line "quantization=q5_0" || die "pre-existing Whisper quantization differs"
    manifest_has_line "silero_vad_version=${SILERO_VAD_VERSION}" || die "pre-existing Silero VAD version differs"
    manifest_has_line "silero_vad_commit=${SILERO_VAD_COMMIT}" || die "pre-existing Silero VAD commit differs"
    manifest_has_line "silero_vad_sha256=${SILERO_VAD_SHA256}" || die "pre-existing Silero VAD checksum differs"
    manifest_has_line "cuda_compiler=${CUDA_NVCC}" || die "pre-existing CUDA compiler path differs"
    manifest_has_line "cuda_architectures=${CUDA_ARCHITECTURES}" || die "pre-existing CUDA architecture target differs"
    manifest_has_line "cmake_ggml_cuda=ON" || die "pre-existing whisper.cpp build is not marked CUDA-enabled"

    line_count="$(wc -l < "${STT_DIR}/SHA256SUMS")"
    [[ "$line_count" -eq "${#artifacts[@]}" ]] ||
        die "pre-existing checksum manifest has an unexpected number of entries"

    for relative_path in "${artifacts[@]}"; do
        expected="$(checksum_from_manifest "$relative_path")"
        verify_sha256 "${STT_DIR}/${relative_path}" "$expected" "installed ${relative_path}"
    done
    verify_sha256 \
        "${STT_DIR}/models/silero_vad-v6.2.1.onnx" \
        "$SILERO_VAD_SHA256" \
        "installed Silero VAD ${SILERO_VAD_VERSION}"

    [[ ! -e "${STT_DIR}/models/ggml-small.en.bin" ]] ||
        die "pre-existing installation retained the temporary unquantized small.en model"
    [[ ! -e "${STT_DIR}/models/ggml-base.en.bin" ]] ||
        die "pre-existing installation retained the temporary unquantized base.en model"
}

print_paths() {
    printf '\nSTT runtime paths:\n'
    printf '  install root:      %s\n' "$STT_DIR"
    printf '  whisper-cli:       %s\n' "${STT_DIR}/bin/whisper-cli"
    printf '  whisper-quantize:  %s\n' "${STT_DIR}/bin/whisper-quantize"
    printf '  small.en Q5_0:     %s\n' "${STT_DIR}/models/ggml-small.en-q5_0.bin"
    printf '  base.en Q5_0:      %s\n' "${STT_DIR}/models/ggml-base.en-q5_0.bin"
    printf '  Silero VAD:        %s\n' "${STT_DIR}/models/silero_vad-v6.2.1.onnx"
    printf '  manifest:          %s\n' "${STT_DIR}/MANIFEST"
    printf '  checksums:         %s\n' "${STT_DIR}/SHA256SUMS"
}

quantize_model() {
    local model_name="$1"
    local source_sha256="$2"
    local source_size="$3"
    local source_file="${DOWNLOAD_DIR}/ggml-${model_name}.bin"
    local output_file="${STAGE_MODEL_DIR}/ggml-${model_name}-q5_0.bin"
    local output_size

    download_verified \
        "${WHISPER_MODEL_BASE_URL}/ggml-${model_name}.bin?download=true" \
        "$source_file" \
        "$source_sha256" \
        "$source_size" \
        "official unquantized Whisper ${model_name}"

    printf 'Quantizing Whisper %s to Q5_0 ...\n' "$model_name"
    "$BUILT_QUANTIZER" "$source_file" "$output_file" q5_0
    [[ -f "$output_file" && ! -L "$output_file" && -s "$output_file" ]] ||
        die "quantizer did not produce a regular, non-empty model: ${output_file}"

    output_size="$(stat -c '%s' -- "$output_file")"
    [[ "$output_size" -gt 1048576 && "$output_size" -lt "$source_size" ]] ||
        die "quantized ${model_name} model has an implausible size: ${output_size}"
    sha256_of "$output_file" >/dev/null

    # The originals are staging inputs only. Remove each one immediately after
    # the quantizer succeeds and its output has passed the checks above.
    rm -f -- "$source_file"
    [[ ! -e "$source_file" ]] || die "failed to delete temporary unquantized model: ${source_file}"
}

write_manifest() {
    {
        printf 'format=1\n'
        printf 'whisper_cpp_version=%s\n' "$WHISPER_CPP_VERSION"
        printf 'whisper_cpp_commit=%s\n' "$WHISPER_CPP_COMMIT"
        printf 'whisper_cpp_source_url=%s\n' "$WHISPER_CPP_ARCHIVE_URL"
        printf 'whisper_cpp_source_sha256=%s\n' "$WHISPER_CPP_ARCHIVE_SHA256"
        printf 'whisper_model_revision=%s\n' "$WHISPER_MODEL_REVISION"
        printf 'small_en_source_sha256=%s\n' "$SMALL_EN_SOURCE_SHA256"
        printf 'base_en_source_sha256=%s\n' "$BASE_EN_SOURCE_SHA256"
        printf 'quantization=q5_0\n'
        printf 'silero_vad_version=%s\n' "$SILERO_VAD_VERSION"
        printf 'silero_vad_commit=%s\n' "$SILERO_VAD_COMMIT"
        printf 'silero_vad_sha256=%s\n' "$SILERO_VAD_SHA256"
        printf 'cuda_compiler=%s\n' "$CUDA_NVCC"
        printf 'cuda_architectures=%s\n' "$CUDA_ARCHITECTURES"
        printf 'cmake_ggml_cuda=ON\n'
    } > "${STAGE_DIR}/MANIFEST"
}

write_checksums() {
    local relative_path
    local checksum
    local -a artifacts=(
        "bin/whisper-cli"
        "bin/whisper-quantize"
        "models/ggml-small.en-q5_0.bin"
        "models/ggml-base.en-q5_0.bin"
        "models/silero_vad-v6.2.1.onnx"
        "MANIFEST"
    )

    : > "${STAGE_DIR}/SHA256SUMS"
    for relative_path in "${artifacts[@]}"; do
        checksum="$(sha256_of "${STAGE_DIR}/${relative_path}")"
        printf '%s  %s\n' "$checksum" "$relative_path" >> "${STAGE_DIR}/SHA256SUMS"
    done
}

WORK_DIR=""
LOCK_HELD="0"

cleanup() {
    local exit_status=$?

    trap - EXIT HUP INT TERM
    if [[ -n "$WORK_DIR" && -d "$WORK_DIR" ]]; then
        case "$WORK_DIR" in
            "${INSTALL_ROOT}"/.setup-stt.*)
                rm -rf -- "$WORK_DIR"
                ;;
            *)
                printf 'setup_stt.sh: refusing to clean unexpected work path: %s\n' "$WORK_DIR" >&2
                ;;
        esac
    fi
    if [[ "$LOCK_HELD" == "1" ]]; then
        rmdir -- "$LOCK_DIR" 2>/dev/null ||
            printf 'setup_stt.sh: warning: could not remove lock directory: %s\n' "$LOCK_DIR" >&2
    fi
    exit "$exit_status"
}

trap cleanup EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

: "${HOME:?HOME must be set}"
DATA_HOME="${HOME}/.local/share"
[[ "$DATA_HOME" == /* ]] || die "data directory must be an absolute path: ${DATA_HOME}"
[[ "$DATA_HOME" != *$'\n'* ]] || die "data directory must not contain a newline"

readonly DATA_HOME
readonly INSTALL_ROOT="${DATA_HOME%/}/oline-hri"
readonly STT_DIR="${INSTALL_ROOT}/stt"
readonly LOCK_DIR="${INSTALL_ROOT}/.setup-stt.lock"

for command_name in awk cmake curl grep install mkdir mktemp mv rm rmdir sha256sum stat tar wc; do
    require_command "$command_name"
done
[[ -x "$CUDA_NVCC" && ! -d "$CUDA_NVCC" ]] ||
    die "CUDA compiler is not executable: ${CUDA_NVCC}"

if [[ -L "$INSTALL_ROOT" ]]; then
    die "refusing to use symlinked install root: ${INSTALL_ROOT}"
elif [[ -e "$INSTALL_ROOT" && ! -d "$INSTALL_ROOT" ]]; then
    die "install root exists but is not a directory: ${INSTALL_ROOT}"
fi
mkdir -p -- "$INSTALL_ROOT"

if ! mkdir -m 0700 -- "$LOCK_DIR" 2>/dev/null; then
    die "another setup may be active, or a stale lock exists: ${LOCK_DIR}"
fi
LOCK_HELD="1"

if [[ -e "$STT_DIR" || -L "$STT_DIR" ]]; then
    validate_existing_install
    printf 'Verified existing pinned STT installation.\n'
    print_paths
    exit 0
fi

BUILD_JOBS="${BUILD_JOBS:-}"
if [[ -z "$BUILD_JOBS" ]]; then
    # CUDA compilation is memory hungry on the 8 GB Jetson. Keep the default
    # conservative; callers with more headroom can explicitly override it.
    BUILD_JOBS="1"
fi
[[ "$BUILD_JOBS" =~ ^[1-9][0-9]*$ ]] || die "BUILD_JOBS must be a positive integer"
readonly BUILD_JOBS

WORK_DIR="$(mktemp -d "${INSTALL_ROOT}/.setup-stt.XXXXXX")"
readonly DOWNLOAD_DIR="${WORK_DIR}/downloads"
readonly SOURCE_ARCHIVE="${DOWNLOAD_DIR}/whisper.cpp-${WHISPER_CPP_VERSION}.tar.gz"
readonly SOURCE_DIR="${WORK_DIR}/whisper.cpp-1.9.2"
readonly BUILD_DIR="${SOURCE_DIR}/build"
readonly STAGE_DIR="${WORK_DIR}/stt"
readonly STAGE_BIN_DIR="${STAGE_DIR}/bin"
readonly STAGE_MODEL_DIR="${STAGE_DIR}/models"

mkdir -p -- "$DOWNLOAD_DIR" "$STAGE_BIN_DIR" "$STAGE_MODEL_DIR"

download_verified \
    "$WHISPER_CPP_ARCHIVE_URL" \
    "$SOURCE_ARCHIVE" \
    "$WHISPER_CPP_ARCHIVE_SHA256" \
    "9622263" \
    "whisper.cpp ${WHISPER_CPP_VERSION} source archive"

printf 'Extracting whisper.cpp %s ...\n' "$WHISPER_CPP_VERSION"
tar --extract --gzip --file "$SOURCE_ARCHIVE" --directory "$WORK_DIR" --no-same-owner --no-same-permissions
[[ -d "$SOURCE_DIR" && ! -L "$SOURCE_DIR" ]] ||
    die "source archive did not produce the expected directory: ${SOURCE_DIR}"
rm -f -- "$SOURCE_ARCHIVE"

printf 'Building whisper.cpp %s with CUDA using %s ...\n' "$WHISPER_CPP_VERSION" "$CUDA_NVCC"
CUDACXX="$CUDA_NVCC" cmake \
    -S "$SOURCE_DIR" \
    -B "$BUILD_DIR" \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_CUDA_COMPILER="$CUDA_NVCC" \
    -DCMAKE_CUDA_ARCHITECTURES="$CUDA_ARCHITECTURES" \
    -DGGML_CUDA=ON \
    -DBUILD_SHARED_LIBS=OFF \
    -DWHISPER_BUILD_TESTS=OFF \
    -DWHISPER_BUILD_EXAMPLES=ON \
    -DWHISPER_BUILD_SERVER=OFF
cmake \
    --build "$BUILD_DIR" \
    --config Release \
    --parallel "$BUILD_JOBS" \
    --target whisper-cli whisper-quantize

readonly BUILT_CLI="${BUILD_DIR}/bin/whisper-cli"
readonly BUILT_QUANTIZER="${BUILD_DIR}/bin/whisper-quantize"
[[ -x "$BUILT_CLI" ]] || die "build did not produce whisper-cli at ${BUILT_CLI}"
[[ -x "$BUILT_QUANTIZER" ]] || die "build did not produce whisper-quantize at ${BUILT_QUANTIZER}"
grep --fixed-strings --line-regexp --quiet 'GGML_CUDA:BOOL=ON' "${BUILD_DIR}/CMakeCache.txt" ||
    die "whisper.cpp CMake cache does not confirm GGML_CUDA=ON"

install -m 0755 -- "$BUILT_CLI" "${STAGE_BIN_DIR}/whisper-cli"
install -m 0755 -- "$BUILT_QUANTIZER" "${STAGE_BIN_DIR}/whisper-quantize"

quantize_model "small.en" "$SMALL_EN_SOURCE_SHA256" "$SMALL_EN_SOURCE_SIZE"
quantize_model "base.en" "$BASE_EN_SOURCE_SHA256" "$BASE_EN_SOURCE_SIZE"

download_verified \
    "$SILERO_VAD_URL" \
    "${STAGE_MODEL_DIR}/silero_vad-v6.2.1.onnx" \
    "$SILERO_VAD_SHA256" \
    "$SILERO_VAD_SIZE" \
    "Silero VAD ${SILERO_VAD_VERSION} ONNX model"

write_manifest
write_checksums

[[ ! -e "$STT_DIR" && ! -L "$STT_DIR" ]] ||
    die "STT destination appeared during setup; refusing to overwrite it: ${STT_DIR}"
mv -T -- "$STAGE_DIR" "$STT_DIR"

printf 'Installed the pinned CUDA STT runtime successfully.\n'
print_paths
