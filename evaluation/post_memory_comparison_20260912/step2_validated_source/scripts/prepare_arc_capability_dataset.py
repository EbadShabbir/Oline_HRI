"""Freeze the ARC capability subset from the two pinned official Parquet files.

Requires duckdb==1.3.2 only for preparation; inference uses the JSON artifact.
Download provenance lives in source/manifest.json next to the frozen dataset.
"""
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import random

import duckdb


ROOT = Path(__file__).resolve().parents[1] / "evaluation" / "arc_capability_20260911"
REVISION = "210d026faf9955653af8916fad021475a3f00453"


def main():
    source = json.loads((ROOT / "source" / "manifest.json").read_text())
    rng = random.Random(42)
    connection = duckdb.connect(":memory:")
    cases, counts = [], {}
    for subset, expected_count in (("ARC-Easy", 2376), ("ARC-Challenge", 1172)):
        path = ROOT / "source" / f"{subset}-test.parquet"
        assert source[subset]["revision"] == REVISION
        assert sha256(path.read_bytes()).hexdigest() == source[subset]["sha256"]
        rows = connection.execute(
            "SELECT id, question, choices, answerKey FROM read_parquet(?) ORDER BY id",
            [str(path)],
        ).fetchall()
        assert len(rows) == expected_count
        counts[subset] = len(rows)
        for identifier, question, choices, answer in rng.sample(rows, 50):
            labels, texts = choices["label"], choices["text"]
            assert len(labels) == len(texts) == len(set(labels))
            assert answer in labels
            cases.append({
                "id": identifier, "subset": subset, "question": question,
                "choices": [{"label": label, "text": text}
                            for label, text in zip(labels, texts)],
                "answerKey": answer,
            })
    rng.shuffle(cases)
    assert len({case["id"] for case in cases}) == 100
    lengths = [len(case["question"] + "\n\n" + "\n".join(
        f'{choice["label"]}. {choice["text"]}' for choice in case["choices"]
    )) for case in cases]
    assert max(lengths) <= 1000, "Frozen sample exceeds production routing limit"
    dataset = {
        "metadata": {
            "name": "AI2 ARC 100-question capability pilot",
            "source": "https://huggingface.co/datasets/allenai/ai2_arc",
            "revision": REVISION, "source_files": source,
            "license": "CC-BY-SA-4.0", "attribution": "Clark et al., AI2 ARC (2018), Allen Institute for AI",
            "paper": "https://arxiv.org/abs/1803.05457",
            "split": "test", "source_counts": counts,
            "sampling": "Python Random(42), sample 50 from each ID-sorted split in Easy/Challenge order, then shuffle combined cases with same RNG",
            "selection_seed": 42, "per_subset": 50, "excluded_cases": [],
            "maximum_question_and_choices_characters": max(lengths),
            "labels": "Published native labels and option order preserved",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "reader_version": duckdb.__version__,
            "preparation_source_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
            "scope": "Zero-shot generated-label accuracy; not full benchmark or likelihood-normalized leaderboard accuracy",
        },
        "cases": cases,
    }
    path = ROOT / "dataset.json"
    with path.open("x", encoding="utf-8") as stream:
        json.dump(dataset, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    print(json.dumps({"path": str(path), "sha256": sha256(path.read_bytes()).hexdigest(),
                      "cases": len(cases), "maximum_prompt_characters": max(lengths)}))


if __name__ == "__main__":
    main()
