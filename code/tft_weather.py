# ESP32-C3 Super Mini + ST7735 0.96" (80x160) DASHBOARD - 2 Columns (no scroll, fast, one-pass bg)
from machine import Pin, SPI
import time, struct, ntptime, network, urequests

# ── 사용자 설정 ──
SSID="mtinet"; PASSWORD="33333333"; HOSTNAME="esp32c3-mini"
API_KEY="24109ddecb29a5405afe2a8df42c5e34"; CITY="Seoul"; UNITS="metric"; LANG="en"
DHT_PIN=None
ROTATION=1        # 90도 회전(가로 160 사용)
MIRROR_X=True     # 필요시 False로
PIN_CS=5; PIN_MOSI=4; PIN_MISO=3; PIN_SCLK=2; PIN_DC=1; PIN_RST=0
TFT_W=80; TFT_H=160

# ── ST7735 ──
SWRESET=0x01; SLPOUT=0x11; DISPON=0x29; CASET=0x2A; PASET=0x2B; RAMWR=0x2C
MADCTL=0x36; COLMOD=0x3A; INVON=0x21; INVOFF=0x20
MY=0x80; MX=0x40; MV=0x20; BGR=0x08

def rgb565(r,g,b): return ((r&0xF8)<<8)|((g&0xFC)<<3)|(b>>3)

FONT5x7={" ":[0,0,0,0,0],"!":[0,0,0x5F,0,0],":":[0,0x36,0x36,0,0],"-":[8,8,8,8,8],
"0":[0x3E,0x51,0x49,0x45,0x3E],"1":[0,0x42,0x7F,0x40,0],
"2":[0x42,0x61,0x51,0x49,0x46],"3":[0x21,0x41,0x45,0x4B,0x31],
"4":[0x18,0x14,0x12,0x7F,0x10],"5":[0x27,0x45,0x45,0x45,0x39],
"6":[0x3C,0x4A,0x49,0x49,0x30],"7":[1,0x71,9,5,3],
"8":[0x36,0x49,0x49,0x49,0x36],"9":[6,0x49,0x49,0x29,0x1E],
"A":[0x7E,0x11,0x11,0x11,0x7E],"B":[0x7F,0x49,0x49,0x49,0x36],
"C":[0x3E,0x41,0x41,0x41,0x22],"D":[0x7F,0x41,0x41,0x22,0x1C],
"E":[0x7F,0x49,0x49,0x49,0x41],"F":[0x7F,9,9,9,1],
"G":[0x3E,0x41,0x49,0x49,0x7A],"H":[0x7F,8,8,8,0x7F],
"I":[0,0x41,0x7F,0x41,0],"J":[0x20,0x40,0x41,0x3F,1],
"K":[0x7F,8,0x14,0x22,0x41],"L":[0x7F,0x40,0x40,0x40,0x40],
"M":[0x7F,2,4,2,0x7F],"N":[0x7F,4,8,0x10,0x7F],
"O":[0x3E,0x41,0x41,0x41,0x3E],"P":[0x7F,9,9,9,6],
"Q":[0x3E,0x41,0x51,0x21,0x5E],"R":[0x7F,9,0x19,0x29,0x46],
"S":[0x46,0x49,0x49,0x49,0x31],"T":[1,1,0x7F,1,1],
"U":[0x3F,0x40,0x40,0x40,0x3F],"V":[0x1F,0x20,0x40,0x20,0x1F],
"W":[0x3F,0x40,0x38,0x40,0x3F],"X":[0x63,0x14,8,0x14,0x63],
"Y":[7,8,0x70,8,7],"Z":[0x61,0x51,0x49,0x45,0x43],
".":[0,0x40,0x60,0,0],",":[0,0x40,0x20,0,0],"/":[0x40,0x20,0x10,8,4]}

class ST7735_80x160:
    def __init__(self, spi, cs, dc, rst, rotation=0, invert=False, mirror_x=False):
        self.spi=spi; self.cs=Pin(cs,Pin.OUT,value=1); self.dc=Pin(dc,Pin.OUT,value=0); self.rst=Pin(rst,Pin.OUT,value=1)
        self.rotation=rotation; self.invert=invert; self.width=TFT_W; self.height=TFT_H
        self._apply_rotation(rotation, mirror_x); self._init_display()
    def _apply_rotation(self, rot, mirror_x):
        if rot in (0,2): self.x_offset,self.y_offset=26,1; self.width,self.height=TFT_W,TFT_H
        else:            self.x_offset,self.y_offset=1,26;  self.width,self.height=TFT_H,TFT_W
        if   rot==0: mad=BGR|(MX if not mirror_x else 0)
        elif rot==1: mad=BGR|MV|(0 if not mirror_x else MX)
        elif rot==2: mad=BGR|MY|(MX if not mirror_x else 0)
        else:        mad=BGR|MX|MY|MV;  mad ^= (MX if mirror_x else 0)
        self._mad=mad
    def _cmd(self,c): self.cs.value(0); self.dc.value(0); self.spi.write(bytearray([c])); self.cs.value(1)
    def _data(self,b): self.cs.value(0); self.dc.value(1); self.spi.write(b); self.cs.value(1)
    def _reset(self): self.rst.value(0); time.sleep_ms(50); self.rst.value(1); time.sleep_ms(120)
    def _init_display(self):
        self._reset(); self._cmd(SWRESET); time.sleep_ms(150); self._cmd(SLPOUT); time.sleep_ms(120)
        self._cmd(COLMOD); self._data(bytearray([0x05])); time.sleep_ms(10)
        self._cmd(MADCTL); self._data(bytearray([self._mad]))
        self._cmd(INVON); time.sleep_ms(10)   # 모듈에 따라 INVOFF가 자연스러우면 바꾸세요
        self._cmd(DISPON); time.sleep_ms(80); self.fill_color(rgb565(0,0,0))
    def set_window(self,x0,y0,x1,y1):
        x0+=self.x_offset; x1+=self.x_offset; y0+=self.y_offset; y1+=self.y_offset
        self._cmd(CASET); self._data(struct.pack(">HH",x0,x1)); self._cmd(PASET); self._data(struct.pack(">HH",y0,y1)); self._cmd(RAMWR)
    def fill_color(self,color,x=0,y=0,w=None,h=None):
        if w is None:w=self.width
        if h is None:h=self.height
        if w<=0 or h<=0:return
        self.set_window(x,y,x+w-1,y+h-1)
        hi=(color>>8)&0xFF; lo=color&0xFF; pair=bytes([hi,lo]); chunk=pair*2048
        px=w*h; self.cs.value(0); self.dc.value(1)
        while px>0: n=min(px,2048); self.spi.write(memoryview(chunk)[:n*2]); px-=n
        self.cs.value(1)
    def pixel(self,x,y,c):
        if 0<=x<self.width and 0<=y<self.height:
            self.set_window(x,y,x,y); self._data(bytes([(c>>8)&0xFF,c&0xFF]))
    def fill_rect(self,x,y,w,h,c): self.fill_color(c,x,y,w,h)
    def hline(self,x,y,w,c): self.fill_color(c,x,y,w,1)
    def vline(self,x,y,h,c): self.fill_color(c,x,y,1,h)
    def draw_char(self,x,y,ch,color,bg=None,scale=2):
        g=FONT5x7.get(ch,FONT5x7[" "])
        for cx in range(5):
            col=g[cx]
            for cy in range(7):
                if (col>>cy)&1:
                    if scale==1:self.pixel(x+cx,y+cy,color)
                    else:self.fill_rect(x+cx*scale,y+cy*scale,scale,scale,color)
                elif bg is not None:
                    if scale==1:self.pixel(x+cx,y+cy,bg)
                    else:self.fill_rect(x+cx*scale,y+cy*scale,scale,scale,bg)
        if bg is not None:
            if scale==1:self.vline(x+5,y,7,bg)
            else:self.fill_rect(x+5*scale,y,scale,7*scale,bg)
        return 6*scale
    def draw_text(self,x,y,text,color,bg=None,scale=1):
        for ch in text: x+=self.draw_char(x,y,ch,color,bg,scale)

# ── SPI ──
try:
    spi=SPI(1,baudrate=60_000_000,polarity=0,phase=0,sck=Pin(PIN_SCLK),mosi=Pin(PIN_MOSI),miso=Pin(PIN_MISO))
except:
    spi=SPI(1,baudrate=40_000_000,polarity=0,phase=0,sck=Pin(PIN_SCLK),mosi=Pin(PIN_MOSI),miso=Pin(PIN_MISO))
tft=ST7735_80x160(spi,PIN_CS,PIN_DC,PIN_RST,rotation=ROTATION,invert=True,mirror_x=MIRROR_X)

# ── (옵션) DHT ──
_dht=None
if DHT_PIN is not None:
    try:
        import dht; _dht=dht.DHT22(Pin(DHT_PIN))
    except: _dht=None

# ── 네트워크/시간 ──
def wifi_connect(timeout=15):
    wlan=network.WLAN(network.STA_IF); wlan.active(True)
    try:wlan.config(hostname=HOSTNAME)
    except:pass
    if not wlan.isconnected():
        wlan.connect(SSID,PASSWORD); t0=time.ticks_ms()
        while not wlan.isconnected():
            time.sleep_ms(200)
            if time.ticks_diff(time.ticks_ms(),t0)>timeout*1000:return None
    return wlan
def ntp_sync(max_try=3):
    for _ in range(max_try):
        try: ntptime.host="pool.ntp.org"; ntptime.settime(); return True
        except: time.sleep(2)
    return False
def now_kst(): return time.localtime(time.time()+9*3600)

# ── 데이터 소스 ──
def read_dht():
    if _dht is None: return None
    try: _dht.measure(); return (_dht.temperature(), _dht.humidity())
    except: return None
def get_weather():
    if not API_KEY: return None
    url="http://api.openweathermap.org/data/2.5/weather?q={}&appid={}&units={}&lang={}".format(CITY,API_KEY,UNITS,LANG)
    try: r=urequests.get(url); d=r.json(); r.close(); return (d["weather"][0]["description"], d["main"]["temp"], d["main"]["humidity"])
    except: return None

# ── 색상/레이아웃 ──
BG=rgb565(0,0,0); PANEL=rgb565(10,10,20); LBG=rgb565(5,5,12); RBG=rgb565(8,8,16)
FG=rgb565(240,240,240); ACCENT=rgb565(100,200,255); OK=rgb565(60,220,130); WARN=rgb565(255,180,0)

TOP_PAD=2            # ↑ 상단 여유 2px 보정
HEADER_H=16
COL_MARGIN=2
COL_W=(tft.width//2)-COL_MARGIN*2
LEFT_X=COL_MARGIN
RIGHT_X=tft.width//2+COL_MARGIN
CONTENT_Y=HEADER_H+TOP_PAD   # 상단 2px 여유 반영
CONTENT_H=tft.height-CONTENT_Y-2

# 텍스트 위치(한 줄 높이는 대략 10~12px 잡음)
CLOCK_X=4; CLOCK_Y=TOP_PAD+4

# 라인 영역(부분 갱신용) 정의
L_LINE1=(LEFT_X+2,  CONTENT_Y+16, COL_W-4, 10)  # 센서 T
L_LINE2=(LEFT_X+2,  CONTENT_Y+28, COL_W-4, 10)  # 센서 H
R_LINE1=(RIGHT_X+2, CONTENT_Y+16, COL_W-4, 10)  # 날씨 T
R_LINE2=(RIGHT_X+2, CONTENT_Y+28, COL_W-4, 10)  # 날씨 H
R_DESC =(RIGHT_X+2, CONTENT_Y+40, COL_W-4, 12)  # 날씨 설명

_last_sec=-1
_synced=False

# ── 배경 1회 그리기(순서 보장: 배경 → 그 위에 텍스트) ──
def draw_background_once():
    # 헤더
    tft.fill_rect(0,0,tft.width,HEADER_H+TOP_PAD,PANEL)
    # 좌/우 패널 배경
    tft.fill_rect(LEFT_X, CONTENT_Y,  COL_W, CONTENT_H,  LBG)
    tft.fill_rect(RIGHT_X,CONTENT_Y,  COL_W, CONTENT_H,  RBG)
    # 고정 타이틀 텍스트(한 번만)
    tft.draw_text(LEFT_X+2,  CONTENT_Y+2,  "SENSOR",  ACCENT,                 bg=LBG, scale=1)
    tft.draw_text(RIGHT_X+2, CONTENT_Y+2,  "WEATHER", rgb565(255,220,120),    bg=RBG, scale=1)

def clear_line(x,y,w,h,bg):
    # 부분 영역만 지움(빠름)
    tft.fill_rect(x,y,w,h,bg)

def draw_clock_fast():
    global _last_sec
    t=now_kst(); s=t[5]
    if s==_last_sec: return
    _last_sec=s
    clock="{:02d}:{:02d}:{:02d}".format(t[3],t[4],s)
    # 헤더는 이미 칠해져 있으므로 해당 숫자 영역만 덮고 다시 그림
    tft.draw_text(CLOCK_X, CLOCK_Y, clock, OK if _synced else WARN, bg=PANEL, scale=1)

def draw_sensor_text(d):
    x1,y1,w1,h1 = L_LINE1
    x2,y2,w2,h2 = L_LINE2
    if d is None:
        clear_line(x1,y1,w1,h1,LBG); tft.draw_text(x1,y1,"No sensor",FG,bg=LBG,scale=1)
        clear_line(x2,y2,w2,h2,LBG)
    else:
        tc,hu=d
        clear_line(x1,y1,w1,h1,LBG); tft.draw_text(x1,y1,"T:{:>4.1f}C".format(tc),FG,bg=LBG,scale=1)
        clear_line(x2,y2,w2,h2,LBG); tft.draw_text(x2,y2,"H:{:>3.0f}%".format(hu),FG,bg=LBG,scale=1)

def draw_weather_text(w):
    x1,y1,w1,h1 = R_LINE1
    x2,y2,w2,h2 = R_LINE2
    xd,yd,wd,hd = R_DESC
    if w is None:
        clear_line(x1,y1,w1,h1,RBG); tft.draw_text(x1,y1,"No data",FG,bg=RBG,scale=1)
        clear_line(x2,y2,w2,h2,RBG)
        clear_line(xd,yd,wd,hd,RBG)
        return
    desc,tmp,hum=w
    clear_line(x1,y1,w1,h1,RBG); tft.draw_text(x1,y1,"T:{:>4.1f}C".format(tmp),FG,bg=RBG,scale=1)
    clear_line(x2,y2,w2,h2,RBG); tft.draw_text(x2,y2,"H:{:>3.0f}%".format(hum),FG,bg=RBG,scale=1)
    # 설명: 스크롤 없이 칼럼 폭에 맞춰 고정 표시
    txt = desc.upper() if LANG=="en" else desc
    maxchars = wd//6
    clear_line(xd,yd,wd,hd,RBG); tft.draw_text(xd,yd,txt[:maxchars],ACCENT,bg=RBG,scale=1)

def main():
    global _synced
    tft.fill_color(BG)
    draw_background_once()       # 배경 한 번에
    draw_clock_fast()            # 최초 시계

    # 네트워크/시간
    wlan=wifi_connect()
    _synced=ntp_sync() if wlan else False
    draw_clock_fast()            # 색상 반영

    # 첫 데이터 페인트(글씨만)
    dht_data = read_dht()
    weather  = get_weather() if wlan else None
    draw_sensor_text(dht_data)
    draw_weather_text(weather)

    # 주기 타이머
    t_dht=time.ticks_ms()
    t_w  =time.ticks_ms()

    while True:
        draw_clock_fast()  # 초 바뀔 때만 갱신

        now=time.ticks_ms()
        if time.ticks_diff(now,t_dht)>5000:
            dht_data=read_dht()
            draw_sensor_text(dht_data)
            t_dht=now

        if wlan and time.ticks_diff(now,t_w)>600_000:
            weather=get_weather()
            draw_weather_text(weather)
            t_w=now

        time.sleep_ms(5)  # 루프 템포(조금 더 빠르게)
# ── 실행 ──
try:
    # SPI는 위에서 초기화됨
    main()
except KeyboardInterrupt:
    pass

