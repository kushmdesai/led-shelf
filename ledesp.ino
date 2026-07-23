#include <ESP8266WiFi.h>
#include <PubSubClient.h>
#include <Adafruit_NeoPixel.h>
#include <cmath>
#include <algorithm>

// ===== WiFi =====
#define WIFI_SSID     "VIRGIN478"
#define WIFI_PASSWORD "4C6F551CC2AE"

IPAddress local_IP(192, 168, 2, 50);
IPAddress gateway(192, 168, 2, 1);
IPAddress subnet(255, 255, 255, 0);
IPAddress dns(192, 168, 2, 1);

// ===== MQTT =====
#define MQTT_BROKER "192.168.2.15"
#define MQTT_PORT   1883
#define MQTT_ID     "ledesp"

// ===== Hardware =====
#define LED_PIN    2
#define LED_COUNT  200
#define RELAY_PIN  0

// ===== Global state =====
int   current_r         = 255;
int   current_g         = 255;
int   current_b         = 255;
float current_brightness = 1.0f;
bool  power_on          = false;
String currentEffect    = "none";
int   effectSpeed       = 50;

// Effect internal state
unsigned long lastStep = 0;
int           effectStep = 0;
float         breatheVal = 0.0f;

// ===== RGB struct for Kelvin conversion =====
struct RGB { float r, g, b; };

// ===== Objects =====
WiFiClient        wifiClient;
PubSubClient      mqtt(wifiClient);
Adafruit_NeoPixel strip(LED_COUNT, LED_PIN, NEO_GRB + NEO_KHZ800);

// =============================================
// HELPERS
// =============================================

// Map speed (1-100) to a millisecond delay (fast=low ms, slow=high ms)
int speedToDelay(int speed, int minMs = 5, int maxMs = 200) {
  return map(speed, 1, 100, maxMs, minMs);
}

void applyColor() {
  strip.fill(strip.Color(
    current_r * current_brightness,
    current_g * current_brightness,
    current_b * current_brightness
  ));
  strip.show();
}

void clearStrip() {
  strip.clear();
  strip.show();
}

// Wheel: input 0-255, output a colour cycling R→G→B
uint32_t wheel(byte pos) {
  pos = 255 - pos;
  if (pos < 85)  return strip.Color(255 - pos * 3, 0, pos * 3);
  if (pos < 170) { pos -= 85;  return strip.Color(0, pos * 3, 255 - pos * 3); }
  pos -= 170;
  return strip.Color(pos * 3, 255 - pos * 3, 0);
}

// =============================================
// KELVIN → RGB
// =============================================
RGB KelvinToRGB(float kelvin) {
  kelvin = std::clamp(kelvin, 1000.0f, 40000.0f);
  float temp = kelvin / 100.0f;
  float red, green, blue;

  red   = (temp <= 66.0f) ? 1.0f
        : std::clamp(329.698727446f * std::pow(temp - 60.0f, -0.1332047592f) / 255.0f, 0.0f, 1.0f);

  green = (temp <= 66.0f)
        ? std::clamp((99.4708025861f * std::log(temp) - 161.119563425f) / 255.0f, 0.0f, 1.0f)
        : std::clamp(288.1221695283f * std::pow(temp - 60.0f, -0.0755148492f) / 255.0f, 0.0f, 1.0f);

  blue  = (temp >= 66.0f) ? 1.0f
        : (temp <= 19.0f) ? 0.0f
        : std::clamp((138.5177312231f * std::log(temp - 10.0f) - 305.0447927307f) / 255.0f, 0.0f, 1.0f);

  return RGB{ red * 255, green * 255, blue * 255 };
}

// =============================================
// EFFECTS  (all non-blocking)
// =============================================

void effect_rainbow() {
  if (millis() - lastStep < speedToDelay(effectSpeed)) return;
  lastStep = millis();
  for (int i = 0; i < LED_COUNT; i++) {
    strip.setPixelColor(i, wheel((i + effectStep) & 255));
  }
  strip.show();
  effectStep = (effectStep + 1) % 256;
}

void effect_rainbow_wave() {
  if (millis() - lastStep < speedToDelay(effectSpeed)) return;
  lastStep = millis();
  for (int i = 0; i < LED_COUNT; i++) {
    strip.setPixelColor(i, wheel(((i * 256 / LED_COUNT) + effectStep) & 255));
  }
  strip.show();
  effectStep = (effectStep + 1) % 256;
}

void effect_breathe() {
  if (millis() - lastStep < speedToDelay(effectSpeed, 10, 30)) return;
  lastStep = millis();
  float b = (sin(breatheVal) + 1.0f) / 2.0f;
  strip.fill(strip.Color(
    current_r * b * current_brightness,
    current_g * b * current_brightness,
    current_b * b * current_brightness
  ));
  strip.show();
  breatheVal += 0.05f;
  if (breatheVal > TWO_PI) breatheVal = 0.0f;
}

void effect_color_wipe() {
  if (millis() - lastStep < speedToDelay(effectSpeed)) return;
  lastStep = millis();
  if (effectStep < LED_COUNT) {
    strip.setPixelColor(effectStep, strip.Color(
      current_r * current_brightness,
      current_g * current_brightness,
      current_b * current_brightness
    ));
    strip.show();
    effectStep++;
  } else {
    // wipe back to black
    if (effectStep < LED_COUNT * 2) {
      strip.setPixelColor(effectStep - LED_COUNT, 0);
      strip.show();
      effectStep++;
    } else {
      effectStep = 0;
    }
  }
}

void effect_theater_chase() {
  if (millis() - lastStep < speedToDelay(effectSpeed)) return;
  lastStep = millis();
  strip.clear();
  for (int i = effectStep; i < LED_COUNT; i += 3) {
    strip.setPixelColor(i, strip.Color(
      current_r * current_brightness,
      current_g * current_brightness,
      current_b * current_brightness
    ));
  }
  strip.show();
  effectStep = (effectStep + 1) % 3;
}

void effect_twinkle() {
  if (millis() - lastStep < speedToDelay(effectSpeed)) return;
  lastStep = millis();
  int led = random(LED_COUNT);
  strip.clear();
  strip.setPixelColor(led, strip.Color(
    current_r * current_brightness,
    current_g * current_brightness,
    current_b * current_brightness
  ));
  strip.show();
}

void effect_fire() {
  if (millis() - lastStep < speedToDelay(effectSpeed, 10, 80)) return;
  lastStep = millis();
  for (int i = 0; i < LED_COUNT; i++) {
    int flicker = random(100, 255);
    int r = min(255, (int)(flicker * current_brightness));
    int g = min(255, (int)(flicker * 0.3f * current_brightness));
    strip.setPixelColor(i, strip.Color(r, g, 0));
  }
  strip.show();
}

void effect_meteor() {
  if (millis() - lastStep < speedToDelay(effectSpeed)) return;
  lastStep = millis();
  // Fade all LEDs slightly
  for (int i = 0; i < LED_COUNT; i++) {
    uint32_t c = strip.getPixelColor(i);
    uint8_t r = (c >> 16) & 0xFF;
    uint8_t g = (c >> 8)  & 0xFF;
    uint8_t b =  c        & 0xFF;
    strip.setPixelColor(i, strip.Color(r * 0.7, g * 0.7, b * 0.7));
  }
  // Draw meteor head
  int pos = effectStep % LED_COUNT;
  for (int j = 0; j < 5 && pos - j >= 0; j++) {
    float fade = 1.0f - (j / 5.0f);
    strip.setPixelColor(pos - j, strip.Color(
      current_r * fade * current_brightness,
      current_g * fade * current_brightness,
      current_b * fade * current_brightness
    ));
  }
  strip.show();
  effectStep++;
  if (effectStep >= LED_COUNT + 5) effectStep = 0;
}

void effect_color_cycle() {
  if (millis() - lastStep < speedToDelay(effectSpeed, 20, 500)) return;
  lastStep = millis();
  strip.fill(wheel(effectStep & 255));
  strip.show();
  effectStep = (effectStep + 1) % 256;
}

void effect_strobe() {
  if (millis() - lastStep < speedToDelay(effectSpeed, 20, 300)) return;
  lastStep = millis();
  if (effectStep % 2 == 0) {
    strip.fill(strip.Color(
      current_r * current_brightness,
      current_g * current_brightness,
      current_b * current_brightness
    ));
  } else {
    strip.clear();
  }
  strip.show();
  effectStep++;
}

void effect_bouncing_ball() {
  if (millis() - lastStep < speedToDelay(effectSpeed)) return;
  lastStep = millis();
  static int pos = 0;
  static int dir = 1;
  strip.clear();
  strip.setPixelColor(pos, strip.Color(
    current_r * current_brightness,
    current_g * current_brightness,
    current_b * current_brightness
  ));
  strip.show();
  pos += dir;
  if (pos >= LED_COUNT - 1 || pos <= 0) dir = -dir;
}

void effect_running_lights() {
  if (millis() - lastStep < speedToDelay(effectSpeed)) return;
  lastStep = millis();
  for (int i = 0; i < LED_COUNT; i++) {
    float wave = (sin((i + effectStep) * 0.2f) + 1.0f) / 2.0f;
    strip.setPixelColor(i, strip.Color(
      current_r * wave * current_brightness,
      current_g * wave * current_brightness,
      current_b * wave * current_brightness
    ));
  }
  strip.show();
  effectStep++;
}

// =============================================
// EFFECT DISPATCHER
// =============================================
void runEffect() {
  if (currentEffect == "rainbow")        effect_rainbow();
  else if (currentEffect == "rainbow_wave")   effect_rainbow_wave();
  else if (currentEffect == "breathe")        effect_breathe();
  else if (currentEffect == "color_wipe")     effect_color_wipe();
  else if (currentEffect == "theater_chase")  effect_theater_chase();
  else if (currentEffect == "twinkle")        effect_twinkle();
  else if (currentEffect == "fire")           effect_fire();
  else if (currentEffect == "meteor")         effect_meteor();
  else if (currentEffect == "color_cycle")    effect_color_cycle();
  else if (currentEffect == "strobe")         effect_strobe();
  else if (currentEffect == "bouncing_ball")  effect_bouncing_ball();
  else if (currentEffect == "running_lights") effect_running_lights();
}

// =============================================
// MQTT CALLBACK
// =============================================
void onMessage(char* topic, byte* payload, unsigned int length) {
  String message = String((char*)payload).substring(0, length);
  String t = String(topic);
  Serial.println("Topic: " + t + " | Message: " + message);

  if (t == "ledshelf/power") {
    if (message == "on") {
      power_on = true;
      digitalWrite(RELAY_PIN, HIGH);
      if (currentEffect == "none") applyColor();
    } else {
      power_on = false;
      currentEffect = "none";
      clearStrip();
      digitalWrite(RELAY_PIN, LOW);
    }

  } else if (t == "ledshelf/brightness") {
    current_brightness = message.toInt() / 100.0f;
    if (power_on && currentEffect == "none") applyColor();

  } else if (t == "ledshelf/color") {
    int c1 = message.indexOf(',');
    int c2 = message.lastIndexOf(',');
    current_r = message.substring(0, c1).toInt();
    current_g = message.substring(c1 + 1, c2).toInt();
    current_b = message.substring(c2 + 1).toInt();
    if (power_on && currentEffect == "none") applyColor();

  } else if (t == "ledshelf/whitebalance") {
    RGB rgb = KelvinToRGB(message.toInt());
    current_r = rgb.r;
    current_g = rgb.g;
    current_b = rgb.b;
    if (power_on && currentEffect == "none") applyColor();

  } else if (t == "ledshelf/effect") {
    currentEffect = message;
    effectStep    = 0;
    breatheVal    = 0.0f;
    if (message == "none" && power_on) applyColor();
    if (message == "none" && !power_on) clearStrip();

  } else if (t == "ledshelf/speed") {
    effectSpeed = message.toInt();
  }
}

// =============================================
// WIFI & MQTT
// =============================================
void connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.setSleepMode(WIFI_NONE_SLEEP);
  WiFi.persistent(false);
  WiFi.config(local_IP, gateway, subnet, dns);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("Connecting WiFi");
  while (WiFi.status() != WL_CONNECTED) { delay(500); Serial.print("."); }
  Serial.println("\nWiFi connected — " + WiFi.localIP().toString());
}

void connectMQTT() {
  while (!mqtt.connected()) {
    Serial.print("Connecting MQTT...");
    if (mqtt.connect(MQTT_ID, "ledesp", "ledesp")) {
      Serial.println("connected");
      mqtt.subscribe("ledshelf/power");
      mqtt.subscribe("ledshelf/brightness");
      mqtt.subscribe("ledshelf/color");
      mqtt.subscribe("ledshelf/whitebalance");
      mqtt.subscribe("ledshelf/effect");
      mqtt.subscribe("ledshelf/speed");
    } else {
      Serial.print("failed rc="); Serial.println(mqtt.state());
      delay(2000);
    }
  }
}

// =============================================
// SETUP & LOOP
// =============================================
void setup() {
  Serial.begin(115200);

  pinMode(RELAY_PIN, OUTPUT);
  digitalWrite(RELAY_PIN, LOW);

  strip.begin();
  strip.setBrightness(255);
  strip.show();

  connectWiFi();
  mqtt.setServer(MQTT_BROKER, MQTT_PORT);
  mqtt.setCallback(onMessage);
  connectMQTT();
}

void loop() {
  if (!mqtt.connected()) connectMQTT();
  mqtt.loop();
  if (power_on) runEffect();
}
