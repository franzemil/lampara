# /// script
# requires-python = ">=3.12"
# dependencies = ["tensorflow>=2.16", "numpy>=1.26"]
# ///
"""Train a small int8 keyword-spotting model on EI-MFCC features dumped by
`lampara local features`, and export a full-int8 TFLite flatbuffer that runs on
the ESP32 through the EI SDK's non-EON TFLite-Micro engine."""

import sys
from pathlib import Path

import numpy as np

npz_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("tools/.cache/features.npz")
out_tflite = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("tools/.cache/lampara_local_int8.tflite")

import tensorflow as tf

d = np.load(npz_path, allow_pickle=True)
X = d["features"]
y = d["labels"]
labels = ["apaga", "enciende", "noise"]
y_idx = np.array([labels.index(l) for l in y])
X_seq = X.reshape(-1, 50, 13)

rng = np.random.default_rng(42)
val_mask = np.zeros(len(y_idx), dtype=bool)
for c in range(3):
    idx = np.where(y_idx == c)[0]
    rng.shuffle(idx)
    n_val = max(1, len(idx) // 10)
    val_mask[idx[:n_val]] = True

X_train, y_train = X_seq[~val_mask], y_idx[~val_mask]
X_val, y_val = X_seq[val_mask], y_idx[val_mask]
print(f"train: {len(y_train)}  val: {len(y_val)}")

counts = np.bincount(y_train, minlength=3)
total = counts.sum()
class_weight = {i: total / (3 * counts[i]) for i in range(3)}

model = tf.keras.Sequential(
    [
        tf.keras.layers.Input(shape=(50, 13)),
        tf.keras.layers.Conv1D(16, 3, activation="relu"),
        tf.keras.layers.MaxPooling1D(2),
        tf.keras.layers.Conv1D(8, 3, activation="relu"),
        tf.keras.layers.GlobalAveragePooling1D(),
        tf.keras.layers.Dense(16, activation="relu"),
        tf.keras.layers.Dense(3, activation="softmax"),
    ]
)
model.compile(
    optimizer=tf.keras.optimizers.Adam(1e-3),
    loss="sparse_categorical_crossentropy",
    metrics=["accuracy"],
)

cb = [
    tf.keras.callbacks.EarlyStopping(monitor="val_loss", patience=30, restore_best_weights=True),
]
model.fit(
    X_train,
    y_train,
    validation_data=(X_val, y_val),
    epochs=300,
    batch_size=16,
    class_weight=class_weight,
    callbacks=cb,
    verbose=2,
)

val_loss, val_acc = model.evaluate(X_val, y_val, verbose=0)
pred = np.argmax(model.predict(X_val, verbose=0), axis=1)
print(f"float val accuracy: {val_acc:.3f}")
for c, name in enumerate(labels):
    m = y_val == c
    if m.sum():
        print(f"  {name}: recall {np.mean(pred[m] == c):.2f} ({int(m.sum())} samples)")


def representative():
    for i in range(len(X_train)):
        yield [X_train[i : i + 1]]


converter = tf.lite.TFLiteConverter.from_keras_model(model)
converter.optimizations = [tf.lite.Optimize.DEFAULT]
converter.representative_dataset = representative
converter.target_spec.supported_ops = [tf.lite.OpsSet.TFLITE_BUILTINS_INT8]
converter.inference_input_type = tf.int8
converter.inference_output_type = tf.int8
tfl = converter.convert()

out_tflite.parent.mkdir(parents=True, exist_ok=True)
out_tflite.write_bytes(tfl)
print(f"int8 tflite: {len(tfl)} bytes -> {out_tflite}")

interp = tf.lite.Interpreter(model_content=tfl)
interp.allocate_tensors()
inp = interp.get_input_details()[0]
outp = interp.get_output_details()[0]
scale, zp = inp["quantization"]
correct = 0
for i in range(len(X_val)):
    q = np.round(X_val[i : i + 1] / scale + zp).astype(np.int8).reshape(1, 50, 13)
    interp.set_tensor(inp["index"], q)
    interp.invoke()
    o = interp.get_tensor(outp["index"])[0].astype(np.int32)
    scores = (o - outp["quantization"][1]) * outp["quantization"][0]
    if int(np.argmax(scores)) == y_val[i]:
        correct += 1
print(f"int8 tflite val accuracy: {correct / len(X_val):.3f}")
print(f"input quantization: scale={scale} zero_point={zp}")
