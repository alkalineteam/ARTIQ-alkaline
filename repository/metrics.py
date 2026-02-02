import logging
import time
from typing import Any, Dict, Optional

from influxdb_client import InfluxDBClient
from influxdb_client.client.write_api import SYNCHRONOUS

logger = logging.getLogger(__name__)

class MetricLogger:
    """
    A helper class to log metrics to an InfluxDB v2 instance.
    """

    def __init__(
        self,
        url: str = "http://localhost:8086",
        token: str = "administrativetoken123",
        org: str = "alkaline",
        bucket: str = "experiments",
    ):
        self.url = url
        self.token = token
        self.org = org
        self.bucket = bucket
        self.client: Optional[InfluxDBClient] = None
        self.write_api = None

    def connect(self):
        """Establish connection to InfluxDB."""
        try:
            self.client = InfluxDBClient(url=self.url, token=self.token, org=self.org)
            self.write_api = self.client.write_api(write_options=SYNCHRONOUS)
            logger.info(f"Connected to InfluxDB at {self.url}")
        except Exception as e:
            logger.error(f"Failed to connect to InfluxDB: {e}")
            self.client = None

    def close(self):
        """Close the InfluxDB connection."""
        if self.client:
            self.client.close()
            self.client = None
            self.write_api = None

    def log_fields(self, name: str, fields: Dict[str, Any], tags: Optional[Dict[str, str]] = None):
        """
        Log multiple fields for a single measurement point.
        Useful for XY plotting (e.g. fields={'x': 1, 'y': 2}).
        
        :param name: Name of the metric (measurement).
        :param fields: Dictionary of field key-values (e.g. {'x': 1.0, 'y': 2.5}).
        :param tags: Dictionary of tags associated with the metric.
        """
        if not self.write_api:
            # Try to connect if not connected
            self.connect()
            if not self.write_api:
                logger.warning(f"Dropping metric {name}={fields} (Not connected)")
                return

        try:
            point = {
                "measurement": name,
                "fields": fields,
                "time": int(time.time_ns()),
            }
            if tags:
                point["tags"] = tags

            self.write_api.write(bucket=self.bucket, org=self.org, record=point)
        except Exception as e:
            logger.error(f"Failed to write metric {name}: {e}")

    def log_scalar(self, name: str, value: Any, tags: Optional[Dict[str, str]] = None):
        """
        Log a single scalar value.
        
        :param name: Name of the measurement.
        :param value: Value to log (stored as field 'value').
        :param tags: Optional tags.
        """
        self.log_fields(name, {"value": value}, tags)

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
