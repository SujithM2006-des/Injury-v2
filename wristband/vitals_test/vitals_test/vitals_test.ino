// Vitals test v8: MAX30100 heart rate + SpO2 on ESP32-C3, shown on the 2.8" ILI9341 display.
// Software fixes for the green MAX30100 board's weak (1.8 V) I2C pull-ups:
//  - very slow I2C (20 kHz) so the weak signal has time to rise
//  - settings are written, read back and re-written until they are correct
//  - every 2 s the settings are checked again and repaired if they got corrupted
//  - frozen / impossible readings are ignored
// Heart rate from autocorrelation of the last 4 s of pulse, median of the last 5 results.
// Sensor SCL on GPIO 3 (GPIO 9 is a start-up pin - never use it).
#include <Wire.h>
#include <SPI.h>
#include <math.h>
#include <Adafruit_GFX.h>
#include <Adafruit_ILI9341.h>
#include "MAX30100.h"     // library: MAX30100lib by OXullo Intersecans

// ===== Display pins (tested and working) =====
#define TFT_SCK   4
#define TFT_MOSI  6
#define TFT_CS    7
#define TFT_DC    5
#define TFT_RST   10
// ===== Sensor pins =====
#define I2C_SDA   8
#define I2C_SCL   3
#define I2C_HZ    20000   // slow I2C: the sensor's 1.8 V pull-ups need time to rise
#define MAX_ADDR  0x57
#define FINGER_IR 25000   // raw IR above this = finger on the sensor

Adafruit_ILI9341 tft(TFT_CS, TFT_DC, TFT_RST);
MAX30100 sensor;

const uint16_t C_BLACK = 0x0000, C_WHITE = 0xFFFF, C_RED = 0xF800, C_CYAN = 0x07FF,
               C_GREY = 0x8410, C_NAVY = 0x000F, C_GREEN = 0x07E0, C_YELLOW = 0xFFE0;

// ===== Heart rate by autocorrelation (robust to noise) + SpO2 estimate =====
#define VB_N 400            // 4 s at 100 Hz
#define MAW  60             // drift filter window (0.6 s)
#define LP1  0.6f           // noise smoothing
#define DCA  0.995f         // baseline tracking
struct Vitals {
  float buf[VB_N]; int pos = 0, count = 0;
  float dcIR = 0, dcRed = 0, lp = 0, lp2 = 0; bool init = false;
  double sumAcIR2 = 0, sumAcRed2 = 0; int nAc = 0;
  float bpm = 0, spo2 = 0; int nEst = 0, nSpo2 = 0;
  float hist[5]; int nHist = 0, iHist = 0;
  int sinceCalc = 0;
  float quality = 0;

  void reset() { *this = Vitals(); }

  static float median(float* a, int n) {
    float t[5]; for (int i = 0; i < n; i++) t[i] = a[i];
    for (int i = 0; i < n; i++) for (int j = i + 1; j < n; j++) if (t[j] < t[i]) { float x = t[i]; t[i] = t[j]; t[j] = x; }
    return t[n / 2];
  }

  bool sample(float ir, float red) {
    if (!init) { dcIR = ir; dcRed = red; init = true; }
    dcIR  = DCA * dcIR  + (1 - DCA) * ir;
    dcRed = DCA * dcRed + (1 - DCA) * red;
    float acIR = dcIR - ir, acRed = dcRed - red;
    lp  = LP1 * lp  + (1 - LP1) * acIR;
    lp2 = LP1 * lp2 + (1 - LP1) * lp;
    buf[pos] = lp2; pos = (pos + 1) % VB_N; if (count < VB_N) count++;
    sumAcIR2 += acIR * acIR; sumAcRed2 += acRed * acRed; nAc++;

    if (++sinceCalc < 100 || count < VB_N) return false;
    sinceCalc = 0;

    static float x[VB_N];
    static float raw[VB_N];
    for (int i = 0; i < VB_N; i++) raw[i] = buf[(pos + i) % VB_N];
    const int H = MAW / 2;
    float acc = 0; int lo = 0, hi = -1;
    for (int i = 0; i < VB_N; i++) {
      int a0 = i - H < 0 ? 0 : i - H, b0 = i + H >= VB_N ? VB_N - 1 : i + H;
      while (hi < b0) acc += raw[++hi];
      while (lo < a0) acc -= raw[lo++];
      x[i] = raw[i] - acc / (hi - lo + 1);
    }
    float e0 = 0; for (int i = 0; i < VB_N; i++) e0 += x[i] * x[i];
    if (e0 <= 0) return false;

    const int LMIN = 30, LMAX = 200;
    static float r[LMAX + 2];
    for (int L = LMIN - 1; L <= LMAX + 1; L++) {
      float s = 0; for (int i = 0; i + L < VB_N; i++) s += x[i] * x[i + L];
      r[L] = s / e0 * VB_N / (VB_N - L);
    }
    float best = 0;
    for (int L = LMIN; L <= LMAX; L++) if (r[L] > r[L - 1] && r[L] >= r[L + 1] && r[L] > best) best = r[L];
    int pickL = 0;
    for (int L = LMIN; L <= LMAX; L++) if (r[L] > r[L - 1] && r[L] >= r[L + 1] && r[L] > 0.8f * best) { pickL = L; break; }
    quality = best;
    if (!pickL || best < 0.3f) return false;
    float a = r[pickL - 1], b = r[pickL], c = r[pickL + 1];
    float d = (a - 2 * b + c) != 0 ? 0.5f * (a - c) / (a - 2 * b + c) : 0;
    float est = 6000.0f / (pickL + d);

    hist[iHist] = est; iHist = (iHist + 1) % 5; if (nHist < 5) nHist++;
    bpm = median(hist, nHist); nEst++;

    if (nAc > 0 && dcIR > 0 && dcRed > 0) {
      float rmsIR = sqrt(sumAcIR2 / nAc), rmsRed = sqrt(sumAcRed2 / nAc);
      if (rmsIR > 0) {
        float R = (rmsRed / dcRed) / (rmsIR / dcIR);
        float s = 110.0f - 25.0f * R;
        if (s > 100) s = 100;
        if (s < 70) s = 70;
        spo2 = nSpo2 ? 0.7f * spo2 + 0.3f * s : s; nSpo2++;
      }
    }
    sumAcIR2 = sumAcRed2 = 0; nAc = 0;
    return true;
  }
};

Vitals vit;
bool fingerOn = false;
unsigned long lastDrawMs = 0;
uint16_t lastIR = 0;

// ----- Direct register access with read-back check -----
int readReg(uint8_t reg) {
  Wire.beginTransmission(MAX_ADDR);
  Wire.write(reg);
  if (Wire.endTransmission(false) != 0) return -1;
  if (Wire.requestFrom((uint8_t)MAX_ADDR, (uint8_t)1) != 1) return -1;
  return Wire.read();
}

bool writeRegChecked(uint8_t reg, uint8_t value) {
  for (int attempt = 0; attempt < 10; attempt++) {
    Wire.beginTransmission(MAX_ADDR);
    Wire.write(reg);
    Wire.write(value);
    Wire.endTransmission();
    delay(2);
    if (readReg(reg) == value) return true;
    delay(5);
  }
  return false;
}

// SpO2 + heart-rate mode, high resolution, 100 samples/s, 1600 us pulses, both LEDs 27.1 mA
const uint8_t REG_MODE = 0x06, REG_SPO2 = 0x07, REG_LED = 0x09;
const uint8_t VAL_MODE = 0x03, VAL_SPO2 = 0x47, VAL_LED = 0x88;

bool applySettings() {
  bool ok = writeRegChecked(REG_MODE, VAL_MODE);
  ok = writeRegChecked(REG_SPO2, VAL_SPO2) && ok;
  ok = writeRegChecked(REG_LED, VAL_LED) && ok;
  return ok;
}

bool settingsOk() {
  return readReg(REG_MODE) == VAL_MODE && readReg(REG_LED) == VAL_LED;
}

unsigned long lastCheckMs = 0;
int repairs = 0;
uint16_t prevIR = 0, prevRed = 0; int sameCount = 0;

void centred(const char* text, int y, uint8_t size, uint16_t fg, uint16_t bg) {
  int16_t x1, y1; uint16_t w, h;
  tft.setTextSize(size);
  tft.getTextBounds(text, 0, 0, &x1, &y1, &w, &h);
  tft.fillRect(0, y - 2, tft.width(), h + 6, bg);
  tft.setTextColor(fg);
  tft.setCursor((tft.width() - w) / 2, y);
  tft.print(text);
}

void drawFrame() {
  tft.fillScreen(C_BLACK);
  tft.fillRect(0, 0, tft.width(), 36, C_NAVY);
  centred("VITALS TEST", 10, 2, C_WHITE, C_NAVY);
  tft.setTextSize(2);
  tft.setTextColor(C_GREY);
  tft.setCursor(30, 60);  tft.print("HEART RATE");
  tft.setCursor(200, 60); tft.print("SpO2");
}

void showValues(int hr, bool hrOk, int ox, bool oxOk) {
  char t[16];
  tft.fillRect(0, 85, tft.width(), 70, C_BLACK);
  tft.setTextSize(5);
  tft.setTextColor(hrOk ? C_RED : C_GREY);
  snprintf(t, sizeof(t), hrOk ? "%d" : "--", hr);
  tft.setCursor(40, 95); tft.print(t);
  tft.setTextColor(oxOk ? C_CYAN : C_GREY);
  snprintf(t, sizeof(t), oxOk ? "%d%%" : "--", ox);
  tft.setCursor(190, 95); tft.print(t);
  tft.setTextSize(2); tft.setTextColor(C_GREY);
  tft.setCursor(40, 145); tft.print("bpm");
  tft.setCursor(190, 145); tft.print("est.");
}

void status(const char* text, uint16_t colour) {
  centred(text, 195, 2, colour, C_BLACK);
}

void setup() {
  Serial.begin(115200);
  delay(1500);
  Serial.println("vitals_test v8 (MAX30100, slow I2C + self-repair) starting");
  SPI.begin(TFT_SCK, -1, TFT_MOSI, TFT_CS);
  tft.begin(40000000);
  tft.setRotation(1);
  drawFrame();
  showValues(0, false, 0, false);

  Wire.begin(I2C_SDA, I2C_SCL);
  Wire.setClock(I2C_HZ);
  if (!sensor.begin()) {
    Serial.println("MAX30100 library start failed - trying the settings directly");
  }
  // The library may restart I2C: put our pins and slow speed back
  Wire.begin(I2C_SDA, I2C_SCL);
  Wire.setClock(I2C_HZ);
  if (readReg(0xFF) < 0) {
    Serial.println("MAX30100 not answering - check VIN, GND, SDA (GPIO 8), SCL (GPIO 3)");
    status("SENSOR NOT FOUND", C_RED);
    while (true) delay(1000);
  }
  bool ok = applySettings();
  Serial.print("Settings written and checked: "); Serial.println(ok ? "OK" : "FAILED (will keep retrying)");
  Serial.print("Mode=0x"); Serial.print(readReg(REG_MODE), HEX);
  Serial.print(" SpO2=0x"); Serial.print(readReg(REG_SPO2), HEX);
  Serial.print(" LED=0x"); Serial.println(readReg(REG_LED), HEX);
  Serial.println("Ready. Place your finger on the sensor and keep still.");
  status(ok ? "Place your finger" : "Sensor unstable...", ok ? C_YELLOW : C_RED);
}

void loop() {
  // Every 2 s: check the sensor still has the right settings, repair them if not
  if (millis() - lastCheckMs > 2000) {
    lastCheckMs = millis();
    if (!settingsOk()) {
      repairs++;
      Serial.print("Settings corrupted - repairing (#"); Serial.print(repairs); Serial.println(")");
      applySettings();
      vit.reset();
    }
  }

  // Read every new sample (100 per second)
  sensor.update();
  uint16_t ir, red;
  while (sensor.getRawValues(&ir, &red)) {
    // Ignore frozen or impossible readings (a sign of a bad I2C read)
    if (ir == prevIR && red == prevRed) { if (++sameCount > 20) { vit.reset(); fingerOn = false; lastIR = ir; } continue; }
    sameCount = 0; prevIR = ir; prevRed = red;
    if (ir == red && ir > 0) continue;
    lastIR = ir;
    bool on = ir > FINGER_IR;
    if (on && !fingerOn) vit.reset();          // finger just placed: start fresh
    fingerOn = on;
    if (fingerOn && vit.sample(ir, red)) {
      Serial.print("HR="); Serial.print(vit.bpm, 0);
      Serial.print(" bpm  SpO2~"); Serial.print(vit.spo2, 0);
      Serial.print(" %  quality="); Serial.println(vit.quality, 2);
    }
  }

  // Redraw once per second
  if (millis() - lastDrawMs > 1000) {
    lastDrawMs = millis();
    if (!fingerOn) {
      showValues(0, false, 0, false);
      status("Place your finger", C_YELLOW);
      Serial.print("No finger (IR="); Serial.print(lastIR); Serial.println(")");
      return;
    }
    bool hrOk = vit.nEst >= 3 && vit.bpm > 35 && vit.bpm < 200;
    bool oxOk = vit.nSpo2 >= 3;
    showValues((int)(vit.bpm + 0.5f), hrOk, (int)(vit.spo2 + 0.5f), oxOk);
    if (!hrOk) status(vit.count < VB_N ? "Measuring... keep still" : "Hold still...", C_WHITE);
    else if (vit.quality < 0.5f) status("Weak signal - keep still", C_YELLOW);
    else status("Reading OK", C_GREEN);
  }
}