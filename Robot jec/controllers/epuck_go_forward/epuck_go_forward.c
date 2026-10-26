#include <webots/robot.h>

// Added a new include file
#include <webots/motor.h>
#include <stdio.h>

#define TIME_STEP 64
#define MAX 6.28
#define ACC_F 2.1332
#define ACC_S -2.1332
int main(int argc, char **argv) {
 wb_robot_init();

 // get the motor devices
 WbDeviceTag left_motor = wb_robot_get_device("left wheel motor");
 WbDeviceTag right_motor = wb_robot_get_device("right wheel motor");
 // set the target position of the motors
 wb_motor_set_position(left_motor, INFINITY);
 wb_motor_set_position(right_motor, INFINITY);
 
 FILE *fp;
 fp = fopen("data.csv", "w");
 if (fp == NULL)
 {
   printf("Error\n");
   return (1);
 }
 
double i;
double speed;
double time;
i = 0.0;
speed = 0.0;
 while (wb_robot_step(TIME_STEP) != -1)
 {
  time = 0.001 * i * TIME_STEP;
   printf("%f and current  speed: %f\n ", time, speed);
    wb_motor_set_velocity(left_motor, speed);
    wb_motor_set_velocity(right_motor, speed);
   if (time >= 0.0 && time <= 3.0)
   {
     speed = (ACC_F * time);
     if (speed > 6.28)
       speed = 6.28;
   }
   else if (time >= 7.0 && time <= 10.0)
   {
     speed = 6.28 + (ACC_S * (time - 7.0));
     if (speed < 0.0)
       speed = 0.0;
   }
   fprintf(fp, "%f, %f\n", time, speed);
   i = i + 1;
 }
 fclose(fp);
 wb_robot_cleanup();

 return 0;
}
