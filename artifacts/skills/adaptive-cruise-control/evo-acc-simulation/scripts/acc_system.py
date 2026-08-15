from pid_controller import PIDController


class AdaptiveCruiseControl:
    def __init__(self, config):
        acc = config['acc_settings']
        self.set_speed = acc['set_speed']
        self.time_headway = acc['time_headway']
        self.min_distance = acc['min_distance']
        self.emergency_ttc = acc['emergency_ttc_threshold']
        
        veh = config['vehicle']
        self.max_accel = veh['max_acceleration']
        self.max_decel = veh['max_deceleration']
        
        pid_s = config.get('pid_speed', {})
        pid_d = config.get('pid_distance', {})
        
        self.speed_pid = PIDController(
            kp=pid_s.get('kp', 1.0),
            ki=pid_s.get('ki', 0.1),
            kd=pid_s.get('kd', 0.0),
            integral_min=-5.0, integral_max=5.0
        )
        self.distance_pid = PIDController(
            kp=pid_d.get('kp', 0.5),
            ki=pid_d.get('ki', 0.05),
            kd=pid_d.get('kd', 0.3),
            integral_min=-10.0, integral_max=10.0
        )
        
        self.prev_mode = None
    
    def compute(self, ego_speed, lead_speed, distance, dt):
        mode = 'cruise'
        ttc = None
        distance_error = None
        
        if lead_speed is not None and distance is not None:
            if ego_speed > lead_speed and distance > 0:
                ttc = distance / (ego_speed - lead_speed)
            if ttc is not None and ttc < self.emergency_ttc:
                mode = 'emergency'
            else:
                mode = 'follow'
        
        if self.prev_mode is not None and mode != self.prev_mode:
            self.speed_pid.reset()
            self.distance_pid.reset()
        self.prev_mode = mode
        
        if mode == 'cruise':
            speed_error = self.set_speed - ego_speed
            accel_cmd = self.speed_pid.compute(speed_error, dt)
            
        elif mode == 'emergency':
            # Use max braking but compute distance_error like follow mode
            accel_cmd = self.max_decel
            desired_dist = self.time_headway * ego_speed + self.min_distance
            distance_error = desired_dist - distance
            
        elif mode == 'follow':
            desired_dist = self.time_headway * ego_speed + self.min_distance
            distance_error = desired_dist - distance
            excess_gap = distance - desired_dist
            
            tau = 8.0
            gap_adj = max(-5.0, min(5.0, excess_gap / tau))
            
            pid_out = self.distance_pid.compute(distance_error, dt)
            pid_adj = max(-2.0, min(2.0, -0.1 * pid_out))
            
            target_speed = min(lead_speed, self.set_speed) + gap_adj + pid_adj
            target_speed = max(0.0, min(self.set_speed, target_speed))
            
            speed_err = target_speed - ego_speed
            accel_cmd = 2.0 * speed_err
        
        accel_cmd = max(self.max_decel, min(self.max_accel, accel_cmd))
        return accel_cmd, mode, distance_error
