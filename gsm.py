import blynklib
import gpiod
import time
import serial

# --- Configuration & Tokens ---
BLYNK_AUTH = 'Your_Auth_Token_Here'
ARDUINO_PORT = '/dev/ttyUSB0'
GSM_PORT = '/dev/ttyAMA0'
BAUD_RATE = 9600
BUZZER_PIN = 18
ALARM_DURATION = 30

# Initialize Blynk
blynk = blynklib.Blynk(BLYNK_AUTH)

# Initial phone number (will be updated by Blynk)
dynamic_recipient = "+1234567890" 

# --- GPIO & Serial Setup ---
chip = gpiod.Chip('gpiochip4')
buzzer_line = chip.get_line(BUZZER_PIN)
buzzer_line.request(consumer="AlarmSystem", type=gpiod.LINE_REQ_DIR_OUT)

arduino = serial.Serial(ARDUINO_PORT, BAUD_RATE, timeout=0.1)
gsm = serial.Serial(GSM_PORT, BAUD_RATE, timeout=1)

# --- Blynk Virtual Pin Handler ---
@blynk.handle_event('write V1')
def write_handler(pin, value):
    global dynamic_recipient
    # value is a list of strings sent from the Text Input widget
    new_number = value[0].strip()
    if new_number:
        dynamic_recipient = new_number
        print(f"Updated Emergency Number to: {dynamic_recipient}")

def send_sms(number, message):
    """Sends SMS via SIM900A."""
    print(f"Sending SMS to {number}...")
    gsm.write(b'AT+CMGF=1\r')
    time.sleep(1)
    gsm.write(f'AT+CMGS="{number}"\r'.encode())
    time.sleep(1)
    gsm.write(f'{message}\x1A'.encode())
    time.sleep(3)

def trigger_alarm():
    """Activates buzzer and GSM."""
    send_sms(dynamic_recipient, "Security Alert: 5 Unauthorized Attempts!")
    buzzer_line.set_value(1)
    time.sleep(ALARM_DURATION)
    buzzer_line.set_value(0)

# --- Main Loop ---
failed_attempts = 0

try:
    print("System Online. Use Blynk V1 to set phone number.")
    while True:
        blynk.run() # Processes Blynk events
        
        if arduino.in_waiting > 0:
            raw_data = arduino.readline().decode('utf-8').strip()
            
            if raw_data == "FAIL":
                failed_attempts += 1
                if failed_attempts >= 5:
                    trigger_alarm()
                    failed_attempts = 0
            
            elif raw_data == "SUCCESS":
                failed_attempts = 0

except KeyboardInterrupt:
    buzzer_line.release()
    arduino.close()
    gsm.close()