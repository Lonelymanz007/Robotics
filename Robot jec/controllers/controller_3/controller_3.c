#include <webots/robot.h>
#include <webots/motor.h>
#include <webots/position_sensor.h>
#include <webots/distance_sensor.h>
#include <math.h>
#include <stdio.h>

#define TIME_STEP 64

int main(int argc, char **argv) {
  wb_robot_init();

  WbDeviceTag left_motor = wb_robot_get_device("left_motor");
  WbDeviceTag right_motor = wb_robot_get_device("right_motor");
  WbDeviceTag left_encoder = wb_robot_get_device("left_encoder");
  WbDeviceTag right_encoder = wb_robot_get_device("right_encoder");
  
  // 2. ADDED: Get the distance sensors from Webots
  // IMPORTANT: Ensure "left_ds" and "right_ds" match the names in your Webots device tree exactly!
  WbDeviceTag left_ds = wb_robot_get_device("left_ds");
  WbDeviceTag right_ds = wb_robot_get_device("right_ds");
  
  wb_position_sensor_enable(left_encoder, TIME_STEP);
  wb_position_sensor_enable(right_encoder, TIME_STEP);
  
  // 2. ADDED: Enable distance sensors before using them
  wb_distance_sensor_enable(left_ds, TIME_STEP);
  wb_distance_sensor_enable(right_ds, TIME_STEP);

  wb_motor_set_position(left_motor, INFINITY);
  wb_motor_set_position(right_motor, INFINITY);

  wb_motor_set_velocity(left_motor, 2.0); 
  wb_motor_set_velocity(right_motor, 2.0);
  
  // 3. FIXED: Changed from bool to int so it can count down from 100
  int avoid_obstacle_counter = 0;
  
  while (wb_robot_step(TIME_STEP) != -1) {
    double left_value = wb_position_sensor_get_value(left_encoder);
    double right_value = wb_position_sensor_get_value(right_encoder);
    
    double left_speed = 2.0;
    double right_speed = 2.0;
    
    // 4. FIXED: Moved this array outside the if/else blocks so printf can see it
    double ds_values[2] = {0.0, 0.0}; 

    if (avoid_obstacle_counter > 0) {
      avoid_obstacle_counter--;
      left_speed = 2.0;
      right_speed = -2.0; // Turn right to avoid obstacle
    } else { 
      // Read sensors
      ds_values[0] = wb_distance_sensor_get_value(left_ds);
      ds_values[1] = wb_distance_sensor_get_value(right_ds);
      
      // Note: Depending on your sensor model, you might need to adjust "950.0". 
      // Some sensors return smaller numbers when close to a wall, some return larger.
      if (ds_values[0] < 950.0 || ds_values[1] < 950.0) {
        avoid_obstacle_counter = 100;
      }
    }
    
    wb_motor_set_velocity(left_motor, left_speed);
    wb_motor_set_velocity(right_motor, right_speed);
    
    printf("left ds: %f and right ds: %f\n", ds_values[0], ds_values[1]);
  }

  wb_robot_cleanup();
  return 0;
}