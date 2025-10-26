from machine import Pin, SPI
import time, struct

# ===== 핀 매핑 =====
PIN_CS   = 5
PIN_MOSI = 4
PIN_MISO = 3
PIN_SCLK = 2
PIN_DC   = 1
PIN_RST  = 0

# ===== 디스플레이 해상도 =====
TFT_W = 80
TFT_H = 160

# ===== ST7735 명령 =====
SWRESET = 0x01
SLPOUT  = 0x11
DISPON  = 0x29
CASET   = 0x2A
PASET   = 0x2B
RAMWR   = 0x2C
MADCTL  = 0x36
COLMOD  = 0x3A
INVON   = 0x21
INVOFF  = 0x20

# MADCTL 비트
MY   = 0x80
MX   = 0x40
MV   = 0x20
BGR  = 0x08

def rgb565(r, g, b):
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)

class ST7735_80x160:
    def __init__(self, spi, cs, dc, rst, rotation=0, invert=False):
        self.spi = spi
        self.cs  = Pin(cs,  Pin.OUT, value=1)
        self.dc  = Pin(dc,  Pin.OUT, value=0)
        self.rst = Pin(rst, Pin.OUT, value=1)

        self.width  = TFT_W
        self.height = TFT_H
        self.rotation = rotation
        self.invert = invert

        # 기본 오프셋 (회전 0/2)
        self.x_offset = 26
        self.y_offset = 1
        self._apply_rotation(rotation)
        self._init_display()

    def _apply_rotation(self, rot):
        if rot == 0:
            self._mad = MX | BGR
            self.width, self.height = TFT_W, TFT_H
            self.x_offset, self.y_offset = 26, 1
        elif rot == 1:
            self._mad = MV | BGR
            self.width, self.height = TFT_H, TFT_W
            self.x_offset, self.y_offset = 1, 26  # swap
        elif rot == 2:
            self._mad = MY | BGR
            self.width, self.height = TFT_W, TFT_H
            self.x_offset, self.y_offset = 26, 1
        else:  # rot == 3
            self._mad = MX | MY | MV | BGR
            self.width, self.height = TFT_H, TFT_W
            self.x_offset, self.y_offset = 1, 26  # swap

    def _cmd(self, c):
        self.cs.value(0); self.dc.value(0)
        self.spi.write(bytearray([c]))
        self.cs.value(1)

    def _data(self, b):
        self.cs.value(0); self.dc.value(1)
        self.spi.write(b)
        self.cs.value(1)

    def _reset(self):
        self.rst.value(0); time.sleep_ms(50)
        self.rst.value(1); time.sleep_ms(120)

    def _init_display(self):
        self._reset()
        self._cmd(SWRESET); time.sleep_ms(150)
        self._cmd(SLPOUT);  time.sleep_ms(120)

        # 16bpp
        self._cmd(COLMOD); self._data(bytearray([0x05])); time.sleep_ms(10)

        # 회전
        self._cmd(MADCTL); self._data(bytearray([self._mad]))

        # 색반전(모듈에 따라 ON/OFF 달라요)
        self._cmd(INVON if self.invert else INVOFF); time.sleep_ms(10)

        self._cmd(DISPON); time.sleep_ms(100)
        self.fill_color(rgb565(0,0,0))

    def set_window(self, x0, y0, x1, y1):
        x0 += self.x_offset; x1 += self.x_offset
        y0 += self.y_offset; y1 += self.y_offset

        self._cmd(CASET); self._data(struct.pack(">HH", x0, x1))
        self._cmd(PASET); self._data(struct.pack(">HH", y0, y1))
        self._cmd(RAMWR)

    def fill_color(self, color565, x=0, y=0, w=None, h=None):
        if w is None: w = self.width
        if h is None: h = self.height
        if w <= 0 or h <= 0: return

        self.set_window(x, y, x+w-1, y+h-1)
        hi = (color565 >> 8) & 0xFF
        lo = color565 & 0xFF

        # ✅ bytes 사용 (MicroPython 호환)
        pair = bytes([hi, lo])
        # 1024바이트(=512픽셀) 청크 준비
        chunk = pair * 512

        pixels = w * h
        self.cs.value(0); self.dc.value(1)
        while pixels > 0:
            n = min(pixels, 512)  # 픽셀 수
            self.spi.write(memoryview(chunk)[:n*2])
            pixels -= n
        self.cs.value(1)

    def rect(self, x, y, w, h, color):
        self.fill_color(color, x, y, w, 1)
        self.fill_color(color, x, y+h-1, w, 1)
        self.fill_color(color, x, y, 1, h)
        self.fill_color(color, x+w-1, y, 1, h)

    def hline(self, x, y, w, color):
        self.fill_color(color, x, y, w, 1)

    def vline(self, x, y, h, color):
        self.fill_color(color, x, y, 1, h)

# ===== SPI 초기화 & 데모 =====
spi = SPI(1,
          baudrate=20_000_000,  # 불안하면 10_000_000
          polarity=0, phase=0,
          sck=Pin(PIN_SCLK),
          mosi=Pin(PIN_MOSI),
          miso=Pin(PIN_MISO))

tft = ST7735_80x160(spi, cs=PIN_CS, dc=PIN_DC, rst=PIN_RST,
                    rotation=0, invert=True)

# 화면 테스트
tft.fill_color(rgb565(0,0,0)); time.sleep_ms(200)

colors = [
    rgb565(255, 0, 0),
    rgb565(0, 255, 0),
    rgb565(0, 0, 255),
    rgb565(255, 255, 0),
    rgb565(255, 0, 255),
    rgb565(0, 255, 255),
    rgb565(255, 255, 255),
    rgb565(32, 32, 32),
]
bar_h = tft.height // len(colors)
for i, c in enumerate(colors):
    tft.fill_color(c, 0, i*bar_h, tft.width, bar_h)
    time.sleep_ms(120)

tft.rect(0, 0, tft.width, tft.height, rgb565(255,255,255))
tft.hline(0, tft.height//2, tft.width, rgb565(255,128,0))
tft.vline(tft.width//2, 0, tft.height, rgb565(0,255,255))
print("TFT init OK")


