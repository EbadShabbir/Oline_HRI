"""Read installed GGUF tokenizer metadata without loading model weights.

Qwen's GPT-2 byte BPE begins with at most one vocabulary token per UTF-8
byte. Its pretokenizer partitions text; BPE merges only reduce that count.
Recognized special-token strings also cannot exceed their byte lengths.
This helper verifies both local tokenizers have the same metadata and all
256 ordinary byte symbols, then supplies a deliberately loose byte bound.
It does not claim that the bound is an exact Ollama token count.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import struct


MODEL_ROOT = Path('/usr/share/ollama/.ollama/models')
MODELS = ('qwen3:0.6b', 'qwen3:1.7b')
MAX_METADATA_BYTES = 32 * 1024 * 1024
_SCALARS = {0:'B', 1:'b', 2:'H', 3:'h', 4:'I', 5:'i', 6:'f',
            7:'?', 10:'Q', 11:'q', 12:'d'}


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


def _hash(value):
    return sha256(_canonical(value)).hexdigest()


def byte_alphabet():
    """The reversible 256-symbol GPT-2 bytes-to-Unicode mapping."""
    visible = list(range(ord('!'), ord('~') + 1))
    visible += list(range(ord('¡'), ord('¬') + 1))
    visible += list(range(ord('®'), ord('ÿ') + 1))
    mapping = {byte: chr(byte) for byte in visible}
    extra = 0
    for byte in range(256):
        if byte not in mapping:
            mapping[byte] = chr(256 + extra)
            extra += 1
    return {byte: mapping[byte] for byte in range(256)}


def read_gguf_metadata(path):
    """Parse a bounded GGUF v2/v3 metadata prefix; never read tensor data."""
    with Path(path).open('rb') as stream:
        prefix = bytearray()

        def read(length):
            if length < 0 or len(prefix) + length > MAX_METADATA_BYTES:
                raise ValueError('GGUF metadata exceeds bounded reader limit')
            data = stream.read(length)
            if len(data) != length:
                raise ValueError('truncated GGUF metadata')
            prefix.extend(data)
            return data

        def scalar(fmt):
            return struct.unpack('<' + fmt, read(struct.calcsize('<' + fmt)))[0]

        def string():
            return read(scalar('Q')).decode('utf-8')

        def value(kind, *, nested=False):
            if kind == 8:
                return string()
            if kind == 9:
                if nested:
                    raise ValueError('nested GGUF arrays are unsupported')
                element_kind, count = scalar('I'), scalar('Q')
                if count > 1_000_000:
                    raise ValueError('GGUF array exceeds bounded reader limit')
                return [value(element_kind, nested=True) for _ in range(count)]
            if kind not in _SCALARS:
                raise ValueError(f'unsupported GGUF metadata type {kind}')
            return scalar(_SCALARS[kind])

        if read(4) != b'GGUF':
            raise ValueError('invalid GGUF magic')
        version = scalar('I')
        if version not in (2, 3):
            raise ValueError('unsupported GGUF version')
        tensor_count, entry_count = scalar('Q'), scalar('Q')
        if entry_count > 100_000:
            raise ValueError('too many GGUF metadata entries')
        metadata = {}
        for _ in range(entry_count):
            key = string()
            if key in metadata:
                raise ValueError('duplicate GGUF metadata key')
            metadata[key] = value(scalar('I'))
        return metadata, dict(gguf_version=version, tensor_count=tensor_count,
                              metadata_entry_count=entry_count,
                              metadata_prefix_bytes=len(prefix),
                              metadata_prefix_sha256=sha256(prefix).hexdigest())


def _validate_tokenizer(metadata):
    tokenizer = {key: val for key, val in metadata.items()
                 if key.startswith('tokenizer.')}
    if (tokenizer.get('tokenizer.ggml.model') != 'gpt2'
            or tokenizer.get('tokenizer.ggml.pre') != 'qwen2'):
        raise ValueError('byte bound requires the installed GPT-2/Qwen2 byte BPE')
    tokens = tokenizer.get('tokenizer.ggml.tokens')
    kinds = tokenizer.get('tokenizer.ggml.token_type')
    merges = tokenizer.get('tokenizer.ggml.merges')
    if (not isinstance(tokens, list) or not tokens
            or any(not isinstance(token, str) or not token for token in tokens)
            or len(set(tokens)) != len(tokens)
            or not isinstance(kinds, list) or len(kinds) != len(tokens)
            or not isinstance(merges, list) or not merges
            or any(not isinstance(merge, str) for merge in merges)):
        raise ValueError('incomplete byte BPE vocabulary, token types, or merges')
    vocabulary = {token: i for i, token in enumerate(tokens)}
    byte_ids = []
    for symbol in byte_alphabet().values():
        if symbol not in vocabulary or kinds[vocabulary[symbol]] != 1:
            raise ValueError('ordinary single-byte vocabulary coverage is incomplete')
        byte_ids.append(vocabulary[symbol])
    if tokenizer.get('tokenizer.ggml.add_bos_token') is not False:
        raise ValueError('unexpected automatic BOS token configuration')
    if tokenizer.get('tokenizer.ggml.add_eos_token', False) is not False:
        raise ValueError('unexpected automatic EOS token configuration')
    for key in ('tokenizer.ggml.bos_token_id', 'tokenizer.ggml.eos_token_id'):
        if type(tokenizer.get(key)) is not int or not 0 <= tokenizer[key] < len(tokens):
            raise ValueError('invalid special-token ID')
    return tokenizer, byte_ids


def tokenizer_proof(model_root=MODEL_ROOT):
    """Verify identical installed tokenizer metadata and emit reproducible proof."""
    root = Path(model_root)
    evidence, common_hash = {}, None
    for model in MODELS:
        tag = model.split(':')[1]
        manifest_path = root / 'manifests/registry.ollama.ai/library/qwen3' / tag
        manifest_raw = manifest_path.read_bytes()
        manifest = json.loads(manifest_raw)
        layers = [item for item in manifest['layers']
                  if item['mediaType'] == 'application/vnd.ollama.image.model']
        if len(layers) != 1:
            raise ValueError('expected exactly one installed GGUF layer')
        layer = layers[0]
        parts = layer['digest'].split(':')
        if (len(parts) != 2 or parts[0] != 'sha256' or len(parts[1]) != 64
                or any(c not in '0123456789abcdef' for c in parts[1])):
            raise ValueError('invalid model-layer digest')
        blob = root / 'blobs' / layer['digest'].replace(':', '-')
        if blob.stat().st_size != layer['size']:
            raise ValueError('installed GGUF size differs from manifest')
        metadata, details = read_gguf_metadata(blob)
        tokenizer, byte_ids = _validate_tokenizer(metadata)
        token_hash = _hash(tokenizer)
        if common_hash is not None and common_hash != token_hash:
            raise ValueError('installed models have different tokenizer metadata')
        common_hash = token_hash
        evidence[model] = dict(
            manifest_path=str(manifest_path), manifest_sha256=sha256(manifest_raw).hexdigest(),
            gguf_path=str(blob), declared_gguf_sha256=parts[1], gguf_size_bytes=layer['size'],
            full_gguf_hash_recomputed=False, **details,
            tokenizer_metadata_sha256=token_hash,
            tokenizer_field_sha256={key: _hash(val) for key, val in tokenizer.items()},
            vocabulary_size=len(tokenizer['tokenizer.ggml.tokens']),
            merge_count=len(tokenizer['tokenizer.ggml.merges']),
            tokenizer_model=tokenizer['tokenizer.ggml.model'],
            pretokenizer=tokenizer['tokenizer.ggml.pre'],
            complete_ordinary_byte_coverage=True, byte_token_ids=byte_ids,
            add_bos_token=False, add_eos_token=False,
        )
    return dict(
        schema_version=1, method='verified_common_gguf_gpt2_byte_bpe_upper_bound_v1',
        models=evidence, common_tokenizer_metadata_sha256=common_hash,
        identical_tokenizer_metadata=True, inference_performed=False,
        proof=('The common gpt2/qwen2 byte BPE has all 256 ordinary byte symbols. '
               'Pretokenization partitions UTF-8 text and BPE only merges its byte symbols; '
               'special-token recognition replaces a nonempty string with one token. '
               'Thus tokens for the supplied raw prompt are at most its UTF-8 byte count. '
               'Add two conservative special-token slots, 192 output slots, and 64 safety '
               'slots; require that total to be at most 2048. No evidence is truncated.'),
        budget_formula='len(raw_rendered_prompt.encode("utf-8")) + 2 + 192 + 64 <= 2048',
        automatic_special_token_reserve=2, output_reserve=192, safety_reserve=64,
        context_length=2048,
    )


def prompt_budget(prompt):
    if not isinstance(prompt, str):
        raise TypeError('rendered prompt must be a string')
    count = len(prompt.encode('utf-8'))
    return dict(prompt_utf8_bytes=count, conservative_prompt_token_bound=count + 2,
                output_reserve=192, safety_reserve=64,
                total_upper_bound=count + 2 + 192 + 64,
                fits=count + 2 + 192 + 64 <= 2048)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-root', type=Path, default=MODEL_ROOT)
    args = parser.parse_args()
    print(json.dumps(tokenizer_proof(args.model_root), indent=2, ensure_ascii=False))
