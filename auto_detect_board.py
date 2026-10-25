"""
=============================================================================
Project: Hybrid 'Digital Twin' Chess System
Team: GM ลงเชิฟ (Robotics Course 01306202)
File: auto_detect_board.py

Description:
  Automatic Chessboard Corner Detection (Zero Manual Clicking).
  - Works with iPhone Camera (Live or Snapshot mode).
  - Also works by passing an iPhone photo directly: python3 auto_detect_board.py photo.jpg
  - Automatically identifies the 4 outer corners using largest quadrilateral contour.
  - Automatically warps and overlays the 8x8 grid.
  - Saves corners to 'board_corners.json'.
=============================================================================
"""

import sys
import json
import os
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
    """Automatically find the 4 outer corners of the chessboard."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    thresh = cv2.adaptiveThreshold(
        blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV, 11, 2
    )

    # Find contours
    contours, _ = cv2.findContours(thresh, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    # Sort contours by area descending
    contours = sorted(contours, key=cv2.contourArea, reverse=True)

    for cnt in contours[:10]:
        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.03 * peri, True)

        # Looking for a 4-corner polygon with reasonable size
        if len(approx) == 4 and cv2.contourArea(cnt) > (frame.shape[0] * frame.shape[1] * 0.15):
            pts = approx.reshape(4, 2)
            ordered = order_points(pts)
            return ordered

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

def get_working_camera(preferred_idx=1):
    for idx in [preferred_idx, 0 if preferred_idx != 0 else 1, 2]:
        cap = cv2.VideoCapture(idx)
        if cap.isOpened():
            ret, _ = cap.read()
            if ret:
                print(f"[✓] Connected to Camera Index {idx}")
                return cap, idx
            cap.release()
    return None, -1

def process_and_save(frame, corners):
    target_dst = np.array([
        [0, 0],
        [WARP_SIZE - 1, 0],
        [WARP_SIZE - 1, WARP_SIZE - 1],
        [0, WARP_SIZE - 1]
    ], dtype="float32")

    M = cv2.getPerspectiveTransform(corners, target_dst)
    warped = cv2.warpPerspective(frame, M, (WARP_SIZE, WARP_SIZE))
    draw_grid_and_labels(warped)

    # Save to JSON
    with open(CORNERS_FILE, "w") as f:
        json.dump(corners.tolist(), f)
    print(f"[✓] Auto-detected corners saved to {CORNERS_FILE} successfully!")

    cv2.imshow("Auto-Detected 8x8 Board", warped)
    cv2.waitKey(0)

def main():
    # If image file passed as argument
    if len(sys.argv) > 1 and os.path.exists(sys.argv[1]):
        image_path = sys.argv[1]
        print(f"[*] Processing iPhone photo: {image_path}...")
        frame = cv2.imread(image_path)
        if frame is None:
            print("[!] Cannot read image file.")
            return

        corners = auto_find_chessboard_corners(frame)
        if corners is not None:
            print("[✓] Chessboard corners found automatically!")
            process_and_save(frame, corners)
        else:
            print("[!] Could not auto-detect chessboard in this photo.")
        return

    # Otherwise run camera mode
    cap, actual_idx = get_working_camera(1)
    if cap is None:
        print("[!] No camera found.")
        return

    print("\n" + "="*60)
    print(" AUTO CHESSBOARD CAPTURE (iPhone)")
    print(" - Point your iPhone at the chessboard.")
    print(" - Press 'SPACE' to TAKE A PHOTO & AUTO-DETECT corners.")
    print(" - Press 'q' to quit.")
    print("="*60 + "\n")

    target_dst = np.array([
        [0, 0],
        [WARP_SIZE - 1, 0],
        [WARP_SIZE - 1, WARP_SIZE - 1],
        [0, WARP_SIZE - 1]
    ], dtype="float32")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        display_frame = frame.copy()
        corners = auto_find_chessboard_corners(frame)

        if corners is not None:
            pts_array = np.array(corners, np.int32).reshape((-1, 1, 2))
            cv2.polylines(display_frame, [pts_array], isClosed=True, color=(0, 255, 0), thickness=3)
            for i, pt in enumerate(corners):
                cv2.circle(display_frame, (int(pt[0]), int(pt[1])), 8, (0, 0, 255), -1)

            cv2.putText(display_frame, "CHESSBOARD DETECTED! Press SPACE to Capture & Save",
                        (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        else:
            cv2.putText(display_frame, "Searching for Chessboard...",
                        (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)

        cv2.imshow("iPhone Live Feed - Auto Chessboard", display_frame)

        key = cv2.waitKey(20) & 0xFF
        if key == ord('q'):
            break
        elif key == 32:  # SPACEBAR
            if corners is not None:
                print("[*] Photo captured! Processing corners...")
                M = cv2.getPerspectiveTransform(corners, target_dst)
                warped = cv2.warpPerspective(frame, M, (WARP_SIZE, WARP_SIZE))
                draw_grid_and_labels(warped)

                with open(CORNERS_FILE, "w") as f:
                    json.dump(corners.tolist(), f)
                print(f"[✓] Saved corners to {CORNERS_FILE}!")

                cv2.imshow("Captured & Warped 8x8 Board", warped)
                print("[✓] Done! Press any key on the image window to close.")
                cv2.waitKey(0)
                break
            else:
                print("[!] Cannot capture: Chessboard contour not clearly visible yet.")

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
