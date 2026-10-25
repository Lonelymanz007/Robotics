#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
====================================================================
 Hybrid 'Digital Twin' Chess System - Single Player Mode
 Physical Human (White) vs C Language Minimax AI Robot (Black)
 Team: GM ลงเซิฟ (Robotics Course 01306202)
====================================================================
 Flow การทำงาน:
 1. ฝั่งขาว (ผู้เล่นคนจริง):
    - เลื่อนหมากขาวบนกระดานจริงในโลกจริง
    - กดปุ่ม [Spacebar] เพื่อสแกนและตรวจจับความเปลี่ยนแปลง
    - ระบบส่งพิกัดการเดิน (เช่น 'e2e4') ไปตรวจสอบกติกากับ C Language Engine
    - หากถูกต้อง อัปเดตกระดานดิจิทัล 2D Twin ทันที
 2. ฝั่งดำ (Robot AI):
    - เรียก C Language Decision Engine (Minimax + Alpha-Beta Pruning)
    - คำนวณหาตาเดินที่ดีที่สุดของฝั่งดำ (เช่น 'g8f6')
    - อนิเมตและอัปเดตการเดินของฝั่งดำบนหน้าจอ 2D ทันที
    - สร้างคำสั่ง Kinematics / Gripper Protocol ส่งออกไปยัง Webots Simulation
 3. วนลูปกลับมารอผู้เล่นคนจริงเดินตาต่อไป!
====================================================================
"""

import sys
import os
import re
import json
import time
import ctypes
import subprocess
from collections import Counter
import cv2
import numpy as np

# ─── Load C Chess Engine Shared Library (ctypes) ──────────────────
DYLIB_PATH = "./libchess_ai.dylib"
if not os.path.exists(DYLIB_PATH):
    print(f"[ENGINE] ไม่พบไฟล์ {DYLIB_PATH} กำลังคอมไพล์ผ่าน Makefile...")
    subprocess.run(["make", "all"], check=True)

try:
    c_engine = ctypes.CDLL(DYLIB_PATH)
    # Define C function prototypes
    c_engine.engine_init.restype = None
    c_engine.engine_is_legal_move.argtypes = [ctypes.c_char_p]
    c_engine.engine_is_legal_move.restype = ctypes.c_bool
    c_engine.engine_apply_human_move.argtypes = [ctypes.c_char_p]
    c_engine.engine_apply_human_move.restype = ctypes.c_bool

    c_engine.engine_robot_think.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.c_char_p
    ]
    c_engine.engine_robot_think.restype = ctypes.c_int

    c_engine.engine_is_white_in_check.restype = ctypes.c_bool
    c_engine.engine_is_black_in_check.restype = ctypes.c_bool
    print("[ENGINE] โหลด C Decision Engine (libchess_ai.dylib) สำเร็จ!")
except Exception as e:
    print(f"[ERROR] ไม่สามารถโหลด C Engine ได้: {e}")
    sys.exit(1)

# ─── 2D Board & Display Configuration ─────────────────────────
CELL_SIZE = 72
MARGIN    = 42
BOARD_SIZE = CELL_SIZE * 8
WIN_W = BOARD_SIZE + MARGIN * 2
WIN_H = BOARD_SIZE + MARGIN * 2 + 50

CLR_LIGHT     = (181, 217, 240)    # #F0D9B5
CLR_DARK      = ( 99, 136, 181)    # #B58863
CLR_BG        = ( 24,  24,  28)
CLR_TEXT      = (190, 190, 190)
CLR_ARROW     = (  0, 215, 255)
CLR_HL_SRC    = ( 90, 190,  90)
CLR_HL_DST    = ( 80, 140, 230)
CLR_HL_ROBOT  = (220,  80, 120)

# HSV Ranges สำหรับสีสติกเกอร์แยกตามประเภทหมาก
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

# ─── Dual Red Anchor Detector ──────────────────────────────────
RED_LOWER1 = np.array([  0, 100, 100])
RED_UPPER1 = np.array([  8, 255, 255])
RED_LOWER2 = np.array([170, 100, 100])
RED_UPPER2 = np.array([180, 255, 255])

def detect_red_anchors(frame):
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    m1 = cv2.inRange(hsv, RED_LOWER1, RED_UPPER1)
    m2 = cv2.inRange(hsv, RED_LOWER2, RED_UPPER2)
    mask = cv2.bitwise_or(m1, m2)
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, k)
    mask = cv2.morphologyEx(mask, cv2.MORPH_DILATE, k)
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    anchors = []
    for c in cnts:
        area = cv2.contourArea(c)
        if area < 60: continue
        peri = cv2.arcLength(c, True)
        if peri == 0: continue
        circularity = 4 * np.pi * area / (peri * peri)
        if circularity < 0.45: continue
        M_c = cv2.moments(c)
        if M_c['m00'] == 0: continue
        cx = M_c['m10'] / M_c['m00']
        cy = M_c['m01'] / M_c['m00']
        anchors.append((cx, cy))
    if len(anchors) >= 2:
        anchors.sort(key=lambda p: cv2.contourArea(cnts[anchors.index(p)] if p in anchors else cnts[0]), reverse=True)
        return anchors[:2]
    return anchors

# ─── Config Files & State ─────────────────────────────────────
CORNERS_FILE = "board_corners.json"
ZOOM_CONFIG_FILE = "camera_zoom.json"
ORIENTATION_CONFIG_FILE = "board_orientation.json"
WEBOTS_CMD_FILE = "webots_command.txt"
WEBOTS_JSON_FILE = "webots_move.json"
MINI_MEMORY_FILE = "mini_memory_board.json"

def save_mini_memory_state(turn, board_2d, last_move=None, active_turn="White (Human)"):
    """
    บันทึกสถานะกระดานล่าสุดลงในระบบความจำมินิ (Mini Memory State)
    เพื่อให้ C Engine และ Simulation ใช้เป็นข้อมูลอ้างอิงสภาพแวดล้อมกระดานปัจจุบัน
    """
    state = {
        "turn": turn,
        "active_turn": active_turn,
        "last_move": last_move,
        "board_matrix": [
            [board_2d[r][c] if board_2d[r][c] else "." for c in range(8)]
            for r in range(8)
        ],
        "pieces_count": {
            "white": sum(1 for r in range(8) for c in range(8) if board_2d[r][c] and board_2d[r][c][0] == 'W'),
            "black": sum(1 for r in range(8) for c in range(8) if board_2d[r][c] and board_2d[r][c][0] == 'B'),
        },
        "timestamp": time.time(),
        "time_str": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    try:
        with open(MINI_MEMORY_FILE, "w") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        print(f"[MEMORY] Error saving mini memory: {e}")

def load_corners(fw=1920, fh=1080):
    if os.path.exists(CORNERS_FILE):
        try:
            with open(CORNERS_FILE, 'r') as f:
                data = json.load(f)
                return np.array(data, dtype=np.float32)
        except Exception:
            pass
    # Default: Inner 8x8 squares 670x670 perfect square
    cx, cy = fw / 2.0, fh / 2.0
    side = 670.0
    half = side / 2.0
    return np.array([
        [cx - half, cy - half],
        [cx + half, cy - half],
        [cx + half, cy + half],
        [cx - half, cy + half]
    ], dtype=np.float32)

def save_corners(corners):
    try:
        with open(CORNERS_FILE, 'w') as f:
            json.dump(corners.tolist(), f)
    except Exception:
        pass

def load_zoom():
    if os.path.exists(ZOOM_CONFIG_FILE):
        try:
            with open(ZOOM_CONFIG_FILE, 'r') as f:
                return float(json.load(f).get('zoom', 1.0))
        except Exception:
            pass
    return 1.0

def save_zoom(zoom):
    try:
        with open(ZOOM_CONFIG_FILE, 'w') as f:
            json.dump({'zoom': float(zoom)}, f)
    except Exception:
        pass

def load_orientation():
    if os.path.exists(ORIENTATION_CONFIG_FILE):
        try:
            with open(ORIENTATION_CONFIG_FILE, 'r') as f:
                return int(json.load(f).get('orientation', 3))
        except Exception:
            pass
    return 3

def save_orientation(orientation):
    try:
        with open(ORIENTATION_CONFIG_FILE, 'w') as f:
            json.dump({'orientation': int(orientation)}, f)
    except Exception:
        pass

def apply_camera_zoom(frame, zoom_factor):
    if zoom_factor <= 1.001:
        return frame
    h, w = frame.shape[:2]
    new_w = int(w / zoom_factor)
    new_h = int(h / zoom_factor)
    x1 = (w - new_w) // 2
    y1 = (h - new_h) // 2
    cropped = frame[y1:y1+new_h, x1:x1+new_w]
    return cv2.resize(cropped, (w, h), interpolation=cv2.INTER_LINEAR)

def rescale_corners_for_zoom(corners, old_zoom, new_zoom, fw=1920, fh=1080):
    if old_zoom == new_zoom or old_zoom <= 0:
        return corners
    ratio = new_zoom / old_zoom
    cx, cy = fw / 2.0, fh / 2.0
    scaled = corners.copy()
    scaled[:, 0] = np.clip((scaled[:, 0] - cx) * ratio + cx, 0.0, fw)
    scaled[:, 1] = np.clip((scaled[:, 1] - cy) * ratio + cy, 0.0, fh)
    return scaled

ORIENTATIONS = [
    "White at Bottom (Rank 1 ล่าง / Rank 8 บน)",
    "White at Left (Rank 1 ซ้าย / Rank 8 ขวา)",
    "White at Top (Rank 1 บน / Rank 8 ล่าง)",
    "White at Right (Rank 1 ขวา / Rank 8 ซ้าย)"
]

def order_corners_90deg(corners, orientation=3, dest_size=800):
    pts = list(corners)
    pts_by_y = sorted(pts, key=lambda p: p[1])
    top_two = sorted(pts_by_y[:2], key=lambda p: p[0])
    bot_two = sorted(pts_by_y[2:], key=lambda p: p[0])

    c_tl = top_two[0]
    c_tr = top_two[1]
    c_br = bot_two[1]
    c_bl = bot_two[0]

    dst = np.array([
        [0, 0],
        [dest_size, 0],
        [dest_size, dest_size],
        [0, dest_size]
    ], dtype=np.float32)

    if orientation == 0:
        src_ordered = [c_tl, c_tr, c_br, c_bl]
    elif orientation == 1:
        # White at Left: Rank 1 ซ้าย / Rank 8 ขวา (File a บน / File h ล่าง)
        src_ordered = [c_tr, c_br, c_bl, c_tl]
    elif orientation == 2:
        src_ordered = [c_bl, c_br, c_tr, c_tl]
    else:
        # orientation == 3: White at Right (Rank 1 ขวา / Rank 8 ซ้าย, File a บน / File h ล่าง)
        src_ordered = [c_tl, c_bl, c_br, c_tr]

    src = np.array(src_ordered, dtype=np.float32)
    M = cv2.getPerspectiveTransform(src, dst)
    corner_dict = {
        'a8': src_ordered[0],
        'h8': src_ordered[1],
        'h1': src_ordered[2],
        'a1': src_ordered[3],
        'tl': c_tl, 'tr': c_tr, 'br': c_br, 'bl': c_bl
    }
    return M, dest_size, corner_dict

def point_to_chess_square(cx, cy, M, dest_size=800):
    pt = np.array([[[cx, cy]]], dtype=np.float32)
    transformed = cv2.perspectiveTransform(pt, M)[0][0]
    tx, ty = transformed[0], transformed[1]

    OUT_OF_BOUNDS_TOLERANCE = 60.0
    if (tx < -OUT_OF_BOUNDS_TOLERANCE or tx > dest_size + OUT_OF_BOUNDS_TOLERANCE or
        ty < -OUT_OF_BOUNDS_TOLERANCE or ty > dest_size + OUT_OF_BOUNDS_TOLERANCE):
        return None

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

# ─── 2D Board Rendering & Animation ───────────────────────────
def render_board_2d(board_state, highlight=None, anim=None, status="", robot_action="", in_check_color=None):
    img = np.full((WIN_H + 40, WIN_W, 3), CLR_BG, dtype=np.uint8)

    for r in range(8):
        for c in range(8):
            x0 = MARGIN + c * CELL_SIZE
            y0 = MARGIN + r * CELL_SIZE
            is_light = ((r + c) % 2 == 0)
            clr = CLR_LIGHT if is_light else CLR_DARK
            cv2.rectangle(img, (x0, y0), (x0 + CELL_SIZE, y0 + CELL_SIZE), clr, -1)

            # Highlight King in check (Red)
            p = board_state[r][c]
            if p and p[1] == 'K':
                if (p[0] == 'W' and in_check_color == 'W') or (p[0] == 'B' and in_check_color == 'B'):
                    ov = img[y0:y0+CELL_SIZE, x0:x0+CELL_SIZE].copy()
                    cv2.rectangle(ov, (0, 0), (CELL_SIZE, CELL_SIZE), (0, 0, 220), -1)
                    cv2.addWeighted(ov, 0.55, img[y0:y0+CELL_SIZE, x0:x0+CELL_SIZE], 0.45, 0,
                                    img[y0:y0+CELL_SIZE, x0:x0+CELL_SIZE])

            if highlight:
                hl_col = None
                if (r, c) == highlight[0]: hl_col = CLR_HL_SRC
                elif (r, c) == highlight[1]: hl_col = CLR_HL_DST
                if hl_col:
                    ov = img[y0:y0+CELL_SIZE, x0:x0+CELL_SIZE].copy()
                    cv2.rectangle(ov, (0, 0), (CELL_SIZE, CELL_SIZE), hl_col, -1)
                    cv2.addWeighted(ov, 0.45, img[y0:y0+CELL_SIZE, x0:x0+CELL_SIZE], 0.55, 0,
                                    img[y0:y0+CELL_SIZE, x0:x0+CELL_SIZE])

            if p:
                cx = x0 + CELL_SIZE // 2
                cy = y0 + CELL_SIZE // 2
                blit_alpha(img, get_piece_icon(p), cx, cy)

    if anim:
        blit_alpha(img, get_piece_icon(anim['piece']), anim['cur_px'][0], anim['cur_px'][1])
        sp = anim['src_px']; dp = anim['dst_px']; t = anim['progress']
        ep = (int(sp[0] + (dp[0] - sp[0]) * t), int(sp[1] + (dp[1] - sp[1]) * t))
        if sp != ep:
            arrow_col = CLR_HL_ROBOT if anim.get('is_robot', False) else CLR_ARROW
            cv2.arrowedLine(img, sp, ep, arrow_col, 3, tipLength=0.25)

    cv2.rectangle(img, (MARGIN, MARGIN), (MARGIN + BOARD_SIZE, MARGIN + BOARD_SIZE), (60, 60, 60), 1)

    for i in range(8):
        rank = str(8 - i)
        cv2.putText(img, rank, (MARGIN // 2 - 4, MARGIN + i * CELL_SIZE + CELL_SIZE // 2 + 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, CLR_TEXT, 1)
        file_c = chr(ord('a') + i)
        cv2.putText(img, file_c, (MARGIN + i * CELL_SIZE + CELL_SIZE // 2 - 5, MARGIN + BOARD_SIZE + MARGIN // 2 + 4),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.42, CLR_TEXT, 1)

    # Status Bar
    cv2.putText(img, status, (MARGIN, WIN_H - 14),
                cv2.FONT_HERSHEY_SIMPLEX, 0.38, (160, 220, 160), 1)

    # Robot Command / Sim Feed Banner
    if robot_action:
        cv2.rectangle(img, (MARGIN, WIN_H + 4), (WIN_W - MARGIN, WIN_H + 32), (35, 45, 55), -1)
        cv2.rectangle(img, (MARGIN, WIN_H + 4), (WIN_W - MARGIN, WIN_H + 32), (0, 180, 255), 1)
        cv2.putText(img, f"SIM PROTOCOL: {robot_action}", (MARGIN + 8, WIN_H + 24),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, (0, 230, 255), 1)

    return img

def execute_robot_turn(c_engine, board_2d, turn_count, win_2d):
    """
    ฟังก์ชันสั่งให้ C Engine วิเคราะห์สถานการณ์และเดินหมากฝั่งดำ (AI Robot)
    ส่งคำสั่ง Kinematics ไปยัง Webots และอนิเมตลงกระดาน 2D
    """
    print("\n🧠 [AI THINKING] AI กำลังวิเคราะห์สถานการณ์กระดานจากความจำมินิ...")
    out_from = ctypes.create_string_buffer(8)
    out_to = ctypes.create_string_buffer(8)
    out_inst = ctypes.create_string_buffer(256)
    out_proto = ctypes.create_string_buffer(128)

    status_code = c_engine.engine_robot_think(3, out_from, out_to, out_inst, out_proto)
    robot_from = out_from.value.decode('utf-8')
    robot_to = out_to.value.decode('utf-8')
    robot_inst = out_inst.value.decode('utf-8')
    robot_proto = out_proto.value.decode('utf-8')

    print(f"🤖 [ROBOT DECISION] Black plays: {robot_from} -> {robot_to}")
    print(f"🦾 [WEBOTS KINEMATICS] {robot_inst}")
    print(f"📡 [SIM PROTOCOL] {robot_proto}")

    # ส่งข้อมูลคำสั่งไปยัง Webots Simulator
    emit_webots_instruction(turn_count, "Black", robot_from, robot_to, robot_inst, robot_proto)

    # อนิเมตการเดินของฝั่งดำบนกระดาน 2D
    r_src = square_name_to_rc(robot_from)
    r_dst = square_name_to_rc(robot_to)
    if r_src and r_dst:
        if board_2d[r_src[0]][r_src[1]] == 'BK' and abs(r_src[1] - r_dst[1]) == 2:
            animate_move(board_2d, r_src, r_dst, win_2d, is_robot=True)
            board_2d[r_dst[0]][r_dst[1]] = board_2d[r_src[0]][r_src[1]]
            board_2d[r_src[0]][r_src[1]] = None
            if r_dst[1] == 6:
                rook_src = (0, 7); rook_dst = (0, 5)
            else:
                rook_src = (0, 0); rook_dst = (0, 3)
            animate_move(board_2d, rook_src, rook_dst, win_2d, is_robot=True)
            board_2d[rook_dst[0]][rook_dst[1]] = board_2d[rook_src[0]][rook_src[1]]
            board_2d[rook_src[0]][rook_src[1]] = None
        else:
            animate_move(board_2d, r_src, r_dst, win_2d, is_robot=True)
            board_2d[r_dst[0]][r_dst[1]] = board_2d[r_src[0]][r_src[1]]
            board_2d[r_src[0]][r_src[1]] = None

    turn_count += 1
    # อัปเดตความจำมินิหลังฝั่งดำเดินเสร็จ
    save_mini_memory_state(turn_count, board_2d, last_move=f"{robot_from}{robot_to}", active_turn="White (Human)")

    in_check_color = None
    if status_code == 1:
        last_status_msg = "🏆 [GAME OVER] CHECKMATE! HUMAN (WHITE) WINS!"
        next_state = 'GAME_OVER'
        print("\n" + "="*50 + "\n🏆 CHECKMATE! WHITE (HUMAN) WINS!\n" + "="*50)
    elif status_code == 2:
        last_status_msg = "🤖 [GAME OVER] CHECKMATE! ROBOT (BLACK) WINS!"
        next_state = 'GAME_OVER'
        print("\n" + "="*50 + "\n🤖 CHECKMATE! BLACK (ROBOT) WINS!\n" + "="*50)
    elif status_code in (3, 4):
        last_status_msg = "🤝 [GAME OVER] DRAW / STALEMATE!"
        next_state = 'GAME_OVER'
        print("\n" + "="*50 + "\n🤝 STALEMATE / DRAW!\n" + "="*50)
    else:
        if c_engine.engine_is_white_in_check():
            in_check_color = 'W'
            last_status_msg = f"[CHECK] White King in check! Robot: {robot_from}->{robot_to} | Your turn (White)"
        else:
            in_check_color = None
            last_status_msg = f"Robot: {robot_from}->{robot_to} | [YOUR TURN] White, move piece on board & press [Space]"
        next_state = 'WAITING_HUMAN'
        print(f"\n👤 ตาของคุณแล้ว (หมากขาว): เดินหมากบนกระดานจริงเสร็จแล้วกด [Spacebar]")

    return next_state, turn_count, last_status_msg, robot_proto, in_check_color

def animate_move(board_2d, src, dst, win_name, is_robot=False, steps=10, delay_ms=18):
    sr, sc = src; dr, dc = dst
    p = board_2d[sr][sc]
    if not p: return

    sx = MARGIN + sc * CELL_SIZE + CELL_SIZE // 2
    sy = MARGIN + sr * CELL_SIZE + CELL_SIZE // 2
    dx = MARGIN + dc * CELL_SIZE + CELL_SIZE // 2
    dy = MARGIN + dr * CELL_SIZE + CELL_SIZE // 2

    saved = board_2d[sr][sc]
    board_2d[sr][sc] = None

    player_str = "Robot (Black)" if is_robot else "Human (White)"
    for step in range(steps + 1):
        t = step / float(steps)
        t_ease = (1.0 - np.cos(t * np.pi)) / 2.0
        cur_x = int(sx + (dx - sx) * t_ease)
        cur_y = int(sy + (dy - sy) * t_ease)

        anim = {
            'piece': saved,
            'src_px': (sx, sy),
            'dst_px': (dx, dy),
            'cur_px': (cur_x, cur_y),
            'progress': t_ease,
            'is_robot': is_robot
        }
        status_txt = f"[ANIMATING] {player_str} moving {saved}..."
        frame = render_board_2d(board_2d, highlight=(src, dst), anim=anim, status=status_txt)
        cv2.imshow(win_name, frame)
        cv2.waitKey(delay_ms)

    board_2d[sr][sc] = saved

def square_name_to_rc(sq_str):
    # e.g. 'e4' -> (4, 4)
    if len(sq_str) != 2: return None
    c = ord(sq_str[0].lower()) - ord('a')
    r = 8 - int(sq_str[1])
    if 0 <= r < 8 and 0 <= c < 8:
        return (r, c)
    return None

def rc_to_square_name(r, c):
    return f"{chr(ord('a')+c)}{8-r}"

# ─── Write Webots Simulation Files ────────────────────────────
def emit_webots_instruction(move_count, player, from_sq, to_sq, instruction, protocol):
    try:
        with open(WEBOTS_CMD_FILE, "a") as f:
            f.write(f"{protocol}\n")
        data = {
            "turn": move_count,
            "player": player,
            "move": f"{from_sq}{to_sq}",
            "from": from_sq,
            "to": to_sq,
            "instruction": instruction,
            "protocol": protocol,
            "timestamp": time.time()
        }
        with open(WEBOTS_JSON_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[WEBOTS] Error writing command file: {e}")

# ─── Main Single Player Application ───────────────────────────
def main():
    print("=" * 70)
    print(" ♚ Hybrid 'Digital Twin' Chess - Single Player Mode ♚")
    print(" ⚪ Human (White): Real-World iPhone Camera Tracking")
    print(" ⚫ Robot AI (Black): C Engine Minimax Decision + Webots Sim Protocol")
    print("=" * 70)

    # 1. Initialize C Chess Engine
    c_engine.engine_init()
    print("[ENGINE] Game initialized in C engine (Initial Board State).")

    # Clear Webots command buffer
    if os.path.exists(WEBOTS_CMD_FILE):
        try: os.remove(WEBOTS_CMD_FILE)
        except: pass

    # 2. Camera Setup
    cam_index = 1
    if len(sys.argv) > 1:
        try: cam_index = int(sys.argv[1])
        except: pass

    cap = cv2.VideoCapture(cam_index)
    if not cap.isOpened():
        print(f"[CAMERA] ไม่สามารถเปิดกล้อง Index {cam_index} ได้ ลองเปิด Index 0...")
        cap = cv2.VideoCapture(0)
        cam_index = 0

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    # Continuity Camera Warmup Loop
    print("[CAMERA] กำลังเชื่อมต่อสัญญาณภาพกล้อง (Warmup Loop)...")
    frame = None
    ret = False
    for attempt in range(40):
        ret, frame = cap.read()
        if ret and frame is not None:
            break
        time.sleep(0.04)

    if not ret or frame is None:
        print("[ERROR] ไม่สามารถรับสัญญาณภาพจากกล้องได้!")
        return

    fh, fw = frame.shape[:2]
    print(f"[CAMERA] เชื่อมต่อสำเร็จ: ขนาด {fw}x{fh} px")

    # Load configuration
    corners = load_corners(fw, fh)
    zoom_factor = load_zoom()
    corners = rescale_corners_for_zoom(corners, 1.0, zoom_factor, fw, fh)

    # ตรวจสอบทิศทางกระดานสดจากตำแหน่งของหมากขาว/ดำจริงในกล้อง (ป้องกันการเดินสลับสี 100%)
    live_orient = auto_detect_orientation_from_board(frame, corners)
    orientation = live_orient
    save_orientation(orientation)
    print(f"🧭 [AUTO-ORIENT] ตรวจพบตำแหน่งหมากจริง: {ORIENTATIONS[orientation]}")

    # Digital Twin Board State
    board_2d = [row[:] for row in STANDARD_INITIAL_BOARD]
    save_mini_memory_state(0, board_2d, last_move=None, active_turn="White (Human)")

    # Windows
    win_cam = "Hybrid Single Player - Camera View"
    win_2d = "Hybrid Single Player - 2D Digital Twin & Sim"
    cv2.namedWindow(win_cam, cv2.WINDOW_NORMAL)
    cv2.namedWindow(win_2d, cv2.WINDOW_NORMAL)
    cv2.resizeWindow(win_cam, 760, int(760 * fh / fw))
    cv2.resizeWindow(win_2d, WIN_W, WIN_H + 40)

    # Mouse Callback for manual calibration
    calib_mode = False
    calib_clicks = []
    def on_mouse(event, x, y, flags, param):
        nonlocal calib_mode, corners
        if calib_mode and event == cv2.EVENT_LBUTTONDOWN:
            # Map click back to full frame
            disp_w = 760
            disp_h = int(fh * 760 / fw)
            fx = float(x * fw / disp_w)
            fy = float(y * fh / disp_h)
            calib_clicks.append([fx, fy])
            print(f"[CALIB] คลิกมุม {len(calib_clicks)}/4: ({fx:.1f}, {fy:.1f})")
            if len(calib_clicks) == 4:
                corners = np.array(calib_clicks, dtype=np.float32)
                save_corners(corners)
                calib_mode = False
                calib_clicks.clear()
                print("✅ [CALIB] บันทึก 4 มุมกระดานเรียบร้อย!")
    cv2.setMouseCallback(win_cam, on_mouse)

    kernel_open   = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    kernel_dilate = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))

    # Single Player State Machine
    # STATES:
    # 'WAITING_HUMAN' -> Human makes move on physical board, presses [Space]
    # 'SCANNING_HUMAN' -> Camera scans 16 passes, verifies White move
    # 'WAITING_AI_TRIGGER' -> White move confirmed on 2D, waiting user to press [Enter] to start AI
    # 'GAME_OVER' -> Checkmate or Stalemate
    game_state = 'WAITING_HUMAN'
    turn_count = 1
    last_status_msg = "[HUMAN TURN] White, move a physical piece & press [Space]"
    last_robot_protocol = ""
    in_check_color = None
    scan_passes = []

    print("\n" + "=" * 68)
    print(" 🎮 SINGLE PLAYER CHESS PIPELINE (HUMAN vs AI ROBOT)")
    print(" 1. เดินหมากขาวบนกระดานจริง (เช่น Pawn e2 -> e4)")
    print(" 2. กดปุ่ม [Spacebar] เพื่อสแกนและอัปเดตลงตาราง 2D")
    print(" 3. 👉 เมื่อจบตาคุณแล้ว ให้กดปุ่ม [Enter] (หรือ Space) เพื่อสั่ง AI เริ่มวิเคราะห์และเดินฝั่งดำ!")
    print(" 4. C Engine จะส่งคำสั่ง Kinematics ไปยัง Webots Sim และขยับบนกระดาน 2D ทันที")
    print(" 🔄 [f] กลับด้านกระดาน 180° | [u] Auto-Detect ทิศทางกระดาน | [o] หมุน 90°")
    print(" [1/r] รีเซ็ตเกมใหม่ | [z/x] ซูมกล้อง | [w/s/a/d] ขยับกรอบ | [q] ออก")
    print("=" * 68 + "\n")

    drop_count = 0
    while True:
        ret, frame = cap.read()
        if not ret or frame is None:
            drop_count += 1
            if drop_count > 60:
                print("[CAMERA] ขาดการเชื่อมต่อ!")
                break
            time.sleep(0.02)
            continue
        drop_count = 0

        # Apply digital camera zoom
        if zoom_factor > 1.001:
            frame = apply_camera_zoom(frame, zoom_factor)

        cam_display = frame.copy()
        frame_hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        # Order corners & Perspective Transform
        M, dest_size, corner_dict = order_corners_90deg(corners, orientation=orientation, dest_size=800)

        # Draw Grid & Outer Boundaries
        pts_poly = corners.astype(np.int32).reshape((-1, 1, 2))
        cv2.polylines(cam_display, [pts_poly], isClosed=True, color=(0, 255, 0), thickness=3)

        c_tl = (int(corner_dict['tl'][0]), int(corner_dict['tl'][1]))
        c_tr = (int(corner_dict['tr'][0]), int(corner_dict['tr'][1]))
        c_br = (int(corner_dict['br'][0]), int(corner_dict['br'][1]))
        c_bl = (int(corner_dict['bl'][0]), int(corner_dict['bl'][1]))

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

        # Draw labels
        c_a1 = (int(corner_dict['a1'][0]), int(corner_dict['a1'][1]))
        c_h1 = (int(corner_dict['h1'][0]), int(corner_dict['h1'][1]))
        c_a8 = (int(corner_dict['a8'][0]), int(corner_dict['a8'][1]))
        c_h8 = (int(corner_dict['h8'][0]), int(corner_dict['h8'][1]))

        cv2.circle(cam_display, c_a1, 8, (255, 255, 255), -1)
        cv2.putText(cam_display, "a1", (c_a1[0] - 25, c_a1[1] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.50, (255, 255, 255), 2)
        cv2.circle(cam_display, c_h1, 8, (255, 255, 255), -1)
        cv2.putText(cam_display, "h1", (c_h1[0] - 25, c_h1[1] + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.50, (255, 255, 255), 2)
        cv2.circle(cam_display, c_a8, 8, (100, 100, 255), -1)
        cv2.putText(cam_display, "a8", (c_a8[0] + 8, c_a8[1] - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.50, (100, 100, 255), 2)
        cv2.circle(cam_display, c_h8, 8, (100, 100, 255), -1)
        cv2.putText(cam_display, "h8", (c_h8[0] + 8, c_h8[1] + 18), cv2.FONT_HERSHEY_SIMPLEX, 0.50, (100, 100, 255), 2)

        mid_w = (int((c_a1[0] + c_h1[0]) / 2), int((c_a1[1] + c_h1[1]) / 2))
        mid_b = (int((c_a8[0] + c_h8[0]) / 2), int((c_a8[1] + c_h8[1]) / 2))
        cv2.putText(cam_display, "WHITE (Human Rank 1-2)", (mid_w[0] - 230, mid_w[1]), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 2)
        cv2.putText(cam_display, "BLACK (Robot Rank 7-8)", (mid_b[0] + 15, mid_b[1]), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (100, 100, 255), 2)

        # Scan instant frame
        instant_board, detections, _ = scan_board_frame(
            frame, frame_hsv, M, dest_size, kernel_open, kernel_dilate
        )

        for (x, y, w, h, team, piece_name, piece_id, r, c, clr) in detections:
            sq_name = f"{chr(ord('a')+c)}{8-r}"
            lbl = f"{team} {piece_name} [{sq_name}]"
            cv2.rectangle(cam_display, (x, y), (x + w, y + h), clr, 2)
            cv2.putText(cam_display, lbl, (x, max(y - 6, 12)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, clr, 2)

        # ── State Machine: Human Scan & Robot Turn ───────────────
        if game_state == 'SCANNING_HUMAN':
            scan_passes.append([row[:] for row in instant_board])

            # Draw laser sweep
            sweep_idx = min(3, len(scan_passes) // 4)
            sweep_defs = [
                (c_a1, c_h8, "⚡ SWEEP: Verifying Human Move...", (0, 165, 255)),
                (c_h8, c_a1, "⚡ SWEEP: Analyzing Board...", (0, 165, 255)),
                (c_a8, c_h1, "⚡ SWEEP: Checking Rules...", (255, 255, 0)),
                (c_h1, c_a8, "⚡ SWEEP: Final Consensus...", (255, 255, 0))
            ]
            p_start, p_end, sweep_name, sweep_color = sweep_defs[sweep_idx]
            sub_step = (len(scan_passes) % 4) / 4.0
            lx = int(p_start[0] + sub_step * (p_end[0] - p_start[0]))
            ly = int(p_start[1] + sub_step * (p_end[1] - p_start[1]))
            cv2.circle(cam_display, (lx, ly), 8, sweep_color, -1)
            cv2.putText(cam_display, sweep_name, (30, 80), cv2.FONT_HERSHEY_SIMPLEX, 0.65, sweep_color, 2)

            if len(scan_passes) >= 16:
                hit_counts = [[0]*8 for _ in range(8)]
                detected_types = [[None]*8 for _ in range(8)]
                for r in range(8):
                    for c in range(8):
                        readings = [scan_passes[i][r][c] for i in range(len(scan_passes)) if scan_passes[i][r][c] is not None]
                        hit_counts[r][c] = len(readings)
                        if readings:
                            detected_types[r][c] = Counter(readings).most_common(1)[0][0]

                scan_passes.clear()

                # Differential Tracking for Human (White)
                cand_emptied = []
                for r in range(8):
                    for c in range(8):
                        # เฉพาะตัวหมากของฝั่งขาวที่เดิมมีอยู่ แต่ตอนนี้ตรวจไม่พบ
                        if board_2d[r][c] is not None and board_2d[r][c][0] == 'W':
                            if hit_counts[r][c] < 2:
                                cand_emptied.append((r, c, board_2d[r][c], hit_counts[r][c]))

                cand_occupied = []
                for r in range(8):
                    for c in range(8):
                        if board_2d[r][c] is None:
                            if hit_counts[r][c] >= 2 and detected_types[r][c] is not None:
                                cand_occupied.append((r, c, detected_types[r][c], hit_counts[r][c], True))
                        else:
                            # การกินหมาก (White กิน Black)
                            if board_2d[r][c][0] == 'B' and hit_counts[r][c] >= 6 and detected_types[r][c] is not None:
                                cand_occupied.append((r, c, detected_types[r][c], hit_counts[r][c], False))

                candidate_moves = []
                for (sr, sc, p_src, _) in cand_emptied:
                    for (dr, dc, p_dst, _, is_empty) in cand_occupied:
                        if (sr, sc) == (dr, dc): continue
                        dist_r = abs(sr - dr)
                        dist_c = abs(sc - dc)
                        total_dist = dist_r + dist_c

                        # กฎเบี้ยขาว
                        if p_src and p_src[1:] == 'P':
                            if is_empty:
                                if dist_c > 1 or dist_r > 2: continue
                            else:
                                if dist_c != 1 or dist_r != 1: continue

                        score = 10
                        if is_empty: score += 200
                        if p_dst and p_dst[1:] == p_src[1:]: score += 100
                        if p_dst and p_dst[0] == p_src[0]: score += 50
                        score -= total_dist * 15

                        candidate_moves.append({
                            'src': (sr, sc),
                            'dst': (dr, dc),
                            'piece': p_src,
                            'score': score
                        })

                if candidate_moves:
                    best_move = max(candidate_moves, key=lambda m: m['score'])
                    sr, sc = best_move['src']
                    dr, dc = best_move['dst']
                    src_sq = rc_to_square_name(sr, sc)
                    dst_sq = rc_to_square_name(dr, dc)
                    human_move_str = f"{src_sq}{dst_sq}"

                    # 1. บันทึกและเดินหมากขาวใน C Engine
                    c_engine.engine_apply_human_move(human_move_str.encode('utf-8'))
                    moved_p = board_2d[sr][sc]
                    print(f"\n👤 [HUMAN MOVE] White played: {moved_p} ({src_sq} -> {dst_sq})")

                    # 2. อนิเมตหมากขาวบนกระดาน 2D
                    animate_move(board_2d, (sr, sc), (dr, dc), win_2d, is_robot=False)
                    board_2d[dr][dc] = moved_p
                    board_2d[sr][sc] = None

                    # 3. บันทึกสถานะสภาพแวดล้อมกระดานล่าสุดลงในระบบความจำมินิ
                    save_mini_memory_state(turn_count, board_2d, last_move=human_move_str, active_turn="Waiting Trigger -> Black (Robot)")
                    print(f"💾 [MINI MEMORY] บันทึกสภาพแวดล้อมกระดานล่าสุดลง '{MINI_MEMORY_FILE}' เรียบร้อย")

                    # 4. เข้าสู่สถานะ WAITING_AI_TRIGGER รอผู้เล่นกด [Enter] เพื่อสั่งให้ AI เริ่มวิเคราะห์และเดิน
                    game_state = 'WAITING_AI_TRIGGER'
                    last_status_msg = f"[WHITE CONFIRMED] {src_sq}->{dst_sq} | Press [ENTER] to tell AI to move!"

                    print("\n" + "=" * 68)
                    print(f" ✅ [WHITE MOVE CONFIRMED] หมากขาวเดิน: {moved_p} ({src_sq} -> {dst_sq}) เรียบร้อย!")
                    print(" 👉 จบตาผู้เล่นแล้ว! กดปุ่ม [ENTER] (หรือ Spacebar) เพื่อสั่ง AI วิเคราะห์และเริ่มเดินฝั่งดำ!")
                    print("=" * 68 + "\n")
                else:
                    print("[INFO] ไม่พบการขยับหมากของฝั่งขาว กระดานคงเดิม")
                    last_status_msg = "[WAITING] No move detected | Move White piece on board & press [Space]"
                    game_state = 'WAITING_HUMAN'

        # Badge Text on Camera window
        if game_state == 'SCANNING_HUMAN':
            badge_txt = f"STATE: [SCANNING ({len(scan_passes)}/16)] Verifying White Move..."
            badge_col = (0, 215, 255)
        elif game_state == 'WAITING_AI_TRIGGER':
            badge_txt = "STATE: [PRESS ENTER] Tell AI to analyze & move Black!"
            badge_col = (0, 215, 255)
        elif game_state == 'GAME_OVER':
            badge_txt = "STATE: [GAME OVER] Match Concluded"
            badge_col = (0, 0, 255)
        else:
            badge_txt = "STATE: [WAITING HUMAN] Move White on board & press [Space]"
            badge_col = (0, 255, 0)

        cv2.putText(cam_display, badge_txt, (30, 45), cv2.FONT_HERSHEY_SIMPLEX, 0.60, badge_col, 2)
        orient_txt = f"ORIENT: {ORIENTATIONS[orientation].split(' (')[0]} [f: Flip 180 | o: Rotate | u: Auto]"
        cv2.putText(cam_display, orient_txt, (30, 75), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (0, 255, 255), 2)
        zoom_txt = f"ZOOM: {zoom_factor:.1f}x [z/x] | [w/s/a/d: Shift] | [p: Square 1:1]"
        cv2.putText(cam_display, zoom_txt, (30, 105), cv2.FONT_HERSHEY_SIMPLEX, 0.48, (0, 255, 120), 2)

        # Render 2D Digital Twin
        board_render = render_board_2d(
            board_2d, status=last_status_msg,
            robot_action=last_robot_protocol, in_check_color=in_check_color
        )
        cv2.imshow(win_2d, board_render)

        # Render Camera View
        cam_h, cam_w = cam_display.shape[:2]
        cv2.imshow(win_cam, cv2.resize(cam_display, (760, int(cam_h * 760 / cam_w))))

        # Keyboard Controls
        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('1') or key == ord('r'):
            # Reset Game
            live_orient = auto_detect_orientation_from_board(frame, corners)
            if live_orient != orientation:
                orientation = live_orient
                save_orientation(orientation)
                print(f"🧭 [AUTO-ORIENT] อัปเดตทิศทางกระดานให้ตรงกับหมากจริง: {ORIENTATIONS[orientation]}")

            c_engine.engine_init()
            board_2d = [row[:] for row in STANDARD_INITIAL_BOARD]
            game_state = 'WAITING_HUMAN'
            turn_count = 1
            last_robot_protocol = ""
            in_check_color = None
            scan_passes.clear()
            last_status_msg = "[RESET] New game started! White to move (Press [Space])"
            print(f"\n🔄 [RESET] รีเซ็ตกระดานและ C Engine เริ่มเกมใหม่เรียบร้อย! ({ORIENTATIONS[orientation]})")
        elif key in (10, 13):
            # [Enter] หรือ [Return] key: สั่งให้ AI คิดและเดิน
            if game_state == 'WAITING_AI_TRIGGER':
                game_state, turn_count, last_status_msg, last_robot_protocol, in_check_color = execute_robot_turn(
                    c_engine, board_2d, turn_count, win_2d
                )
            elif game_state == 'WAITING_HUMAN':
                print("[INFO] ขณะนี้ตาของหมากขาว: กรุณาเดินหมากบนกระดานจริงแล้วกด [Spacebar] เพื่อสแกนครับ")
        elif key == ord(' '):
            if game_state == 'WAITING_HUMAN':
                print("\n🔄 [SPACE] เริ่มสแกนตรวจสอบการเดินของหมากขาว...")
                game_state = 'SCANNING_HUMAN'
                scan_passes.clear()
            elif game_state == 'WAITING_AI_TRIGGER':
                # อำนวยความสะดวก: สามารถกด Spacebar เพื่อส่งสัญญาณให้ AI เดินได้เช่นกัน
                game_state, turn_count, last_status_msg, last_robot_protocol, in_check_color = execute_robot_turn(
                    c_engine, board_2d, turn_count, win_2d
                )
        elif key == ord('z'):
            old_z = zoom_factor
            zoom_factor = min(4.0, round(zoom_factor + 0.1, 1))
            if zoom_factor != old_z:
                corners = rescale_corners_for_zoom(corners, old_z, zoom_factor, fw, fh)
                save_corners(corners)
                save_zoom(zoom_factor)
        elif key == ord('x'):
            old_z = zoom_factor
            zoom_factor = max(1.0, round(zoom_factor - 0.1, 1))
            if zoom_factor != old_z:
                corners = rescale_corners_for_zoom(corners, old_z, zoom_factor, fw, fh)
                save_corners(corners)
                save_zoom(zoom_factor)
        elif key in (ord('w'), ord('W')):
            corners[:, 1] = np.clip(corners[:, 1] - 15.0, 10.0, fh - 10.0)
            save_corners(corners)
        elif key in (ord('s'), ord('S')):
            corners[:, 1] = np.clip(corners[:, 1] + 15.0, 10.0, fh - 10.0)
            save_corners(corners)
        elif key in (ord('a'), ord('A')):
            corners[:, 0] = np.clip(corners[:, 0] - 15.0, 10.0, fw - 10.0)
            save_corners(corners)
        elif key in (ord('d'), ord('D')):
            corners[:, 0] = np.clip(corners[:, 0] + 15.0, 10.0, fw - 10.0)
            save_corners(corners)
        elif key in (ord('+'), ord('=')):
            cx = float(np.mean(corners[:, 0])); cy = float(np.mean(corners[:, 1]))
            cur_size = float(corners[1][0] - corners[0][0])
            new_size = min(min(fw, fh) - 20.0, cur_size + 20.0)
            half = new_size / 2.0
            corners = np.array([[cx-half, cy-half], [cx+half, cy-half], [cx+half, cy+half], [cx-half, cy+half]], dtype=np.float32)
            save_corners(corners)
        elif key in (ord('-'), ord('_')):
            cx = float(np.mean(corners[:, 0])); cy = float(np.mean(corners[:, 1]))
            cur_size = float(corners[1][0] - corners[0][0])
            new_size = max(200.0, cur_size - 20.0)
            half = new_size / 2.0
            corners = np.array([[cx-half, cy-half], [cx+half, cy-half], [cx+half, cy+half], [cx-half, cy+half]], dtype=np.float32)
            save_corners(corners)
        elif key in (ord('p'), ord('P')):
            cx = float(np.mean(corners[:, 0])); cy = float(np.mean(corners[:, 1]))
            side = 670.0; half = side / 2.0
            corners = np.array([[cx-half, cy-half], [cx+half, cy-half], [cx+half, cy+half], [cx-half, cy+half]], dtype=np.float32)
            save_corners(corners)
            print(f"🟩 [SQUARE] รีเซ็ตกรอบจัตุรัส 1:1 ขนาด {side:.0f}x{side:.0f} px")
        elif key in (ord('f'),):
            # กลับด้านกระดาน 180 องศาทันที (Flip Board 180°: ขวา ⇋ ซ้าย หรือ ล่าง ⇋ บน)
            orientation = (orientation + 2) % 4
            save_orientation(orientation)
            last_status_msg = f"[FLIPPED 180°] {ORIENTATIONS[orientation].split(' (')[0]}"
            print(f"\n🔄 [FLIP 180°] กลับด้านกระดาน 180 องศาเป็น: {ORIENTATIONS[orientation]}")
        elif key in (ord('u'), ord('U')):
            # Auto-Detect ทิศทางกระดานจากภาพกล้องสดทันที
            new_orient = auto_detect_orientation_from_board(frame, corners)
            orientation = new_orient
            save_orientation(orientation)
            last_status_msg = f"[AUTO-ORIENT] {ORIENTATIONS[orientation].split(' (')[0]}"
            print(f"\n🧭 [AUTO-ORIENT] ตรวจพบและตั้งทิศทางกระดานเป็น: {ORIENTATIONS[orientation]}")
        elif key in (ord('o'), ord('O')):
            orientation = (orientation + 1) % 4
            save_orientation(orientation)
            print(f"🔄 [ORIENTATION] สลับทิศทางกระดานเป็น: {ORIENTATIONS[orientation]}")
        elif key == ord('c'):
            calib_mode = True
            calib_clicks.clear()
            print("\n[CALIBRATE] คลิก 4 มุมกระดาน: 1.บนซ้าย -> 2.บนขวา -> 3.ล่างขวา -> 4.ล่างซ้าย")

    cap.release()
    cv2.destroyAllWindows()
    print("\n👋 จบการทำงานของระบบ Single Player เรียบร้อยครับ!")

if __name__ == '__main__':
    main()
