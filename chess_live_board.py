"""
chess_live_board.py - v9 (iPad Continuity Camera + Hand Presence Auto-Move Trigger)
====================================================================================
1. Auto-detect iPad via Continuity Camera (ค้นหาชื่ออุปกรณ์ "iPad" อัตโนมัติ)
2. Auto-Detect Red Dot Anchor: ใช้จุดสีแดงบนขอบกระดานเป็นจุดกำเนิด (a1 Origin)
3. Hand Presence Trigger: มือยื่นเข้า = หยุดสแกน / มือออก = สแกนใหม่ทันที
4. ค้างค่าเดิมไว้บน 2D จนกว่าหมากจะเคลื่อนที่ หรือกด [Space]
"""

import cv2
import numpy as np
import json
import os
import time
import subprocess
import re
import sys
from collections import Counter

# ─── Config & Layout ──────────────────────────────────────────
CELL_SIZE     = 70                 # ขนาดช่อง 2D
MARGIN        = 32                 # ขอบบอก a-h, 1-8
BOARD_SIZE    = CELL_SIZE * 8      # 560
STATUS_H      = 42                 # แถบสถานะล่าง
WIN_W         = BOARD_SIZE + MARGIN * 2
WIN_H         = BOARD_SIZE + MARGIN * 2 + STATUS_H

CORNERS_FILE  = 'board_corners.json'
EVAL_INTERVAL = 2.0                # รอบประเมิน

# ─── Auto-Detect iPad Camera ──────────────────────────────────
def find_ipad_camera_index():
    """
    ค้นหา Index กล้องของ iPad Continuity Camera อัตโนมัติ:
    1. ลองดึงรายชื่ออุปกรณ์จาก imagesnap (ถ้ามี)
    2. Fallback: สแกน OpenCV Index 0-6 แล้วเลือก Index ที่ความละเอียดสูงสุด
       (iPad Continuity Camera มักจะมีความละเอียดสูงกว่า FaceTime MacBook)
    """
    # วิธีที่ 1: ใช้ imagesnap (ถ้าติดตั้งไว้)
    try:
        out = subprocess.check_output(
            ['imagesnap', '-l'], timeout=5, stderr=subprocess.DEVNULL
        ).decode(errors='ignore')
        for line in out.splitlines():
            if 'ipad' in line.lower():
                m = re.search(r'\[(\d+)\]', line)
                if m:
                    idx = int(m.group(1))
                    print(f"[CAMERA] พบ iPad ผ่าน imagesnap: Index {idx}")
                    return idx
    except Exception:
        pass

    # วิธีที่ 2: สแกน AVFoundation Index แล้วเลือกอันที่ใหญ่สุด
    best_idx = 0
    best_pixels = 0
    print("[CAMERA] สแกนหา iPad Camera...")
    for idx in range(7):
        cap = cv2.VideoCapture(idx, cv2.CAP_AVFOUNDATION)
        if cap.isOpened():
            ret, frame = cap.read()
            if ret and frame is not None:
                h, w = frame.shape[:2]
                pixels = w * h
                print(f"  Index {idx}: {w}x{h} ({pixels:,} px)")
                if pixels > best_pixels:
                    best_pixels = pixels
                    best_idx = idx
            cap.release()
    print(f"[CAMERA] เลือก Index {best_idx} ({best_pixels:,} px) → น่าจะเป็น iPad")
    return best_idx

CLR_LIGHT     = (181, 217, 240)    # #F0D9B5
CLR_DARK      = ( 99, 136, 181)    # #B58863
CLR_BG        = ( 32,  32,  32)
CLR_TEXT      = (180, 180, 180)
CLR_ARROW     = (  0, 210, 255)
CLR_HL_SRC    = ( 90, 190,  90)
CLR_HL_DST    = ( 80, 140, 230)

# HSV Ranges จาก color_detect.py
TAGS = {
    'Queen':  {'lower': np.array([ 5, 110, 110]), 'upper': np.array([22, 255, 255]), 'bgr': (0, 100, 255), 'code': 'Q'},
    'Pawn':   {'lower': np.array([22, 110, 110]), 'upper': np.array([36, 255, 255]), 'bgr': (0, 220, 220), 'code': 'P'},
    'Knight': {'lower': np.array([33,  35,  35]), 'upper': np.array([88, 255, 255]), 'bgr': (0, 230,  30), 'code': 'N'},
    'Bishop': {'lower': np.array([88,  70,  70]), 'upper': np.array([120, 255, 255]), 'bgr': (230, 130, 0), 'code': 'B'},
    'King':   {'lower': np.array([120,  30,  60]), 'upper': np.array([148, 255, 255]), 'bgr': (200,   0, 180), 'code': 'K'},
    'Rook':   {'lower': np.array([148,  80,  80]), 'upper': np.array([178, 255, 255]), 'bgr': (150,   0, 220), 'code': 'R'},
}

MIN_AREA      = 20
BELOW_OFFSET  = 2
SAMPLE_H      = 15
BRIGHT_THRESH = 155

# ─── Unicode Icons ────────────────────────────────────────────
try:
    from PIL import Image, ImageDraw, ImageFont
    _FONT_PATH = '/System/Library/Fonts/Supplemental/Arial Unicode.ttf'
    if not os.path.exists(_FONT_PATH):
        _FONT_PATH = '/System/Library/Fonts/Geneva.ttf'
    _pil_font = ImageFont.truetype(_FONT_PATH, int(CELL_SIZE * 0.82))
    USE_PIL = True
except Exception:
    USE_PIL = False

UNICODE_PIECES = {
    'WK':'♔','WQ':'♕','WR':'♖','WB':'♗','WN':'♘','WP':'♙',
    'BK':'♚','BQ':'♛','BR':'♜','BB':'♝','BN':'♞','BP':'♟',
}

_ICON_CACHE = {}

def get_piece_icon(piece_id):
    if piece_id in _ICON_CACHE:
        return _ICON_CACHE[piece_id]

    sz = CELL_SIZE - 8
    is_white = piece_id[0] == 'W'

    if USE_PIL:
        img = Image.new('RGBA', (sz, sz), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        sym = UNICODE_PIECES.get(piece_id, '?')
        fg_col = (255, 255, 255, 255) if is_white else (25, 25, 25, 255)
        sh_col = (0, 0, 0, 180) if is_white else (210, 210, 210, 160)
        d.text((2, 2), sym, font=_pil_font, fill=sh_col)
        d.text((0, 0), sym, font=_pil_font, fill=fg_col)
        icon_bgra = cv2.cvtColor(np.array(img), cv2.COLOR_RGBA2BGRA)
    else:
        icon_bgra = np.zeros((sz, sz, 4), dtype=np.uint8)
        cx, cy = sz // 2, sz // 2
        r = sz // 2 - 2
        bg_col = (255, 255, 255) if is_white else (35, 35, 35)
        bd_col = (40, 40, 40) if is_white else (210, 210, 210)
        cv2.circle(icon_bgra, (cx, cy), r, (*bd_col, 255), -1)
        cv2.circle(icon_bgra, (cx, cy), r - 3, (*bg_col, 255), -1)
        sym = piece_id[1]
        ts = cv2.getTextSize(sym, cv2.FONT_HERSHEY_SIMPLEX, 0.75, 2)[0]
        cv2.putText(icon_bgra, sym, (cx - ts[0]//2, cy + ts[1]//2),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.75, (*bd_col, 255), 2)

    _ICON_CACHE[piece_id] = icon_bgra
    return icon_bgra

def blit_alpha(canvas, icon_bgra, cx, cy):
    h, w = icon_bgra.shape[:2]
    x0, y0 = cx - w // 2, cy - h // 2
    x1, y1 = x0 + w, y0 + h
    xi0, yi0 = max(0, -x0), max(0, -y0)
    xi1, yi1 = w - max(0, x1 - canvas.shape[1]), h - max(0, y1 - canvas.shape[0])
    x0, y0 = max(0, x0), max(0, y0)
    x1, y1 = x0 + (xi1 - xi0), y0 + (yi1 - yi0)
    if x1 <= x0 or y1 <= y0: return
    roi = canvas[y0:y1, x0:x1].astype(float)
    src = icon_bgra[yi0:yi1, xi0:xi1]
    alpha = src[:, :, 3:] / 255.0
    canvas[y0:y1, x0:x1] = (src[:, :, :3] * alpha + roi * (1.0 - alpha)).astype(np.uint8)

# ─── Red Dot Anchor Detector ──────────────────────────────────
# ─── Dual Red Dot Anchor Detector ─────────────────────────────
def detect_red_anchors(frame):
    """
    ตรวจจับจุดสีแดง (Red Fiducial Markers) ทั้ง 2 จุดบนขอบกระดาน:
    - จุดที่ 1: ขอบมุมบนซ้าย (ฝั่ง h1 / a1)
    - จุดที่ 2: ขอบมุมล่างขวา (ฝั่ง a8 / h8)
    คืนค่ารายการ [anchor1, anchor2] โดยเรียงจากบนซ้ายไปล่างขวา
    """
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    # สีแดงใน HSV ครอบคลุม 2 ช่วง: 0-12 และ 168-180
    mask1 = cv2.inRange(hsv, np.array([0,   120,  90]), np.array([12,  255, 255]))
    mask2 = cv2.inRange(hsv, np.array([168, 120,  90]), np.array([180, 255, 255]))
    red_mask = mask1 | mask2

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    red_mask = cv2.morphologyEx(red_mask, cv2.MORPH_OPEN, kernel)
    red_mask = cv2.morphologyEx(red_mask, cv2.MORPH_DILATE, kernel)

    contours, _ = cv2.findContours(red_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates = []

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area > 18:
            x, y, w, h = cv2.boundingRect(cnt)
            aspect = float(w) / float(h)
            if 0.35 <= aspect <= 2.8:
                candidates.append((area, (int(x + w / 2), int(y + h / 2))))

    candidates.sort(key=lambda item: item[0], reverse=True)
    
    anchors = []
    for area, pt in candidates:
        if len(anchors) == 0:
            anchors.append(pt)
        elif len(anchors) == 1:
            if np.hypot(pt[0] - anchors[0][0], pt[1] - anchors[0][1]) > 100:
                anchors.append(pt)
                break

    # เรียงให้จุด 1 อยู่ฝั่งบนซ้าย (x+y น้อยกว่า) และจุด 2 อยู่ฝั่งล่างขวา (x+y มากกว่า)
    if len(anchors) == 2:
        anchors.sort(key=lambda p: p[0] + p[1])

    return anchors

# ─── Corner Management ────────────────────────────────────────
calib_clicks = []
calib_mode   = False

def mouse_callback(event, x, y, flags, param):
    global calib_clicks, calib_mode
    if calib_mode and event == cv2.EVENT_LBUTTONDOWN:
        calib_clicks.append([float(x), float(y)])
        print(f"[CALIB] บันทึกจุดที่ {len(calib_clicks)}: ({x}, {y})")

def load_corners():
    if not os.path.exists(CORNERS_FILE):
        return None
    try:
        with open(CORNERS_FILE, 'r') as f:
            pts = np.array(json.load(f), dtype=np.float32)
            if pts.shape == (4, 2):
                return pts
    except Exception:
        pass
    return None

def save_corners(pts):
    with open(CORNERS_FILE, 'w') as f:
        json.dump(pts.tolist(), f)
    print(f"[INFO] บันทึกมุมใหม่ลงใน {CORNERS_FILE} สำเร็จ")

# ─── Camera Zoom Utilities ────────────────────────────────────
ZOOM_CONFIG_FILE = "camera_zoom.json"

def load_zoom():
    if os.path.exists(ZOOM_CONFIG_FILE):
        try:
            with open(ZOOM_CONFIG_FILE, 'r') as f:
                data = json.load(f)
                return float(data.get('zoom', 1.0))
        except Exception:
            pass
    return 1.0

def save_zoom(zoom):
    try:
        with open(ZOOM_CONFIG_FILE, 'w') as f:
            json.dump({'zoom': float(zoom)}, f)
    except Exception:
        pass

def apply_camera_zoom(frame, zoom_factor):
    """
    ขยายภาพด้วย Digital/Sensor Zoom ตรงกึ่งกลางภาพ (Center-Crop)
    โดยไม่สูญเสีย Aspect Ratio ทำให้หมากและกระดานมีขนาดใหญ่ขึ้นตามต้องการ
    โดยผู้ใช้ไม่ต้องขยับหรือยก iPhone เข้าใกล้กระดาน
    """
    if zoom_factor <= 1.001:
        return frame
    h, w = frame.shape[:2]
    new_w = int(w / zoom_factor)
    new_h = int(h / zoom_factor)
    x1 = (w - new_w) // 2
    y1 = (h - new_h) // 2
    x2 = x1 + new_w
    y2 = y1 + new_h
    cropped = frame[y1:y2, x1:x2]
    return cv2.resize(cropped, (w, h), interpolation=cv2.INTER_LINEAR)

def rescale_corners_for_zoom(corners, old_zoom, new_zoom, fw=1920, fh=1080):
    if old_zoom == new_zoom or old_zoom <= 0:
        return corners
    ratio = new_zoom / old_zoom
    cx = fw / 2.0
    cy = fh / 2.0
    scaled = corners.copy()
    scaled[:, 0] = np.clip((scaled[:, 0] - cx) * ratio + cx, 0.0, fw)
    scaled[:, 1] = np.clip((scaled[:, 1] - cy) * ratio + cy, 0.0, fh)
    return scaled

ORIENTATION_CONFIG_FILE = "board_orientation.json"

def load_orientation():
    if os.path.exists(ORIENTATION_CONFIG_FILE):
        try:
            with open(ORIENTATION_CONFIG_FILE, 'r') as f:
                data = json.load(f)
                return int(data.get('orientation', 3))
        except Exception:
            pass
    return 3

def save_orientation(orientation):
    try:
        with open(ORIENTATION_CONFIG_FILE, 'w') as f:
            json.dump({'orientation': int(orientation)}, f)
    except Exception:
        pass

def auto_detect_orientation_from_board(frame, corners):
    """
    ตรวจจับทิศทางกระดานอัตโนมัติจากการกระจายตัวของหมากขาวและหมากดำ:
    - หาค่าความสว่างของฝั่งซ้าย, ขวา, บน, ล่าง ในกรอบกระดาน
    - ฝั่งที่มีค่าความสว่างสูงกว่าคือฝั่งของ White (Rank 1-2)
    คืนค่า orientation (0=ล่าง, 1=ซ้าย, 2=บน, 3=ขวา)
    """
    try:
        x_min = int(np.min(corners[:, 0]))
        x_max = int(np.max(corners[:, 0]))
        y_min = int(np.min(corners[:, 1]))
        y_max = int(np.max(corners[:, 1]))
        w = x_max - x_min
        h = y_max - y_min
        if w < 100 or h < 100:
            return 3

        roi = frame[y_min:y_max, x_min:x_max]
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        rh, rw = gray.shape[:2]

        top_bright   = float(np.mean(gray[:rh//4, :]))
        bot_bright   = float(np.mean(gray[3*rh//4:, :]))
        left_bright  = float(np.mean(gray[:, :rw//4]))
        right_bright = float(np.mean(gray[:, 3*rw//4:]))

        horiz_diff = abs(right_bright - left_bright)
        vert_diff  = abs(bot_bright - top_bright)

        if horiz_diff > vert_diff:
            return 3 if right_bright > left_bright else 1
        else:
            return 0 if bot_bright > top_bright else 2
    except Exception:
        return 3

ORIENTATIONS = [
    "White at Bottom (Rank 1 ล่าง / Rank 8 บน)",
    "White at Left (Rank 1 ซ้าย / Rank 8 ขวา)",
    "White at Top (Rank 1 บน / Rank 8 ล่าง)",
    "White at Right (Rank 1 ขวา / Rank 8 ซ้าย)"
]

def order_corners_90deg(corners, orientation=0, dest_size=800):
    """
    จัดเรียง 4 มุมสำหรับมุมกล้อง Top-Down 90 องศา (Perfect Square):
    orientation (0, 1, 2, 3):
    - 0: White อยู่ล่าง (Rank 1 อยู่ล่าง, Black อยู่บน) [ค่าเริ่มต้น]
    - 1: White อยู่ซ้าย (Rank 1 อยู่ซ้าย, Black อยู่ขวา) [ตามมุมกระดานแบบพับ]
    - 2: White อยู่บน (Rank 1 อยู่บน, Black อยู่ล่าง)
    - 3: White อยู่ขวา (Rank 1 อยู่ขวา, Black อยู่ซ้าย)
    """
    pts = list(corners)
    # หา 4 มุมตามเข็มนาฬิกา: บนซ้าย, บนขวา, ล่างขวา, ล่างซ้าย
    pts_by_y = sorted(pts, key=lambda p: p[1])
    top_two = sorted(pts_by_y[:2], key=lambda p: p[0])
    bot_two = sorted(pts_by_y[2:], key=lambda p: p[0])

    c_tl = top_two[0]  # บนซ้าย
    c_tr = top_two[1]  # บนขวา
    c_br = bot_two[1]  # ล่างขวา
    c_bl = bot_two[0]  # ล่างซ้าย

    clock_pts = [c_tl, c_tr, c_br, c_bl]

    # Destination 2D standard coordinates:
    # a8=[0,0] (Black TL), h8=[dest,0] (Black TR), h1=[dest,dest] (White BR), a1=[0,dest] (White BL)
    dst = np.array([
        [0, 0],
        [dest_size, 0],
        [dest_size, dest_size],
        [0, dest_size]
    ], dtype=np.float32)

    # กำหนดมุม src_ordered ตาม orientation ให้ตรงกับกายภาพกระดานจริง 100%:
    if orientation == 0:
        # White at Bottom: Rank 1 ล่าง / Rank 8 บน (a8=tl, h8=tr, h1=br, a1=bl)
        src_ordered = [c_tl, c_tr, c_br, c_bl]
    elif orientation == 1:
        # White at Left: Rank 1 ซ้าย / Rank 8 ขวา (File a บน / File h ล่าง)
        # a8 บนขวา -> h8 ล่างขวา -> h1 ล่างซ้าย -> a1 บนซ้าย
        src_ordered = [c_tr, c_br, c_bl, c_tl]
    elif orientation == 2:
        # White at Top: Rank 1 บน / Rank 8 ล่าง
        src_ordered = [c_bl, c_br, c_tr, c_tl]
    else:
        # orientation == 3: White at Right: Rank 1 ขวา / Rank 8 ซ้าย (File a บน / File h ล่าง)
        # a8 บนซ้าย -> h8 ล่างซ้าย -> h1 ล่างขวา -> a1 บนขวา
        src_ordered = [c_tl, c_bl, c_br, c_tr]

    src = np.array(src_ordered, dtype=np.float32)
    M = cv2.getPerspectiveTransform(src, dst)

    corner_dict = {
        'a8': src_ordered[0],
        'h8': src_ordered[1],
        'h1': src_ordered[2],
        'a1': src_ordered[3],
        'tl': c_tl,
        'tr': c_tr,
        'br': c_br,
        'bl': c_bl
    }
    return M, dest_size, corner_dict

# ─── Direct 8x8 Grid Mapper (Wide Parallax & Low-Angle Support) ───
def point_to_chess_square(cx, cy, M, dest_size=800):
    """
    แปลงพิกัดกล้อง (cx, cy) -> พิกัดช่องหมากรุก (r, c) โดยตรง:
    - r (0..7): 0=Rank 8, 7=Rank 1
    - c (0..7): 0=File a, 7=File h
    """
    pt = np.array([[[cx, cy]]], dtype=np.float32)
    transformed = cv2.perspectiveTransform(pt, M)[0][0]
    tx, ty = transformed[0], transformed[1]

    # ขอบเขต Tolerance ป้องกัน Noise นอกกระดานหลุดเข้ามา
    OUT_OF_BOUNDS_TOLERANCE = 60.0
    if (tx < -OUT_OF_BOUNDS_TOLERANCE or tx > dest_size + OUT_OF_BOUNDS_TOLERANCE or
        ty < -OUT_OF_BOUNDS_TOLERANCE or ty > dest_size + OUT_OF_BOUNDS_TOLERANCE):
        return None

    # Clamping เพื่อให้หมากริมขอบกระดานไม่หลุดหาย
    tx_c = max(0.0, min(float(dest_size - 1), float(tx)))
    ty_c = max(0.0, min(float(dest_size - 1), float(ty)))

    cell_px = dest_size / 8.0
    c = int(tx_c / cell_px)   # 0=a, 7=h
    r = int(ty_c / cell_px)   # 0=Rank 8, 7=Rank 1

    r = max(0, min(7, r))
    c = max(0, min(7, c))
    return r, c

def get_team_color(frame, x, y, w, h):
    sy0 = max(0, y + h + BELOW_OFFSET)
    sy1 = min(frame.shape[0], sy0 + SAMPLE_H)
    sx0 = max(0, x)
    sx1 = min(frame.shape[1], x + w)
    if sy1 <= sy0 or sx1 <= sx0:
        return 'W'
    region = frame[sy0:sy1, sx0:sx1]
    if region.size == 0: return 'W'
    gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
    return 'W' if float(np.mean(gray)) > BRIGHT_THRESH else 'B'

# ─── Standard Initial Chess Board ─────────────────────────────
STANDARD_INITIAL_BOARD = [
    ['BR', 'BN', 'BB', 'BQ', 'BK', 'BB', 'BN', 'BR'],  # row 0: Rank 8
    ['BP', 'BP', 'BP', 'BP', 'BP', 'BP', 'BP', 'BP'],  # row 1: Rank 7
    [None, None, None, None, None, None, None, None],  # row 2: Rank 6
    [None, None, None, None, None, None, None, None],  # row 3: Rank 5
    [None, None, None, None, None, None, None, None],  # row 4: Rank 4
    [None, None, None, None, None, None, None, None],  # row 5: Rank 3
    ['WP', 'WP', 'WP', 'WP', 'WP', 'WP', 'WP', 'WP'],  # row 6: Rank 2
    ['WR', 'WN', 'WB', 'WQ', 'WK', 'WB', 'WN', 'WR'],  # row 7: Rank 1
]

def scan_board_frame(frame, frame_hsv, M, dest_size, kernel_open, kernel_dilate):
    """
    สแกนหากระดาน 1 เฟรม คืนค่า (board_8x8, detections_list, detected_count)
    """
    board = [[None]*8 for _ in range(8)]
    detections = []
    detected_count = 0

    for piece_name, cfg in TAGS.items():
        mask = cv2.inRange(frame_hsv, cfg['lower'], cfg['upper'])
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN,   kernel_open)
        mask = cv2.morphologyEx(mask, cv2.MORPH_DILATE, kernel_dilate)

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        for cnt in contours:
            if cv2.contourArea(cnt) < MIN_AREA: continue

            x, y, w, h = cv2.boundingRect(cnt)
            cx, cy = x + w // 2, y + h // 2

            grid_pos = point_to_chess_square(cx, cy, M, dest_size)
            if grid_pos is None: continue

            r, c = grid_pos
            team = get_team_color(frame, x, y, w, h)
            piece_id = f"{team}{cfg['code']}"

            board[r][c] = piece_id
            detected_count += 1
            detections.append((x, y, w, h, team, piece_name, piece_id, r, c, cfg['bgr']))

    return board, detections, detected_count

def evaluate_quad_consensus(passes, prev_board=None):
    """
    ทำการประเมินผลจากทั้ง 4 สแกน/4 มุม เพื่อเทียบความถูกต้องของข้อมูล
    กฎ 3/4 (Three-Fourths Quorum):
    - สำหรับแต่ละช่อง (r, c) ดึงผลลัพธ์จากทั้ง 4 สแกน: [pass0, pass1, pass2, pass3]
    - นับความถี่: หากผลลัพธ์ตรงกันอย่างน้อย 3 ใน 4 (>= 75%): ถือว่าข้อมูลถูกต้อง และนำค่านั้นมาใช้!
    - หากไม่ถึง 3 ใน 4: ถือว่าข้อมูลยังไม่นิ่ง ให้คงค่าเดิมไว้ (ไม่นำเข้ามามั่ว)
    """
    consensus_board = [[None]*8 for _ in range(8)]
    confidences = {}

    for r in range(8):
        for c in range(8):
            votes = [passes[i][r][c] for i in range(4)]
            most_common = Counter(votes).most_common(1)
            winner, count = most_common[0]

            if count >= 3:
                # ผ่านเกณฑ์ 3/4 ชัดเจน
                consensus_board[r][c] = winner
                confidences[(r, c)] = count / 4.0
            else:
                # ไม่ผ่านเกณฑ์ 3/4 -> ใช้ค่าเดิมที่มีอยู่ ไม่เอาเข้ามา
                if prev_board is not None:
                    consensus_board[r][c] = prev_board[r][c]
                else:
                    consensus_board[r][c] = None
                confidences[(r, c)] = 0.0

    # อัปเดตตามค่าจริงที่ตรวจจับได้โดยตรง ไม่ดัดแปลงข้อมูลจริง
    return consensus_board, confidences


# ─── Demographic & Rule Enforcement ───────────────────────────
def apply_demographic_filter(board):
    cleaned = [row[:] for row in board]
    # แถว 1-3 (r=5, 6, 7) เป็นฐานทัพขาว
    white_zone = [cleaned[r][c] for r in [5, 6, 7] for c in range(8) if cleaned[r][c]]
    if len(white_zone) >= 5:
        w_count = sum(1 for p in white_zone if p[0] == 'W')
        if w_count / float(len(white_zone)) >= 0.65:
            for r in [5, 6, 7]:
                for c in range(8):
                    p = cleaned[r][c]
                    if p and p[0] == 'B':
                        cleaned[r][c] = f"W{p[1:]}"

    # แถว 6-8 (r=0, 1, 2) เป็นฐานทัพดำ
    black_zone = [cleaned[r][c] for r in [0, 1, 2] for c in range(8) if cleaned[r][c]]
    if len(black_zone) >= 3:
        b_count = sum(1 for p in black_zone if p[0] == 'B')
        if b_count / float(len(black_zone)) >= 0.65:
            for r in [0, 1, 2]:
                for c in range(8):
                    p = cleaned[r][c]
                    if p and p[0] == 'W':
                        cleaned[r][c] = f"B{p[1:]}"
    return cleaned

MAX_PIECE_LIMITS = {'K': 1, 'Q': 1, 'R': 2, 'B': 2, 'N': 2, 'P': 8}

def enforce_chess_rules(board, confidences):
    cleaned = [row[:] for row in board]
    for team in ['W', 'B']:
        for p_type, max_limit in MAX_PIECE_LIMITS.items():
            piece_code = f"{team}{p_type}"
            positions = []
            for r in range(8):
                for c in range(8):
                    if cleaned[r][c] == piece_code:
                        positions.append((r, c, confidences.get((r, c), 0.0)))
            if len(positions) > max_limit:
                positions.sort(key=lambda x: x[2], reverse=True)
                for r, c, conf in positions[max_limit:]:
                    sq_name = f"{chr(ord('a')+c)}{8-r}"
                    team_str = "White" if team == 'W' else "Black"
                    print(f"🚫 [RULE ENFORCED] Pruned excess: {team_str} {p_type} at [{sq_name}] (quota {max_limit})")
                    cleaned[r][c] = None
    return cleaned

# ─── 2D Renderer ──────────────────────────────────────────────
def render_board_2d(board_state, highlight=None, anim=None, status="", flip_view=False, current_turn='W'):
    img = np.full((WIN_H, WIN_W, 3), CLR_BG, dtype=np.uint8)

    # ── Top Turn Indicator Box (ช่องบอกสถานะตาเดินบนหน้า 2D ชัดเจน) ──
    turn_str = "WHITE (ขาว)" if current_turn == 'W' else "BLACK (ดำ)"
    turn_box_bg = (18, 48, 18) if current_turn == 'W' else (50, 25, 25)
    turn_border = (0, 255, 120) if current_turn == 'W' else (100, 100, 255)
    turn_txt = f"TURN: {turn_str} | Move piece on board & press [Space]"
    turn_txt_col = (255, 255, 255) if current_turn == 'W' else (220, 220, 255)

    cv2.rectangle(img, (MARGIN, 6), (WIN_W - MARGIN, 36), turn_box_bg, -1)
    cv2.rectangle(img, (MARGIN, 6), (WIN_W - MARGIN, 36), turn_border, 2)
    cv2.putText(img, turn_txt, (MARGIN + 12, 27),
                cv2.FONT_HERSHEY_SIMPLEX, 0.44, turn_txt_col, 2)

    for r in range(8):
        for c in range(8):
            vr = (7 - r) if flip_view else r
            vc = (7 - c) if flip_view else c

            x0 = MARGIN + vc * CELL_SIZE
            y0 = MARGIN + vr * CELL_SIZE
            is_light = ((r + c) % 2 != 0)  # สลับ Pattern สีตารางให้ตรงกับกระดานจริง
            clr = CLR_LIGHT if is_light else CLR_DARK
            cv2.rectangle(img, (x0, y0), (x0 + CELL_SIZE, y0 + CELL_SIZE), clr, -1)

            if highlight:
                hl_col = None
                if (r, c) == highlight[0]: hl_col = CLR_HL_SRC
                elif (r, c) == highlight[1]: hl_col = CLR_HL_DST
                if hl_col:
                    ov = img[y0:y0+CELL_SIZE, x0:x0+CELL_SIZE].copy()
                    cv2.rectangle(ov, (0, 0), (CELL_SIZE, CELL_SIZE), hl_col, -1)
                    cv2.addWeighted(ov, 0.45, img[y0:y0+CELL_SIZE, x0:x0+CELL_SIZE], 0.55, 0,
                                    img[y0:y0+CELL_SIZE, x0:x0+CELL_SIZE])

            piece_id = board_state[r][c]
            if piece_id:
                cx = x0 + CELL_SIZE // 2
                cy = y0 + CELL_SIZE // 2
                blit_alpha(img, get_piece_icon(piece_id), cx, cy)

    if anim:
        sp = anim['src_px']; dp = anim['dst_px']; t = anim['progress']
        if flip_view:
            sp = (MARGIN + BOARD_SIZE - (sp[0] - MARGIN), MARGIN + BOARD_SIZE - (sp[1] - MARGIN))
            dp = (MARGIN + BOARD_SIZE - (dp[0] - MARGIN), MARGIN + BOARD_SIZE - (dp[1] - MARGIN))
        cur_px = (int(sp[0] + (dp[0] - sp[0]) * t), int(sp[1] + (dp[1] - sp[1]) * t))
        blit_alpha(img, get_piece_icon(anim['piece']), cur_px[0], cur_px[1])
        if sp != dp:
            cv2.arrowedLine(img, sp, dp, CLR_ARROW, 3, tipLength=0.25)

    cv2.rectangle(img, (MARGIN, MARGIN), (MARGIN + BOARD_SIZE, MARGIN + BOARD_SIZE), (60, 60, 60), 1)

    for i in range(8):
        rank = str(1 + i) if flip_view else str(8 - i)
        cv2.putText(img, rank, (MARGIN // 2 - 4, MARGIN + i * CELL_SIZE + CELL_SIZE // 2 + 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, CLR_TEXT, 1)
        file_c = chr(ord('h') - i) if flip_view else chr(ord('a') + i)
        cv2.putText(img, file_c, (MARGIN + i * CELL_SIZE + CELL_SIZE // 2 - 5, MARGIN + BOARD_SIZE + MARGIN // 2 + 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, CLR_TEXT, 1)

    view_tag = " [VIEW: BLACK BOTTOM]" if flip_view else ""
    cv2.putText(img, f"{status}{view_tag}", (MARGIN, WIN_H - 12),
                cv2.FONT_HERSHEY_SIMPLEX, 0.40, (160, 220, 160), 1)

    return img

def is_plausible_chess_move(piece, sr, sc, dr, dc):
    """
    ตรวจสอบว่าการเดินจาก (sr, sc) ไปยัง (dr, dc) เป็นไปตามกติกาหมากรุกสากลเบื้องต้นหรือไม่
    (ป้องกัน ghost move เช่น เบี้ยกระโดดข้ามกระดาน หรือเดินผิดทิศทาง)
    """
    if sr == dr and sc == dc:
        return False
    color = piece[0]  # 'W' หรือ 'B'
    ptype = piece[1]  # 'P', 'R', 'N', 'B', 'Q', 'K'
    dr_diff = dr - sr
    dc_diff = dc - sc
    abs_r = abs(dr_diff)
    abs_c = abs(dc_diff)

    if ptype == 'P':
        # Pawn:
        # r=0 (ดำแถวหลัง), r=1 (เบี้ยดำเริ่มต้น)
        # r=6 (เบี้ยขาวเริ่มต้น), r=7 (ขาวแถวหลัง)
        # ขาวเดินขึ้น: dr_diff < 0 (เช่น จาก r=6 ไป r=5 หรือ r=4)
        # ดำเดินลง: dr_diff > 0 (เช่น จาก r=1 ไป r=2 หรือ r=3)
        if color == 'W':
            if dr_diff == -1 and abs_c == 0:
                return True
            if sr == 6 and dr_diff == -2 and abs_c == 0:
                return True
            if dr_diff == -1 and abs_c == 1:
                return True
            return False
        else: # 'B'
            if dr_diff == 1 and abs_c == 0:
                return True
            if sr == 1 and dr_diff == 2 and abs_c == 0:
                return True
            if dr_diff == 1 and abs_c == 1:
                return True
            return False

    elif ptype == 'N':
        return (abs_r == 2 and abs_c == 1) or (abs_r == 1 and abs_c == 2)

    elif ptype == 'B':
        return abs_r == abs_c and abs_r > 0

    elif ptype == 'R':
        return (abs_r == 0 and abs_c > 0) or (abs_c == 0 and abs_r > 0)

    elif ptype == 'Q':
        return (abs_r == abs_c and abs_r > 0) or (abs_r == 0 and abs_c > 0) or (abs_c == 0 and abs_r > 0)

    elif ptype == 'K':
        if max(abs_r, abs_c) == 1:
            return True
        if abs_r == 0 and abs_c == 2 and ((color == 'W' and sr == 7) or (color == 'B' and sr == 0)):
            return True
        return False

    return False

def animate_move(board_2d, src_rc, dst_rc, win_name, frames=20, delay=16, flip_view=False, current_turn='W'):
    sr, sc = src_rc; dr, dc = dst_rc
    piece = board_2d[sr][sc]
    if not piece: return

    board_2d[sr][sc] = None
    sp = (MARGIN + sc * CELL_SIZE + CELL_SIZE // 2, MARGIN + sr * CELL_SIZE + CELL_SIZE // 2)
    dp = (MARGIN + dc * CELL_SIZE + CELL_SIZE // 2, MARGIN + dr * CELL_SIZE + CELL_SIZE // 2)
    src_sq = f"{chr(ord('a')+sc)}{8-sr}"
    dst_sq = f"{chr(ord('a')+dc)}{8-dr}"

    for f in range(frames + 1):
        t = f / float(frames)
        cur_px = (int(sp[0] + (dp[0] - sp[0]) * t), int(sp[1] + (dp[1] - sp[1]) * t))
        anim_data = {'piece': piece, 'src_px': sp, 'dst_px': dp, 'cur_px': cur_px, 'progress': t}
        frame = render_board_2d(board_2d, highlight=(src_rc, dst_rc), anim=anim_data,
                                status=f"Move: {src_sq}->{dst_sq}", flip_view=flip_view, current_turn=current_turn)
        cv2.imshow(win_name, frame)
        if cv2.waitKey(delay) & 0xFF == ord('q'): break

    board_2d[dr][dc] = piece

# ─── Main Pipeline ────────────────────────────────────────────
def main():
    global calib_clicks, calib_mode

    corners = load_corners()
    if corners is None:
        corners = np.array([[480.0, 60.0], [1440.0, 60.0], [1440.0, 1020.0], [480.0, 1020.0]], dtype=np.float32)

    dest_size = 800
    orientation = load_orientation()

    cam_index = 1  # iPhone Continuity Camera
    cap = cv2.VideoCapture(cam_index)
    if not cap.isOpened():
        print(f"[ERROR] ไม่สามารถเปิดกล้อง iPhone (Index {cam_index}) ได้")
        print("[HINT] ตรวจสอบว่า iPhone เชื่อมต่อ USB/WiFi และ Continuity Camera เปิดอยู่")
        return
    print(f"[CAMERA] เปิดกล้อง Index {cam_index} สำเร็จ")

    # ตรวจสอบขนาด Frame และปรับสเกลกรอบมุมเริ่มต้นให้พอดีอัตโนมัติ (รอวอร์มกล้อง Continuity Camera)
    fw, fh = 1920, 1080
    test_frame = None
    ret = False
    for _ in range(40):
        ret, test_frame = cap.read()
        if ret and test_frame is not None:
            break
        cv2.waitKey(40)

    if ret and test_frame is not None:
        fh, fw = test_frame.shape[:2]
        print(f"[CAMERA] ความละเอียดกล้อง: {fw}x{fh}")
        if np.max(corners[:, 0]) > fw or np.max(corners[:, 1]) > fh:
            scale_x = fw / 1920.0
            scale_y = fh / 1080.0
            corners[:, 0] *= scale_x
            corners[:, 1] *= scale_y
            print(f"[INFO] Auto-scaled corners → {fw}x{fh}")

    # ตรวจสอบ CLI Arguments
    assume_mode = 1
    flip_cli = False
    auto_orient_cli = False
    flip_view_2d = False

    args_lower = [a.lower() for a in sys.argv[1:]]
    if '0' in args_lower:
        assume_mode = 0
    elif '1' in args_lower:
        assume_mode = 1

    if any(a in args_lower for a in ('flip', '--flip', '-f', 'reverse')):
        flip_cli = True
    if any(a in args_lower for a in ('auto', '--auto', '-a')):
        auto_orient_cli = True
    if any(a in args_lower for a in ('black', '--black', '-b', 'view-black')):
        flip_view_2d = True

    # ตรวจสอบทิศทางกระดานสดจากตำแหน่งของหมากขาว/ดำจริงในกล้อง (ป้องกันการเดินสลับสี 100%)
    if test_frame is not None:
        live_orient = auto_detect_orientation_from_board(test_frame, corners)
        if flip_cli:
            orientation = (live_orient + 2) % 4
            save_orientation(orientation)
            print(f"🔄 [CLI FLIP] สลับทิศทางกระดานกลับด้าน 180°: {ORIENTATIONS[orientation]}")
        else:
            orientation = live_orient
            save_orientation(orientation)
            print(f"🧭 [AUTO-ORIENT] ตรวจพบตำแหน่งหมากจริง: {ORIENTATIONS[orientation]}")
    else:
        print(f"🧭 [ORIENT] ทิศทางกระดานปัจจุบัน: {ORIENTATIONS[orientation]} (กด [f] เพื่อสลับ 180°)")

    # โหลดค่า Zoom เริ่มต้น (1.0x ถึง 4.0x)
    zoom_factor = load_zoom()
    print(f"[CAMERA] กำลังขยาย Zoom: {zoom_factor:.1f}x (กด [z]/[x] เพื่อซูมกล้องเข้า/ออก)")

    if assume_mode == 1:
        board_2d = [row[:] for row in STANDARD_INITIAL_BOARD]
        has_initial_render = True
        is_locked = True
        is_scanning = False
        last_status_msg = "[LOCKED] Mode 1: Assumed standard initial setup! Press [Space] after move."
    else:
        board_2d = [[None]*8 for _ in range(8)]
        has_initial_render = False
        is_locked = False
        is_scanning = True
        last_status_msg = "[SCANNING] Mode 0: Scanning starting setup from camera..."

    scan_passes = []
    scan_frame_timer = 0
    init_stable_cycles = 0
    current_turn = 'W'  # White เดินก่อนเสมอตามกติกาหมากรุกสากล

    kernel_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    kernel_dilate = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))

    win_cam = f"iPhone Camera (Index {cam_index})"
    win_2d  = "2D Digital Twin Chess Board"
    cv2.namedWindow(win_cam, cv2.WINDOW_NORMAL)
    cv2.namedWindow(win_2d,  cv2.WINDOW_NORMAL)
    cv2.setMouseCallback(win_cam, mouse_callback)
    cv2.resizeWindow(win_2d, WIN_W, WIN_H)

    cached_anchors = []

    print("=" * 68)
    print(" Hybrid Chess Pipeline v12 (Perfect Square 90° + Multi-Orientation)")
    print(" 🟩 กรอบเขียว: Perfect Square 90° (จัตุรัสสมบูรณ์แบบ 1:1)")
    print(f" 🧭 ทิศทางกระดาน: {ORIENTATIONS[orientation]}")
    print(" 🔄 [f]     : กลับด้านกระดาน 180° ทันที (ขวา ⇋ ซ้าย / ล่าง ⇋ บน)")
    print(" 🔄 [F / v] : สลับมุมมองกระดาน 2D (มุมมองฝั่งขาว ⇋ ฝั่งดำ)")
    print(" 🧭 [u]     : สแกนตรวจสอบทิศทางกระดานอัตโนมัติจากสีหมาก (Auto-Orient)")
    print(" 🧭 [o]     : หมุนทิศทางกระดาน 90° (ล่าง -> ซ้าย -> บน -> ขวา)")
    print(" 🔢 [1 / 0] : โหมดเริ่มต้นมาตรฐาน (1) / โหมดสแกนสดจากกล้อง (0)")
    print(" ⚡ เมื่อขยับหมากเสร็จ: กดปุ่ม [Spacebar] เพื่อสแกนและอัปเดตตารางดิจิทัล")
    print(" [z / x] : ซูมกล้องเข้า / ออก (+/- 0.1x) เพื่อไม่ต้องยก iPhone สูงเกินไป")
    print(" [Z / X] : ซูมกล้องเข้า / ออก ขั้นใหญ่ (+/- 0.5x)")
    print(" [t]     : สลับตาเดินหมากด้วยมือ (White ⇋ Black)")
    print(" [w / s] : เลื่อนกรอบจัตุรัส ขึ้น / ลง")
    print(" [a / d] : เลื่อนกรอบจัตุรัส ซ้าย / ขวา")
    print(" [+ / -] : ขยาย / ย่อ ขนาดกรอบจัตุรัส (คงรูปทรงจัตุรัส 90° เสมอ)")
    print(" [p]     : บังคับรีเซ็ตกรอบเป็น สี่เหลี่ยมจัตุรัส 1:1 ทันที")
    print(" [c]     : Calibrate 4 มุมขอบกระดานสดๆ บนจอกล้อง")
    print(" [r]     : รีเซ็ตกระดาน 2D ให้ว่างเปล่า | [q] : ออกจากโปรแกรม")
    print("=" * 68)

    drop_count = 0
    while True:
        ret, raw_frame = cap.read()
        if not ret or raw_frame is None:
            drop_count += 1
            if drop_count > 60:
                print("\n[ERROR] ไม่สามารถรับสัญญาณภาพจากกล้อง iPhone ได้ต่อเนื่อง (การเชื่อมต่อหลุด)")
                break
            cv2.waitKey(30)
            continue
        drop_count = 0

        frame = apply_camera_zoom(raw_frame, zoom_factor)

        cam_display = frame.copy()
        frame_hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        # ── Calibration Mode ─────────────────────────────────
        if calib_mode:
            cv2.putText(cam_display, f"CALIBRATION: Click Corner {len(calib_clicks)+1}/4",
                        (30, 60), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 255), 3)
            for idx, pt in enumerate(calib_clicks):
                cv2.circle(cam_display, (int(pt[0]), int(pt[1])), 8, (0, 0, 255), -1)
                cv2.putText(cam_display, str(idx+1), (int(pt[0])+10, int(pt[1])-10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

            if len(calib_clicks) == 4:
                corners = np.array(calib_clicks, dtype=np.float32)
                save_corners(corners)
                calib_mode = False
                calib_clicks.clear()
                scan_passes.clear()
                print("[INFO] บันทึกมุมกระดานใหม่เรียบร้อย")

            cam_h, cam_w = cam_display.shape[:2]
            cv2.imshow(win_cam, cv2.resize(cam_display, (760, int(cam_h * 760 / cam_w))))
            if cv2.waitKey(1) & 0xFF == ord('c'):
                calib_mode = False; calib_clicks.clear()
            continue

        # ── 1. ตรวจจับจุดสีแดง 2 จุด (Dual Red Anchors) ───────
        anchors = detect_red_anchors(frame)
        if len(anchors) > 0:
            cached_anchors = anchors
        else:
            anchors = cached_anchors

        # คำนวณ Homography Matrix M สำหรับมุมมอง Top-down 90 องศา (Perfect Square)
        M, dest_size, corner_dict = order_corners_90deg(corners, orientation=orientation, dest_size=800)

        # ── 2. วาดกรอบ Area Green (Perfect Square 90 องศา) และเส้นตาราง 8x8 ──
        pts_poly = corners.astype(np.int32).reshape((-1, 1, 2))
        cv2.polylines(cam_display, [pts_poly], isClosed=True, color=(0, 255, 0), thickness=3)

        c_tl = (int(corner_dict['tl'][0]), int(corner_dict['tl'][1]))
        c_tr = (int(corner_dict['tr'][0]), int(corner_dict['tr'][1]))
        c_br = (int(corner_dict['br'][0]), int(corner_dict['br'][1]))
        c_bl = (int(corner_dict['bl'][0]), int(corner_dict['bl'][1]))

        # วาดเส้นตารางย่อย 8x8 ภายในกรอบ เพื่อให้ผู้ใช้เทียบกับช่องจริงบนกระดานได้แม่นยำ
        for i in range(1, 8):
            t = i / 8.0
            tx = int(c_tl[0] + t * (c_tr[0] - c_tl[0]))
            ty = int(c_tl[1] + t * (c_tr[1] - c_tl[1]))
            bx = int(c_bl[0] + t * (c_br[0] - c_bl[0]))
            by = int(c_bl[1] + t * (c_br[1] - c_bl[1]))
            cv2.line(cam_display, (tx, ty), (bx, by), (0, 150, 0), 1)

            lx = int(c_tl[0] + t * (c_bl[0] - c_tl[0]))
            ly = int(c_tl[1] + t * (c_bl[1] - c_tl[1]))
            rx = int(c_tr[0] + t * (c_br[0] - c_tr[0]))
            ry = int(c_tr[1] + t * (c_br[1] - c_tr[1]))
            cv2.line(cam_display, (lx, ly), (rx, ry), (0, 150, 0), 1)

        # แสดงป้ายชื่อชัดเจนว่าฝั่งไหนคือ WHITE ฝั่งไหนคือ BLACK
        c_a1 = (int(corner_dict['a1'][0]), int(corner_dict['a1'][1]))
        c_h1 = (int(corner_dict['h1'][0]), int(corner_dict['h1'][1]))
        c_a8 = (int(corner_dict['a8'][0]), int(corner_dict['a8'][1]))
        c_h8 = (int(corner_dict['h8'][0]), int(corner_dict['h8'][1]))

        mid_w = (int((c_a1[0] + c_h1[0]) / 2), int((c_a1[1] + c_h1[1]) / 2))
        mid_b = (int((c_a8[0] + c_h8[0]) / 2), int((c_a8[1] + c_h8[1]) / 2))

        # ป้ายฝั่ง White (สีขาว) และ Black (สีแดง/ชมพู)
        if abs(mid_w[0] - mid_b[0]) > abs(mid_w[1] - mid_b[1]):
            if mid_w[0] > mid_b[0]:
                w_lbl_pos = (mid_w[0] - 220, mid_w[1] + 5)
                b_lbl_pos = (mid_b[0] + 15,  mid_b[1] + 5)
            else:
                w_lbl_pos = (mid_w[0] + 15,  mid_w[1] + 5)
                b_lbl_pos = (mid_b[0] - 220, mid_b[1] + 5)
        else:
            if mid_w[1] >= mid_b[1]:
                w_lbl_pos = (mid_w[0] - 110, mid_w[1] + 28)
                b_lbl_pos = (mid_b[0] - 110, mid_b[1] - 14)
            else:
                w_lbl_pos = (mid_w[0] - 110, mid_w[1] - 14)
                b_lbl_pos = (mid_b[0] - 110, mid_b[1] + 28)

        cv2.putText(cam_display, "▲ WHITE (Rank 1-2) ▲", w_lbl_pos,
                    cv2.FONT_HERSHEY_SIMPLEX, 0.58, (255, 255, 255), 2)
        cv2.putText(cam_display, "▼ BLACK (Rank 7-8) ▼", b_lbl_pos,
                    cv2.FONT_HERSHEY_SIMPLEX, 0.58, (100, 100, 255), 2)

        # มาร์กเกอร์จุด 4 มุมกระดาน (a1, h1, a8, h8)
        cv2.circle(cam_display, c_a1, 8, (255, 255, 255), -1)
        cv2.putText(cam_display, "a1", (c_a1[0] + 8, c_a1[1] - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.50, (255, 255, 255), 2)

        cv2.circle(cam_display, c_h1, 8, (255, 255, 255), -1)
        cv2.putText(cam_display, "h1", (c_h1[0] - 25, c_h1[1] - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.50, (255, 255, 255), 2)

        cv2.circle(cam_display, c_a8, 8, (100, 100, 255), -1)
        cv2.putText(cam_display, "a8", (c_a8[0] + 8, c_a8[1] + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.50, (100, 100, 255), 2)

        cv2.circle(cam_display, c_h8, 8, (100, 100, 255), -1)
        cv2.putText(cam_display, "h8", (c_h8[0] - 25, c_h8[1] + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.50, (100, 100, 255), 2)

        # ไฮไลต์จุดแดง (Red Anchors) ถ้าตรวจพบในภาพ
        for anc in anchors:
            cv2.circle(cam_display, (int(anc[0]), int(anc[1])), 14, (0, 0, 255), 2)
            cv2.circle(cam_display, (int(anc[0]), int(anc[1])), 5,  (0, 0, 255), -1)

        instant_board, detections, detected_count = scan_board_frame(
            frame, frame_hsv, M, dest_size, kernel_open, kernel_dilate
        )

        for (x, y, w, h, team, piece_name, piece_id, r, c, clr) in detections:
            sq_name = f"{chr(ord('a')+c)}{8-r}"
            lbl = f"{team} {piece_name} [{sq_name}]"
            cv2.rectangle(cam_display, (x, y), (x + w, y + h), clr, 2)
            cv2.putText(cam_display, lbl, (x, max(y - 6, 12)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.48, clr, 2)

        # ── 3. 4-Way Cross-Sweeping & 3/4 Quorum Consensus ───
        if is_scanning:
            scan_frame_timer += 1
            sweep_idx = min(3, len(scan_passes))
            sweep_defs = [
                (c_a1, c_h8, "⚡ SWEEP 1/4: Red 1 -> Red 2 (Diagonal Sweep)", (0, 165, 255)),
                (c_h8, c_a1, "⚡ SWEEP 2/4: Red 2 -> Red 1 (Reverse Sweep)", (0, 165, 255)),
                (c_a8, c_h1, "⚡ SWEEP 3/4: Non-Red 1 -> Non-Red 2 (Cross Sweep)", (255, 255, 0)),
                (c_h1, c_a8, "⚡ SWEEP 4/4: Non-Red 2 -> Non-Red 1 (Cross Back)", (255, 255, 0))
            ]
            p_start, p_end, sweep_name, sweep_color = sweep_defs[sweep_idx]

            # วาด Laser Line กวาดข้ามกระดานตามเวกเตอร์ Sweep
            sub_step = (scan_frame_timer % 3)
            t_laser = (sub_step + 1) / 3.0
            lx = int(p_start[0] + t_laser * (p_end[0] - p_start[0]))
            ly = int(p_start[1] + t_laser * (p_end[1] - p_start[1]))

            dx = float(p_end[0] - p_start[0])
            dy = float(p_end[1] - p_start[1])
            length = np.hypot(dx, dy)
            if length > 0:
                ux, uy = -dy / length, dx / length
                laser_p1 = (int(lx + ux * 300), int(ly + uy * 300))
                laser_p2 = (int(lx - ux * 300), int(ly - uy * 300))
                cv2.line(cam_display, laser_p1, laser_p2, sweep_color, 3, cv2.LINE_AA)
                cv2.circle(cam_display, (lx, ly), 7, sweep_color, -1)

            cv2.putText(cam_display, sweep_name, (30, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.65, sweep_color, 2)

            # บันทึก instant_board ทุกเฟรมจนครบ 16 เฟรม (~0.5 วินาที) เพื่อรวบรวมข้อมูลที่แม่นยำ
            scan_passes.append([row[:] for row in instant_board])

            if len(scan_passes) >= 16:
                # วิเคราะห์ 16 เฟรม: นับความถี่การตรวจพบหมากในแต่ละช่อง
                hit_counts = [[0]*8 for _ in range(8)]
                detected_types = [[None]*8 for _ in range(8)]
                for r in range(8):
                    for c in range(8):
                        readings = [scan_passes[i][r][c] for i in range(len(scan_passes)) if scan_passes[i][r][c] is not None]
                        hit_counts[r][c] = len(readings)
                        if readings:
                            detected_types[r][c] = Counter(readings).most_common(1)[0][0]

                scan_passes.clear()
                scan_frame_timer = 0

                # ── Differential Tracking จากกระดานก่อนหน้า ──
                # 1. หาช่องที่เคยมีหมากในบอร์ดดิจิทัล แต่ตอนนี้แทบไม่ตรวจพบสติกเกอร์ (หมากถูกยกออกไป)
                cand_emptied = []
                for r in range(8):
                    for c in range(8):
                        if board_2d[r][c] is not None:
                            # ถ้าตรวจพบ < 2 จาก 16 เฟรม แสดงว่าหมากถูกยกออกไปจริง
                            if hit_counts[r][c] < 2:
                                cand_emptied.append((r, c, board_2d[r][c], hit_counts[r][c]))

                # 2. หาช่องปลายทางที่มีหมากเข้ามาใหม่
                cand_occupied = []
                for r in range(8):
                    for c in range(8):
                        # กรณีที่ 1: ช่องนี้เดิม "ว่าง" ในตารางดิจิทัล แต่ตอนนี้มีสติกเกอร์ (ตรวจพบ >= 2 เฟรม)
                        if board_2d[r][c] is None:
                            if hit_counts[r][c] >= 2 and detected_types[r][c] is not None:
                                cand_occupied.append((r, c, detected_types[r][c], hit_counts[r][c], True))
                        # กรณีที่ 2: ช่องนี้เดิมมีหมากอยู่แล้ว เกิดการกินหมาก (ต้องตรวจพบชัดเจน >= 6 เฟรม และเป็นหมากต่างสี/ชนิด)
                        else:
                            if hit_counts[r][c] >= 6 and detected_types[r][c] is not None:
                                if board_2d[r][c] != detected_types[r][c]:
                                    cand_occupied.append((r, c, detected_types[r][c], hit_counts[r][c], False))

                # จับคู่การเดินหมากที่แท้จริง: ในโลกจริง ผู้ใช้จะขยับหมากทีละ 1 ตัวอย่างแม่นยำ
                candidate_moves = []
                for (sr, sc, p_src, h_src) in cand_emptied:
                    for (dr, dc, p_dst, h_dst, is_empty) in cand_occupied:
                        if (sr, sc) == (dr, dc):
                            continue

                        dist_r = abs(sr - dr)
                        dist_c = abs(sc - dc)
                        total_dist = dist_r + dist_c

                        # กฎระยะทางทางกายภาพ:
                        # ถ้าเป็น Pawn (เบี้ย): เดินหน้าได้ 1-2 ช่องเท่านั้น (และห้ามข้ามกระดานเด็ดขาด!)
                        if p_src and p_src[1:] == 'P':
                            if is_empty:
                                if dist_c > 1 or dist_r > 2:
                                    continue  # เบี้ยไม่สามารถเดินเกิน 2 ช่องหรือข้ามคอลัมน์กว้างได้
                            else:
                                # กินหมาก: ทแยง 1 ช่องเท่านั้น
                                if dist_c != 1 or dist_r != 1:
                                    continue

                        score = 10
                        # ให้คะแนนสูงเป็นพิเศษสำหรับช่องที่เดิมว่าง (เพราะการเดินส่วนใหญ่เป็นการเดินเข้าช่องว่าง)
                        if is_empty:
                            score += 200

                        # โบนัสสูงถ้าชนิดหมากตรงกัน (Pawn->Pawn, Knight->Knight ฯลฯ)
                        if p_dst and p_dst[1:] == p_src[1:]:
                            score += 100
                        # โบนัสถ้าสีทีมตรงกัน
                        if p_dst and p_dst[0] == p_src[0]:
                            score += 50

                        # หักคะแนนตามระยะทางอย่างสมเหตุสมผล เพื่อเลือกช่องที่ใกล้เคียงที่สุด
                        score -= total_dist * 15

                        candidate_moves.append({
                            'src': (sr, sc),
                            'dst': (dr, dc),
                            'piece': p_src,
                            'score': score
                        })

                # Fallback 1: ถ้า cand_emptied มี 1 ตัวแต่ cand_occupied ยังหาไม่เจอ
                if not candidate_moves and len(cand_emptied) == 1:
                    sr, sc, p_src, _ = cand_emptied[0]
                    best_dr, best_dc, max_h = None, None, 1
                    for r in range(8):
                        for c in range(8):
                            if board_2d[r][c] is None and hit_counts[r][c] > max_h:
                                # ตรวจสอบระยะถ้าเป็น Pawn
                                if p_src and p_src[1:] == 'P':
                                    if abs(sc - c) > 1 or abs(sr - r) > 2:
                                        continue
                                max_h = hit_counts[r][c]
                                best_dr, best_dc = r, c
                    if best_dr is not None:
                        candidate_moves.append({
                            'src': (sr, sc),
                            'dst': (best_dr, best_dc),
                            'piece': p_src,
                            'score': 50
                        })

                # Fallback 2: ถ้า cand_occupied มี 1 ตัวแต่ cand_emptied ยังไม่หลุด
                if not candidate_moves and len(cand_occupied) == 1:
                    dr, dc, p_dst, _, is_empty = cand_occupied[0]
                    best_sr, best_sc, min_h = None, None, 16
                    for r in range(8):
                        for c in range(8):
                            if board_2d[r][c] is not None and board_2d[r][c] == p_dst:
                                if hit_counts[r][c] < min_h:
                                    min_h = hit_counts[r][c]
                                    best_sr, best_sc = r, c
                    if best_sr is not None and (best_sr, best_sc) != (dr, dc):
                        candidate_moves.append({
                            'src': (best_sr, best_sc),
                            'dst': (dr, dc),
                            'piece': board_2d[best_sr][best_sc],
                            'score': 50
                        })

                if candidate_moves:
                    # ⭐ บังคับเลือกเฉพาะการเดินที่ดีที่สุดเพียง 1 ตัวเท่านั้น! (ป้องกัน Double Move 100%)
                    best_move = max(candidate_moves, key=lambda m: m['score'])
                    if best_move['score'] > 0:
                        sr, sc = best_move['src']
                        dr, dc = best_move['dst']
                        moved_p = board_2d[sr][sc] if board_2d[sr][sc] is not None else best_move['piece']

                        src_name = f"{chr(ord('a')+sc)}{8-sr}"
                        dst_name = f"{chr(ord('a')+dc)}{8-dr}"
                        print(f"\n⚡ [MOVE SYNCED] {moved_p}: {src_name} -> {dst_name}")
                        animate_move(board_2d, (sr, sc), (dr, dc), win_2d, flip_view=flip_view_2d)

                        # 👉 อัปเดตเฉพาะช่องที่ขยับจริง (ช่องอื่นทั้ง 63 ช่องคงเดิม 100%)
                        board_2d[dr][dc] = moved_p
                        board_2d[sr][sc] = None

                        # 🏰 ตรวจจับการเข้าป้อม (Castling): ขยับเรือ (Rook) ตามด้วย
                        if moved_p and moved_p[1] == 'K' and abs(sc - dc) == 2:
                            rook_row = sr
                            if dc == 6:  # Kingside (O-O)
                                rook_src = (rook_row, 7); rook_dst = (rook_row, 5)
                            else:        # Queenside (O-O-O)
                                rook_src = (rook_row, 0); rook_dst = (rook_row, 3)
                            animate_move(board_2d, rook_src, rook_dst, win_2d, flip_view=flip_view_2d)
                            board_2d[rook_dst[0]][rook_dst[1]] = board_2d[rook_src[0]][rook_src[1]]
                            board_2d[rook_src[0]][rook_src[1]] = None
                            print(f"🏰 [CASTLING] เข้าป้อมสำเร็จ! ย้ายเรือ {rook_src} -> {rook_dst} เรียบร้อย")

                        last_status_msg = f"[SYNCED] Moved {moved_p}: {src_name}->{dst_name} | Waiting for next move"
                        print(f"✅ [SYNCED] อัปเดตตารางดิจิทัลตรงกับโลกจริงเป๊ะๆ แล้ว! เข้าสู่สถานะหยุดรอตาต่อไป")
                    else:
                        last_status_msg = "[SYNCED] No change detected | Digital board preserved"
                        print("[INFO] ไม่พบการขยับหมาก ตารางดิจิทัลคงเดิม 100% (เข้าสู่สถานะหยุดรอ)")
                else:
                    last_status_msg = "[SYNCED] No change detected | Digital board preserved"
                    print("[INFO] ไม่พบการขยับหมาก ตารางดิจิทัลคงเดิม 100% (เข้าสู่สถานะหยุดรอ)")

                is_locked = True
                is_scanning = False

        # วาด Badge สถานะมุมซ้ายบนของหน้าต่างกล้อง
        if is_scanning:
            badge_txt = f"STATE: [SCANNING ({len(scan_passes)}/16)] Checking board changes..."
            badge_col = (0, 215, 255)
        elif is_locked:
            badge_txt = "STATE: [STOPPED/WAITING] Move a piece & press [Space]"
            badge_col = (0, 255, 0)
        else:
            badge_txt = "STATE: [INITIALIZING] Verifying Start Board..."
            badge_col = (255, 200, 0)
        cv2.putText(cam_display, badge_txt, (30, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.65, badge_col, 2)
        orient_txt = f"ORIENT: {ORIENTATIONS[orientation].split(' (')[0]} [f: Flip 180 | o: Rotate | u: Auto]"
        cv2.putText(cam_display, orient_txt, (30, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.50, (0, 255, 255), 2)
        zoom_txt = f"ZOOM: {zoom_factor:.1f}x [z: In | x: Out] | [w/s/a/d: Move | +/-: Size]"
        cv2.putText(cam_display, zoom_txt, (30, 105), cv2.FONT_HERSHEY_SIMPLEX, 0.50, (0, 255, 120), 2)

        # Render 2D Board
        if last_status_msg.startswith("[LOCKED]") or last_status_msg.startswith("[SCANNING]") or last_status_msg.startswith("[INIT]"):
            display_status = last_status_msg
        else:
            status_prefix = "[LOCKED]" if is_locked else "[SCANNING]"
            display_status = f"{status_prefix} {last_status_msg}"
        board_render = render_board_2d(board_2d, status=display_status, flip_view=flip_view_2d, current_turn=current_turn)
        cv2.imshow(win_2d, board_render)

        cam_h, cam_w = cam_display.shape[:2]
        cv2.imshow(win_cam, cv2.resize(cam_display, (760, int(cam_h * 760 / cam_w))))

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('1'):
            # ตั้งค่า Assume ว่าทุกตัวอยู่ในตำแหน่งเริ่มต้นทันที (Mode 1)
            live_orient = auto_detect_orientation_from_board(frame, corners)
            if live_orient != orientation:
                orientation = live_orient
                save_orientation(orientation)
                print(f"🧭 [AUTO-ORIENT] อัปเดตทิศทางกระดานให้ตรงกับหมากจริง: {ORIENTATIONS[orientation]}")

            board_2d = [row[:] for row in STANDARD_INITIAL_BOARD]
            has_initial_render = True
            is_locked = True
            is_scanning = False
            assume_mode = 1
            current_turn = 'W'
            last_status_msg = "[SYNCED] Mode 1: Assumed standard initial setup! Press [Space] after move."
            print("\n" + "=" * 68)
            print("✅ [MODE 1] เซ็ต Assume หมากทั้ง 32 ตัวอยู่ในตำแหน่งเริ่มต้นเรียบร้อย")
            print(f"🧭 ทิศทางกระดาน: {ORIENTATIONS[orientation]}")
            print("⚪ พร้อมเทียบความเปลี่ยนแปลง: ขยับหมากแล้วกด [Spacebar] เพื่ออัปเดตตารางดิจิทัล")
            print("=" * 68 + "\n")
        elif key in (ord('t'), ord('T')):
            # สลับตาเดินด้วยมือ
            current_turn = 'B' if current_turn == 'W' else 'W'
            turn_str = "White (ขาว)" if current_turn == 'W' else "Black (ดำ)"
            last_status_msg = f"[LOCKED] Manual Turn Toggle: {turn_str} | Press [Space]"
            print(f"\n🔄 [TURN] สลับตาเดินเป็น: {turn_str}")
        elif key == ord('0'):
            # สลับเป็นโหมดสแกนหาหมากทั้งกระดานจากกล้อง (Mode 0)
            board_2d = [[None]*8 for _ in range(8)]
            has_initial_render = False
            is_locked = False
            is_scanning = True
            assume_mode = 0
            scan_passes.clear()
            scan_frame_timer = 0
            init_stable_cycles = 0
            last_status_msg = "[SCANNING] Mode 0: Scanning board from camera..."
            print("\n" + "=" * 68)
            print("🔄 [MODE 0] สลับเป็นโหมดสแกนหาหมากทั้งกระดานจากกล้องสด")
            print("=" * 68 + "\n")
        elif key == ord(' '):
            if not is_scanning:
                print("\n🔄 [SPACE] เริ่มสแกน 4 มุมตรวจสอบการเดินหมาก (เกณฑ์ 3/4 Consensus)...")
                is_scanning = True
                scan_passes.clear()
                scan_frame_timer = 0
                last_status_msg = "[SCANNING 4-PASS...] Verifying with 3/4 consensus rule..."
        elif key == ord('z'):
            # Zoom In (+0.1x)
            old_z = zoom_factor
            zoom_factor = min(4.0, round(zoom_factor + 0.1, 1))
            if zoom_factor != old_z:
                corners = rescale_corners_for_zoom(corners, old_z, zoom_factor, fw, fh)
                save_corners(corners)
                save_zoom(zoom_factor)
                print(f"🔍 [ZOOM IN] ซูมกล้องเข้า: {zoom_factor:.1f}x (ขยายขนาดกรอบตามกระดาน)")
        elif key == ord('Z'):
            # Zoom In ก้าวกว้าง (+0.5x)
            old_z = zoom_factor
            zoom_factor = min(4.0, round(zoom_factor + 0.5, 1))
            if zoom_factor != old_z:
                corners = rescale_corners_for_zoom(corners, old_z, zoom_factor, fw, fh)
                save_corners(corners)
                save_zoom(zoom_factor)
                print(f"🔍 [ZOOM IN] ซูมกล้องเข้า: {zoom_factor:.1f}x")
        elif key == ord('x'):
            # Zoom Out (-0.1x)
            old_z = zoom_factor
            zoom_factor = max(1.0, round(zoom_factor - 0.1, 1))
            if zoom_factor != old_z:
                corners = rescale_corners_for_zoom(corners, old_z, zoom_factor, fw, fh)
                save_corners(corners)
                save_zoom(zoom_factor)
                print(f"🔍 [ZOOM OUT] ซูมกล้องออก: {zoom_factor:.1f}x")
        elif key == ord('X'):
            # Zoom Out ก้าวกว้าง (-0.5x)
            old_z = zoom_factor
            zoom_factor = max(1.0, round(zoom_factor - 0.5, 1))
            if zoom_factor != old_z:
                corners = rescale_corners_for_zoom(corners, old_z, zoom_factor, fw, fh)
                save_corners(corners)
                save_zoom(zoom_factor)
                print(f"🔍 [ZOOM OUT] ซูมกล้องออก: {zoom_factor:.1f}x")
        elif key in (ord('w'), ord('W')):
            # เลื่อนกรอบจัตุรัสขึ้น (Move Square Up)
            corners[:, 1] = np.clip(corners[:, 1] - 15.0, 10.0, fh - 10.0 if ret else 1070.0)
            save_corners(corners)
            print(f"[SQUARE] เลื่อนขึ้น: Y = {corners[0][1]:.0f}")
        elif key in (ord('s'), ord('S')):
            # เลื่อนกรอบจัตุรัสลง (Move Square Down)
            corners[:, 1] = np.clip(corners[:, 1] + 15.0, 10.0, fh - 10.0 if ret else 1070.0)
            save_corners(corners)
            print(f"[SQUARE] เลื่อนลง: Y = {corners[0][1]:.0f}")
        elif key in (ord('a'), ord('A')):
            # เลื่อนกรอบจัตุรัสไปซ้าย (Move Square Left)
            corners[:, 0] = np.clip(corners[:, 0] - 15.0, 10.0, fw - 10.0 if ret else 1910.0)
            save_corners(corners)
            print(f"[SQUARE] เลื่อนซ้าย: X = {corners[0][0]:.0f}")
        elif key in (ord('d'), ord('D')):
            # เลื่อนกรอบจัตุรัสไปขวา (Move Square Right)
            corners[:, 0] = np.clip(corners[:, 0] + 15.0, 10.0, fw - 10.0 if ret else 1910.0)
            save_corners(corners)
            print(f"[SQUARE] เลื่อนขวา: X = {corners[0][0]:.0f}")
        elif key in (ord('+'), ord('=')):
            # ขยายขนาดจัตุรัส (Perfect Square Zoom In)
            cx = float(np.mean(corners[:, 0]))
            cy = float(np.mean(corners[:, 1]))
            cur_size = float(corners[1][0] - corners[0][0])
            new_size = min(min(fw if ret else 1920, fh if ret else 1080) - 20.0, cur_size + 20.0)
            half = new_size / 2.0
            corners = np.array([
                [cx - half, cy - half],
                [cx + half, cy - half],
                [cx + half, cy + half],
                [cx - half, cy + half]
            ], dtype=np.float32)
            save_corners(corners)
            print(f"[SQUARE] ขยายขนาด: {new_size:.0f}x{new_size:.0f} (Perfect Square)")
        elif key in (ord('-'), ord('_')):
            # ย่อขนาดจัตุรัส (Perfect Square Zoom Out)
            cx = float(np.mean(corners[:, 0]))
            cy = float(np.mean(corners[:, 1]))
            cur_size = float(corners[1][0] - corners[0][0])
            new_size = max(200.0, cur_size - 20.0)
            half = new_size / 2.0
            corners = np.array([
                [cx - half, cy - half],
                [cx + half, cy - half],
                [cx + half, cy + half],
                [cx - half, cy + half]
            ], dtype=np.float32)
            save_corners(corners)
            print(f"[SQUARE] ย่อขนาด: {new_size:.0f}x{new_size:.0f} (Perfect Square)")
        elif key in (ord('p'), ord('P')):
            # บังคับรีเซ็ตกรอบให้เป็นสี่เหลี่ยมจัตุรัส 1:1 ทันที (Force 1:1 Perfect Square)
            cx = float(np.mean(corners[:, 0]))
            cy = float(np.mean(corners[:, 1]))
            side = 670.0
            half = side / 2.0
            corners = np.array([
                [cx - half, cy - half],
                [cx + half, cy - half],
                [cx + half, cy + half],
                [cx - half, cy + half]
            ], dtype=np.float32)
            save_corners(corners)
            print(f"🟩 [SQUARE] ปรับเป็นสี่เหลี่ยมจัตุรัสสมบูรณ์แบบ (1:1) ขนาด {side:.0f}x{side:.0f} เรียบร้อย!")
        elif key in (ord('f'),):
            # กลับด้านกระดาน 180 องศาทันที (Flip Board 180°: ขวา ⇋ ซ้าย หรือ ล่าง ⇋ บน)
            orientation = (orientation + 2) % 4
            save_orientation(orientation)
            last_status_msg = f"[FLIPPED 180°] {ORIENTATIONS[orientation].split(' (')[0]}"
            print(f"\n🔄 [FLIP 180°] กลับด้านกระดาน 180 องศาเป็น: {ORIENTATIONS[orientation]}")
        elif key in (ord('F'), ord('v'), ord('V')):
            # สลับมุมมองกระดาน 2D (ขาวอยู่ล่าง ⇋ ดำอยู่ล่าง)
            flip_view_2d = not flip_view_2d
            view_str = "มุมมองฝั่งดำ (Black Bottom)" if flip_view_2d else "มุมมองฝั่งขาว (White Bottom)"
            last_status_msg = f"[2D VIEW] {view_str}"
            print(f"\n🔄 [2D VIEW] สลับมุมมองกระดาน 2D เป็น: {view_str}")
        elif key in (ord('u'), ord('U')):
            # Auto-Detect ทิศทางกระดานจากภาพกล้องสดทันที
            new_orient = auto_detect_orientation_from_board(frame, corners)
            orientation = new_orient
            save_orientation(orientation)
            last_status_msg = f"[AUTO-ORIENT] {ORIENTATIONS[orientation].split(' (')[0]}"
            print(f"\n🧭 [AUTO-ORIENT] ตรวจพบและตั้งทิศทางกระดานเป็น: {ORIENTATIONS[orientation]}")
        elif key in (ord('o'), ord('O')):
            # หมุนทิศทางกระดาน 90 องศา
            orientation = (orientation + 1) % 4
            save_orientation(orientation)
            print(f"\n🔄 [ORIENTATION] สลับทิศทางกระดานเป็น: {ORIENTATIONS[orientation]}")
        elif key == ord('c'):
            calib_mode = True
            calib_clicks.clear()
            cached_anchors.clear()
            print("\n[CALIBRATE] คลิก 4 มุมกระดาน: 1.บนซ้าย -> 2.บนขวา -> 3.ล่างขวา -> 4.ล่างซ้าย")
        elif key == ord('r'):
            board_2d = [[None]*8 for _ in range(8)]
            has_initial_render = False
            is_locked = False
            is_scanning = True
            current_turn = 'W'
            scan_passes.clear()
            scan_frame_timer = 0
            init_stable_cycles = 0
            last_status_msg = "Board reset. Re-verifying starting setup..."
            print("[INFO] Reset กระดาน 2D และเริ่มสแกน Initial ใหม่อัตโนมัติ (ตาเดินรีเซ็ตเป็น White)")

    cap.release()
    cv2.destroyAllWindows()

if __name__ == '__main__':
    main()
