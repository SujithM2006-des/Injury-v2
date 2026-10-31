// Board test for a new ESP32-C3: prints to the Serial Monitor and blinks the on-board LED.
// Many ESP32-C3 SuperMini boards have their small LED on GPIO 8 (it lights when the pin is LOW).
const int LED_PIN = 8;

void setup() {
  Serial.begin(115200);
  delay(1000);
  pinMode(LED_PIN, OUTPUT);
  Serial.println("ESP32-C3 board test OK");
  Serial.print("Chip model: ");
  Serial.println(ESP.getChipModel());
  Serial.print("CPU MHz: ");
  Serial.println(ESP.getCpuFreqMHz());
}

void loop() {
  digitalWrite(LED_PIN, LOW);
  Serial.println("LED ON");
  delay(500);
  digitalWrite(LED_PIN, HIGH);
  Serial.println("LED OFF");
  delay(500);
}