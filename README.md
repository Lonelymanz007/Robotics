# ♚ Hybrid Physical-to-Digital Twin Chess System

> **Team:** GM ลงเซิฟ — Robotics Course 01306202
> 🇹🇭 [ภาษาไทย (Thai version)](README_TH.md)

## What is this?

A chess system that connects a **real chessboard** to a **digital twin**. A top-down iPhone camera watches the physical board. Each piece has a coloured sticker that identifies its type. The system turns each physical move into a move on a 2D digital board. In Single Player mode, a **C chess AI** answers as Black and sends the move to a Webots robot simulation.

| Program | What it does |
| :--- | :--- |
| `chess_live_board.py` | Tracks every physical move (White and Black) and mirrors it on the 2D board. No AI. |
| `chess_single_player.py` | Human (White, real board) vs. Robot AI (Black, C engine). Checks the human's move against the chess rules, checks that the physical board matches memory, then lets the AI move. |
| `libchess_ai.dylib` (C) | Chess rules + Minimax AI (Alpha-Beta, depth 3), called from Python via `ctypes`. |

---

## Overall Pipeline

```mermaid
flowchart LR
    CAM["iPhone Camera"] --> GEO["Board Mapping<br/>pixel to square"]
    GEO --> DET["Piece Detection<br/>sticker colour + team"]
    DET --> MOVE["Move Detection<br/>compare with memory"]
    MOVE --> TWIN[("2D Digital Twin")]
    MOVE -->|Single Player| AI["C Engine<br/>rules + Minimax"]
    AI --> TWIN
    AI --> WEB["Webots Robot Command"]
```

---

## 1. Board Mapping (Camera Pixels → Chess Squares)

The 4 board corners (saved, or clicked during calibration) are matched to `a8, h8, h1, a1` based on which side White sits on (auto-detected from brightness). A **perspective transform** then turns the camera view into a flat 800×800 board, where each 100×100 cell is one square.

```mermaid
flowchart TD
    A(["Camera frame"]) --> B["Digital zoom (center crop)"]
    B --> C["Load 4 board corners"]
    C --> D["Auto-detect orientation<br/>brighter side = White"]
    D --> E["Assign corners to a8, h8, h1, a1"]
    E --> F["Perspective transform matrix M"]
    F --> G["Sticker center (u,v) to flat board (x,y)"]
    G --> H(["Square: col = x/100, row = y/100"])
```

## 2. Piece Detection

| Sticker colour | Piece |
| :--- | :--- |
| Orange | Queen |
| Yellow | Pawn |
| Green | Knight |
| Blue | Bishop |
| Violet | King |
| Magenta | Rook |

The team is read from the brightness of the piece body just below the sticker (bright = White, dark = Black).

```mermaid
flowchart TD
    A(["Frame (HSV)"]) --> B["Mask each sticker colour"]
    B --> C["Clean noise (open + dilate)"]
    C --> D["Find contours, drop tiny blobs"]
    D --> E["Map center to a square"]
    E --> F["Check body brightness: White or Black"]
    F --> G(["8x8 detected board, e.g. WP at e2"])
```

## 3. Move Detection

When the user presses a key, the camera scans **16 frames** and counts how often each square is seen occupied. It then compares this with the digital board kept in memory:

- **Source:** a square that should have a piece but is now almost never seen.
- **Destination:** an empty square that is now occupied (or an enemy square for a capture).
- Each candidate pair gets a score (destination empty, same piece type, same team, short distance). The highest score wins, and **only one move** is applied per scan.
- If the King moves 2 squares (castling), the Rook moves automatically.

```mermaid
flowchart TD
    A(["Key pressed"]) --> B["Scan 16 frames"]
    B --> C["Count hits per square"]
    C --> D["Find source squares (piece disappeared)"]
    C --> E["Find destination squares (piece appeared)"]
    D --> F["Score every source to destination pair"]
    E --> F
    F --> G{"Any candidate?"}
    G -->|no| H(["No move, board unchanged"])
    G -->|yes| I["Apply best move to the 2D board"]
    I --> J{"King moved 2 squares?"}
    J -->|yes| K(["Also move the Rook (castling)"])
    J -->|no| L(["Done"])
```

---

## 4. `chess_live_board.py` — Live Board Tracker

Mirrors every physical move, for both colours, onto the 2D board.

```mermaid
flowchart TD
    S(["Start"]) --> A["Open camera, load settings,<br/>auto-detect orientation"]
    A --> B["2D board = standard start position"]
    B --> L["Live loop: show camera + grid + detections"]
    L --> K{"Key"}
    K -->|Space| M["Move Detection (16-frame scan)"]
    M --> U["Update 2D board"] --> L
    K -->|"f / o / u"| O["Flip / rotate / auto-orient"] --> L
    K -->|"z x w a s d + - p c"| Z["Zoom / move / resize / calibrate frame"] --> L
    K -->|"1 / 0 / r"| R["Reset board"] --> L
    K -->|q| E(["Exit"])
```

---

## 5. `chess_single_player.py` — Human vs. Robot AI

You play **White** on the real board. The **AI plays Black**. The AI only moves if:
1. Your move is **legal** (checked by the C engine). Otherwise both squares **glow red** and show "ILLEGAL".
2. The **physical board matches memory**. Otherwise the missing squares **flash amber** and show "MISSING".

```mermaid
flowchart TD
    A(["Your turn: move a White piece"]) --> B{"Key"}
    B -->|Space| C["Scan + detect move"]
    B -->|Enter| C2["Scan + detect move<br/>(then go straight to AI)"]
    C --> D{"Legal move?<br/>engine_is_legal_move"}
    C2 --> D
    D -->|no| E(["Red ILLEGAL glow<br/>put the piece back, try again"])
    D -->|yes| F["Update 2D board + save mini memory"]
    F --> G{"Enter pressed?"}
    G -->|"not yet"| G1["Wait for Enter"] --> H
    G -->|yes| H{"Physical board matches memory?<br/>8-frame field check"}
    H -->|no| I(["Amber MISSING squares<br/>fix the board, press Enter"])
    H -->|yes| J["Send move to C engine"]
    J --> K["AI thinks (Minimax depth 3)"]
    K --> L["Animate Black move<br/>write Webots command"]
    L --> M{"Game over?"}
    M -->|no| A
    M -->|yes| N(["Checkmate / Draw"])
```

---

## 6. C Engine — How the AI Decides

1. Python sends the move as text, e.g. `"e2e4"`, which is converted to board indices.
2. The engine **generates all legal moves**: it makes each candidate move and rejects it if its own King ends up in check. This covers checks, pins and castling.
3. For Black's reply, it runs **Minimax with Alpha-Beta pruning** (depth 3):
   - **Score** = material (P=100, N=320, B=330, R=500, Q=900) + position bonus for pawns and knights. White − Black.
   - White maximises and Black (the AI) minimises. Faster checkmates are preferred.
4. It returns the best move, a robot instruction and a game status (continue / checkmate / stalemate).

```mermaid
flowchart TD
    A(["'e2e4' from Python"]) --> B["Convert to board indices"]
    B --> C["Generate legal moves"]
    C --> D{"Move in legal list?"}
    D -->|no| E(["Reject: ILLEGAL"])
    D -->|yes| F["Apply White move"]
    F --> G{"Black has legal moves?"}
    G -->|no| H(["Checkmate or Stalemate"])
    G -->|yes| I["Minimax + Alpha-Beta, depth 3"]
    I --> J["Best Black move, e.g. g8f6"]
    J --> K["Build robot command:<br/>MOVE g8 f6 + gripper instruction"]
    K --> L(["Return move + game status"])
```

**Robot output:** `webots_command.txt` (e.g. `MOVE g8 f6`) and `webots_move.json` (latest move + gripper instruction).

---

## 7. Installation

```bash
pip3 install opencv-python numpy pillow
make            # builds libchess_ai.dylib and robotic_engine
```

Setup tips: place the iPhone **directly above** the board. Make sure the green frame lines up with the board edges and the `WHITE` label sits on the White side.

---

## 8. Usage

### Live Board

```bash
python3 chess_live_board.py 1         # standard start position (recommended)
python3 chess_live_board.py 0         # read the board from the camera
python3 chess_live_board.py 1 flip    # board rotated 180°
python3 chess_live_board.py 1 black   # show the 2D board from Black's side
```

1. Move one piece (either colour) and take your hand away.
2. Press **Space**. The move appears on the 2D board.

### Single Player

```bash
python3 chess_single_player.py 1
```

1. Move a **White** piece and take your hand away.
2. Press **Enter** to end your turn: scan → rule check → board check → AI moves.
   (Press **Space** first if you only want to preview and check your move.)
3. Red glow = illegal move, so put the piece back. Amber = missing pieces, so fix the board and press Enter.
4. Copy the AI's Black move onto the real board, then play your next move.

### Keys

| Key | Live Board | Single Player |
| :---: | :--- | :--- |
| `Space` | Scan & sync move | Scan & check move (no AI) |
| `Enter` | — | End turn → AI moves |
| `1` | Reset to start position | New game |
| `r` | Clear & re-scan | New game |
| `0` | Scan board from camera | — |
| `t` | Toggle turn indicator | — |
| `f` | Flip board 180° | Flip board 180° |
| `F` / `v` | Flip 2D view | — |
| `o` / `u` | Rotate 90° / Auto-orient | Rotate 90° / Auto-orient |
| `z` / `x` | Zoom in / out | Zoom in / out |
| `w a s d` | Move frame | Move frame |
| `+` / `-` | Resize frame | Resize frame |
| `p` | Reset to square frame | Reset to square frame |
| `c` | Click 4 corners to calibrate | Click 4 corners to calibrate |
| `q` | Quit | Quit |
