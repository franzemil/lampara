"""TTS sample generation via macOS `say` + ffmpeg conversion."""

from __future__ import annotations

from pathlib import Path

from . import ffmpeg

KEYWORD_PHRASES: dict[str, list[str]] = {
    "enciende": ["enciende", "enciende la luz"],
    "apaga": ["apaga", "apaga la luz"],
}

ES_UNKNOWN_WORDS = "perro ventana casa mesa silla gato libro puerta reloj coche arbol mano noche dia".split()
EN_UNKNOWN_WORDS = "dog tree house table seven three hello computer water light".split()


def _slug(text: str) -> str:
    return text.replace(" ", "_")


def tts_keywords(
    dataset_dir: Path,
    tts_cache: Path,
    max_voices: int = 6,
    rates: tuple[int, ...] = (150, 190),
    tempos: tuple[float, ...] = (0.9, 1.1),
    dry_run: bool = False,
) -> dict[str, int]:
    voices = ffmpeg.list_voices(("es_",), max_voices=max_voices)
    if not voices:
        raise ffmpeg.ToolError("no Spanish say voices found")
    tts_cache.mkdir(parents=True, exist_ok=True)
    counts = {"enciende": 0, "apaga": 0}

    for voice, locale in voices:
        tag = f"{voice}_{locale}".replace(" ", "-")
        for label, phrases in KEYWORD_PHRASES.items():
            out_dir = dataset_dir / label
            out_dir.mkdir(parents=True, exist_ok=True)
            for phrase in phrases:
                for rate in rates:
                    aiff = tts_cache / f"{tag}_{_slug(phrase)}_r{rate}.aiff"
                    ffmpeg.say_to_file(voice, rate, phrase, aiff, dry_run=dry_run)
                    for tempo in tempos:
                        out = out_dir / f"tts_{tag}_{_slug(phrase)}_r{rate}_t{tempo}.wav"
                        ffmpeg.ffmpeg(
                            [
                                "-i",
                                str(aiff),
                                "-af",
                                f"atempo={tempo},apad=whole_dur=1,atrim=0:1",
                                "-ar",
                                "16000",
                                "-ac",
                                "1",
                                str(out),
                            ],
                            dry_run=dry_run,
                        )
                        counts[label] += 1
    return counts


def tts_unknown(
    noise_dir: Path,
    tts_cache: Path,
    max_es_voices: int = 6,
    max_en_voices: int = 4,
    rate: int = 170,
    dry_run: bool = False,
) -> int:
    es_voices = ffmpeg.list_voices(("es_",), max_voices=max_es_voices)
    en_voices = ffmpeg.list_voices(("en_",), max_voices=max_en_voices)
    if not es_voices and not en_voices:
        raise ffmpeg.ToolError("no say voices found")
    tts_cache.mkdir(parents=True, exist_ok=True)
    noise_dir.mkdir(parents=True, exist_ok=True)
    count = 0

    for lang, voices, words in (("es", es_voices, ES_UNKNOWN_WORDS), ("en", en_voices, EN_UNKNOWN_WORDS)):
        for voice, locale in voices:
            tag = f"{voice}_{locale}".replace(" ", "-")
            for word in words:
                aiff = tts_cache / f"{lang}_{tag}_{word}.aiff"
                out = noise_dir / f"unk_{lang}_{tag}_{word}.wav"
                ffmpeg.say_to_file(voice, rate, word, aiff, dry_run=dry_run)
                ffmpeg.ffmpeg(
                    [
                        "-i",
                        str(aiff),
                        "-af",
                        "apad=whole_dur=1,atrim=0:1",
                        "-ar",
                        "16000",
                        "-ac",
                        "1",
                        str(out),
                    ],
                    dry_run=dry_run,
                )
                count += 1
    return count
