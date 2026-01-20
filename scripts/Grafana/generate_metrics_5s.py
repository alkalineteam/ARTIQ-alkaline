import time
import random
from datetime import datetime
from repository.metrics import MetricLogger

def main():
    # Generate a unique Run ID based on the current time
    run_id = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    print(f"Starting periodic generation with Run ID: {run_id}")
    
    # Initialize the logger
    with MetricLogger() as logger:
        for i in range(1, 11):
            # Generate a random value between 0 and 100
            value = random.uniform(0, 100)
            
            # print(f"[{i}/10] Logging value: {value:.2f}")
            
            # Log the value with the run_id tag
            logger.log_scalar(
                "periodic_test", 
                value, 
                tags={
                    "type": "5s_interval",
                    "run_id": run_id
                }
            )
            
            # Sleep for 5 seconds (but not after the last one)
            if i < 10:
                time.sleep(5)

    print("Done.")

if __name__ == "__main__":
    main()
