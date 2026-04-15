#!/usr/bin/env python3
"""
Smart Safety & Accident Detection System — Raspberry Pi 5
==========================================================
Sensors  : HC-SR04 (ultrasonic), MPU9250 (gyro+accel, I2C), Pulse sensor (SPI/ADC)
Outputs  : LED, Buzzer, SSD1306 OLED (I2C)
Camera   : Pi Camera via rpicam-still  →  HTTP POST to server
Server   : sends back "Pothole has been detected." message
"""

import io
import math
import subprocess
import threading
import time

import requests
import smbus2
import spidev
from gpiozero import Buzzer, DistanceSensor, LED
from luma.core.interface.serial import i2c as luma_i2c
from luma.core.render import canvas
from luma.oled.device import ssd1306
from PIL import Image, ImageFont

# ──────────────────────────────────────────────────────────────────
#  CONFIGURATION  ← edit the values in this block
# ──────────────────────────────────────────────────────────────────

SERVER_IP   = "192.168.X.X"   # ← set your server IP here
SERVER_PORT = 5000             # ← set your server port here

# GPIO pins
LED_PIN     = 17
BUZZER_PIN  = 26
TRIG_PIN    = 23
ECHO_PIN    = 24

# I2C
MPU9250_ADDR   = 0x68   # AD0 low → 0x68;  AD0 high → 0x69
I2C_BUS        = 1
OLED_I2C_PORT  = 1
OLED_I2C_ADDR  = 0x3C  # most SSD1306 breakouts; try 0x3D if 0x3C doesn't work

# SPI (pulse sensor via MCP3008 ADC)
SPI_BUS     = 0
SPI_DEVICE  = 0
PULSE_CH    = 0   # MCP3008 channel (0-7) the pulse sensor is wired to

# Distance thresholds (cm)
DIST_CLOSE     = 60
DIST_STOP      = 40
DIST_COLLISION = 15

# Accident-detection thresholds
GYRO_FALL_DEG          = 70    # tilt from vertical that counts as "fallen"
ACCEL_IMPACT_G         = 1.8   # g-force delta above which an impact is logged
ACCEL_REST_G           = 0.15  # g-force deviation from 1 g counted as "at rest"
ACCEL_REST_TICKS_NEED  = 20    # consecutive ~50 ms ticks at rest = confirmed rest
PULSE_LOSS_TIMEOUT_S   = 5     # seconds without a valid SPI reading → no-pulse

# Camera
CAPTURE_INTERVAL_S = 2   # how often to snap and upload (seconds)

# ──────────────────────────────────────────────────────────────────
#  SHARED STATE  (all fields accessed under state_lock)
# ──────────────────────────────────────────────────────────────────

state = {
    # sensor readings
    "distance_cm"        : 999.0,
    "gyro_tilt_deg"      : 0.0,
    "accel_mag_g"        : 1.0,
    "pulse_bpm"          : 0.0,
    "last_pulse_time"    : time.time(),

    # derived accident flags
    "accel_impact_seen"  : False,
    "accel_rest_seen"    : False,

    # display / notification
    "server_message"     : "",
    "accident_confirmed" : False,

    # LED state management
    "led_state"          : "off",   # "off" | "on" | "blink_fast" | "blink_slow"
}
state_lock = threading.Lock()

# ──────────────────────────────────────────────────────────────────
#  HARDWARE INIT
# ──────────────────────────────────────────────────────────────────

led      = LED(LED_PIN)
buzzer   = Buzzer(BUZZER_PIN)
ultrasonic = DistanceSensor(echo=ECHO_PIN, trigger=TRIG_PIN, max_distance=3)

oled_serial = luma_i2c(port=OLED_I2C_PORT, address=OLED_I2C_ADDR)
oled        = ssd1306(oled_serial)

i2c_bus = smbus2.SMBus(I2C_BUS)

spi = spidev.SpiDev()
spi.open(SPI_BUS, SPI_DEVICE)
spi.max_speed_hz = 1_350_000

# ──────────────────────────────────────────────────────────────────
#  MPU9250 HELPERS
# ──────────────────────────────────────────────────────────────────
# Register map
_PWR_MGMT_1  = 0x6B
_ACCEL_CFG   = 0x1C   # ±2 g  → 0x00
_GYRO_CFG    = 0x1B   # ±250 °/s → 0x00
_ACCEL_XOUT  = 0x3B
_GYRO_XOUT   = 0x43
_ACCEL_SCALE = 16384.0   # LSB/g  for ±2 g
_GYRO_SCALE  = 131.0     # LSB/(°/s) for ±250 °/s

def _mpu_init():
    i2c_bus.write_byte_data(MPU9250_ADDR, _PWR_MGMT_1, 0x00)   # wake up
    i2c_bus.write_byte_data(MPU9250_ADDR, _ACCEL_CFG, 0x00)
    i2c_bus.write_byte_data(MPU9250_ADDR, _GYRO_CFG,  0x00)
    time.sleep(0.1)

def _read_word_2c(reg: int) -> int:
    hi  = i2c_bus.read_byte_data(MPU9250_ADDR, reg)
    lo  = i2c_bus.read_byte_data(MPU9250_ADDR, reg + 1)
    val = (hi << 8) | lo
    return val - 0x10000 if val >= 0x8000 else val

def _read_mpu9250():
    """Returns ((ax,ay,az) in g, (gx,gy,gz) in °/s)."""
    ax = _read_word_2c(_ACCEL_XOUT)     / _ACCEL_SCALE
    ay = _read_word_2c(_ACCEL_XOUT + 2) / _ACCEL_SCALE
    az = _read_word_2c(_ACCEL_XOUT + 4) / _ACCEL_SCALE
    gx = _read_word_2c(_GYRO_XOUT)      / _GYRO_SCALE
    gy = _read_word_2c(_GYRO_XOUT + 2)  / _GYRO_SCALE
    gz = _read_word_2c(_GYRO_XOUT + 4)  / _GYRO_SCALE
    return (ax, ay, az), (gx, gy, gz)

# ──────────────────────────────────────────────────────────────────
#  MCP3008 SPI ADC HELPER
# ──────────────────────────────────────────────────────────────────

def _read_adc(channel: int) -> int:
    """Read 10-bit value (0–1023) from MCP3008 ADC channel."""
    assert 0 <= channel <= 7
    reply = spi.xfer2([1, (8 + channel) << 4, 0])
    return ((reply[1] & 3) << 8) | reply[2]

# ──────────────────────────────────────────────────────────────────
#  OLED DISPLAY HELPER
# ──────────────────────────────────────────────────────────────────

_FONT = ImageFont.load_default()   # built-in monospace font (no file needed)

def oled_show(text: str):
    """Display up to 4 lines on the SSD1306; newlines or long text auto-wraps."""
    lines = []
    for raw_line in text.split("\n"):
        words, cur = raw_line.split(), ""
        for w in words:
            candidate = (cur + " " + w).strip()
            # approx character width of default font is 6 px
            if len(candidate) * 6 < oled.width - 4:
                cur = candidate
            else:
                if cur:
                    lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
    lines = lines[:4]

    with canvas(oled) as draw:
        draw.rectangle(oled.bounding_box, fill="black")
        for i, line in enumerate(lines):
            draw.text((2, 2 + i * 15), line, fill="white", font=_FONT)

# ──────────────────────────────────────────────────────────────────
#  LED MANAGER THREAD
#  Reads "led_state" from shared state and drives the LED.
#  Having one dedicated thread means no other thread needs to call
#  led.blink() directly — preventing concurrent blink conflicts.
# ──────────────────────────────────────────────────────────────────

def led_manager():
    current = "off"
    blink_tick = False

    while True:
        with state_lock:
            desired = state["led_state"]

        if desired != current:
            led.off()
            current = desired
            blink_tick = False

        if current == "off":
            led.off()
        elif current == "on":
            led.on()
        elif current == "blink_slow":
            blink_tick = not blink_tick
            led.on() if blink_tick else led.off()
            time.sleep(0.5)
            continue
        elif current == "blink_fast":
            blink_tick = not blink_tick
            led.on() if blink_tick else led.off()
            time.sleep(0.15)
            continue

        time.sleep(0.05)

# ──────────────────────────────────────────────────────────────────
#  SENSOR THREADS
# ──────────────────────────────────────────────────────────────────

def ultrasonic_thread():
    """Polls HC-SR04 via gpiozero; updates distance_cm in shared state."""
    while True:
        try:
            dist_cm = (ultrasonic.distance or 3.0) * 100.0
        except Exception:
            dist_cm = 999.0
        with state_lock:
            state["distance_cm"] = dist_cm
        time.sleep(0.05)   # 20 Hz


def mpu9250_thread():
    """
    Reads accelerometer + gyroscope from MPU9250.

    Tilt detection
    ──────────────
    We compute the angle between the Z-axis and the gravity vector
    using atan2.  When the board (vehicle) is upright the tilt is ≈0°.
    A complete fall → tilt approaching 90°.

    Impact + rest detection
    ───────────────────────
    Magnitude of acceleration = sqrt(ax²+ay²+az²).
    At rest = ~1 g.  A crash → sudden spike well above 1 g,
    followed by the sensor settling near 0 g (free-fall immediately
    post-crash) or returning to 1 g (resting on ground).
    We flag "rest" when mag stays within ACCEL_REST_G of 1.0 for
    ACCEL_REST_TICKS_NEED consecutive ticks.
    """
    prev_mag    = 1.0
    rest_ticks  = 0
    impact_seen = False

    while True:
        try:
            (ax, ay, az), (gx, gy, gz) = _read_mpu9250()
        except Exception as e:
            print(f"[MPU9250] read error: {e}")
            time.sleep(0.1)
            continue

        # tilt = angle from the Z-axis (upright = 0 °)
        tilt = math.degrees(math.atan2(math.sqrt(ax**2 + ay**2), abs(az)))
        mag  = math.sqrt(ax**2 + ay**2 + az**2)

        with state_lock:
            state["gyro_tilt_deg"] = tilt
            state["accel_mag_g"]   = mag

            # ── impact detection ──
            if (mag - prev_mag) > ACCEL_IMPACT_G:
                state["accel_impact_seen"] = True
                impact_seen = True
                rest_ticks  = 0

            # ── rest detection (only relevant after an impact) ──
            if impact_seen:
                if abs(mag - 1.0) < ACCEL_REST_G:
                    rest_ticks += 1
                    if rest_ticks >= ACCEL_REST_TICKS_NEED:
                        state["accel_rest_seen"] = True
                else:
                    rest_ticks = 0

        prev_mag = mag
        time.sleep(0.05)   # 20 Hz


def pulse_thread():
    """
    Reads heartbeat/pulse sensor through MCP3008 ADC on SPI.

    BPM estimation
    ──────────────
    We keep a rolling 10-second buffer of raw ADC values.
    Peaks above 120% of the running mean are counted as heartbeats.
    If the peak rate is in the plausible 40–200 BPM range we report it
    and reset the "last valid time" stamp.  If nothing valid arrives
    for PULSE_LOSS_TIMEOUT_S seconds the "no pulse" flag triggers.
    """
    SAMPLE_RATE = 20   # Hz
    BUF_SECS    = 10
    buf         = []

    while True:
        val = _read_adc(PULSE_CH)
        buf.append(val)
        if len(buf) > SAMPLE_RATE * BUF_SECS:
            buf.pop(0)

        bpm = 0.0
        if len(buf) >= SAMPLE_RATE * 2:
            mean  = sum(buf) / len(buf)
            peaks = 0
            for i in range(1, len(buf) - 1):
                if buf[i] > mean * 1.2 and buf[i] > buf[i-1] and buf[i] > buf[i+1]:
                    peaks += 1
            duration = len(buf) / SAMPLE_RATE
            bpm_raw  = (peaks / duration) * 60.0
            if 40 <= bpm_raw <= 200:
                bpm = bpm_raw

        with state_lock:
            state["pulse_bpm"] = bpm
            if bpm > 0:
                state["last_pulse_time"] = time.time()

        time.sleep(1.0 / SAMPLE_RATE)


def camera_thread():
    """
    Captures a JPEG with rpicam-still → opens with Pillow (required by spec)
    → sends as multipart POST to the server.
    The server response JSON is expected to contain {"message": "..."}.
    """
    IMG_PATH = "/tmp/pi_capture.jpg"

    while True:
        try:
            # Use the default rpicam software as required
            result = subprocess.run(
                [
                    "rpicam-still",
                    "--output",    IMG_PATH,
                    "--nopreview",
                    "--timeout",   "200",   # ms warm-up
                    "--width",     "640",
                    "--height",    "480",
                ],
                capture_output=True,
                timeout=15,
            )
            if result.returncode != 0:
                print(f"[Camera] rpicam-still failed: {result.stderr.decode()}")
                time.sleep(CAPTURE_INTERVAL_S)
                continue

            # Open with Pillow (as required), re-export to bytes buffer
            img = Image.open(IMG_PATH).convert("RGB")
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=75)
            buf.seek(0)

            resp = requests.post(
                f"http://{SERVER_IP}:{SERVER_PORT}/upload",
                files={"image": ("frame.jpg", buf, "image/jpeg")},
                timeout=6,
            )
            if resp.ok:
                msg = resp.json().get("message", "")
                if msg:
                    with state_lock:
                        state["server_message"] = msg
                    print(f"[Camera] Server says: {msg}")

        except requests.exceptions.ConnectionError:
            print("[Camera] Server unreachable — will retry")
        except Exception as e:
            print(f"[Camera] Error: {e}")

        time.sleep(CAPTURE_INTERVAL_S)

# ──────────────────────────────────────────────────────────────────
#  ACCIDENT DETECTION
# ──────────────────────────────────────────────────────────────────

def _accident_conditions_met() -> bool:
    """
    All four conditions must be true simultaneously:
      (a) Ultrasonic ≤ 15 cm  ("COLLISION OCCURRED")
      (b) Gyroscope tilt > GYRO_FALL_DEG  (vehicle has fallen)
      (c) No pulse data for > PULSE_LOSS_TIMEOUT_S seconds
      (d) Accelerometer: impact spike seen AND rest confirmed afterwards
    """
    with state_lock:
        a = state["distance_cm"]      <= DIST_COLLISION
        b = state["gyro_tilt_deg"]    >= GYRO_FALL_DEG
        c = (time.time() - state["last_pulse_time"]) > PULSE_LOSS_TIMEOUT_S
        d = state["accel_impact_seen"] and state["accel_rest_seen"]
    return a and b and c and d

# ──────────────────────────────────────────────────────────────────
#  MAIN LOOP
# ──────────────────────────────────────────────────────────────────

def main():
    print("=" * 50)
    print("  Safety System — Raspberry Pi 5")
    print("=" * 50)

    # Init MPU9250
    try:
        _mpu_init()
        print("[INIT] MPU9250 ready")
    except Exception as e:
        print(f"[INIT] MPU9250 failed: {e}")

    # Start all threads
    thread_targets = [
        led_manager,
        ultrasonic_thread,
        mpu9250_thread,
        pulse_thread,
        camera_thread,
    ]
    for fn in thread_targets:
        t = threading.Thread(target=fn, daemon=True, name=fn.__name__)
        t.start()
        print(f"[INIT] Thread started: {fn.__name__}")

    # Startup signal
    oled_show("System Ready")
    with state_lock:
        state["led_state"] = "on"
    time.sleep(1)
    with state_lock:
        state["led_state"] = "off"

    print("[INIT] All systems up. Monitoring...\n")

    try:
        while True:
            # ── snapshot of shared state ──────────────────────────
            with state_lock:
                dist       = state["distance_cm"]
                tilt       = state["gyro_tilt_deg"]
                pulse      = state["pulse_bpm"]
                srv_msg    = state["server_message"]
                accident   = state["accident_confirmed"]

            # ── (1) Accident is already confirmed — keep alerting ─
            if accident:
                oled_show("ACCIDENT!!!!")
                with state_lock:
                    state["led_state"] = "blink_fast"
                buzzer.on()
                time.sleep(0.5)
                continue

            # ── (2) Check if accident just triggered ─────────────
            if _accident_conditions_met():
                with state_lock:
                    state["accident_confirmed"] = True
                print("\n[!!!] ACCIDENT DETECTED — all four conditions met!\n")
                oled_show("ACCIDENT!!!!")
                with state_lock:
                    state["led_state"] = "blink_fast"
                buzzer.on()
                continue

            # ── (3) Pothole message from server ──────────────────
            if "Pothole has been detected" in srv_msg:
                print(f"[SERVER] {srv_msg}")
                oled_show(srv_msg)
                with state_lock:
                    state["led_state"]    = "blink_slow"
                    state["server_message"] = ""   # acknowledge & clear
                time.sleep(5)
                with state_lock:
                    state["led_state"] = "off"
                continue

            # ── (4) Ultrasonic distance alerts ────────────────────
            if dist <= DIST_COLLISION:
                msg = "COLLISION\nOCCURRED"
                print(f"[ULTRA] COLLISION OCCURRED  ({dist:.1f} cm)")
                buzzer.on()
                with state_lock:
                    state["led_state"] = "blink_fast"
            elif dist <= DIST_STOP:
                msg = "STOP"
                print(f"[ULTRA] STOP  ({dist:.1f} cm)")
                buzzer.on()
                with state_lock:
                    state["led_state"] = "blink_slow"
            elif dist <= DIST_CLOSE:
                msg = "Object close"
                print(f"[ULTRA] Object close  ({dist:.1f} cm)")
                buzzer.off()
                with state_lock:
                    state["led_state"] = "on"
            else:
                msg = f"Dist: {dist:.0f}cm\nPulse:{pulse:.0f}bpm\nTilt:{tilt:.1f}deg"
                buzzer.off()
                with state_lock:
                    state["led_state"] = "off"

            oled_show(msg)
            time.sleep(0.1)

    except KeyboardInterrupt:
        print("\n[EXIT] Ctrl+C — shutting down gracefully...")

    finally:
        buzzer.off()
        led.off()
        oled_show("System Off")
        time.sleep(0.5)
        oled.cleanup()
        spi.close()
        i2c_bus.close()
        print("[EXIT] Done.")


if __name__ == "__main__":
    main()