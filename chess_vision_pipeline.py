"""
=============================================================================
Project: Hybrid 'Digital Twin' Chess System
Team: GM ลงเชิฟ (Robotics Course 01306202)
File: chess_vision_pipeline.py (Updated with Smart Camera Auto-Scan)
=============================================================================
"""

import sys
import json
import os
import subprocess
import cv2
import numpy as np

CORNERS_FILE = "board_corners.json"
ENGINE_BIN = "./robotic_engine"
WARP_SIZE = 640
SQ_SIZE = WARP_SIZE // 8

FILES = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h']
RANKS = ['8', '7', '6', '5', '4', '3', '2', '1']

def get_working_camera(preferred_idx=1):
    indices_to_try = [preferred_idx, 0 if preferred_idx != 0 else 1, 2]
    for idx in indices_to_try:
        cap = cv2.VideoCapture(idx)
        if cap.isOpened():
            ret, _ = cap.read()
            if ret:
                print(f"[✓] Successfully connected to Camera Index {idx}")
                return cap, idx
            cap.release()
    return None, -1

class ChessVisionPipeline:
    def __init__(self, cam_source=1):
        self.cam_source = cam_source
        self.corners = self.load_corners()
        self.reference_board = None
        self.stable_counter = 0
        self.last_move_detected = None
        self.is_human_turn = True
        self.engine_proc = None

        self.start_engine()

    def load_corners(self):
        if os.path.exists(CORNERS_FILE):
            with open(CORNERS_FILE, "r") as f:
                return np.array(json.load(f), dtype="float32")
        return None

    def start_engine(self):
        if not os.path.exists(ENGINE_BIN):
            print(f"[*] Compiling C engine via Makefile...")
            subprocess.run(["make"], check=True)

        print("[*] Starting C Chess Engine (robotic_engine)...")
        self.engine_proc = subprocess.Popen(
            [ENGINE_BIN],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )

    def warp_board(self, frame):
        target_dst = np.array([
            [0, 0],
            [WARP_SIZE - 1, 0],
            [WARP_SIZE - 1, WARP_SIZE - 1],
            [0, WARP_SIZE - 1]
        ], dtype="float32")
        M = cv2.getPerspectiveTransform(self.corners, target_dst)
        return cv2.warpPerspective(frame, M, (WARP_SIZE, WARP_SIZE))

    def get_square_coords(self, file_idx, rank_idx):
        x1 = file_idx * SQ_SIZE
        y1 = rank_idx * SQ_SIZE
        return x1, y1, x1 + SQ_SIZE, y1 + SQ_SIZE

    def analyze_board_diff(self, current_warped):
        if self.reference_board is None:
            self.reference_board = cv2.cvtColor(current_warped, cv2.COLOR_BGR2GRAY)
            return None

        curr_gray = cv2.cvtColor(current_warped, cv2.COLOR_BGR2GRAY)
        diff = cv2.absdiff(self.reference_board, curr_gray)
        _, thresh = cv2.threshold(diff, 35, 255, cv2.THRESH_BINARY)

        changed_squares = []
        for r in range(8):
            for c in range(8):
                x1, y1, x2, y2 = self.get_square_coords(c, r)
                sq_diff = thresh[y1+8:y2-8, x1+8:x2-8]
                change_ratio = np.count_nonzero(sq_diff) / (sq_diff.size + 1e-5)
                if change_ratio > 0.18:
                    changed_squares.append((FILES[c], RANKS[r], (c, r)))

        return changed_squares

    def send_move_to_engine(self, move_str):
        print(f"\n[>>> VISION MOVE DETECTED] Sending '{move_str}' to C Engine...")
        try:
            self.engine_proc.stdin.write(f"{move_str}\n")
            self.engine_proc.stdin.flush()
        except Exception as e:
            print(f"[!] Engine pipe error: {e}")

    def run(self):
        cap, actual_idx = get_working_camera(self.cam_source)
        if cap is None:
            print("[!] Cannot open camera. Please wake up your iPhone or check webcam connection.")
            return

        print("\n" + "="*65)
        print(" CHESS DIGITAL TWIN - LIVE VISION PIPELINE ACTIVE")
        print(" - Make a move on physical board (e.g. e2 to e4).")
        print(" - Press 'c' to capture initial board state as baseline.")
        print(" - Press 'q' to quit.")
        print("="*65 + "\n")

        while True:
            ret, frame = cap.read()
            if not ret:
                break

            if self.corners is None:
                cv2.putText(frame, "CORNERS NOT CALIBRATED! Please run calibrate_board.py first.",
                            (30, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                cv2.imshow("Chess Vision Pipeline - GM ลงเชิฟ", frame)
                if cv2.waitKey(20) & 0xFF == ord('q'):
                    break
                continue

            warped = self.warp_board(frame)
            display_warped = warped.copy()

            for r in range(8):
                for c in range(8):
                    x1, y1, x2, y2 = self.get_square_coords(c, r)
                    cv2.rectangle(display_warped, (x1, y1), (x2, y2), (60, 60, 60), 1)

            changed = self.analyze_board_diff(warped)
            if changed and len(changed) == 2:
                self.stable_counter += 1
                sq1 = f"{changed[0][0]}{changed[0][1]}"
                sq2 = f"{changed[1][0]}{changed[1][1]}"

                for sq in changed:
                    c, r = sq[2]
                    x1, y1, x2, y2 = self.get_square_coords(c, r)
                    cv2.rectangle(display_warped, (x1, y1), (x2, y2), (0, 255, 255), 3)

                cv2.putText(display_warped, f"Move Candidate: {sq1} <-> {sq2}", (20, 30),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)

                if self.stable_counter > 25:
                    move_candidate = f"{sq1}{sq2}"
                    self.send_move_to_engine(move_candidate)
                    self.reference_board = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)
                    self.stable_counter = 0
            else:
                self.stable_counter = max(0, self.stable_counter - 1)

            cv2.imshow("Chess Vision Pipeline - Live iPhone Board", display_warped)

            key = cv2.waitKey(25) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('c'):
                self.reference_board = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)
                print("[*] Captured new baseline board state.")

        cap.release()
        cv2.destroyAllWindows()
        if self.engine_proc:
            self.engine_proc.terminate()

def main():
    cam_id = 1
    if len(sys.argv) > 1:
        try:
            cam_id = int(sys.argv[1])
        except ValueError:
            pass
    pipeline = ChessVisionPipeline(cam_source=cam_id)
    pipeline.run()

if __name__ == "__main__":
    main()
