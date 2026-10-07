// POSIX/macOS porting implementation for the Edge Impulse C++ SDK.
// Provides the user-defined functions declared in
// edge-impulse-sdk/porting/ei_classifier_porting.h

#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cstdarg>

#include "edge-impulse-sdk/porting/ei_classifier_porting.h"

__attribute__((weak)) EI_IMPULSE_ERROR ei_run_impulse_check_canceled() {
    return EI_IMPULSE_OK;
}

__attribute__((weak)) void ei_serial_set_baudrate(int baudrate) {
    (void)baudrate;
}

__attribute__((weak)) EI_IMPULSE_ERROR ei_sleep(int32_t time_ms) {
    (void)time_ms;
    return EI_IMPULSE_OK;
}

__attribute__((weak)) uint64_t ei_read_timer_ms() {
    using namespace std::chrono;
    return duration_cast<milliseconds>(steady_clock::now().time_since_epoch()).count();
}

__attribute__((weak)) uint64_t ei_read_timer_us() {
    using namespace std::chrono;
    return duration_cast<microseconds>(steady_clock::now().time_since_epoch()).count();
}

__attribute__((weak)) void ei_putchar(char c) {
    fputc(c, stderr);
}

__attribute__((weak)) char ei_getchar(void) {
    return getchar();
}

__attribute__((weak)) void ei_printf(const char *format, ...) {
    va_list args;
    va_start(args, format);
    vfprintf(stderr, format, args);
    va_end(args);
}

__attribute__((weak)) void ei_printf_float(float f) {
    fprintf(stderr, "%f", f);
}

__attribute__((weak)) void *ei_malloc(size_t size) {
    return malloc(size);
}

__attribute__((weak)) void *ei_calloc(size_t nitems, size_t size) {
    return calloc(nitems, size);
}

__attribute__((weak)) void ei_free(void *ptr) {
    free(ptr);
}
