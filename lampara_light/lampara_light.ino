#define EIDSP_QUANTIZE_FILTERBANK 0

#include <Lampara_inferencing.h>
#include <ESP_I2S.h>

#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

#define MIC_PDM_CLK 42
#define MIC_PDM_DATA 41

#define LIGHT_PIN 21
#define LIGHT_ACTIVE_LOW 1
#define AUDIO_GAIN 4
#define LIGHT_TRIGGER_THRESHOLD 0.8f
#define LIGHT_TRIGGER_MARGIN 0.15f
#define LIGHT_COOLDOWN_MS 1500

I2SClass i2s;

typedef struct {
    signed short *buffers[2];
    volatile unsigned char buf_select;
    volatile unsigned char buf_ready;
    unsigned int buf_count;
    unsigned int n_samples;
} inference_t;

static inference_t inference;
static const uint32_t sample_buffer_size = 2048;
static signed short sampleBuffer[sample_buffer_size];
static bool debug_nn = false;
static int print_results = -(EI_CLASSIFIER_SLICES_PER_MODEL_WINDOW);
static bool record_status = true;
static bool lightOn = false;
static uint32_t lastTriggerMs = 0;

static void setLight(bool on) {
#if LIGHT_ACTIVE_LOW
    digitalWrite(LIGHT_PIN, on ? LOW : HIGH);
#else
    digitalWrite(LIGHT_PIN, on ? HIGH : LOW);
#endif
    lightOn = on;
}

static void audio_inference_callback(uint32_t n_bytes) {
    for (uint32_t i = 0; i < n_bytes >> 1; i++) {
        inference.buffers[inference.buf_select][inference.buf_count++] = sampleBuffer[i];

        if (inference.buf_count >= inference.n_samples) {
            inference.buf_select ^= 1;
            inference.buf_count = 0;
            inference.buf_ready = 1;
        }
    }
}

static void capture_samples(void *arg) {
    const uint32_t i2s_bytes_to_read = (uint32_t)(uintptr_t)arg;

    while (record_status) {
        size_t bytes_read = i2s.readBytes((char *)sampleBuffer, i2s_bytes_to_read);

        if (bytes_read == 0) {
            ei_printf("Error in I2S read: timeout\n");
            continue;
        }

        for (uint32_t x = 0; x < bytes_read / 2; x++) {
            sampleBuffer[x] = (signed short)(sampleBuffer[x] * AUDIO_GAIN);
        }

        if (record_status) {
            audio_inference_callback(bytes_read);
        } else {
            break;
        }
    }
    vTaskDelete(NULL);
}

static bool microphone_inference_start(uint32_t n_samples) {
    inference.buffers[0] = (signed short *)malloc(n_samples * sizeof(signed short));
    if (inference.buffers[0] == NULL) {
        return false;
    }

    inference.buffers[1] = (signed short *)malloc(n_samples * sizeof(signed short));
    if (inference.buffers[1] == NULL) {
        ei_free(inference.buffers[0]);
        return false;
    }

    inference.buf_select = 0;
    inference.buf_count = 0;
    inference.n_samples = n_samples;
    inference.buf_ready = 0;

    i2s.setPinsPdmRx(MIC_PDM_CLK, MIC_PDM_DATA);
    if (!i2s.begin(I2S_MODE_PDM_RX, EI_CLASSIFIER_FREQUENCY, I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_MONO)) {
        ei_printf("Failed to start I2S!\n");
        ei_free(inference.buffers[0]);
        ei_free(inference.buffers[1]);
        return false;
    }

    ei_sleep(100);
    record_status = true;
    xTaskCreate(capture_samples, "CaptureSamples", 1024 * 16, (void *)(uintptr_t)sample_buffer_size, 10, NULL);

    return true;
}

static bool microphone_inference_record(void) {
    if (inference.buf_ready == 1) {
        ei_printf(
            "Error sample buffer overrun. Decrease the number of slices per model window "
            "(EI_CLASSIFIER_SLICES_PER_MODEL_WINDOW)\n");
        return false;
    }

    while (inference.buf_ready == 0) {
        delay(1);
    }

    inference.buf_ready = 0;
    return true;
}

static int microphone_audio_signal_get_data(size_t offset, size_t length, float *out_ptr) {
    numpy::int16_to_float(&inference.buffers[inference.buf_select ^ 1][offset], out_ptr, length);
    return 0;
}

void setup() {
    Serial.begin(115200);
    uint32_t t0 = millis();
    while (!Serial && millis() - t0 < 3000) delay(10);

    pinMode(LIGHT_PIN, OUTPUT);
    setLight(false);

    ei_printf("Inferencing settings:\n");
    ei_printf("\tInterval: ");
    ei_printf_float((float)EI_CLASSIFIER_INTERVAL_MS);
    ei_printf(" ms.\n");
    ei_printf("\tFrame size: %d\n", EI_CLASSIFIER_DSP_INPUT_FRAME_SIZE);
    ei_printf("\tSample length: %d ms.\n", EI_CLASSIFIER_RAW_SAMPLE_COUNT / 16);
    ei_printf("\tNo. of classes: %d\n", sizeof(ei_classifier_inferencing_categories) / sizeof(ei_classifier_inferencing_categories[0]));

    run_classifier_init();

    if (microphone_inference_start(EI_CLASSIFIER_SLICE_SIZE) == false) {
        ei_printf("ERR: Could not allocate audio buffer (size %d), this could be due to the window length of your model\r\n", EI_CLASSIFIER_RAW_SAMPLE_COUNT);
        while (1) delay(1000);
    }

    ei_printf("Listening...\n");
}

void loop() {
    bool m = microphone_inference_record();
    if (!m) {
        ei_printf("ERR: Failed to record audio...\n");
        return;
    }

    signal_t signal;
    signal.total_length = EI_CLASSIFIER_SLICE_SIZE;
    signal.get_data = &microphone_audio_signal_get_data;
    ei_impulse_result_t result = {0};

    EI_IMPULSE_ERROR r = run_classifier_continuous(&signal, &result, debug_nn);
    if (r != EI_IMPULSE_OK) {
        ei_printf("ERR: Failed to run classifier (%d)\n", r);
        return;
    }

    if (++print_results >= (EI_CLASSIFIER_SLICES_PER_MODEL_WINDOW)) {
        float onScore = 0.0f, offScore = 0.0f, noiseScore = 0.0f;
        for (size_t ix = 0; ix < EI_CLASSIFIER_LABEL_COUNT; ix++) {
            if (strcmp(result.classification[ix].label, "enciende") == 0) {
                onScore = result.classification[ix].value;
            } else if (strcmp(result.classification[ix].label, "apaga") == 0) {
                offScore = result.classification[ix].value;
            } else if (strcmp(result.classification[ix].label, "noise") == 0) {
                noiseScore = result.classification[ix].value;
            }
        }

        ei_printf("Predictions (DSP: %d ms., Classification: %d ms.): ",
            result.timing.dsp, result.timing.classification);
        for (size_t ix = 0; ix < EI_CLASSIFIER_LABEL_COUNT; ix++) {
            ei_printf("%s: ", result.classification[ix].label);
            ei_printf_float(result.classification[ix].value);
            ei_printf(" ");
        }
        ei_printf("\n");

        uint32_t now = millis();
        if (now - lastTriggerMs > LIGHT_COOLDOWN_MS) {
            float onRunnerUp = (offScore > noiseScore) ? offScore : noiseScore;
            float offRunnerUp = (onScore > noiseScore) ? onScore : noiseScore;
            bool onWins = onScore >= LIGHT_TRIGGER_THRESHOLD && (onScore - onRunnerUp) >= LIGHT_TRIGGER_MARGIN;
            bool offWins = offScore >= LIGHT_TRIGGER_THRESHOLD && (offScore - offRunnerUp) >= LIGHT_TRIGGER_MARGIN;
            if (onWins) {
                setLight(true);
                lastTriggerMs = now;
                ei_printf(">> LIGHT ON (enciende: ");
                ei_printf_float(onScore);
                ei_printf(")\n");
            } else if (offWins) {
                setLight(false);
                lastTriggerMs = now;
                ei_printf(">> LIGHT OFF (apaga: ");
                ei_printf_float(offScore);
                ei_printf(")\n");
            }
        }

        print_results = 0;
    }
}
