#!/usr/bin/env python3
import sys
import os

# Add the project root directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.snapshot_aggregator import SnapshotAggregator
from datetime import datetime, timedelta

def main():
    aggregator = SnapshotAggregator()
    yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    today = datetime.now().strftime('%Y-%m-%d')
    
    try:
        aggregator.aggregate_snapshots(yesterday, today)
        print(f"Successfully aggregated snapshots from {yesterday} to {today}")
    except Exception as e:
        print(f"Error aggregating snapshots: {str(e)}")

if __name__ == "__main__":
    main() 