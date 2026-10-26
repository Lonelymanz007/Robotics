#include <webots/robot.h>
#include <webots/motor.h>
#include <webots/position_sensor.h>
#include <math.h>
#include <stdio.h>

#define TIME_STEP 16

int main(int argc, char **argv) {
  wb_robot_init();

  WbDeviceTag cart_motor = wb_robot_get_device("cart_motor");
  wb_motor_set_position(cart_motor, INFINITY);
  wb_motor_set_velocity(cart_motor, 0.0);

  WbDeviceTag pos = wb_robot_get_device("PENDULUM_SENSOR");
  wb_position_sensor_enable(pos, TIME_STEP);

  double P = 200;
  double D = 20.0;
  double I =  4.5; 

  double integral = 0.0;
  double dt = TIME_STEP * 0.001;
  double prev_err = 0.0;
  double derivative = 0.0;
  double time = 0.0;
  
  while (wb_robot_step(TIME_STEP) != -1) {
    double current_angle = wb_position_sensor_get_value(pos);
    
    double target_angle = -1.6501; 
    double error = current_angle - target_angle;
    
    while (error >  M_PI) 
      error -= 2.0 * M_PI;
    while (error < -M_PI) 
      error += 2.0 * M_PI;

    derivative = (error - prev_err) / dt;
    integral = integral + (error * dt);

    double speed = (P * error) + (I * integral) + (D * derivative);
    time = time + (TIME_STEP * 0.001);
    printf("%.3f\n", error);

    if (speed >  100.0)
      speed =  100.0;
    if (speed < -100.0)
      speed = -100.0;
      
    wb_motor_set_velocity(cart_motor, speed);

      prev_err = error;
  }

  wb_robot_cleanup();
  return 0;
}