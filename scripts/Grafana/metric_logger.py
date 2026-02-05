"""
MetricLogger - Helper class for logging metrics to InfluxDB for Grafana visualization.

Usage:
    from scripts.Grafana.metric_logger import MetricLogger
    
    with MetricLogger() as logger:
        logger.log_scalar("measurement_name", 42.0, tags={"run_id": "2026-02-05"})
        logger.log_fields("xy_data", {"x": 1.0, "y": 2.0}, tags={"type": "scan"})
"""

from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS
from datetime import datetime


class MetricLogger:
    """Context manager for logging metrics to InfluxDB."""
    
    def __init__(
        self,
        url: str = "http://localhost:8086",
        token: str = "administrativetoken123",
        org: str = "alkaline",
        bucket: str = "experiments"
    ):
        self.url = url
        self.token = token
        self.org = org
        self.bucket = bucket
        self._client = None
        self._write_api = None
    
    def __enter__(self):
        self._client = InfluxDBClient(url=self.url, token=self.token, org=self.org)
        self._write_api = self._client.write_api(write_options=SYNCHRONOUS)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._write_api:
            self._write_api.close()
        if self._client:
            self._client.close()
        return False
    
    def log_scalar(self, name: str, value: float, tags: dict = None):
        """
        Log a single scalar value.
        
        Args:
            name: Measurement name (e.g., "test_metric", "coil_samples")
            value: The numeric value to log
            tags: Optional dict of tags for filtering (e.g., {"run_id": "...", "channel": "0"})
        """
        point = Point(name).field("value", float(value))
        if tags:
            for key, val in tags.items():
                point = point.tag(key, str(val))
        self._write_api.write(bucket=self.bucket, org=self.org, record=point)
    
    def log_fields(self, name: str, fields: dict, tags: dict = None):
        """
        Log multiple fields in a single measurement.
        
        Args:
            name: Measurement name (e.g., "xy_demo", "scan_data")
            fields: Dict of field names to values (e.g., {"x": 1.0, "y": 2.0})
            tags: Optional dict of tags for filtering
        """
        point = Point(name)
        for field_name, field_value in fields.items():
            point = point.field(field_name, float(field_value))
        if tags:
            for key, val in tags.items():
                point = point.tag(key, str(val))
        self._write_api.write(bucket=self.bucket, org=self.org, record=point)
