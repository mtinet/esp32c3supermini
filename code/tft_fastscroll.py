from machine import Pin, SPI
import time, struct, urandom
import framebuf

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
MY = 0x80; MX = 0x40; MV = 0x20; BGR = 0x08

def rgb565(r, g, b):
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)

# ── 5x7 폰트(대문자/숫자 최소만): 필요시 확장 가능
FONT5x7 = {
    " ": [0x00,0x00,0x00,0x00,0x00], "!":[0x00,0x00,0x5F,0x00,0x00],
    "0":[0x3E,0x51,0x49,0x45,0x3E], "1":[0x00,0x42,0x7F,0x40,0x00],
    "2":[0x42,0x61,0x51,0x49,0x46], "3":[0x21,0x41,0x45,0x4B,0x31],
    "4":[0x18,0x14,0x12,0x7F,0x10], "5":[0x27,0x45,0x45,0x45,0x39],
    "6":[0x3C,0x4A,0x49,0x49,0x30], "7":[0x01,0x71,0x09,0x05,0x03],
    "8":[0x36,0x49,0x49,0x49,0x36], "9":[0x06,0x49,0x49,0x29,0x1E],
    "A":[0x7E,0x11,0x11,0x11,0x7E], "B":[0x7F,0x49,0x49,0x49,0x36],
    "C":[0x3E,0x41,0x41,0x41,0x22], "D":[0x7F,0x41,0x41,0x22,0x1C],
    "E":[0x7F,0x49,0x49,0x49,0x41], "F":[0x7F,0x09,0x09,0x09,0x01],
    "G":[0x3E,0x41,0x49,0x49,0x7A], "H":[0x7F,0x08,0x08,0x08,0x7F],
    "I":[0x00,0x41,0x7F,0x41,0x00], "J":[0x20,0x40,0x41,0x3F,0x01],
    "K":[0x7F,0x08,0x14,0x22,0x41], "L":[0x7F,0x40,0x40,0x40,0x40],
    "M":[0x7F,0x02,0x04,0x02,0x7F], "N":[0x7F,0x04,0x08,0x10,0x7F],
    "O":[0x3E,0x41,0x41,0x41,0x3E], "P":[0x7F,0x09,0x09,0x09,0x06],
    "Q":[0x3E,0x41,0x51,0x21,0x5E], "R":[0x7F,0x09,0x19,0x29,0x46],
    "S":[0x46,0x49,0x49,0x49,0x31], "T":[0x01,0x01,0x7F,0x01,0x01],
    "U":[0x3F,0x40,0x40,0x40,0x3F], "V":[0x1F,0x20,0x40,0x20,0x1F],
    "W":[0x3F,0x40,0x38,0x40,0x3F], "X":[0x63,0x14,0x08,0x14,0x63],
    "Y":[0x07,0x08,0x70,0x08,0x07], "Z":[0x61,0x51,0x49,0x45,0x43],
    "-":[0x08,0x08,0x08,0x08,0x08], ":":[0x00,0x36,0x36,0x00,0x00],
}

class ST7735_80x160:
    def __init__(self, spi, cs, dc, rst, rotation=0, invert=False, mirror_x=False):
        self.spi = spi
        self.cs  = Pin(cs,  Pin.OUT, value=1)
        self.dc  = Pin(dc,  Pin.OUT, value=0)
        self.rst = Pin(rst, Pin.OUT, value=1)
        self.rotation = rotation
        self.invert = invert
        self.mirror_x = mirror_x

        self.width  = TFT_W
        self.height = TFT_H
        # 기본 오프셋 (회전 0/2)
        self.x_offset = 26
        self.y_offset = 1

        self._apply_rotation(rotation, mirror_x)
        self._init_display()

    def _apply_rotation(self, rot, mirror_x):
        # 기본 MADCTL
        if rot == 0:
            mad = BGR | (MX if not mirror_x else 0)  # 좌우 반전 토글
            self.width, self.height = TFT_W, TFT_H
            self.x_offset, self.y_offset = 26, 1
        elif rot == 1:
            mad = BGR | MV | (0 if not mirror_x else MX)  # 회전시 미러 방향 달라짐
            self.width, self.height = TFT_H, TFT_W
            self.x_offset, self.y_offset = 1, 26
        elif rot == 2:
            mad = BGR | MY | (MX if not mirror_x else 0)
            self.width, self.height = TFT_W, TFT_H
            self.x_offset, self.y_offset = 26, 1
        else:  # rot == 3
            mad = BGR | MX | MY | MV
            if mirror_x:
                mad ^= MX  # 토글
            self.width, self.height = TFT_H, TFT_W
            self.x_offset, self.y_offset = 1, 26

        self._mad = mad

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

        self._cmd(COLMOD); self._data(bytearray([0x05])); time.sleep_ms(10)
        self._cmd(MADCTL); self._data(bytearray([self._mad]))
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
        pair = bytes([hi, lo])
        chunk = pair * 1024  # 2KB 청크
        pixels = w * h
        self.cs.value(0); self.dc.value(1)
        while pixels > 0:
            n = min(pixels, 1024)
            self.spi.write(memoryview(chunk)[:n*2])
            pixels -= n
        self.cs.value(1)

    def fill_rect(self, x, y, w, h, color):
        self.fill_color(color, x, y, w, h)

    def hline(self, x, y, w, color):
        self.fill_color(color, x, y, w, 1)

    def vline(self, x, y, h, color):
        self.fill_color(color, x, y, 1, h)

    # ── 5x7 텍스트
    def pixel(self, x, y, color):
        if 0 <= x < self.width and 0 <= y < self.height:
            self.set_window(x, y, x, y)
            self._data(bytes([(color>>8)&0xFF, color&0xFF]))

    def draw_char(self, x, y, ch, color, bg=None, scale=1):
        glyph = FONT5x7.get(ch, FONT5x7[" "])
        for cx in range(5):
            col = glyph[cx]
            for cy in range(7):
                bit = (col >> cy) & 1
                if bit:
                    if scale == 1:
                        self.pixel(x+cx, y+cy, color)
                    else:
                        self.fill_rect(x+cx*scale, y+cy*scale, scale, scale, color)
                elif bg is not None:
                    if scale == 1:
                        self.pixel(x+cx, y+cy, bg)
                    else:
                        self.fill_rect(x+cx*scale, y+cy*scale, scale, scale, bg)
        if bg is not None:
            if scale == 1:
                self.vline(x+5, y, 7, bg)
            else:
                self.fill_rect(x+5*scale, y, scale, 7*scale, bg)
        return 6*scale

    def draw_text(self, x, y, text, color, bg=None, scale=1):
        for ch in text:
            x += self.draw_char(x, y, ch, color, bg, scale)

# ===== SPI: 배선 짧으면 40MHz까지 시도 (불안하면 20MHz) =====
spi = SPI(1,
          baudrate=40_000_000,
          polarity=0, phase=0,
          sck=Pin(PIN_SCLK),
          mosi=Pin(PIN_MOSI),
          miso=Pin(PIN_MISO))

# 좌우반전 원하시면 mirror_x=True
tft = ST7735_80x160(spi, cs=PIN_CS, dc=PIN_DC, rst=PIN_RST,
                    rotation=0, invert=True, mirror_x=True)

# ── 데모1: 바운싱 볼(최소 영역만 갱신)
def demo_bounce(duration_s=6):
    bg = rgb565(0,0,0)
    tft.fill_color(bg)
    r = 6
    x, y = 10, 10
    dx, dy = 2, 3
    color = rgb565(255, 220, 0)
    t0 = time.ticks_ms()
    prev = (x, y)
    while time.ticks_diff(time.ticks_ms(), t0) < duration_s*1000:
        # 이전 위치만 지우기(오버드로 최소화)
        px, py = prev
        tft.fill_rect(px-r-1, py-r-1, 2*r+2, 2*r+2, bg)

        # 이동 및 경계 반사
        x += dx; y += dy
        if x-r <= 0 or x+r >= tft.width:
            dx = -dx; color = rgb565(urandom.getrandbits(8), urandom.getrandbits(8), urandom.getrandbits(8))
        if y-r <= 0 or y+r >= tft.height:
            dy = -dy; color = rgb565(urandom.getrandbits(8), urandom.getrandbits(8), urandom.getrandbits(8))

        # 사각형 + 십자 클리핑으로 원 느낌
        tft.fill_rect(x-r, y-r, 2*r, 2*r, color)
        tft.hline(x-r, y, 2*r, bg)
        tft.vline(x, y-r, 2*r, bg)
        prev = (x, y)
        time.sleep_ms(12)  # 프레임 템포

# ── 데모2: 초고속 스크롤 라인(프레임버퍼로 한방에 전송)
def demo_fast_scroll():
    # 한 줄 버퍼(높이 16): RGB565 => 2바이트 * 80 * 16 = 2560바이트
    LINE_H = 16
    buf = bytearray(TFT_W * LINE_H * 2)
    fb = framebuf.FrameBuffer(buf, TFT_W, LINE_H, framebuf.RGB565)

    y = TFT_H - LINE_H - 2
    bg = rgb565(0, 0, 0)
    text_color = rgb565(100, 255, 180)

    msg = "FAST SCROLL  ST7735  ESP32-C3  "
    # 프레임버퍼에 배경 칠하고 텍스트를 직접 찍기(간단 폰트)
    def fb_draw_text(x, y, s, color):
        # 최소 렌더: 5x7 폰트 사용
        for ch in s:
            g = FONT5x7.get(ch, FONT5x7[" "])
            for cx in range(5):
                col = g[cx]
                for cy in range(7):
                    if (col >> cy) & 1:
                        fb.pixel(x+cx, y+cy, color)
            x += 6

    # 배경 초기화
    fb.fill(bg)
    fb_draw_text(TFT_W, 4, msg, text_color)  # 화면 오른쪽 밖에서 시작

    x_off = TFT_W
    w_msg = len(msg)*6
    while True:
        # 배경 지우고 현재 위치에 텍스트 다시
        fb.fill(bg)
        fb_draw_text(x_off, 4, msg, text_color)
        # 화면에 빠르게 전송(한 창만 업데이트)
        tft.set_window(0, y, TFT_W-1, y+LINE_H-1)
        tft.cs.value(0); tft.dc.value(1)
        tft.spi.write(buf)
        tft.cs.value(1)

        x_off -= 2
        if x_off < -w_msg:
            x_off = TFT_W
        time.sleep_ms(10)  # 스크롤 속도

# 실행
demo_bounce(5)
demo_fast_scroll()

