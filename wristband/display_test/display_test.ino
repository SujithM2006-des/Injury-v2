// Display-only test for the 2.8" ILI9341 on ESP32-C3 SuperMini.
// Blinks the on-board LED (GPIO 8) so you can see the sketch is running.
// Cycles the screen through RED, GREEN, BLUE, WHITE, BLACK and a text screen.
#include <SPI.h>
#include <Adafruit_GFX.h>
#include <Adafruit_ILI9341.h>

#define TFT_SCK   4
#define TFT_MOSI  6
#define TFT_CS    7
#define TFT_DC    5
#define TFT_RST   10
#define LED_PIN   8          // on-board blue LED (on when LOW)
#define SPI_HZ    10000000   // 10 MHz: slower and more forgiving than 40 MHz

Adafruit_ILI9341 tft(TFT_CS, TFT_DC, TFT_RST);

const uint16_t C_BLACK = 0x0000, C_WHITE = 0xFFFF, C_RED = 0xF800,
               C_GREEN = 0x07E0, C_BLUE = 0x001F, C_YELLOW = 0xFFE0;

void blink(int times) {
  for (int i = 0; i < times; i++) {
    digitalWrite(LED_PIN, LOW);  delay(100);
    digitalWrite(LED_PIN, HIGH); delay(100);
  }
}

void showColour(const char* name, uint16_t colour) {
  Serial.print("Screen: "); Serial.println(name);
  tft.fillScreen(colour);
  blink(1);
  delay(1000);
}

void setup() {
  pinMode(LED_PIN, OUTPUT);
  digitalWrite(LED_PIN, HIGH);
  Serial.begin(115200);
  delay(1500);
  Serial.println();
  Serial.println("display_only test starting");
  blink(3);                                   // 3 quick blinks = sketch has started

  // Hard reset of the display
  pinMode(TFT_RST, OUTPUT);
  digitalWrite(TFT_RST, HIGH); delay(50);
  digitalWrite(TFT_RST, LOW);  delay(50);
  digitalWrite(TFT_RST, HIGH); delay(150);

  SPI.begin(TFT_SCK, -1, TFT_MOSI, TFT_CS);
  tft.begin(SPI_HZ);
  tft.setRotation(1);
  Serial.println("Display started (SCK 4, MOSI 6, CS 7, DC 5, RST 10)");
}

void loop() {
  showColour("RED", C_RED);
  showColour("GREEN", C_GREEN);
  showColour("BLUE", C_BLUE);
  showColour("WHITE", C_WHITE);
  showColour("BLACK", C_BLACK);

  Serial.println("Screen: TEXT");
  tft.fillScreen(C_BLACK);
  tft.setTextColor(C_YELLOW);
  tft.setTextSize(3);
  tft.setCursor(40, 80);
  tft.print("DISPLAY OK");
  tft.setTextSize(2);
  tft.setTextColor(C_WHITE);
  tft.setCursor(40, 130);
  tft.print("ESP32-C3 + ILI9341");
  blink(1);
  delay(2000);
}