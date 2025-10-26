import network
import time
from machine import Pin

# ====== Wi-Fi 설정 ======
SSID = "mtinet"       # ← Wi-Fi 이름 입력
PASSWORD = "33333333"  # ← Wi-Fi 비밀번호 입력
HOSTNAME = "esp32c3-mini"

# ====== LED 설정 ======
LED_PIN = 8          # ESP32-C3 Super Mini 기본 내장 LED (대부분 GPIO8)
ACTIVE_LOW = True    # LED가 0일 때 켜지는 경우가 많음

led = Pin(LED_PIN, Pin.OUT)

def led_set(on: bool):
    """LED ON/OFF (Active-Low 보드 고려)"""
    led.value(0 if (ACTIVE_LOW and on) else (1 if ACTIVE_LOW else (1 if not on else 0)))

# ====== Wi-Fi 연결 함수 ======
def connect_wifi(ssid, password, timeout=15):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    wlan.config(hostname=HOSTNAME)
    wlan.connect(ssid, password)

    print(f"Connecting to Wi-Fi: {ssid}")
    start = time.ticks_ms()
    while not wlan.isconnected():
        led_set(True)
        time.sleep(0.2)
        led_set(False)
        time.sleep(0.2)

        if time.ticks_diff(time.ticks_ms(), start) > timeout * 1000:
            print("❌ Wi-Fi connection failed.")
            return None

    print("✅ Wi-Fi connected!")
    print("IP info:", wlan.ifconfig())
    led_set(True)   # 연결 성공 시 LED ON (켜진 상태 유지)
    return wlan

# ====== 메인 실행 ======
try:
    wlan = connect_wifi(SSID, PASSWORD)
    if wlan and wlan.isconnected():
        # 연결 유지 확인
        while True:
            if wlan.isconnected():
                print("Wi-Fi OK:", wlan.ifconfig()[0])
                time.sleep(10)
            else:
                print("⚠️ Wi-Fi disconnected, retrying...")
                led_set(False)
                wlan = connect_wifi(SSID, PASSWORD)
except KeyboardInterrupt:
    led_set(False)
    print("프로그램 중단됨")

