#include <ESP_I2S.h>
#include "FS.h"
#include "SD.h"
#include "esp_heap_caps.h"
#include <ctype.h>
#include <string.h>

#define MIC_PDM_CLK 42
#define MIC_PDM_DATA 41
#define SD_CS_PIN 21

#define SAMPLE_RATE 16000U
#define SAMPLE_BITS 16
#define RECORD_SECONDS 10
#define WAV_HEADER_SIZE 44
#define VOLUME_GAIN 2
#define CHUNK_SIZE 4096
#define FLUSH_BYTES 8192
#define MAX_LABEL_LEN 32
#define LINE_BUF_LEN 64

I2SClass i2s;

bool sdOk = false;
char lineBuf[LINE_BUF_LEN];
size_t lineLen = 0;

void generateWavHeader(uint8_t *wavHeader, uint32_t wavSize, uint32_t sampleRate) {
  uint32_t fileSize = wavSize + WAV_HEADER_SIZE - 8;
  uint32_t byteRate = sampleRate * SAMPLE_BITS / 8;
  const uint8_t header[] = {
    'R', 'I', 'F', 'F',
    fileSize, fileSize >> 8, fileSize >> 16, fileSize >> 24,
    'W', 'A', 'V', 'E',
    'f', 'm', 't', ' ',
    0x10, 0x00, 0x00, 0x00,
    0x01, 0x00,
    0x01, 0x00,
    sampleRate, sampleRate >> 8, sampleRate >> 16, sampleRate >> 24,
    byteRate, byteRate >> 8, byteRate >> 16, byteRate >> 24,
    0x02, 0x00,
    0x10, 0x00,
    'd', 'a', 't', 'a',
    wavSize, wavSize >> 8, wavSize >> 16, wavSize >> 24
  };
  memcpy(wavHeader, header, sizeof(header));
}

void pollBusy() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      if (lineLen > 0) {
        Serial.println("ERR busy");
        lineLen = 0;
      }
    } else if (lineLen < LINE_BUF_LEN - 1) {
      lineBuf[lineLen++] = c;
    }
  }
}

void recordWav(const char *path) {
  uint32_t recordSize = SAMPLE_RATE * SAMPLE_BITS / 8 * RECORD_SECONDS;
  uint8_t *recBuffer = (uint8_t *)heap_caps_malloc(recordSize, MALLOC_CAP_SPIRAM);
  if (recBuffer == NULL) {
    Serial.println("ERR mem");
    return;
  }

  for (uint32_t f = 0; f < FLUSH_BYTES; f += CHUNK_SIZE) {
    i2s.readBytes((char *)recBuffer, CHUNK_SIZE);
  }

  Serial.printf("REC %s\n", path);

  uint32_t total = 0;
  while (total < recordSize) {
    uint32_t chunk = (recordSize - total < CHUNK_SIZE) ? recordSize - total : CHUNK_SIZE;
    size_t got = i2s.readBytes((char *)recBuffer + total, chunk);
    if (got == 0) {
      break;
    }
    total += got;
    pollBusy();
  }

  for (uint32_t i = 0; i + 1 < total; i += SAMPLE_BITS / 8) {
    (*(uint16_t *)(recBuffer + i)) <<= VOLUME_GAIN;
  }

  if (total == 0) {
    Serial.println("ERR rec");
    free(recBuffer);
    return;
  }

  File file = SD.open(path, FILE_WRITE);
  if (!file) {
    Serial.println("ERR file");
    free(recBuffer);
    return;
  }

  uint8_t header[WAV_HEADER_SIZE];
  generateWavHeader(header, total, SAMPLE_RATE);
  file.write(header, WAV_HEADER_SIZE);
  size_t written = file.write(recBuffer, total);
  file.close();
  free(recBuffer);

  if (written != total) {
    Serial.println("ERR write");
    return;
  }
  Serial.printf("DONE %s %u bytes\n", path, total + WAV_HEADER_SIZE);
}

void handleLine(char *line) {
  if (!sdOk) {
    Serial.println("ERR sd");
    return;
  }
  if (strncmp(line, "rec ", 4) != 0) {
    Serial.println("ERR usage: rec {label}");
    return;
  }
  char *label = line + 4;
  while (*label == ' ' || *label == '\t') label++;
  char *end = label + strlen(label);
  while (end > label && (end[-1] == ' ' || end[-1] == '\t')) end--;
  *end = '\0';
  size_t len = end - label;
  if (len < 1 || len > MAX_LABEL_LEN) {
    Serial.println("ERR label");
    return;
  }
  for (size_t i = 0; i < len; i++) {
    char c = label[i];
    if (!isalnum((unsigned char)c) && c != '-' && c != '_') {
      Serial.println("ERR label");
      return;
    }
  }
  char path[MAX_LABEL_LEN + 8];
  snprintf(path, sizeof(path), "/%s.wav", label);
  recordWav(path);
}

void setup() {
  Serial.begin(115200);
  uint32_t t0 = millis();
  while (!Serial && millis() - t0 < 3000) delay(10);

  i2s.setPinsPdmRx(MIC_PDM_CLK, MIC_PDM_DATA);
  if (!i2s.begin(I2S_MODE_PDM_RX, SAMPLE_RATE, I2S_DATA_BIT_WIDTH_16BIT, I2S_SLOT_MODE_MONO)) {
    Serial.println("ERR i2s");
    while (1) delay(1000);
  }
  Serial.println("I2S ok");

  Serial.println("SD init...");
  sdOk = SD.begin(SD_CS_PIN);
  if (!sdOk) Serial.println("ERR sd");
  Serial.println("READY");
}

void loop() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      if (lineLen > 0) {
        lineBuf[lineLen] = '\0';
        lineLen = 0;
        handleLine(lineBuf);
      }
    } else if (lineLen < LINE_BUF_LEN - 1) {
      lineBuf[lineLen++] = c;
    }
  }
}
