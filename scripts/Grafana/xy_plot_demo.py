import random
import time
from datetime import datetime
from repository.metrics import MetricLogger

def main():
    # Use the same run_id concept so we can filter later
    run_id = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    print(f"Starting XY Plot generation with Run ID: {run_id}")
    
    with MetricLogger() as logger:
        # Example: Plotting a Parabola y = x^2
        # Reduced range so it doesn't take forever (5s * 20 points = 100s)
        x_values = range(-10, 11)
        total_points = len(x_values)
        
        for i, x in enumerate(x_values):
            y = x**2 + random.uniform(-5, 5) # Add some noise
            
            print(f"[{i+1}/{total_points}] Logging point: x={x}, y={y:.2f}")
            
            # Log both X and Y as fields in the same "measurement"
            logger.log_fields(
                name="xy_demo", 
                fields={"x": x, "y": y}, 
                tags={"run_id": run_id, "type": "parabola"}
            )
            
            # Wait 5 seconds between points (except after the last one)
            if i < total_points - 1:
                time.sleep(5)

    print("Done. Now configure an 'XY Chart' in Grafana.")

if __name__ == "__main__":
    main()
