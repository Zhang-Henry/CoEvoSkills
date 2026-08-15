class PIDController:
    """PID Controller with anti-windup clamping."""
    
    def __init__(self, kp, ki, kd, integral_min=-50.0, integral_max=50.0):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self.integral_min = integral_min
        self.integral_max = integral_max
        self.integral = 0.0
        self.prev_error = 0.0
        self.first_call = True
    
    def reset(self):
        """Reset controller state."""
        self.integral = 0.0
        self.prev_error = 0.0
        self.first_call = True
    
    def compute(self, error, dt):
        """Compute PID output.
        
        Args:
            error: Current error (setpoint - measured)
            dt: Time step in seconds
            
        Returns:
            float: Control output
        """
        # Integral accumulation with anti-windup clamping
        self.integral += error * dt
        # Clamp integral to prevent windup
        self.integral = max(self.integral_min, min(self.integral_max, self.integral))
        
        # Derivative computation
        if self.first_call:
            derivative = 0.0
            self.first_call = False
        else:
            derivative = (error - self.prev_error) / dt
        
        # PID output
        output = self.kp * error + self.ki * self.integral + self.kd * derivative
        
        # Update previous error
        self.prev_error = error
        
        return output
