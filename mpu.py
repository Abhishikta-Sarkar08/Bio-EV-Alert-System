import spidev
import time
import numpy as np

class MPU9250:
    def __init__(self, bus=0, device=0):
        self.spi = spidev.SpiDev()
        self.spi.open(bus, device)
        self.spi.max_speed_hz = 1000000 # 1MHz
        self.spi.mode = 0b11 # MPU-9250 supports SPI mode 3
        
        # Wake up the device (PWR_MGMT_1)
        self.write_register(0x6B, 0x00)
        time.sleep(0.1)
        # Enable SPI mode only (USER_CTRL)
        self.write_register(0x6A, 0x10)

    def write_register(self, reg, data):
        self.spi.xfer2([reg, data])

    def read_registers(self, reg, length):
        # Set MSB to 1 for Read operation
        data = self.spi.xfer2([reg | 0x80] + [0] * length)
        return data[1:]

    def get_data(self):
        # Read Accel (0x3B-0x40) and Gyro (0x43-0x48)
        raw = self.read_registers(0x3B, 14)
        
        # Convert to 16-bit integers
        vals = []
        for i in range(0, 14, 2):
            if i == 6: continue # Skip Temperature
            v = (raw[i] << 8) | raw[i+1]
            if v > 32767: v -= 65536
            vals.append(v)
            
        # Scaling (Default +/- 2g and +/- 250 deg/s)
        accel = np.array(vals[:3]) / 16384.0
        gyro = np.array(vals[3:]) / 131.0
        return accel, gyro

# --- Main Loop ---
try:
    imu = MPU9250()
    print("MPU-9250 SPI Initialized. Press Ctrl+C to stop.\n")
    print(f"{'Accel (g)':^20} | {'Gyro (deg/s)':^20}")
    
    while True:
        acc, gyr = imu.get_data()
        print(f"X:{acc[0]:.2f} Y:{acc[1]:.2f} Z:{acc[2]:.2f} | X:{gyr[0]:.1f} Y:{gyr[1]:.1f} Z:{gyr[2]:.1f}", end='\r')
        time.sleep(0.1)

except KeyboardInterrupt:
    print("\nStopped.")
