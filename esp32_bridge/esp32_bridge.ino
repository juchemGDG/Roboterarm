#include <ArduinoJson.h>
#include <WiFi.h>
#include <esp_now.h>

struct MotorCommandPacket {
  uint8_t motorId;
  float targetDeg;
  uint16_t durationMs;
  uint32_t sequence;
};

constexpr uint8_t MOTOR_COUNT = 4;

const uint8_t PEER_MACS[MOTOR_COUNT][6] = {
  {0x24, 0x6F, 0x28, 0x00, 0x00, 0x01},
  {0x24, 0x6F, 0x28, 0x00, 0x00, 0x02},
  {0x24, 0x6F, 0x28, 0x00, 0x00, 0x03},
  {0x24, 0x6F, 0x28, 0x00, 0x00, 0x04},
};

uint32_t sequenceCounter = 1;

void onEspNowSent(const wifi_tx_info_t *info, esp_now_send_status_t status) {
  if (info == nullptr) {
    return;
  }

  char macText[18] = {};
  snprintf(
      macText,
      sizeof(macText),
      "%02X:%02X:%02X:%02X:%02X:%02X",
      info->des_addr[0],
      info->des_addr[1],
      info->des_addr[2],
      info->des_addr[3],
      info->des_addr[4],
      info->des_addr[5]);

  Serial.print("{\"status\":\"tx\",\"mac\":\"");
  Serial.print(macText);
  Serial.print("\",\"result\":\"");
  Serial.print(status == ESP_NOW_SEND_SUCCESS ? "ok" : "fail");
  Serial.println("\"}");
}

bool ensurePeer(const uint8_t *macAddress) {
  if (esp_now_is_peer_exist(macAddress)) {
    return true;
  }

  esp_now_peer_info_t peerInfo = {};
  memcpy(peerInfo.peer_addr, macAddress, 6);
  peerInfo.channel = 0;
  peerInfo.encrypt = false;
  return esp_now_add_peer(&peerInfo) == ESP_OK;
}

bool sendMotorPacket(uint8_t peerIndex, uint8_t motorId, float targetDeg, uint16_t durationMs) {
  if (peerIndex >= MOTOR_COUNT) {
    return false;
  }

  MotorCommandPacket packet = {};
  packet.motorId = motorId;
  packet.targetDeg = targetDeg;
  packet.durationMs = durationMs;
  packet.sequence = sequenceCounter;

  esp_err_t result = esp_now_send(PEER_MACS[peerIndex], reinterpret_cast<uint8_t *>(&packet), sizeof(packet));
  return result == ESP_OK;
}

bool forwardMotorCommand(JsonObject motor, uint16_t &forwarded, uint16_t &invalid, uint16_t &failed) {
  uint8_t motorId = motor["id"] | 0;
  float targetDeg = motor["target_deg"] | 0.0f;
  uint16_t durationMs = motor["duration_ms"] | 0;

  if (motorId < 1 || motorId > MOTOR_COUNT) {
    invalid++;
    return false;
  }

  if (sendMotorPacket(motorId - 1, motorId, targetDeg, durationMs)) {
    forwarded++;
    return true;
  }

  failed++;
  return false;
}

void setup() {
  Serial.begin(115200);
  WiFi.mode(WIFI_STA);

  if (esp_now_init() != ESP_OK) {
    Serial.println("{\"status\":\"error\",\"message\":\"esp_now_init fehlgeschlagen\"}");
    return;
  }

  esp_now_register_send_cb(onEspNowSent);

  for (uint8_t index = 0; index < MOTOR_COUNT; ++index) {
    if (!ensurePeer(PEER_MACS[index])) {
      Serial.print("{\"status\":\"error\",\"message\":\"Peer konnte nicht hinzugefuegt werden: ");
      Serial.print(index + 1);
      Serial.println("\"}");
    }
  }

  Serial.println("{\"status\":\"ready\",\"message\":\"ESP32 Bridge bereit\"}");
}

void loop() {
  if (!Serial.available()) {
    return;
  }

  String input = Serial.readStringUntil('\n');
  input.trim();
  if (input.isEmpty()) {
    return;
  }

  JsonDocument document;
  DeserializationError error = deserializeJson(document, input);
  if (error) {
    Serial.print("{\"status\":\"error\",\"message\":\"JSON ungueltig: ");
    Serial.print(error.c_str());
    Serial.println("\"}");
    return;
  }

  if (document["command"] != "move") {
    Serial.println("{\"status\":\"error\",\"message\":\"Unbekannter Befehl\"}");
    return;
  }

  JsonArray motors = document["motors"].as<JsonArray>();
  if (motors.isNull() || motors.size() == 0) {
    Serial.println("{\"status\":\"error\",\"message\":\"Keine Motor-Daten enthalten\"}");
    return;
  }

  uint16_t forwarded = 0;
  uint16_t invalid = 0;
  uint16_t failed = 0;
  for (JsonObject motor : motors) {
    forwardMotorCommand(motor, forwarded, invalid, failed);
  }

  Serial.print("{\"status\":\"ok\",\"sequence\":");
  Serial.print(sequenceCounter);
  Serial.print(",\"forwarded\":");
  Serial.print(forwarded);
  Serial.print(",\"invalid\":");
  Serial.print(invalid);
  Serial.print(",\"failed\":");
  Serial.print(failed);
  Serial.println("}");
  sequenceCounter++;
}