"""
PID controller with anti-windup for HVAC temperature control.
"""
import json


class PIDController:
    """PID controller with anti-windup clamping."""
    
    def __init__(self, Kp, Ki, Kd, dt, output_min=0.0, output_max=100.0):
        self.Kp = Kp
        self.Ki = Ki
        self.Kd = Kd
        self.dt = dt
        self.output_min = output_min
        self.output_max = output_max
        
        self.integral = 0.0
        self.prev_error = None
    
    def compute(self, error):
        """
        Compute PID output.
        
        Args:
            error: setpoint - measurement
        
        Returns:
            control output (clamped to [output_min, output_max])
        """
        # Proportional
        P = self.Kp * error
        
        # Integral with anti-windup
        self.integral += error * self.dt
        I = self.Ki * self.integral
        
        # Derivative
        if self.prev_error is not None:
            D = self.Kd * (error - self.prev_error) / self.dt
        else:
            D = 0.0
        self.prev_error = error
        
        # Total output
        output = P + I + D
        
        # Clamp and anti-windup
        if output > self.output_max:
            # Back-calculate integral to prevent windup
            self.integral -= (output - self.output_max) / self.Ki if self.Ki > 0 else 0
            output = self.output_max
        elif output < self.output_min:
            self.integral -= (output - self.output_min) / self.Ki if self.Ki > 0 else 0
            output = self.output_min
        
        return output


def run_closed_loop(sim, gains, duration=180.0):
    """
    Run closed-loop PID control.
    
    Args:
        sim: HVACSimulator instance
        gains: dict with Kp, Ki, Kd
        duration: control duration in seconds
    
    Returns:
        dict with control log data
    """
    setpoint = sim.get_setpoint()
    dt = sim.get_dt()
    steps = int(duration / dt)
    
    initial_temp = sim.reset()
    
    pid = PIDController(
        Kp=gains["Kp"],
        Ki=gains["Ki"],
        Kd=gains["Kd"],
        dt=dt,
        output_min=0.0,
        output_max=100.0
    )
    
    data = [{
        "time": 0.0,
        "temperature": round(initial_temp, 4),
        "setpoint": setpoint,
        "heater_power": 0.0,
        "error": round(setpoint - initial_temp, 4)
    }]
    
    for i in range(steps):
        current_temp = data[-1]["temperature"]
        error = setpoint - current_temp
        
        power = pid.compute(error)
        
        result = sim.step(power)
        
        data.append({
            "time": result["time"],
            "temperature": result["temperature"],
            "setpoint": setpoint,
            "heater_power": result["heater_power"],
            "error": round(setpoint - result["temperature"], 4)
        })
    
    control_log = {
        "phase": "control",
        "setpoint": setpoint,
        "data": data
    }
    
    return control_log


def save_control_log(control_log, path="/root/control_log.json"):
    """Save control log to JSON file."""
    with open(path, 'w') as f:
        json.dump(control_log, f, indent=2)
    return path
