import spidev
import time

# Open SPI bus
spi = spidev.SpiDev()
spi.open(0, 0)  # bus 0, device 0
spi.max_speed_hz = 1350000

# Function to read MCP3208 channel
def read_channel(channel):
    if channel < 0 or channel > 7:
        return -1

    cmd = 0b00000110 | ((channel & 0x04) >> 2)
    cmd2 = (channel & 0x03) << 6

    adc = spi.xfer2([cmd, cmd2, 0])

    value = ((adc[1] & 0x0F) << 8) | adc[2]
    return value

# Main loop
while True:
    pulse_value = read_channel(0)  # Pulse sensor connected to CH0
    print("Pulse Signal:", pulse_value)
    time.sleep(0.1)
