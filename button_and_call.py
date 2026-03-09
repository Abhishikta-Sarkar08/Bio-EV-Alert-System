"""
Emergency Alert System using Raspberry Pi 5 + SIM900A
Uses gpiozero for button input and pySerial for GSM communication
"""

from gpiozero import Button
import serial
import time

# -----------------------------
# USER CONFIGURATION
# -----------------------------

BUTTON_PIN = 17

PHONE_NUMBERS = [
    "+911234567890",
    "+919876543210"
]

EMERGENCY_MESSAGE = "EMERGENCY ALERT: Immediate assistance required!"

CALL_DURATION = 20  # seconds per call


# -----------------------------
# GSM MODULE SETUP
# -----------------------------

ser = serial.Serial(
    port="/dev/serial0",
    baudrate=9600,
    timeout=1
)

time.sleep(2)


def send_at(command, delay=1):
    """
    Send AT command to GSM module
    """
    ser.write((command + "\r").encode())
    time.sleep(delay)
    response = ser.read(ser.in_waiting).decode(errors="ignore")
    return response


def initialize_gsm():
    """
    Initialize SIM900A module
    """
    print("Initializing GSM Module...")

    print(send_at("AT"))
    print(send_at("AT+CMGF=1"))   # SMS text mode


def send_sms(number, message):
    """
    Send SMS to given number
    """

    print(f"Sending SMS to {number}")

    ser.write(f'AT+CMGS="{number}"\r'.encode())
    time.sleep(2)

    ser.write((message + "\x1A").encode())   # CTRL+Z
    time.sleep(5)


def make_call(number):
    """
    Dial a number and hang up after specified time
    """

    print(f"Calling {number}")

    send_at(f"ATD{number};")

    time.sleep(CALL_DURATION)

    send_at("ATH")


def emergency_procedure():
    """
    Runs when button is pressed
    """

    print("Emergency button pressed!")

    for number in PHONE_NUMBERS:
        send_sms(number, EMERGENCY_MESSAGE)

    for number in PHONE_NUMBERS:
        make_call(number)

    print("Emergency procedure completed.")


# -----------------------------
# BUTTON SETUP
# -----------------------------

button = Button(BUTTON_PIN, pull_up=True)


def button_pressed():
    emergency_procedure()


button.when_pressed = button_pressed


# -----------------------------
# MAIN LOOP
# -----------------------------

if __name__ == "__main__":

    initialize_gsm()

    print("System Ready. Waiting for emergency button press...")

    while True:
        time.sleep(1)
