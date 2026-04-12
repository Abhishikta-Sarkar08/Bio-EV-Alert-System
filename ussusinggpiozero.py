import time
from gpiozero import DistanceSensor, Buzzer

# GPIO pins (BCM numbering)
TRIG = 23
ECHO = 24
BUZZER_PIN = 26

# Initialize GPIO devices
sensor = DistanceSensor(echo=ECHO, trigger=TRIG)
buzzer = Buzzer(BUZZER_PIN)

def get_distance():
    try:
        # DistanceSensor returns distance in meters, convert to cm
        distance_m = sensor.distance
        distance_cm = distance_m * 100
        return distance_cm
    except:
        return None


def beep(duration):
    buzzer.on()
    time.sleep(duration)
    buzzer.off()


print("Distance monitor started. Press Ctrl+C to stop.")

try:

    while True:

        d = get_distance()

        if d is None:
            print("Sensor timeout")
            buzzer.off()
            time.sleep(0.5)
            continue

        print(f"Distance: {d:.1f} cm")

        # if d < 20:
             # continuous beep
             # buzzer.on()

        if d < 50:
            # fast beep
            beep(0.1)
            time.sleep(0.1)

        elif d < 500:
            # slow beep
            beep(0.1)
            time.sleep(0.4)

        else:
            buzzer.off()
            time.sleep(0.5)

except KeyboardInterrupt:
    print("\nStopped by user")

finally:
    sensor.close()
    buzzer.close()
