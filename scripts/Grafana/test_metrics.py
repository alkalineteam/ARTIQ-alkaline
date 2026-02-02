from repository.metrics import MetricLogger
import time
import random

def test_metrics():
    print("Connecting to InfluxDB...")
    with MetricLogger() as logger:
        # Log some sample data
        for i in range(100):
            val = random.random() * 100
            print(f"Logging value: {val}")
            logger.log_scalar("test_metric", val, tags={"source": "smoke_test"})
            time.sleep(1)
            
    print("Done! Check Grafana/InfluxDB for 'test_metric'.")

if __name__ == "__main__":
    test_metrics()
