// New board test: display + DS18B20 temperature on the healthy ESP32-C3 SuperMini.
// 1) Shows a start-up screen (proves the display works)
// 2) Checks the DS18B20 line on GPIO 1 and explains any problem on screen
// 3) Shows smoothed skin temperature with SETTLING / SETTLED and a calibration offset
// Never connect anything to GPIO 9 or GPIO 2 (start-up pins).
#include <SPI.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <Adafruit_GFX.h>
#include <Adafruit_ILI9341.h>

// ===== Display pins =====
#define TFT_SCK   4
#define TFT_MOSI  6
#define TFT_CS    7
#define TFT_DC    5
#define TFT_RST   10
// ===== Temperature sensor =====
#define TEMP_PIN  1
#define LED_PIN   8   // on-board blue LED (on when LOW)

// Calibration: (real temperature) - (what this sensor shows). Example: thermometer 29.0, sensor 30.2 -> -1.2
const float TEMP_OFFSET = 0.0;

Adafruit_ILI9341 tft(TFT_CS, TFT_DC, TFT_RST);
OneWire oneWire(TEMP_PIN);
DallasTemperature temps(&oneWire);

const uint16_t C_BLACK = 0x0000, C_WHITE = 0xFFFF, C_RED = 0xF800, C_ORANGE = 0xFD20,
               C_GREY = 0x8410, C_NAVY = 0x000F, C_GREEN = 0x07E0, C_YELLOW = 0xFFE0;

int sensorCount = 0;
unsigned long lastRequestMs = 0;
bool waiting = false;

float recent[5];
int nRecent = 0, iRecent = 0;
float history[10];
int nHist = 0, iHist = 0;
int failsInRow = 0;

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
  centred("TEMPERATURE", 10, 2, C_WHITE, C_NAVY);
  centred("SKIN TEMPERATURE", 60, 2, C_GREY, C_BLACK);
}

void resetFilters() {
  nRecent = 0; iRecent = 0; nHist = 0; iHist = 0; failsInRow = 0;
}

// Looks for the sensor. If not found, explains why on screen.
bool findSensor() {
  pinMode(TEMP_PIN, INPUT_PULLUP);   // weak internal pull-up (helps if no 4.7k resistor)
  delay(20);
  if (digitalRead(TEMP_PIN) == LOW) {
    Serial.println("GPIO 1 is stuck LOW - DATA shorted to GND or sensor wired backwards");
    centred("DATA LINE STUCK LOW", 160, 2, C_RED, C_BLACK);
    centred("Check wiring / is it hot?", 190, 2, C_RED, C_BLACK);
    sensorCount = 0;
    return false;
  }
  temps.begin();
  sensorCount = temps.getDeviceCount();
  Serial.print("DS18B20 sensors found: "); Serial.println(sensorCount);
  if (sensorCount == 0) {
    centred("SENSOR NOT FOUND", 160, 2, C_RED, C_BLACK);
    centred("Check VDD 3V3 / GND / GPIO 1", 190, 2, C_YELLOW, C_BLACK);
    return false;
  }
  temps.setResolution(12);           // 0.0625 C steps
  temps.setWaitForConversion(false); // don't block the loop while measuring
  resetFilters();
  centred("", 160, 2, C_BLACK, C_BLACK);
  centred("Hold the sensor", 190, 2, C_YELLOW, C_BLACK);
  return true;
}

void setup() {
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, HIGH);
  Serial.begin(115200);
  delay(1500);
  Serial.println("new_board_test starting");

  SPI.begin(TFT_SCK, -1, TFT_MOSI, TFT_CS);
  tft.begin(40000000);
  tft.setRotation(1);

  // Start-up screen: proves the display works
  tft.fillScreen(C_NAVY);
  centred("NEW BOARD", 80, 4, C_WHITE, C_NAVY);
  centred("Display OK", 140, 2, C_GREEN, C_NAVY);
  for (int i = 0; i < 3; i++) { digitalWrite(LED_PIN, LOW); delay(150); digitalWrite(LED_PIN, HIGH); delay(150); }
  delay(1500);

  drawFrame();
  centred("Looking for sensor...", 190, 2, C_WHITE, C_BLACK);
  findSensor();
}

void loop() {
  // No sensor yet: look again every 3 s (fix wiring without resetting)
  if (sensorCount == 0) {
    delay(3000);
    findSensor();
    return;
  }

  // Start a measurement, collect it 800 ms later (12-bit takes 750 ms)
  if (!waiting && millis() - lastRequestMs > 1000) {
    temps.requestTemperatures();
    lastRequestMs = millis();
    waiting = true;
  }
  if (!waiting || millis() - lastRequestMs < 800) return;
  waiting = false;

  float c = temps.getTempCByIndex(0);
  if (c == DEVICE_DISCONNECTED_C || c == 85.0f || c < -50 || c > 120) {
    failsInRow++;
    Serial.print("Ignored reading: "); Serial.println(c, 2);
    if (failsInRow >= 5) {
      Serial.println("Read failed 5 times - searching again");
      centred("READ FAILED", 190, 2, C_RED, C_BLACK);
      sensorCount = 0;
    }
    return;
  }
  failsInRow = 0;
  c += TEMP_OFFSET;

  // Smooth: average of the last 5 readings
  recent[iRecent] = c; iRecent = (iRecent + 1) % 5; if (nRecent < 5) nRecent++;
  float avg = 0;
  for (int i = 0; i < nRecent; i++) avg += recent[i];
  avg /= nRecent;

  // Settled = smoothed value changed less than 0.15 C over the last 10 s
  history[iHist] = avg; iHist = (iHist + 1) % 10; if (nHist < 10) nHist++;
  bool stable = false;
  if (nHist == 10) {
    float lo = history[0], hi = history[0];
    for (int i = 1; i < 10; i++) { if (history[i] < lo) lo = history[i]; if (history[i] > hi) hi = history[i]; }
    stable = (hi - lo) < 0.15f;
  }

  Serial.print("Temperature: "); Serial.print(c, 2);
  Serial.print(" C   Smoothed: "); Serial.print(avg, 2);
  Serial.println(stable ? " C   SETTLED" : " C   settling");

  char t[16];
  snprintf(t, sizeof(t), "%.1f C", avg);
  uint16_t colour = avg < 30 ? C_WHITE : (avg < 37.5 ? C_GREEN : (avg < 38.5 ? C_ORANGE : C_RED));
  centred(t, 100, 6, colour, C_BLACK);
  centred("", 160, 2, C_BLACK, C_BLACK);
  if (!stable)         centred("Settling... hold still", 190, 2, C_YELLOW, C_BLACK);
  else if (avg < 30)   centred("Hold the sensor", 190, 2, C_YELLOW, C_BLACK);
  else if (avg < 37.5) centred("Normal", 190, 2, C_GREEN, C_BLACK);
  else if (avg < 38.5) centred("Warm", 190, 2, C_ORANGE, C_BLACK);
  else                 centred("High", 190, 2, C_RED, C_BLACK);
}