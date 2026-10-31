# Prints the ESP32-C3 start-up messages. Reconnects automatically when the board is unplugged and replugged.
import time
import serial
from serial.tools import list_ports

PORT = "COM7"
RUN_SECONDS = 60

def port_present():
    return any(p.device.upper() == PORT for p in list_ports.comports())

print("Running for", RUN_SECONDS, "seconds. Unplug and replug the board now (do not hold BOOT).")
end = time.time() + RUN_SECONDS
ser = None
last_check = 0
while time.time() < end:
    if ser is None:
        if not port_present():
            time.sleep(0.02)
            continue
        try:
            ser = serial.Serial(PORT, 115200, timeout=0.05)
            print("\n--- connected ---", flush=True)
        except Exception:
            time.sleep(0.02)
            continue
    try:
        data = ser.read(256)
        if data:
            print(data.decode("utf-8", errors="replace"), end="", flush=True)
    except Exception:
        data = None
        try:
            ser.close()
        except Exception:
            pass
        ser = None
        print("\n--- disconnected ---", flush=True)
        continue
    if time.time() - last_check > 0.2:
        last_check = time.time()
        if not port_present():
            try:
                ser.close()
            except Exception:
                pass
            ser = None
            print("\n--- disconnected, waiting for the board ---", flush=True)
print("\n--- done ---")