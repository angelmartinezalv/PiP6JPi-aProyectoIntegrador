/**
 * ============================================================
 *  DIAGNÓSTICO: BMP280 + DHT22 en ESP32
 *  Proyecto: proectointegrador
 * ============================================================
 *  Funciones incluidas:
 *    1. Escaneo I2C  → detecta dirección real del BMP280
 *    2. Init robusta → mensajes claros si falla begin()
 *    3. Loop simple  → delay(2000) para respetar el DHT22
 * ============================================================
 */

#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_BMP280.h>
#include <DHT.h>

// ── Pines ESP32 ──────────────────────────────────────────────
#define SDA_PIN     21
#define SCL_PIN     22
#define DHT_PIN     4       // Cambia al GPIO que uses para el DHT22
#define DHT_TYPE    DHT22

// ── Objetos ──────────────────────────────────────────────────
Adafruit_BMP280 bmp;        // usa Wire por defecto (I2C)
DHT             dht(DHT_PIN, DHT_TYPE);

// ── Flags de estado ──────────────────────────────────────────
bool bmpOK = false;
bool dhtOK = false;

// ────────────────────────────────────────────────────────────
//  1. ESCANEO I2C
//     Recorre todas las direcciones 0x01-0x7F y reporta
//     cuáles responden. El BMP280 debe aparecer en 0x76 o 0x77.
// ────────────────────────────────────────────────────────────
void scanI2C() {
    Serial.println("\n==============================");
    Serial.println("  ESCANEO DE BUS I2C");
    Serial.println("==============================");

    uint8_t deviceCount = 0;

    for (uint8_t addr = 1; addr < 127; addr++) {
        Wire.beginTransmission(addr);
        uint8_t error = Wire.endTransmission();

        if (error == 0) {
            Serial.print("  [OK] Dispositivo encontrado en 0x");
            if (addr < 16) Serial.print("0");
            Serial.print(addr, HEX);

            // Identificación de dispositivos comunes
            if (addr == 0x76 || addr == 0x77) {
                Serial.print("  <-- BMP280 / BME280 probable");
            } else if (addr == 0x3C || addr == 0x3D) {
                Serial.print("  <-- Pantalla OLED probable");
            } else if (addr == 0x68 || addr == 0x69) {
                Serial.print("  <-- MPU6050 / RTC probable");
            }
            Serial.println();
            deviceCount++;
        } else if (error == 4) {
            Serial.print("  [ERR] Error desconocido en 0x");
            if (addr < 16) Serial.print("0");
            Serial.println(addr, HEX);
        }
    }

    if (deviceCount == 0) {
        Serial.println("  *** Ningun dispositivo I2C encontrado ***");
        Serial.println("  Verifica el cableado SDA/SCL y alimentacion.");
    } else {
        Serial.print("  Total dispositivos encontrados: ");
        Serial.println(deviceCount);
    }

    Serial.println("==============================\n");
}

// ────────────────────────────────────────────────────────────
//  2. INICIALIZACIÓN ROBUSTA
// ────────────────────────────────────────────────────────────
void initBMP280() {
    Serial.println(">> Inicializando BMP280...");

    // Intenta primero 0x76, luego 0x77
    if (bmp.begin(0x76)) {
        Serial.println("   BMP280 encontrado en 0x76  [OK]");
        bmpOK = true;
    } else if (bmp.begin(0x77)) {
        Serial.println("   BMP280 encontrado en 0x77  [OK]");
        bmpOK = true;
    } else {
        Serial.println("   ERROR BMP280: no responde en 0x76 ni 0x77.");
        Serial.println("   Posibles causas:");
        Serial.println("     - Cable SDA/SCL invertido o suelto");
        Serial.println("     - Sensor sin alimentacion (3.3 V)");
        Serial.println("     - Direccion I2C diferente (ver escaneo)");
        Serial.println("     - Sensor defectuoso");
        bmpOK = false;
        return;
    }

    // Configuracion recomendada para lecturas estables
    bmp.setSampling(
        Adafruit_BMP280::MODE_NORMAL,
        Adafruit_BMP280::SAMPLING_X2,    // temperatura
        Adafruit_BMP280::SAMPLING_X16,   // presion
        Adafruit_BMP280::FILTER_X16,
        Adafruit_BMP280::STANDBY_MS_500
    );
    Serial.println("   BMP280 configurado correctamente.\n");
}

void initDHT22() {
    Serial.print(">> Inicializando DHT22 en GPIO ");
    Serial.println(DHT_PIN);
    dht.begin();

    // El DHT22 tarda ~2 s en estabilizarse
    delay(2000);

    float testHum  = dht.readHumidity();
    float testTemp = dht.readTemperature();

    if (isnan(testHum) || isnan(testTemp)) {
        Serial.println("   ERROR DHT22: lectura inicial invalida (NaN).");
        Serial.println("   Verifica el pin DATA y la resistencia pull-up (4.7 kΩ).");
        dhtOK = false;
    } else {
        Serial.println("   DHT22 respondiendo correctamente.  [OK]");
        dhtOK = true;
    }
}

// ────────────────────────────────────────────────────────────
//  SETUP
// ────────────────────────────────────────────────────────────
void setup() {
    Serial.begin(115200);
    delay(1500);   // Espera a que el monitor serie abra

    Serial.println("\n╔══════════════════════════════╗");
    Serial.println("║   ESP32 - Diagnostico Inicio  ║");
    Serial.println("╚══════════════════════════════╝");

    // Inicia bus I2C con pines explícitos
    Wire.begin(SDA_PIN, SCL_PIN);
    Serial.printf("Bus I2C iniciado  SDA=GPIO%d  SCL=GPIO%d\n\n", SDA_PIN, SCL_PIN);

    // 1. Escaneo I2C — úsalo para confirmar la dirección
    scanI2C();

    // 2. Init sensores
    initBMP280();
    initDHT22();

    // Resumen
    Serial.println("─────────────────────────────────");
    Serial.printf("BMP280 : %s\n", bmpOK ? "LISTO" : "FALLO");
    Serial.printf("DHT22  : %s\n", dhtOK ? "LISTO" : "FALLO");
    Serial.println("─────────────────────────────────\n");
}

// ────────────────────────────────────────────────────────────
//  3. LOOP CON DELAY(2000)
// ────────────────────────────────────────────────────────────
void loop() {
    Serial.println("── Lectura ──────────────────────");

    // ── BMP280 ──
    if (bmpOK) {
        float temp = bmp.readTemperature();    // °C
        float pres = bmp.readPressure() / 100.0F;  // hPa
        float alt  = bmp.readAltitude(1013.25F);   // m (presion al nivel del mar)

        Serial.printf("  BMP280 Temp     : %.2f °C\n",  temp);
        Serial.printf("  BMP280 Presion  : %.2f hPa\n", pres);
        Serial.printf("  BMP280 Altitud  : %.2f m\n",   alt);
    } else {
        Serial.println("  BMP280: sin datos (sensor no inicializado)");
    }

    // ── DHT22 ──
if (dhtOK) {
    float hum = dht.readHumidity();
    float temp = dht.readTemperature();

    if (!isnan(hum) && !isnan(temp)) {

        float pres = 0;
        float alt = 0;

        if (bmpOK) {
            pres = bmp.readPressure() / 100.0F;
            alt = bmp.readAltitude(1013.25F);
        }

        // Formato para Python
Serial.printf(
    "1,%.2f,%.2f,%.2f,%.2f\n",
    temp, pres, hum, alt
);
    } else {
        Serial.println("  DHT22: lectura invalida (NaN)");
    }
} else {
    Serial.println("  DHT22: sin datos (sensor no inicializado)");      
}  

    Serial.println();
    delay(2000);   // 2 s mínimo para el DHT22
}