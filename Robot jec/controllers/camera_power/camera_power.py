from controller import Robot

robot = Robot()
timestep = int(robot.getBasicTimeStep())

# Find the camera and turn it on
cam = robot.getDevice("camera")
cam.enable(timestep)

# Keep the camera running
while robot.step(timestep) != -1:
    pass