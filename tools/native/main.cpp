// Local classifier for the Lampara impulse: WAV -> run_classifier -> JSON scores.
// Built against the Edge Impulse C++ SDK shipped in the Arduino library zip,
// so DSP and weights are identical to what runs on the ESP32.

#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

#include "edge-impulse-sdk/classifier/ei_run_classifier.h"
#include "edge-impulse-sdk/classifier/ei_classifier_smooth.h"
#include "edge-impulse-sdk/dsp/numpy.hpp"
#include "model-parameters/model_metadata.h"

static std::vector<float> g_signal;

static int ei_signal_get_data(size_t offset, size_t length, float *out_ptr) {
    for (size_t i = 0; i < length; i++) {
        size_t ix = offset + i;
        out_ptr[i] = ix < g_signal.size() ? g_signal[ix] : 0.0f;
    }
    return 0;
}

static bool read_wav(const char *path, std::vector<float> &out) {
    FILE *f = fopen(path, "rb");
    if (!f) return false;

    uint8_t hdr[12];
    if (fread(hdr, 1, 12, f) != 12 || memcmp(hdr, "RIFF", 4) != 0 || memcmp(hdr + 8, "WAVE", 4) != 0) {
        fclose(f);
        return false;
    }

    int channels = 1;
    uint32_t sample_rate = 16000;
    int16_t *data = nullptr;
    size_t n_samples = 0;
    bool ok = false;

    while (true) {
        uint8_t ch[8];
        if (fread(ch, 1, 8, f) != 8) break;
        uint32_t size = (uint32_t)ch[4] | ((uint32_t)ch[5] << 8) | ((uint32_t)ch[6] << 16) | ((uint32_t)ch[7] << 24);

        if (memcmp(ch, "fmt ", 4) == 0) {
            uint8_t fmt[16];
            if (fread(fmt, 1, 16, f) != 16) break;
            uint16_t audio_format = (uint16_t)fmt[0] | ((uint16_t)fmt[1] << 8);
            channels = (uint16_t)fmt[2] | ((uint16_t)fmt[3] << 8);
            sample_rate = (uint32_t)fmt[4] | ((uint32_t)fmt[5] << 8) | ((uint32_t)fmt[6] << 16) | ((uint32_t)fmt[7] << 24);
            uint16_t bits = (uint16_t)fmt[14] | ((uint16_t)fmt[15] << 8);
            if (audio_format != 1 || bits != 16) break;
        } else if (memcmp(ch, "data", 4) == 0) {
            size_t bytes = size;
            uint8_t *raw = (uint8_t *)malloc(bytes);
            if (!raw) break;
            if (fread(raw, 1, bytes, f) != bytes) {
                free(raw);
                break;
            }
            n_samples = bytes / 2 / channels;
            data = (int16_t *)raw;
            ok = true;
            break;
        } else {
            fseek(f, size, SEEK_CUR);
        }
    }
    fclose(f);
    if (!ok || !data) {
        free(data);
        return false;
    }

    out.clear();
    out.reserve(n_samples);
    for (size_t i = 0; i < n_samples; i++) {
        int32_t acc = 0;
        for (int c = 0; c < channels; c++) acc += data[i * channels + c];
        out.push_back(acc / channels / 32768.0f);
    }
    free(data);
    (void)sample_rate;
    return true;
}

int main(int argc, char **argv) {
    bool features = false;
    std::vector<std::string> files;
    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--features") == 0) features = true;
        else files.push_back(argv[i]);
    }
    if (files.empty()) {
        fprintf(stderr, "usage: %s [--features] file.wav [file2.wav ...]\n", argv[0]);
        return 1;
    }

    run_classifier_init();

    for (const auto &file : files) {
        if (!read_wav(file.c_str(), g_signal)) {
            printf("{\"file\": \"%s\", \"error\": \"unreadable wav\"}\n", file.c_str());
            continue;
        }

        ei::signal_t signal;
        signal.total_length = g_signal.size();
        signal.get_data = &ei_signal_get_data;

        if (features) {
            std::vector<float> feature_buffer(EI_CLASSIFIER_NN_INPUT_FRAME_SIZE, 0.0f);
            matrix_t features(1, EI_CLASSIFIER_NN_INPUT_FRAME_SIZE, feature_buffer.data());
            if (extract_mfcc_features(
                    &signal, &features, (void *)&ei_dsp_config_1127921_3, 16000.0f) != EI_IMPULSE_OK) {
                printf("{\"file\": \"%s\", \"error\": \"feature extraction failed\"}\n", file.c_str());
                continue;
            }
            printf("FEATURES %s ", file.c_str());
            for (size_t i = 0; i < features.cols; i++) {
                printf("%s%.6f", i ? "," : "", features.buffer[i]);
            }
            printf("\n");
            continue;
        }

        ei_impulse_result_t result = {0};
        run_classifier_init();
        EI_IMPULSE_ERROR r = run_classifier(&signal, &result, false);
        run_classifier_deinit();
        if (r != EI_IMPULSE_OK) {
            printf("{\"file\": \"%s\", \"error\": \"run_classifier failed %d\"}\n", file.c_str(), (int)r);
            continue;
        }

        printf("{\"file\": \"%s\", \"scores\": {", file.c_str());
        for (size_t i = 0; i < EI_CLASSIFIER_LABEL_COUNT; i++) {
            printf("%s\"%s\": %.6f", i ? ", " : "", result.classification[i].label, result.classification[i].value);
        }
        printf("}, \"dsp_ms\": %u, \"classification_ms\": %u}\n",
               (unsigned)result.timing.dsp, (unsigned)result.timing.classification);
    }

    run_classifier_deinit();
    return 0;
}
