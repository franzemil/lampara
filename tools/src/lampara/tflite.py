"""Inject a locally-trained TFLite model into an Edge Impulse Arduino library.

Switches the library from the EON-compiled engine to the TFLite-Micro
interpreter (non-EON) so a plain .tflite flatbuffer can be used without
changing the sketch API."""

from __future__ import annotations

import re
from pathlib import Path

ARENA_DEFAULT = 32768

TRAINED_TFLITE_H = """#ifndef _TRAINED_TFLITE_H_
#define _TRAINED_TFLITE_H_

#include <stddef.h>
#include <stdint.h>

extern const unsigned char trained_tflite[];
extern const size_t trained_tflite_len;

#endif // _TRAINED_TFLITE_H_
"""

RESOLVER_H = """#ifndef _TFLITE_RESOLVER_H_
#define _TFLITE_RESOLVER_H_
// intentionally empty: the tflite_micro engine uses tflite::AllOpsResolver
#endif // _TFLITE_RESOLVER_H_
"""


def _byte_array(data: bytes) -> str:
    lines = []
    for i in range(0, len(data), 12):
        chunk = ", ".join(f"0x{b:02x}" for b in data[i : i + 12])
        lines.append(f"    {chunk},")
    body = "\n".join(lines).rstrip(",")
    return f"alignas(16) const unsigned char trained_tflite[] = {{\n{body}\n}};\n\nconst size_t trained_tflite_len = sizeof(trained_tflite);\n"


def inject(model_tflite: Path, src_dir: Path, arena_size: int = ARENA_DEFAULT) -> Path:
    data = model_tflite.read_bytes()
    tflite_dir = src_dir / "tflite-model"
    tflite_dir.mkdir(parents=True, exist_ok=True)
    (tflite_dir / "trained_tflite.h").write_text(TRAINED_TFLITE_H)
    (tflite_dir / "trained_tflite.cpp").write_text(
        '#include "tflite-model/trained_tflite.h"\n\n' + _byte_array(data)
    )
    (tflite_dir / "tflite-resolver.h").write_text(RESOLVER_H)

    variables = src_dir / "model-parameters" / "model_variables.h"
    text = variables.read_text()
    anchor = '#include "model_metadata.h"'
    if anchor not in text:
        raise RuntimeError(f"anchor include {anchor} not found in {variables}")
    if "#include \"tflite-model/trained_tflite.h\"" not in text:
        text = text.replace(anchor, f'{anchor}\n#include "tflite-model/trained_tflite.h"', 1)

    eon_pattern = re.compile(
        r"const ei_config_tflite_eon_graph_t ei_config_graph_[\d_]+ = \{.*?\};",
        re.DOTALL,
    )
    micro_pattern = re.compile(
        r"const ei_config_tflite_graph_t ei_config_graph_[\d_]+ = \{.*?\};",
        re.DOTALL,
    )
    replacement = (
        "const ei_config_tflite_graph_t ei_config_graph_1127921_4 = {\n"
        "    .implementation_version = 1,\n"
        "    .model = trained_tflite,\n"
        "    .model_size = trained_tflite_len,\n"
        f"    .arena_size = {arena_size},\n"
        "};"
    )
    if eon_pattern.search(text):
        text = eon_pattern.sub(replacement, text, count=1)
    elif not micro_pattern.search(text):
        raise RuntimeError("neither EON nor TFLM graph config found in model_variables.h")
    variables.write_text(text)

    metadata = src_dir / "model-parameters" / "model_metadata.h"
    meta = metadata.read_text()
    meta = re.sub(
        r"#define EI_CLASSIFIER_COMPILED\s+\d+",
        "#define EI_CLASSIFIER_COMPILED                   0",
        meta,
    )
    meta = re.sub(
        r"#define EI_CLASSIFIER_TFLITE_LARGEST_ARENA_SIZE\s+\d+",
        f"#define EI_CLASSIFIER_TFLITE_LARGEST_ARENA_SIZE     {arena_size}",
        meta,
    )
    metadata.write_text(meta)
    return src_dir
