#!/bin/bash
set -e

# Create cron job to run process_data_job.py every 5 minutes
echo "*/5 * * * * cd /var/www/apache-flask && /usr/local/bin/python3 /var/www/apache-flask/process_data_job.py >> /var/log/cron.log 2>&1" > /etc/cron.d/process-data-cron
chmod 0644 /etc/cron.d/process-data-cron
crontab /etc/cron.d/process-data-cron

# Create log file for cron
touch /var/log/cron.log
chmod 666 /var/log/cron.log

# Start cron service
service cron start

# Start Apache
service apache2 start

# Start our application
python3 /var/www/apache-flask/dash_graph.py &

# Keep container running and monitor logs
tail -f /var/log/apache2/access.log /var/log/cron.log
