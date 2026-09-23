#!/bin/bash
set -e

# Create cron job to run process_data_job.py every 5 minutes
echo "*/5 * * * * cd /app && /usr/local/bin/python3 /app/process_data_job.py >> /var/log/cron.log 2>&1" > /etc/cron.d/process-data-cron
chmod 0644 /etc/cron.d/process-data-cron
crontab /etc/cron.d/process-data-cron

# Create log files
touch /var/log/cron.log
chmod 666 /var/log/cron.log

# Start cron service
service cron start

# TLS material: the *.calacademy.org wildcard, deployed to the host by the
# genomics-ansible wildcard-cert role and bind-mounted as a directory at
# /etc/ssl/calacademy. uvicorn holds the files open, so a renewal restarts
# this container (that is what the role's reload action does). No fallback:
# missing files fail the start loudly rather than silently serving http.
CERT=/etc/ssl/calacademy/fullchain.pem
KEY=/etc/ssl/calacademy/privkey.pem
for f in "$CERT" "$KEY"; do
  [ -r "$f" ] || { echo "docker_start.sh: TLS file $f missing or unreadable" >&2; exit 1; }
done

# Start React+FastAPI dashboard on port 443 (TLS)
python3 -m uvicorn api_server:app --host 0.0.0.0 --port 443 \
  --ssl-certfile "$CERT" --ssl-keyfile "$KEY" &

# Port 80 only redirects to https (keeps http://ibss-crontab/ links working)
python3 -m uvicorn https_redirect:app --host 0.0.0.0 --port 80 &

# Keep container running and monitor logs
tail -f /var/log/cron.log
