"""
=============================================================================
Project: Hybrid 'Digital Twin' Chess System
Team: GM ลงเชิฟ (Robotics Course 01306202)
File: calibrate_board.py (Updated with Smart Camera Auto-Scan)
=============================================================================
"""

import sys
import json
import os
import cv2
import numpy as np

CORNERS_FILE = "board_corners.json"
WARP_SIZE = 640
SQUARE_SIZE = WARP_SIZE // 8

clicked_points = []

def mouse_callback(event, x, y, flags, param):
    global clicked_points
    if event == cv2.EVENT_LBUTTONDOWN:
        if len(clicked_points) < 4:
            clicked_points.append([x, y])
            print(f"[+] Clicked Corner {len(clicked_points)}: ({x}, {y})")

def draw_grid_and_labels(img):
    files = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h']
    ranks = ['8', '7', '6', '5', '4', '3', '2', '1']
    for r in range(8):
        for c in range(8):
            x1 = c * SQUARE_SIZE
            y1 = r * SQUARE_SIZE
            x2 = x1 + SQUARE_SIZE
            y2 = y1 + SQUARE_SIZE
            color = (0, 255, 0) if (r + c) % 2 == 0 else (0, 200, 255)
            cv2.rectangle(img, (x1, y1), (x2, y2), color, 1)
            sq_name = f"{files[c]}{ranks[r]}"
            cv2.putText(img, sq_name, (x1 + 6, y1 + 22),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1, cv2.LINE_AA)

def get_working_camera(preferred_idx=1):
    indices_to_try = [preferred_idx, 0 if preferred_idx != 0 else 1, 2]
    for idx in indices_to_try:
        cap = cv2.VideoCapture(idx)
        if cap.isOpened():
            ret, _ = cap.read()
            if ret:
                print(f"[✓] Successfully opened Camera Index {idx}")
                return cap, idx
            cap.release()
    return None, -1

def main():
    global clicked_points

    if os.path.exists(CORNERS_FILE):
        try:
            with open(CORNERS_FILE, "r") as f:
                saved = json.load(f)
                if len(saved) == 4:
                    clicked_points = saved
                    print(f"[*] Loaded existing corners from {CORNERS_FILE}")
        except Exception:
            pass

    preferred_idx = 1
    if len(sys.argv) > 1:
        try:
            preferred_idx = int(sys.argv[1])
        except ValueError:
            pass

    cap, actual_idx = get_working_camera(preferred_idx)
    if cap is None:
        print("[!] No accessible camera found. Please wake up your iPhone or check webcam.")
        return

    cv2.namedWindow("Original Camera Feed")
    cv2.setMouseCallback("Original Camera Feed", mouse_callback)

    print("\n" + "="*60)
    print(" INSTRUCTIONS:")
    print(" 1. Click the 4 corners of the chessboard:")
    print("    [1] Top-Left (a8)  [2] Top-Right (h8)")
    print("    [3] Bottom-Right (h1)  [4] Bottom-Left (a1)")
    print(" 2. Press 's' to SAVE to board_corners.json")
    print(" 3. Press 'r' to RESET corners.")
    print(" 4. Press 'q' to QUIT.")
    print("="*60 + "\n")

    target_dst = np.array([
        [0, 0],
        [WARP_SIZE - 1, 0],
        [WARP_SIZE - 1, WARP_SIZE - 1],
        [0, WARP_SIZE - 1]
    ], dtype="float32")

    corner_names = ["1.Top-Left (a8)", "2.Top-Right (h8)", "3.Bottom-Right (h1)", "4.Bottom-Left (a1)"]
    colors = [(0, 0, 255), (0, 255, 255), (0, 255, 0), (255, 0, 0)]

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        display_frame = frame.copy()

        for i, pt in enumerate(clicked_points):
            cv2.circle(display_frame, (int(pt[0]), int(pt[1])), 7, colors[i], -1)
            cv2.putText(display_frame, corner_names[i], (int(pt[0]) + 10, int(pt[1]) - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, colors[i], 2)

        if len(clicked_points) == 4:
            pts_array = np.array(clicked_points, np.int32).reshape((-1, 1, 2))
            cv2.polylines(display_frame, [pts_array], isClosed=True, color=(0, 255, 0), thickness=2)

            rect = np.array(clicked_points, dtype="float32")
            M = cv2.getPerspectiveTransform(rect, target_dst)
            warped = cv2.warpPerspective(frame, M, (WARP_SIZE, WARP_SIZE))

            draw_grid_and_labels(warped)
            cv2.imshow("Warped 8x8 Chessboard (Bird's Eye View)", warped)
        else:
            hint = f"Click corner {len(clicked_points) + 1}/4: {corner_names[len(clicked_points)]}"
            cv2.putText(display_frame, hint, (20, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 0, 255), 2)

        cv2.imshow("Original Camera Feed", display_frame)

        key = cv2.waitKey(20) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('r'):
            clicked_points = []
            if os.path.exists(CORNERS_FILE):
                os.remove(CORNERS_FILE)
            print("[*] Reset all corners.")
        elif key == ord('s'):
            if len(clicked_points) == 4:
                with open(CORNERS_FILE, "w") as f:
                    json.dump(clicked_points, f)
                print(f"[✓] Saved 4 corners to {CORNERS_FILE} successfully!")

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()
