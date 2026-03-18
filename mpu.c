#include <Wire.h>

#define MPU9255_ADDR 0x68

int16_t ax, ay, az;
int16_t gx, gy, gz;
int16_t temp;

void setup() {
  Serial.begin(9600);
  Wire.begin();

  // Wake up MPU9255
  Wire.beginTransmission(MPU9255_ADDR);
  Wire.write(0x6B);  
  Wire.write(0x00);  
  Wire.endTransmission(true);
}

void loop() {

  // Request accel, temp, gyro data
  Wire.beginTransmission(MPU9255_ADDR);
  Wire.write(0x3B);
  Wire.endTransmission(false);
  Wire.requestFrom(MPU9255_ADDR, 14, true);

  ax = Wire.read() << 8 | Wire.read();
  ay = Wire.read() << 8 | Wire.read();
  az = Wire.read() << 8 | Wire.read();

  temp = Wire.read() << 8 | Wire.read();

  gx = Wire.read() << 8 | Wire.read();
  gy = Wire.read() << 8 | Wire.read();
  gz = Wire.read() << 8 | Wire.read();

  Serial.print("AX: "); Serial.print(ax);
  Serial.print(" AY: "); Serial.print(ay);
  Serial.print(" AZ: "); Serial.print(az);

  Serial.print(" | GX: "); Serial.print(gx);
  Serial.print(" GY: "); Serial.print(gy);
  Serial.print(" GZ: "); Serial.print(gz);

  Serial.print(" | Temp: ");
  Serial.println(temp / 333.87 + 21.0);

  delay(500);
}
