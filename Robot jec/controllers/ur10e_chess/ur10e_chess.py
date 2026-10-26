import ikpy.chain
import numpy as np
from controller import Robot, Supervisor
import warnings
import os
import re
import json
import socket
import sys

# ==============================================================================
# 1. MOVE QUEUE & IPC BRIDGE (Real-time Single Player Link)
# ==============================================================================
CONTROLLER_DIR = os.path.dirname(os.path.abspath(__file__))
QUEUE_FILE = os.path.join(CONTROLLER_DIR, "webots_queue.json")
STATUS_FILE = os.path.join(CONTROLLER_DIR, "webots_status.json")
TURN_FILE = os.path.join(CONTROLLER_DIR, "shared_turn.txt")

# Internal queue for live move commands received from Single Player
pending_moves = []
last_processed_cmd_id = -1

# Height settings:
Z_TRAVEL = 0.50        # High cruise height across board
Z_CLEAR  = 0.30        # High overhead clearance (lifts piece 7cm above all pawn heads)


# ==============================================================================
# 2. CHESSBOARD 2-POINT GROUND TRUTH CALIBRATION & PIECE HEIGHTS
# ==============================================================================
A1_X, A1_Y = -0.41, 0.38
H8_X, H8_Y = -1.15, -0.38

# --- Global Graveyard & Discard Positions (OUTSIDE the function) ---
GRAVEYARD_BLACK = np.array([0.19, 0.02])  # Side of board for Black robot
GRAVEYARD_WHITE = np.array([-1.77,  0.02])  # Side of board for White robot
discard_count = 0

def square_to_world(square_str):
    """Calculates the exact (X, Y) world coordinates of any square a1 to h8."""
    sq = square_str.strip().lower()
    col = ord(sq[0]) - ord('a')   # 'a'->0, 'h'->7
    row = int(sq[1]) - 1          # '1'->0, '8'->7
    
    x = A1_X + (col / 7.0) * (H8_X - A1_X)
    y = A1_Y + (row / 7.0) * (H8_Y - A1_Y)
    return np.array([x, y])
    
def get_piece_touch_z(square_str):
    """Returns the exact top touchdown height for each piece type in Webots."""
    sq = square_str.strip().lower()
    col = sq[0]
    rank = int(sq[1])
    
    if rank in {2, 7}:
        return 0.145  # Pawns
    if col in {'b', 'g'}:
        return 0.173  # Knights
    elif col in {'e'}:
        return 0.178  # Kings
    else:
        return 0.165  # Bishops, Rooks, Queens

# ==============================================================================
# 3. ROBOT & VACUUM GRIPPER INITIALIZATION
# ==============================================================================
try:
    robot = Supervisor()
    is_supervisor = robot.getSelf() is not None
except Exception:
    robot = Robot()
    is_supervisor = False

timestep = int(robot.getBasicTimeStep())
robot_name = robot.getName()

# Dual-Robot Role Identification:
is_white_robot = ("(1)" in robot_name) or ("white" in robot_name.lower())
is_black_robot = not is_white_robot

if is_white_robot:
    role_str = "WHITE ROBOT [UR10e(1)]"
    my_ranks = {1, 2, 3, 4}
else:
    role_str = "BLACK ROBOT [UR10e]"
    my_ranks = {5, 6, 7, 8}

def is_my_move(square_str):
    """Returns True if the piece on square_str belongs to this robot's territory."""
    try:
        rank = int(square_str.strip()[-1])
        return rank in my_ranks
    except Exception:
        return False

# Arm motor initialization
arm_motor_names = [
    'shoulder_pan_joint',
    'shoulder_lift_joint',
    'elbow_joint',
    'wrist_1_joint',
    'wrist_2_joint',
    'wrist_3_joint'
]
arm_motors = [robot.getDevice(name) for name in arm_motor_names]
for motor in arm_motors:
    motor.setVelocity(0.35)
    motor.setAcceleration(0.7)

def calc_duration(angles_a, angles_b, v=0.35):
    """Calculates physical flight time required between two joint configurations."""
    a = angles_a[1:7] if len(angles_a) > 6 else angles_a
    b = angles_b[1:7] if len(angles_b) > 6 else angles_b
    diffs = [abs(x - y) for x, y in zip(a, b)]
    return (max(diffs) / v) + 0.8

# Replace lines 108-112 with:
current_arm_angles = [-1.571, -1.189, 1.805, 0.955, 1.571, 0.0]

def set_arm_angles(angles, v=0.35):
    """Sets joint targets with synchronized speeds so all joints move together without sagging in mid-air."""
    global current_arm_angles
    target = angles[1:7] if len(angles) > 6 else angles
    diffs = [abs(t - c) for t, c in zip(target, current_arm_angles)]
    max_diff = max(diffs)
    
    if max_diff > 1e-4:
        for motor, target_val, diff in zip(arm_motors, target, diffs):
            motor_v = max(0.02, v * (diff / max_diff))
            motor.setVelocity(motor_v)
            motor.setPosition(target_val)
    else:
        for motor, target_val in zip(arm_motors, target):
            motor.setVelocity(v)
            motor.setPosition(target_val)
            
    current_arm_angles = list(target)

# Vacuum gripper device
vacuum = robot.getDevice("vacuum gripper")
if vacuum:
    vacuum.enablePresence(timestep)
    print(f"[{role_str}]: VacuumGripper connected and ready!")
else:
    print(f"[{role_str} WARNING]: 'vacuum gripper' not found in toolSlot.")

def grip_on():
    if vacuum:
        vacuum.turnOn()

def grip_off():
    if vacuum:
        vacuum.turnOff()

grip_off()

# Universal Postures:
# Default resting posture (as usual, arm folded alongside pedestal):
DEFAULT_PARK_POSTURE = [-1.571, -1.189, 1.805, 0.955, 1.571, 0.0]
# Board-facing crane posture (Pan +1.571 turns arm to face directly into the chessboard):
FACE_BOARD_POSTURE   = [1.571, -1.189, 1.805, 0.955, 1.571, 0.0]

SIDE_POSTURE = DEFAULT_PARK_POSTURE
READY_POSTURE = FACE_BOARD_POSTURE
HOME_POSTURE = DEFAULT_PARK_POSTURE
UP_POSTURE = FACE_BOARD_POSTURE

# Initial motor position at spawn:
set_arm_angles(DEFAULT_PARK_POSTURE)


# ==============================================================================
# 4. INVERSE KINEMATICS & BASE TRANSFORM SETUP
# ==============================================================================
urdf_name = f"ur10e_skeleton_{'w' if is_white_robot else 'b'}.urdf"
with open(urdf_name, "w") as f:
    f.write(robot.getUrdf())

with warnings.catch_warnings():
    warnings.simplefilter('ignore')
    arm_chain = ikpy.chain.Chain.from_urdf_file(urdf_name)

arm_chain.active_links_mask = [
    link.name in set(arm_motor_names) for link in arm_chain.links
]

# Around lines 162-165:
# Prevent flat pose (keeps elbow bent upward in clean crane mode)
arm_chain.links[2].bounds = (-2.8, 0.0)
arm_chain.links[3].bounds = (0.1, 2.8)
# Enforce exact base position and rotation
self_node = robot.getSelf()
if self_node:
    if is_black_robot:
        self_node.getField("translation").setSFVec3f([-0.78, -0.61, 0.22])
        self_node.getField("rotation").setSFRotation([0, 0, 1, 0.0])
        self_node.resetPhysics()
    else:
        self_node.getField("translation").setSFVec3f([-0.68, 0.62, 0.24])
        self_node.getField("rotation").setSFRotation([0, 0, 1, -3.14159])
        self_node.resetPhysics()

    ROBOT_BASE_WORLD = np.array(self_node.getPosition())
    rot_flat = self_node.getOrientation()
    ROT_MATRIX = np.array(rot_flat).reshape((3, 3))
else:
    if is_white_robot:
        ROBOT_BASE_WORLD = np.array([-0.68, 0.62, 0.24])
        theta_w = -np.pi
        c_w, s_w = np.cos(theta_w), np.sin(theta_w)
        ROT_MATRIX = np.array([[c_w, -s_w, 0], [s_w, c_w, 0], [0, 0, 1]])
    else:
        ROBOT_BASE_WORLD = np.array([-0.78, -0.61, 0.22])
        ROT_MATRIX = np.eye(3)

print(f"[{role_str} ONLINE]: Base={ROBOT_BASE_WORLD.round(3)}, Assigned Ranks={sorted(list(my_ranks))}")

def solve_waypoint(world_xy, z_height, initial_guess):
    """Calculates IK angles transformed for robot base rotation, with suction cup pointing straight down."""
    target_world = np.array([world_xy[0], world_xy[1], z_height])
    diff_world = target_world - ROBOT_BASE_WORLD
    target_local = ROT_MATRIX.T @ diff_world
    target_ori = ROT_MATRIX.T @ np.array([0.0, 0.0, -1.0])
    
    return arm_chain.inverse_kinematics(
        target_local,
        target_orientation=target_ori,
        orientation_mode='Y',
        initial_position=initial_guess
    )


# ==============================================================================
# 5. REAL-TIME IPC BRIDGE & COMMAND HANDLERS
# ==============================================================================
server_socket = None
listen_port = 10002 if is_white_robot else 10001
try:
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind(("127.0.0.1", listen_port))
    server_socket.listen(5)
    server_socket.setblocking(False)
    print(f"[{role_str}]: TCP Socket Command Server listening on 127.0.0.1:{listen_port}")
except Exception as e:
    server_socket = None

MY_STATUS_FILE = os.path.join(CONTROLLER_DIR, f"webots_status_{'w' if is_white_robot else 'b'}.json")
OTHER_STATUS_FILE = os.path.join(CONTROLLER_DIR, f"webots_status_{'b' if is_white_robot else 'w'}.json")

def write_status(current_stage, is_busy, current_move=None):
    try:
        st = {
            "robot": role_str,
            "stage": current_stage,
            "busy": is_busy,
            "current_move": current_move,
            "timestamp": robot.getTime(),
            "wall_time": time.time()
        }
        with open(MY_STATUS_FILE, "w") as f:
            json.dump(st, f, indent=2)
    except Exception:
        pass

def is_other_robot_busy():
    """Checks if the opposing robot arm is currently executing a move to prevent mid-air collisions."""
    if os.path.exists(OTHER_STATUS_FILE):
        try:
            with open(OTHER_STATUS_FILE, "r") as f:
                data = json.load(f)
            # If the other robot is busy and timestamp was updated recently
            if data.get("busy", False):
                sim_diff = abs(robot.getTime() - data.get("timestamp", 0))
                wall_diff = abs(time.time() - data.get("wall_time", 0))
                if sim_diff < 40.0 or wall_diff < 40.0:
                    return True
        except Exception:
            pass
    return False

MY_QUEUE_FILE = os.path.join(CONTROLLER_DIR, f"webots_queue_{'w' if is_white_robot else 'b'}.json")
SHARED_QUEUE_FILE = os.path.join(CONTROLLER_DIR, "webots_queue.json")

# ชุดบันทึกประวัติคำสั่งเพื่อป้องกันการทำซ้ำ (Single-Execution Guard)
executed_command_keys = set()
processed_cmd_ids = set()

def fetch_incoming_commands():
    """Reads incoming commands from TCP Socket and Dedicated Queue File."""
    cmds = []

    # 1. TCP Socket
    if server_socket:
        try:
            while True:
                conn, _ = server_socket.accept()
                conn.settimeout(0.05)
                raw = conn.recv(4096)
                conn.close()
                if raw:
                    for line in raw.decode('utf-8', errors='ignore').splitlines():
                        line = line.strip()
                        if line:
                            try:
                                cmds.append(json.loads(line))
                            except Exception:
                                pass
        except Exception:
            pass

    # 2. Dedicated Queue File for this specific robot (MY_QUEUE_FILE only - ไม่เช็คคิวรวมเพื่อกันการอ่านซ้ำ)
    if os.path.exists(MY_QUEUE_FILE):
        try:
            with open(MY_QUEUE_FILE, "r") as f:
                data = json.load(f)
            action = data.get("action", "").upper()
            if action in ("MOVE", "RESET", "WIPE", "FLUSH"):
                player = data.get("player", "").lower()
                is_for_me = False
                if action in ("RESET", "WIPE", "FLUSH"):
                    is_for_me = True
                elif is_black_robot and (player.startswith("b") or not player):
                    is_for_me = True
                elif is_white_robot and player.startswith("w"):
                    is_for_me = True

                if is_for_me:
                    # Immediately consume this queue file so it can NEVER be re-read
                    with open(MY_QUEUE_FILE, "w") as f:
                        json.dump({"action": "IDLE", "consumed": True, "timestamp": time.time()}, f, indent=2)
                    cmds.append(data)
        except Exception:
            pass

    return cmds

def process_command(cmd):
    """Processes incoming MOVE or RESET commands from Single Player with strict single-execution guarantee."""
    global stage, state_start_time, pending_moves, elim_str, discard_count, current_move

    action = cmd.get("action", "").upper()

    if action in ("RESET", "WIPE", "FLUSH"):
        print(f"\n[{role_str}] 🔄 [{action} RECEIVED] Flushing all commands & parking arm safely...")
        grip_off()
        set_arm_angles(DEFAULT_PARK_POSTURE)
        pending_moves.clear()
        processed_cmd_ids.clear()
        executed_command_keys.clear()
        elim_str = None
        current_move = None
        discard_count = 0
        stage = "IDLE"
        state_start_time = robot.getTime()
        write_status("IDLE", False)

        # Wipe ALL queue files immediately to IDLE
        for qf in [MY_QUEUE_FILE, SHARED_QUEUE_FILE,
                   os.path.join(CONTROLLER_DIR, "webots_queue.json"),
                   os.path.join(CONTROLLER_DIR, "webots_queue_w.json"),
                   os.path.join(CONTROLLER_DIR, "webots_queue_b.json")]:
            try:
                if os.path.exists(qf):
                    with open(qf, "w") as f:
                        json.dump({"action": "IDLE", "pending": []}, f, indent=2)
            except Exception:
                pass

        if cmd.get("reload_world", False) and is_supervisor and is_black_robot:
            print(f"[{role_str}] 🔄 [SUPERVISOR] Reloading Webots world to initial state...")
            robot.worldReload()
        return

    elif action == "IDLE":
        return

    elif action == "MOVE":
        player = cmd.get("player", "")
        # Determine whether this move is meant for this robot
        is_my_job = False
        if is_black_robot and (player.lower().startswith("b") or not player):
            is_my_job = True
        elif is_white_robot and player.lower().startswith("w"):
            is_my_job = True

        if is_my_job:
            session = cmd.get("session", 0)
            raw_cid = cmd.get("command_id")
            cid = (session, raw_cid) if raw_cid is not None else None
            src = cmd.get("src")
            dst = cmd.get("dst")
            elim = cmd.get("elim")
            turn = cmd.get("turn", 0)

            # 1. ป้องกันการรับคำสั่งซ้ำด้วย (session, command_id)
            if cid is not None and cid in processed_cmd_ids:
                return

            # 2. ป้องกันการรับคำสั่งซ้ำด้วย Move Signature (session_player_turn_src_dst)
            move_key = f"{session}_{player}_{turn}_{src}_{dst}"
            if move_key in executed_command_keys:
                return

            # 3. ป้องกันการเพิ่มท่าเดินที่ซ้ำกับใน pending_moves หรือกำลังเดินอยู่
            if (src, dst, elim) in pending_moves:
                return
            if current_move and current_move[:2] == (src, dst):
                return

            is_castling = cmd.get("is_castling", False)
            rook_src = cmd.get("rook_src")
            rook_dst = cmd.get("rook_dst")

            # ทำเครื่องหมายว่ารับคำสั่งนี้แล้วทันที (ทำแค่รอบเดียวเท่านั้น)
            if cid is not None:
                processed_cmd_ids.add(cid)
            executed_command_keys.add(move_key)

            if is_castling and rook_src and rook_dst:
                pending_moves.append((src, dst, None))
                pending_moves.append((rook_src, rook_dst, None))
                print(f"[{role_str}] 🏰 Castling move enqueued (1x): King {src}->{dst}, Rook {rook_src}->{rook_dst}")
            elif src and dst:
                pending_moves.append((src, dst, elim))
                elim_tag = f" (Capturing {elim})" if elim else ""
                print(f"[{role_str}] 📥 Move enqueued (1x): {src}->{dst}{elim_tag}")

def read_turn():
    return 0

def write_turn(idx):
    pass

# ==============================================================================
# 6. MAIN SIMULATION LOOP (Dynamic Dual-Robot Pick-and-Place State Machine)
# ==============================================================================
stage = "STARTUP_LIFT"
state_start_time = 0.0

current_move = None
src_str = None
dst_str = None
elim_str = None

elim_travel_angles = None
elim_clear_angles  = None
elim_touch_angles  = None
discard_travel_angles = None
discard_clear_angles  = None
discard_touch_angles  = None

flight_to_face = 5.5
flight_to_pick = 3.5
flight_to_elim = 3.5
flight_travel_to_clear = 2.0
flight_clear_to_touch = 2.0
flight_to_park = 5.5
transfer_duration = 5.0

src_travel_angles = None
src_clear_angles = None
src_touch_angles = None
dst_travel_angles = None
dst_clear_angles = None
dst_touch_angles = None

while robot.step(timestep) != -1:
    now = robot.getTime()

    # Always check for incoming commands at each simulation step
    for cmd in fetch_incoming_commands():
        process_command(cmd)

    # --- Phase 1: Initialize game queue and settle into default park posture ---
    if stage == "STARTUP_LIFT":
        if now >= 2.0:
            set_arm_angles(DEFAULT_PARK_POSTURE)
            stage = "STARTUP_PAN"
            state_start_time = now

    # --- Phase 2: Settle into default park posture ---
    elif stage == "STARTUP_PAN" and (now - state_start_time) >= 2.5:
        print(f"[{role_str}]: Safely parked at default posture! Ready for commands.")
        stage = "IDLE"
        write_status("IDLE", False)

    # --- IDLE: Check pending moves queue ---
    elif stage == "IDLE":
        if pending_moves and not is_other_robot_busy():
            move_entry = pending_moves.pop(0)
            src_str = move_entry[0]
            dst_str = move_entry[1]
            elim_str = move_entry[2] if len(move_entry) > 2 else None

            current_move = move_entry
            print(f"\n[{role_str}] >>> Executing Move: {src_str.upper()} -> {dst_str.upper()}" + (f" (Capturing {elim_str.upper()})" if elim_str else "") + " <<<")
            write_status("SWING_TO_BOARD", True, f"{src_str}->{dst_str}")

            src_xy = square_to_world(src_str)
            dst_xy = square_to_world(dst_str)

            ik_guess = [0.0] * len(arm_chain.links)
            ik_guess[1:7] = FACE_BOARD_POSTURE

            # Get the exact piece height:
            piece_z = get_piece_touch_z(src_str)
            src_touch_z = piece_z
            dst_place_z = piece_z   # Holds the exact same piece, so placing height is identical!

            # Check if this move requires an elimination first:
            if elim_str:
                elim_xy = square_to_world(elim_str)
                elim_touch_z = get_piece_touch_z(elim_str)
                discard_xy = (GRAVEYARD_WHITE if is_white_robot else GRAVEYARD_BLACK) + np.array([0.0, discard_count * 0.07])
                
                # 1. Elimination pick waypoints:
                elim_touch_angles     = solve_waypoint(elim_xy, elim_touch_z, ik_guess)
                elim_clear_angles     = solve_waypoint(elim_xy, Z_CLEAR, elim_touch_angles)
                elim_travel_angles    = solve_waypoint(elim_xy, Z_TRAVEL, elim_clear_angles)
                
                # 2. Elimination discard (off-board) waypoints:
                discard_travel_angles = solve_waypoint(discard_xy, Z_TRAVEL, ik_guess)
                discard_clear_angles  = solve_waypoint(discard_xy, Z_CLEAR, discard_travel_angles)
                discard_touch_angles  = solve_waypoint(discard_xy, elim_touch_z, discard_clear_angles)

            # Solve standard move waypoints (as usual):
            src_touch_angles  = solve_waypoint(src_xy, src_touch_z, ik_guess)
            src_clear_angles  = solve_waypoint(src_xy, Z_CLEAR, src_touch_angles)     # 0.38m vertical
            src_travel_angles = solve_waypoint(src_xy, Z_TRAVEL, src_clear_angles)    # 0.50m cruise

            dst_travel_angles = solve_waypoint(dst_xy, Z_TRAVEL, ik_guess)             # 0.50m destination
            dst_clear_angles  = solve_waypoint(dst_xy, Z_CLEAR, dst_travel_angles)    # 0.38m staging
            dst_touch_angles  = solve_waypoint(dst_xy, dst_place_z, dst_clear_angles) # touchdown flat on board
            
            flight_travel_to_clear = calc_duration(src_travel_angles, src_clear_angles)
            flight_clear_to_touch  = calc_duration(src_clear_angles, src_touch_angles)

            # Step 0a: Move from default posture to face the board
            flight_to_face = calc_duration(DEFAULT_PARK_POSTURE, FACE_BOARD_POSTURE)
            print(f"[{role_str}] Moving to face the board ({flight_to_face:.1f}s)...")
            grip_off()
            set_arm_angles(FACE_BOARD_POSTURE)
            stage = "SWING_TO_BOARD"
            state_start_time = now
            write_status("SWING_TO_BOARD", True, f"{src_str}->{dst_str}")

    # Step 0b: Arrived facing board; hold here for 0.5s before reaching for piece
    elif stage == "SWING_TO_BOARD" and (now - state_start_time) >= flight_to_face:
        print(f"[{role_str}] Facing board. Pausing for 0.5s before reaching for piece...")
        stage = "PAUSE_FACING_BOARD"
        state_start_time = now

    elif stage == "PAUSE_FACING_BOARD" and (now - state_start_time) >= 0.5:
        if elim_str:
            # Step A: Fly to the piece to be eliminated first!
            flight_to_elim = calc_duration(FACE_BOARD_POSTURE, elim_travel_angles)
            print(f"[{role_str}] [ELIMINATE] Flying to {elim_str.upper()} to remove piece ({flight_to_elim:.1f}s)...")
            set_arm_angles(elim_travel_angles)
            stage = "ELIM_APPROACH_CRUISE"
            state_start_time = now
        else:
            # No elimination needed -> Go directly to pick source piece
            flight_to_pick = calc_duration(FACE_BOARD_POSTURE, src_travel_angles)
            print(f"[{role_str}] Launching to {src_str.upper()} at {Z_TRAVEL}m ({flight_to_pick:.1f}s)...")
            set_arm_angles(src_travel_angles)
            stage = "APPROACH_CRUISE"
            state_start_time = now
        # --- ELIMINATION PROCESS ---
    # 1. Lower vertically over the captured piece
    elif stage == "ELIM_APPROACH_CRUISE" and (now - state_start_time) >= flight_to_elim:
        flight_clear = calc_duration(elim_travel_angles, elim_clear_angles)
        set_arm_angles(elim_clear_angles)
        stage = "ELIM_APPROACH_CLEAR"
        state_start_time = now

    # 2. Descend to touch the piece (suction off)
    elif stage == "ELIM_APPROACH_CLEAR" and (now - state_start_time) >= flight_clear:
        grip_off()
        flight_touch = calc_duration(elim_clear_angles, elim_touch_angles)
        set_arm_angles(elim_touch_angles)
        stage = "ELIM_TOUCH_DESCEND"
        state_start_time = now

    # 3. Lock suction onto the captured piece
    elif stage == "ELIM_TOUCH_DESCEND" and (now - state_start_time) >= flight_touch:
        grip_on()
        stage = "ELIM_SUCTION"
        state_start_time = now

    # 4. Lift vertically to 0.30m
    elif stage == "ELIM_SUCTION" and (now - state_start_time) >= 1.0:
        flight_lift_clear = calc_duration(elim_touch_angles, elim_clear_angles)
        set_arm_angles(elim_clear_angles)
        stage = "ELIM_LIFT_CLEAR"
        state_start_time = now

    # 5. Rise to 0.50m cruise height
    elif stage == "ELIM_LIFT_CLEAR" and (now - state_start_time) >= flight_lift_clear:
        flight_lift_travel = calc_duration(elim_clear_angles, elim_travel_angles)
        set_arm_angles(elim_travel_angles)
        stage = "ELIM_LIFT_CRUISE"
        state_start_time = now

    # 6. Transfer high at 0.50m to the discard graveyard off the board
    elif stage == "ELIM_LIFT_CRUISE" and (now - state_start_time) >= flight_lift_travel:
        flight_discard = calc_duration(elim_travel_angles, discard_travel_angles)
        print(f"[{role_str}] [ELIMINATE] Taking piece off board to graveyard ({flight_discard:.1f}s)...")
        set_arm_angles(discard_travel_angles)
        stage = "ELIM_TRANSFER"
        state_start_time = now

    # 7. Overhead graveyard at 0.50m -> lower to 0.30m
    elif stage == "ELIM_TRANSFER" and (now - state_start_time) >= flight_discard:
        flight_d_clear = calc_duration(discard_travel_angles, discard_clear_angles)
        set_arm_angles(discard_clear_angles)
        stage = "ELIM_STAGE_CLEAR"
        state_start_time = now

    # 8. Lower to table surface
    elif stage == "ELIM_STAGE_CLEAR" and (now - state_start_time) >= flight_d_clear:
        flight_d_touch = calc_duration(discard_clear_angles, discard_touch_angles)
        set_arm_angles(discard_touch_angles)
        stage = "ELIM_TOUCH_PLACE"
        state_start_time = now

    # 9. Release piece in graveyard
    elif stage == "ELIM_TOUCH_PLACE" and (now - state_start_time) >= flight_d_touch:
        grip_off()
        discard_count += 1
        print(f"[{role_str}] [ELIMINATE] Piece discarded! Starting normal move...")
        stage = "ELIM_RELEASE"
        state_start_time = now

    # 10. Retract up to 0.50m and transition seamlessly into normal pick move!
    elif stage == "ELIM_RELEASE" and (now - state_start_time) >= 0.5:
        flight_retract = calc_duration(discard_touch_angles, discard_travel_angles)
        set_arm_angles(discard_travel_angles)
        stage = "ELIM_RETRACT"
        state_start_time = now

    # 11. Now proceed with the exact same normal move as always!
    elif stage == "ELIM_RETRACT" and (now - state_start_time) >= flight_retract:
        elim_str = None  # Elimination finished!
        flight_to_pick = calc_duration(discard_travel_angles, src_travel_angles)
        print(f"[{role_str}] Launching to {src_str.upper()} at {Z_TRAVEL}m ({flight_to_pick:.1f}s)...")
        set_arm_angles(src_travel_angles)
        stage = "APPROACH_CRUISE"
        state_start_time = now

    # Step 1a: Arrived directly above piece at 0.50m; lower vertically like an elevator to 0.38m
    elif stage == "APPROACH_CRUISE" and (now - state_start_time) >= flight_to_pick:
        print(f"[{role_str}] Overhead at {src_str.upper()}. Lowering to {Z_CLEAR}m...")
        set_arm_angles(src_clear_angles)
        stage = "APPROACH_CLEAR"
        state_start_time = now

    # 1. Lower onto piece head with SUCTION OFF
    elif stage == "APPROACH_CLEAR" and (now - state_start_time) >= flight_travel_to_clear:
        grip_off()                              # Keep suction OFF while descending!
        set_arm_angles(src_touch_angles)
        stage = "TOUCH_DESCEND"
        state_start_time = now

    # 2. Suction cup has landed flat and flush. NOW turn suction ON!
    elif stage == "TOUCH_DESCEND" and (now - state_start_time) >= flight_clear_to_touch:
        grip_on()                               # Turn suction ON only when seated flat!
        stage = "TOUCH_PICK"
        state_start_time = now

    # Step 2: Confirm vacuum presence and seal
    elif stage == "TOUCH_PICK":
        has_piece = vacuum.getPresence() if vacuum else False
        if has_piece or (now - state_start_time) >= 1.5:
            print(f"[{role_str}] Vacuum seal locked. Presence: {has_piece}")
            stage = "SUCTION"
            state_start_time = now

    # Step 3a: Lift straight up vertically like an elevator to 0.38m (clears all pawn heads!)
    elif stage == "SUCTION" and (now - state_start_time) >= 0.5:
        print(f"[{role_str}] Lifting vertically to {Z_CLEAR}m...")
        set_arm_angles(src_clear_angles)
        stage = "LIFT_CLEAR"
        state_start_time = now

    # Step 3b: Rise to 0.50m cruise altitude
    elif stage == "LIFT_CLEAR" and (now - state_start_time) >= flight_clear_to_touch:
        print(f"[{role_str}] Rising to {Z_TRAVEL}m cruise altitude...")
        set_arm_angles(src_travel_angles)
        stage = "LIFT_CRUISE"
        state_start_time = now

    # Step 4: Fly high across board maintaining 0.50m (no mid-air sag!)
    elif stage == "LIFT_CRUISE" and (now - state_start_time) >= flight_travel_to_clear:
        transfer_duration = calc_duration(src_travel_angles, dst_travel_angles)
        print(f"[{role_str}] Transferring high at {Z_TRAVEL}m to {dst_str.upper()} ({transfer_duration:.1f}s)...")
        set_arm_angles(dst_travel_angles)
        stage = "TRANSFER"
        state_start_time = now

    # Step 5: Arrived directly overhead at destination at 0.50m -> Drop down to 0.30m
    elif stage == "TRANSFER" and (now - state_start_time) >= transfer_duration:
        flight_clear_duration = calc_duration(dst_travel_angles, dst_clear_angles)
        print(f"[{role_str}] Overhead at {dst_str.upper()}. Dropping to {Z_CLEAR}m ({flight_clear_duration:.1f}s)...")
        set_arm_angles(dst_clear_angles)
        stage = "STAGE_CLEAR"
        state_start_time = now

    # Step 6: Arrived at 0.30m -> Drop down to 0.15m (or piece touch height) to place
    elif stage == "STAGE_CLEAR" and (now - state_start_time) >= flight_clear_duration:
        flight_touch_duration = calc_duration(dst_clear_angles, dst_touch_angles)
        print(f"[{role_str}] Lowering to place on board at {dst_place_z:.3f}m ({flight_touch_duration:.1f}s)...")
        set_arm_angles(dst_touch_angles)
        stage = "TOUCH_PLACE"
        state_start_time = now

    # Step 7: Piece is sitting flat on the board surface: turn vacuum OFF
    elif stage == "TOUCH_PLACE" and (now - state_start_time) >= flight_touch_duration:
        grip_off()                              # Cut suction!
        print(f"[{role_str}] Placed piece. Releasing vacuum suction...")
        stage = "RELEASE"
        state_start_time = now

    # Step 8: Wait 0.5s for air pressure to release, then retract vertically back to 0.30m
    elif stage == "RELEASE" and (now - state_start_time) >= 0.5:
        flight_retract_duration = calc_duration(dst_touch_angles, dst_clear_angles)
        print(f"[{role_str}] Retracting vertically back to {Z_CLEAR}m...")
        set_arm_angles(dst_clear_angles)        # Retract vertically
        stage = "RETRACT"
        state_start_time = now

    # Step 9: Return smoothly to default parked posture
    elif stage == "RETRACT" and (now - state_start_time) >= flight_retract_duration:
        flight_to_park = calc_duration(dst_clear_angles, DEFAULT_PARK_POSTURE)
        print(f"[{role_str}] Returning to default parked posture ({flight_to_park:.1f}s)...")
        set_arm_angles(DEFAULT_PARK_POSTURE)
        stage = "RETURN"
        state_start_time = now

    # Step 10: Arrived at default parked posture; return to IDLE and wait for next move
    elif stage == "RETURN" and (now - state_start_time) >= flight_to_park:
        print(f"[{role_str}] ✅ Move execution complete! Parked at default posture.")
        stage = "IDLE"
        current_move = None
        src_str = None
        dst_str = None
        elim_str = None
        write_status("IDLE", False)
