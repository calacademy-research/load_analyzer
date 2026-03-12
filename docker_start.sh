#!/bin/bash
set -e

# Create cron job to run process_data_job.py every 5 minutes
echo "*/5 * * * * cd /var/www/apache-flask && /usr/local/bin/python3 /var/www/apache-flask/process_data_job.py >> /var/log/cron.log 2>&1" > /etc/cron.d/process-data-cron
chmod 0644 /etc/cron.d/process-data-cron
crontab /etc/cron.d/process-data-cron

# Create log files
touch /var/log/cron.log
chmod 666 /var/log/cron.log

# Start cron service
service cron start

# Start React+FastAPI dashboard on port 80
python3 -m uvicorn api_server:app --host 0.0.0.0 --port 80 &

# Keep container running and monitor logs
tail -f /var/log/cron.log
