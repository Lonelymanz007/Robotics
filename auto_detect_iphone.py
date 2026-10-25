"""
=============================================================================
Project: Hybrid 'Digital Twin' Chess System
Team: GM ลงเชิฟ (Robotics Course 01306202)
File: auto_detect_iphone.py

Description:
  FORCES iPhone Camera ONLY (Index 1).
  - Explicitly blocks MacBook FaceTime Camera (Index 0).
  - Automatically retries connection to allow iPhone Continuity handshake.
  - Detects 4 outer corners of chessboard automatically.
  - Press SPACE to capture & warp 8x8 board.
  - Press 'q' to quit.
=============================================================================
"""

import sys
import json
import time
import cv2
import numpy as np

CORNERS_FILE = "board_corners.json"
WARP_SIZE = 640
SQ_SIZE = WARP_SIZE // 8

def order_points(pts):
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]       # Top-Left (a8)
    rect[2] = pts[np.argmax(s)]       # Bottom-Right (h1)
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]    # Top-Right (h8)
    rect[3] = pts[np.argmax(diff)]    # Bottom-Left (a1)
    return rect

def auto_find_chessboard_corners(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    thresh = cv2.adaptiveThreshold(
        blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV, 11, 2
    )
    contours, _ = cv2.findContours(thresh, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    contours = sorted(contours, key=cv2.contourArea, reverse=True)
    for cnt in contours[:10]:
        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.03 * peri, True)
        if len(approx) == 4 and cv2.contourArea(cnt) > (frame.shape[0] * frame.shape[1] * 0.15):
            pts = approx.reshape(4, 2)
            return order_points(pts)
    return None

def draw_grid_and_labels(img):
    files = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h']
    ranks = ['8', '7', '6', '5', '4', '3', '2', '1']
    for r in range(8):
        for c in range(8):
            x1 = c * SQ_SIZE
            y1 = r * SQ_SIZE
            x2 = x1 + SQ_SIZE
            y2 = y1 + SQ_SIZE
            color = (0, 255, 0) if (r + c) % 2 == 0 else (0, 200, 255)
            cv2.rectangle(img, (x1, y1), (x2, y2), color, 1)
            sq_name = f"{files[c]}{ranks[r]}"
            cv2.putText(img, sq_name, (x1 + 6, y1 + 22),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1, cv2.LINE_AA)

def connect_iphone_only(target_idx=1, max_retries=6):
    """Exclusively connects to iPhone camera. Rejects MacBook camera (index 0)."""
    print("\n" + "="*60)
    print(" [*] CONNECTING TO IPHONE CAMERA ONLY...")
    print(" [*] (MacBook FaceTime Camera Index 0 is BLOCKED)")
    print("="*60)

    for attempt in range(1, max_retries + 1):
        print(f"[*] Attempt {attempt}/{max_retries}: Checking iPhone (Camera Index {target_idx})...")
        cap = cv2.VideoCapture(target_idx)
        if cap.isOpened():
            # Test frame grab
            for _ in range(5):
                ret, frame = cap.read()
                if ret and frame is not None and frame.size > 0:
                    h, w = frame.shape[:2]
                    print(f"\n[✓] CONNECTED TO IPHONE CAMERA! Resolution: {w}x{h}\n")
                    return cap
                time.sleep(0.3)
            cap.release()

        # If index 1 didn't connect, also test index 2 (some Macs assign iPhone to 2)
        if target_idx != 2:
            alt_cap = cv2.VideoCapture(2)
            if alt_cap.isOpened():
                ret, frame = alt_cap.read()
                if ret and frame is not None:
                    h, w = frame.shape[:2]
                    print(f"\n[✓] CONNECTED TO IPHONE CAMERA (at Index 2)! Resolution: {w}x{h}\n")
                    return alt_cap
                alt_cap.release()

        print("[!] iPhone camera handshake waiting... (Make sure iPhone is unlocked)")
        time.sleep(1.0)

    return None

def main():
    cap = connect_iphone_only(target_idx=1)
    if cap is None:
        print("\n" + "!"*60)
        print(" [!] CANNOT CONNECT TO IPHONE CAMERA")
        print(" วิธีแก้ไขด่วน:")
        print(" 1. เสียบสายชาร์จ (USB) ระหว่าง iPhone กับ MacBook (วิธีนี้ต่อติด 100%)")
        print(" 2. ปลดล็อกหน้าจอ iPhone ให้หน้าจอสว่าง")
        print(" 3. บน Mac: เปิดแอป Photo Booth -> เมนู Camera -> จิ้มเลือก iPhone 1 ครั้ง")
        print("!"*60 + "\n")
        return

    cv2.namedWindow("iPhone Camera - Chessboard Auto-Detect", cv2.WINDOW_NORMAL)

    target_dst = np.array([
        [0, 0],
        [WARP_SIZE - 1, 0],
        [WARP_SIZE - 1, WARP_SIZE - 1],
        [0, WARP_SIZE - 1]
    ], dtype="float32")

    print("[*] Press 'SPACE' on video window to CAPTURE & SAVE.")
    print("[*] Press 'q' to quit.\n")

    while True:
        ret, frame = cap.read()
        if not ret:
            print("[!] Dropped frame from iPhone.")
            break

        display_frame = frame.copy()
        corners = auto_find_chessboard_corners(frame)

        if corners is not None:
            pts_array = np.array(corners, np.int32).reshape((-1, 1, 2))
            cv2.polylines(display_frame, [pts_array], isClosed=True, color=(0, 255, 0), thickness=3)
            for pt in corners:
                cv2.circle(display_frame, (int(pt[0]), int(pt[1])), 8, (0, 0, 255), -1)

            cv2.putText(display_frame, "BOARD FOUND! Press SPACE to Capture",
                        (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
        else:
            cv2.putText(display_frame, "Searching for Chessboard...",
                        (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)

        cv2.imshow("iPhone Camera - Chessboard Auto-Detect", display_frame)

        key = cv2.waitKey(20) & 0xFF
        if key == ord('q'):
            break
        elif key == 32:  # SPACE
            if corners is not None:
                M = cv2.getPerspectiveTransform(corners, target_dst)
                warped = cv2.warpPerspective(frame, M, (WARP_SIZE, WARP_SIZE))
                draw_grid_and_labels(warped)

                with open(CORNERS_FILE, "w") as f:
                    json.dump(corners.tolist(), f)
                print(f"\n[✓] Saved corners to {CORNERS_FILE} successfully!")

                cv2.imshow("Captured 8x8 Board (Saved!)", warped)
                print("[*] Saved! Press any key to finish.")
                cv2.waitKey(0)
                break
            else:
                print("[!] Move camera to clearly see all 4 edges of the board before pressing SPACE.")

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
