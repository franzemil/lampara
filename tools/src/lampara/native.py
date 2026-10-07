"""Native (C++) inference harness: build and run the EI model locally on macOS."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from . import config

EXTRACT_ROOT = config.CACHE_DIR / "ei"
BIN_DIR = config.CACHE_DIR / "bin"


class BuildError(RuntimeError):
    pass


def _src_dir(version: str) -> Path:
    return EXTRACT_ROOT / version / "Lampara_inferencing" / "src"


def _binary(version: str) -> Path:
    return BIN_DIR / f"lampara_classify_{version}"


def extract_library(zip_path: Path, version: str, force: bool = False) -> Path:
    import zipfile

    out = EXTRACT_ROOT / version
    src = _src_dir(version)
    if src.is_dir() and not force:
        return src
    out.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(out)
    if not src.is_dir():
        raise BuildError(f"zip did not contain {src}")
    return src


def _source_files(src: Path) -> list[Path]:
    skip_parts = {"arduino", "particle", "espressif"}
    files: list[Path] = []
    for p in sorted(src.rglob("*.cpp")):
        parts = set(p.relative_to(src).parts)
        if parts & skip_parts:
            continue
        files.append(p)
    native = Path(__file__).resolve().parents[2] / "native"
    files.append(native / "porting_impl.cpp")
    files.append(native / "main.cpp")
    return files


def build(zip_path: Path, version: str, jobs: int = 8, force: bool = False) -> Path:
    import shutil

    src = extract_library(zip_path, version)
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    binary = _binary(version)
    obj_dir = EXTRACT_ROOT / version / "obj"
    if force:
        import shutil

        shutil.rmtree(obj_dir, ignore_errors=True)
    if binary.exists() and not force:
        return binary

    clang = shutil.which("clang++") or shutil.which("g++")
    if not clang:
        raise BuildError("no C++ compiler found (clang++/g++)")

    obj_dir = EXTRACT_ROOT / version / "obj"
    obj_dir.mkdir(parents=True, exist_ok=True)
    includes = [
        "-I",
        str(src),
        "-I",
        str(src / "edge-impulse-sdk"),
        "-I",
        str(src / "model-parameters"),
        "-I",
        str(src / "tflite-model"),
    ]
    flags = [clang, "-std=c++17", "-O2", "-DNDEBUG", *includes, "-c"]

    sources = _source_files(src)
    objs: list[Path] = []
    failed: list[str] = []

    import concurrent.futures

    def compile_one(src_file: Path) -> Path | None:
        digest = abs(hash(str(src_file)))
        obj = obj_dir / f"{abs(hash(str(src_file))) & 0xFFFFFFFF:08x}_{src_file.stem}.o"
        if obj.exists() and obj.stat().st_mtime >= src_file.stat().st_mtime:
            return obj
        r = subprocess.run([*flags, str(src_file), "-o", str(obj)], capture_output=True, text=True)
        if r.returncode != 0:
            failed.append(f"{src_file}\n{r.stderr[-1200:]}")
            return None
        return obj

    with concurrent.futures.ThreadPoolExecutor(max_workers=jobs) as pool:
        for obj in pool.map(compile_one, sources):
            if obj:
                objs.append(obj)

    if failed:
        raise BuildError(f"{len(failed)} source files failed to compile:\n" + "\n\n".join(failed[:3]))
    if len(objs) != len(sources):
        raise BuildError(f"only {len(objs)}/{len(sources)} objects built (cached stale?) use force=True")

    link = subprocess.run(
        [clang, "-std=c++17", "-O2", "-o", str(binary), *[str(o) for o in objs]],
        capture_output=True,
        text=True,
    )
    if link.returncode != 0:
        raise BuildError(f"link failed:\n{link.stderr[-2000:]}")
    return binary


def classify(binary: Path, files: list[Path], features: bool = False) -> list[dict]:
    cmd = [str(binary)]
    if features:
        cmd.append("--features")
    cmd += [str(f) for f in files]
    result = subprocess.run(cmd, capture_output=True, text=True)
    rows: list[dict] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if line.startswith("FEATURES "):
            parts = line.split(" ", 2)
            if len(parts) == 3:
                rows.append({"file": parts[1], "features": [float(x) for x in parts[2].split(",")]})
        elif line.startswith("{"):
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def collect_eval_files(dataset_dir: Path, labels: tuple[str, ...]) -> list[tuple[Path, str]]:
    pairs: list[tuple[Path, str]] = []
    for label in labels:
        folder = dataset_dir / label
        if not folder.is_dir():
            continue
        for wav in sorted(folder.glob("*.wav")):
            if wav.stem.startswith("aug_"):
                continue
            pairs.append((wav, label))
    return pairs


def decide(scores: dict[str, float], threshold: float, margin: float) -> str | None:
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    if not ranked:
        return None
    top_label, top = ranked[0]
    runner_up = ranked[1][1] if len(ranked) > 1 else 0.0
    if top >= threshold and (top - runner_up) >= margin:
        return top_label
    return None


def evaluate_rows(
    rows: list[dict],
    labels: tuple[str, ...],
    threshold: float,
    margin: float,
) -> dict:
    confusion = {t: {p: 0 for p in (*labels, "none")} for t in labels}
    kw_correct = kw_total = 0
    noise_triggered = noise_total = 0
    errors: list[str] = []
    for row in rows:
        name = Path(row["file"]).name
        if "error" in row:
            errors.append(name)
            continue
        scores = {k: v for k, v in row["scores"].items() if k in labels}
        truth = Path(row["file"]).parent.name
        predicted = decide(scores, threshold, margin)
        confusion[truth][predicted] = confusion[truth].get(predicted, 0) + 1
        if truth == "noise":
            noise_total += 1
            if predicted in ("enciende", "apaga"):
                noise_triggered += 1
        else:
            kw_total += 1
            if predicted == truth:
                kw_correct += 1
    kw_recall = kw_correct / kw_total if kw_total else 0.0
    noise_reject = 1 - (noise_triggered / noise_total) if noise_total else 0.0
    return {
        "confusion": confusion,
        "keyword_recall": kw_recall,
        "noise_rejection": noise_reject,
        "noise_false_triggers": noise_triggered,
        "keyword_total": kw_total,
        "errors": errors,
    }


def sweep(
    rows: list[dict],
    labels: tuple[str, ...],
    thresholds: list[float],
    margins: list[float],
) -> list[dict]:
    results = []
    for thr in thresholds:
        for m in margins:
            r = evaluate_rows(rows, labels, thr, m)
            score = 0.5 * r["keyword_recall"] + 0.5 * r["noise_rejection"]
            results.append(
                {
                    "threshold": thr,
                    "margin": m,
                    "keyword_recall": r["keyword_recall"],
                    "noise_rejection": r["noise_rejection"],
                    "score": score,
                }
            )
    results.sort(key=lambda r: r["score"], reverse=True)
    return results
