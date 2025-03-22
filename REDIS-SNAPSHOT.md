
# Redis Snapshot System for Dash Graph Data

This document explains how the system fetches data from MySQL and stores it in Redis for efficient dashboard visualization.

## Overview

The system uses a two-step process:
1. **Data Extraction**: Fetches process data from MySQL database
2. **Data Transformation**: Processes and aggregates the data
3. **Data Storage**: Stores the processed data in Redis for fast retrieval

## Components

### RedisBase

The base class that handles Redis connection initialization with configurable parameters:
- Host (default: localhost)
- Port (default: 6379)
- Database (default: 0)

It also provides a `read_sql()` method to fetch data from MySQL with date range filtering.

### RedisWriter

Responsible for processing data from MySQL and storing it in Redis:

1. **Data Fetching**: 
   - Retrieves raw process data from MySQL using SQL queries
   - Supports date range filtering

2. **Data Processing**:
   - Sorts data by timestamp
   - Converts memory values from bytes to GB
   - Calculates CPU usage normalization
   - Aggregates data in 5-minute intervals
   - Filters out zero CPU usage entries

3. **Data Transformation**:
   - Processes data for each host separately
   - Creates separate datasets for:
     - CPU load by command
     - CPU load by user
     - Memory usage by command
     - Memory usage by user
   - Applies thresholds to filter out insignificant entries

4. **Data Storage**:
   - Uses Redis pipeline for efficient batch writing
   - Stores data with ISO-formatted timestamps as keys
   - Sets expiration time (default: 30 days)
   - Handles errors with retry mechanism

### RedisReader

Retrieves processed data from Redis for dashboard visualization:

1. **Data Retrieval**:
   - Fetches data by host and time range
   - Supports filtering by start and end times
   - Converts ISO timestamps to epoch timestamps
   - Returns data in an ordered dictionary

2. **Error Handling**:
   - Uses retry mechanism for Redis connection issues
   - Logs errors for debugging

## Data Structure in Redis

Each entry in Redis is stored with the following structure:

```
{ISO timestamp} -> {
  "hostname": {
    "cpu": {
      "command": {
        "cpu_norm": float,
        "timestamp": string
      },
      "user": [
        {
          "cpu_norm": float,
          "username": string,
          "comm": string,
          "host": string,
          "timestamp": string
        },
        ...
      ]
    },
    "mem": {
      "command": {
        "rss": float,
        "timestamp": string
      },
      "user": [
        {
          "rss": float,
          "username": string,
          "comm": string,
          "host": string,
          "timestamp": string
        },
        ...
      ]
    }
  }
}
```


## Performance Optimizations

1. **Batch Processing**: Uses Redis pipeline for efficient batch writes
2. **Data Aggregation**: Reduces data volume by aggregating in 5-minute intervals
3. **Thresholding**: Filters out insignificant data points
4. **Retry Mechanism**: Handles transient Redis connection issues
5. **Performance Monitoring**: Uses timer decorator to track execution time

## Usage

The system is typically run as a scheduled job to keep the Redis cache updated:

1. The `RedisWriter.store_data()` method is called periodically
2. It fetches recent data from MySQL
3. Processes and transforms the data
4. Stores it in Redis with appropriate expiration times

The Dash application then uses `RedisReader.get_data()` to efficiently retrieve the pre-processed data for visualization without having to query the MySQL database directly.
