import cv2
import numpy as np

# ============================================================
# HSV Color Tag → Piece mapping
#   Pawn   = สีเหลืองสด     H 22-32  (pure yellow, ไม่ใช่ yellow-green)
#   Knight = สีเขียว lime   H 58-80  (neon green, S สูงมาก)
#   Bishop = สีฟ้า          H 95-115
#   Queen  = สีส้ม          H  8-22
#   Rook   = สีชมพูสด       H 150-175 (hot pink / fuchsia)
#   King   = สีม่วง/magenta H 125-150 (purple-pink, แยกจาก Rook ด้วย H)
# ============================================================
TAGS = {
    'Queen': {
        'lower': np.array([8,  180, 180]),
        'upper': np.array([22, 255, 255]),
        'bgr':   (0, 100, 255),
    },
    'Pawn': {
        'lower': np.array([22, 200, 180]),   # เหลืองสด pure yellow
        'upper': np.array([32, 255, 255]),
        'bgr':   (0, 220, 220),
    },
    'Knight': {
        'lower': np.array([55, 150, 120]),   # lime green — ลด S จาก 200 → 150
        'upper': np.array([80, 255, 255]),
        'bgr':   (0, 230, 30),
    },
    'Bishop': {
        'lower': np.array([95,  130, 100]),  # sky blue
        'upper': np.array([115, 255, 255]),
        'bgr':   (230, 130, 0),
    },
    'King': {
        # ม่วงอ่อน/ลาเวนเดอร์ (pastel) — S ต่ำมากเพราะสีจาง
        'lower': np.array([115,  30,  80]),
        'upper': np.array([145, 180, 220]),
        'bgr':   (200, 0, 180),
    },
    'Rook': {
        'lower': np.array([148, 130, 120]),  # hot pink / fuchsia
        'upper': np.array([175, 255, 255]),
        'bgr':   (150, 0, 220),
    },
}

MIN_AREA     = 250    # ขนาด contour ต่ำสุด (px²)
BELOW_OFFSET = 5      # px เว้นหลัง tag ก่อน sample ตัวหมาก
SAMPLE_H     = 45     # ความสูง sample zone
BRIGHT_THRESH = 135   # > threshold → White piece

# ============================================================
# Debug: click เพื่อดู HSV ณ pixel นั้น
# ============================================================
_click_hsv = None
_frame_hsv = None

def _mouse_cb(event, x, y, flags, param):
    global _click_hsv
    if event == cv2.EVENT_LBUTTONDOWN and _frame_hsv is not None:
        h, s, v = _frame_hsv[y, x]
        _click_hsv = (h, s, v)
        print(f'[HSV @ ({x},{y})]  H={h}  S={s}  V={v}')


def get_team(frame, x, y, w, h):
    """Sample ตัวหมากใต้ tag: สว่าง=White, มืด=Black"""
    sy0 = max(0, y + h + BELOW_OFFSET)
    sy1 = min(frame.shape[0], sy0 + SAMPLE_H)
    sx0 = max(0, x)
    sx1 = min(frame.shape[1], x + w)
    if sy1 <= sy0 or sx1 <= sx0:
        return 'White'
    region = frame[sy0:sy1, sx0:sx1]
    gray   = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
    brightness = float(np.mean(gray))
    return 'White' if brightness > BRIGHT_THRESH else 'Black'


def main():
    global _frame_hsv

    cap = cv2.VideoCapture(1)
    if not cap.isOpened():
        print('ERROR: Cannot open iPhone camera (index 1)')
        return

    cv2.namedWindow('Chess Detection')
    cv2.setMouseCallback('Chess Detection', _mouse_cb)

    kernel_open  = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    kernel_dilate = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        _frame_hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        display    = frame.copy()

        for piece, cfg in TAGS.items():
            mask = cv2.inRange(_frame_hsv, cfg['lower'], cfg['upper'])
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN,   kernel_open)
            mask = cv2.morphologyEx(mask, cv2.MORPH_DILATE, kernel_dilate)
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL,
                                           cv2.CHAIN_APPROX_SIMPLE)
            for cnt in contours:
                if cv2.contourArea(cnt) < MIN_AREA:
                    continue
                x, y, w, h = cv2.boundingRect(cnt)
                team  = get_team(frame, x, y, w, h)
                label = f'{team} {piece}'
                color = cfg['bgr']
                # กรอบ tag
                cv2.rectangle(display, (x, y), (x + w, y + h), color, 2)
                # กรอบ sample zone (เหลือง = debug)
                sy0d = y + h + BELOW_OFFSET
                cv2.rectangle(display,
                              (x, sy0d), (x + w, sy0d + SAMPLE_H),
                              (0, 255, 255), 1)
                cv2.putText(display, label, (x, max(y - 8, 10)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.65, color, 2)

        # แสดง HSV ที่ click ล่าสุด
        if _click_hsv:
            txt = f'H={_click_hsv[0]} S={_click_hsv[1]} V={_click_hsv[2]}'
            cv2.putText(display, txt, (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)

        cv2.imshow('Chess Detection', display)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == '__main__':
    main()
