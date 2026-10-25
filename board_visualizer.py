"""
board_visualizer.py
-------------------
2D Chess Board Visualizer (OpenCV)
- ฉาย 8x8 grid พร้อมหมาก
- เรียก .move(src, dst) เพื่อ animate พร้อมลูกศร
- ใช้เป็น standalone หรือ import ก็ได้
"""

import cv2
import numpy as np
import time

# ─── Config ──────────────────────────────────────────────────
CELL   = 80          # px ต่อช่อง
MARGIN = 40          # ขอบสำหรับตัวเลข/ตัวอักษร
BOARD  = CELL * 8    # 640
WIN_W  = BOARD + MARGIN
WIN_H  = BOARD + MARGIN

CLR_LIGHT  = (210, 220, 205)   # ช่องสว่าง
CLR_DARK   = (80,  120,  60)   # ช่องมืด (เขียว chess)
CLR_BG     = (40,   40,  40)   # พื้นหลัง margin
CLR_ARROW  = (0,   220, 255)   # ลูกศร cyan
CLR_HIGHLIGHT = (0, 180, 255)  # highlight src/dst

ANIM_FRAMES = 25    # จำนวน frame ของ animation
DELAY_MS    = 20    # ms ต่อ frame → ~500ms รวม

PIECES = {
    'WK': 'K', 'WQ': 'Q', 'WR': 'R',
    'WB': 'B', 'WN': 'N', 'WP': 'P',
    'BK': 'K', 'BQ': 'Q', 'BR': 'R',
    'BB': 'B', 'BN': 'N', 'BP': 'P',
}

# ─── Initial Board State ──────────────────────────────────────
# board[row][col]  row=0=rank8 (top), col=0=file a (left)
def init_board():
    b = [[None]*8 for _ in range(8)]
    order = ['R','N','B','Q','K','B','N','R']
    for c, p in enumerate(order):
        b[0][c] = 'B' + p
        b[7][c] = 'W' + p
    for c in range(8):
        b[1][c] = 'BP'
        b[6][c] = 'WP'
    return b


# ─── Coordinate helpers ───────────────────────────────────────
def sq_to_rc(sq: str):
    """'e2' → (row, col)  row=0=rank8"""
    col = ord(sq[0].lower()) - ord('a')
    row = 8 - int(sq[1])
    return row, col

def rc_to_px(row, col):
    """(row,col) → pixel center"""
    x = MARGIN + col * CELL + CELL // 2
    y = MARGIN + row * CELL + CELL // 2
    return x, y

def rc_to_sq(row, col):
    return chr(ord('a') + col) + str(8 - row)


# ─── Drawing ─────────────────────────────────────────────────
def draw_board(img, board, highlight=None):
    img[:] = CLR_BG

    # grid + pieces
    for r in range(8):
        for c in range(8):
            x0 = MARGIN + c * CELL
            y0 = MARGIN + r * CELL
            light = ((r + c) % 2 == 0)
            clr   = CLR_LIGHT if light else CLR_DARK
            cv2.rectangle(img, (x0, y0), (x0+CELL, y0+CELL), clr, -1)

            if highlight and (r, c) in highlight:
                ov = img[y0:y0+CELL, x0:x0+CELL].copy()
                cv2.rectangle(ov, (0,0),(CELL,CELL), CLR_HIGHLIGHT, -1)
                cv2.addWeighted(ov, 0.35, img[y0:y0+CELL, x0:x0+CELL], 0.65, 0,
                                img[y0:y0+CELL, x0:x0+CELL])

            piece = board[r][c]
            if piece:
                _draw_piece(img, piece, x0 + CELL//2, y0 + CELL//2)

    # border
    cv2.rectangle(img, (MARGIN, MARGIN),
                  (MARGIN+BOARD, MARGIN+BOARD), (0,0,0), 2)

    # rank labels (1-8)
    for r in range(8):
        label = str(8 - r)
        y = MARGIN + r * CELL + CELL // 2 + 6
        cv2.putText(img, label, (6, y),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200,200,200), 1)

    # file labels (a-h)
    for c in range(8):
        label = chr(ord('a') + c)
        x = MARGIN + c * CELL + CELL // 2 - 6
        cv2.putText(img, label, (x, MARGIN + BOARD + 28),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200,200,200), 1)


def _draw_piece(img, piece, cx, cy):
    is_white = piece[0] == 'W'
    symbol   = piece[1]
    if is_white:
        fill    = (255, 255, 255)
        outline = (0, 0, 0)
    else:
        fill    = (30, 30, 30)
        outline = (200, 200, 200)

    r = CELL // 2 - 8
    cv2.circle(img, (cx, cy), r, outline, -1)
    cv2.circle(img, (cx, cy), r - 3, fill, -1)

    text_size = cv2.getTextSize(symbol, cv2.FONT_HERSHEY_SIMPLEX, 0.75, 2)[0]
    tx = cx - text_size[0] // 2
    ty = cy + text_size[1] // 2
    cv2.putText(img, symbol, (tx, ty),
                cv2.FONT_HERSHEY_SIMPLEX, 0.75, outline, 3)
    cv2.putText(img, symbol, (tx, ty),
                cv2.FONT_HERSHEY_SIMPLEX, 0.75, fill, 1)


def draw_arrow(img, src_px, dst_px, progress=1.0):
    """วาดลูกศรจาก src → dst, progress 0.0-1.0"""
    x1, y1 = src_px
    x2 = int(x1 + (dst_px[0] - x1) * progress)
    y2 = int(y1 + (dst_px[1] - y1) * progress)
    if (x1, y1) != (x2, y2):
        cv2.arrowedLine(img, (x1, y1), (x2, y2),
                        CLR_ARROW, 3, tipLength=0.25)


# ─── Visualizer Class ─────────────────────────────────────────
class BoardVisualizer:
    def __init__(self, window='Chess Board'):
        self.board  = init_board()
        self.window = window
        self.img    = np.zeros((WIN_H, WIN_W, 3), dtype=np.uint8)
        cv2.namedWindow(self.window)
        self._render()

    def _render(self, highlight=None, anim_piece=None, anim_px=None,
                arrow_src=None, arrow_dst=None, arrow_prog=1.0):
        draw_board(self.img, self.board, highlight)
        if arrow_src and arrow_dst:
            draw_arrow(self.img, arrow_src, arrow_dst, arrow_prog)
        if anim_piece and anim_px:
            _draw_piece(self.img, anim_piece, anim_px[0], anim_px[1])
        cv2.imshow(self.window, self.img)

    def move(self, src: str, dst: str):
        """
        เดินหมากจาก src → dst (e.g. 'e2','e4')
        - แสดง highlight + ลูกศร
        - animate piece เคลื่อนที่
        """
        sr, sc = sq_to_rc(src)
        dr, dc = sq_to_rc(dst)
        piece  = self.board[sr][sc]
        if not piece:
            print(f'[WARN] ไม่มีหมากที่ {src}')
            return

        src_px = rc_to_px(sr, sc)
        dst_px = rc_to_px(dr, dc)

        # ลบหมากออกจากตำแหน่งต้นทางชั่วคราว
        self.board[sr][sc] = None

        # Animation loop
        for f in range(ANIM_FRAMES + 1):
            t = f / ANIM_FRAMES                   # 0.0 → 1.0
            ax = int(src_px[0] + (dst_px[0] - src_px[0]) * t)
            ay = int(src_px[1] + (dst_px[1] - src_px[1]) * t)
            self._render(
                highlight  = {(sr, sc), (dr, dc)},
                anim_piece = piece,
                anim_px    = (ax, ay),
                arrow_src  = src_px,
                arrow_dst  = dst_px,
                arrow_prog = t,
            )
            if cv2.waitKey(DELAY_MS) & 0xFF == ord('q'):
                break

        # วางหมากที่ปลายทาง
        self.board[dr][dc] = piece
        self._render()
        cv2.waitKey(1)

    def set_piece(self, sq: str, piece):
        """วางหมากที่ตำแหน่ง sq (piece='WK','BP',... หรือ None)"""
        r, c = sq_to_rc(sq)
        self.board[r][c] = piece
        self._render()

    def show(self):
        """วาดกระดานปัจจุบัน"""
        self._render()
        cv2.waitKey(1)

    def wait(self):
        """Block จนกด q"""
        while True:
            self._render()
            if cv2.waitKey(30) & 0xFF == ord('q'):
                break
        cv2.destroyWindow(self.window)


# ─── Standalone Demo ──────────────────────────────────────────
if __name__ == '__main__':
    vis = BoardVisualizer()
    vis.show()
    time.sleep(1)

    moves = [
        ('e2', 'e4'),
        ('e7', 'e5'),
        ('g1', 'f3'),
        ('b8', 'c6'),
        ('f1', 'c4'),
    ]

    for src, dst in moves:
        print(f'Moving {src} → {dst}')
        time.sleep(0.5)   # delay ก่อนเดิน
        vis.move(src, dst)
        time.sleep(0.3)

    print('กด q เพื่อปิด')
    vis.wait()
