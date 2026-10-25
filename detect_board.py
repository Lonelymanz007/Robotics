"""
=============================================================================
Project: Hybrid 'Digital Twin' Chess System
Team: GM ลงเชิฟ (Robotics Course 01306202)
File: detect_board.py

Description:
  Real-time Chessboard Detection using the custom-trained YOLO model (best.pt).
  - Automatically tests Webcam (source 0 or 1)
  - Detects 'Board' bounding box with confidence score
  - Displays real-time bounding box and coordinates
  - Press 'q' on the camera window to exit
=============================================================================
"""

import sys
import cv2
from ultralytics import YOLO

def main():
    # 1. Load trained model
    model_path = "best.pt"
    print(f"[*] Loading model from {model_path}...")
    try:
        model = YOLO(model_path)
    except Exception as e:
        print(f"[!] Error loading {model_path}: {e}")
        return

    # 2. Select camera source (0 = built-in Mac, 1 = external webcam)
    cam_index = 0
    if len(sys.argv) > 1:
        try:
            cam_index = int(sys.argv[1])
        except ValueError:
            cam_index = sys.argv[1]

    print(f"[*] Opening Camera (source = {cam_index})...")
    cap = cv2.VideoCapture(cam_index)
    if not cap.isOpened():
        print(f"[!] Cannot open camera {cam_index}. Trying source 1...")
        cap = cv2.VideoCapture(1)
        if not cap.isOpened():
            print("[!] Failed to open any camera. Please check your webcam connection.")
            return

    print("[*] Camera connected! Point your camera at the chessboard.")
    print("[*] Press 'q' on the video window to quit.\n")

    while True:
        ret, frame = cap.read()
        if not ret:
            print("[!] Failed to grab frame.")
            break

        # Run YOLO inference
        results = model.predict(frame, conf=0.4, verbose=False)
        annotated_frame = results[0].plot()

        # Print detection info if detected
        boxes = results[0].boxes
        if len(boxes) > 0:
            for box in boxes:
                cls_id = int(box.cls[0])
                cls_name = model.names[cls_id]
                conf = float(box.conf[0])
                x1, y1, x2, y2 = map(int, box.xyxy[0])
                cv2.putText(
                    annotated_frame,
                    f"DETECTED: {cls_name} ({conf*100:.1f}%)",
                    (x1, max(20, y1 - 10)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (0, 255, 0),
                    2
                )

        cv2.imshow("Chessboard Detection - GM ลงเชิฟ", annotated_frame)

        # Press 'q' to exit
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()
    print("[*] Detection closed.")

if __name__ == "__main__":
    main()
