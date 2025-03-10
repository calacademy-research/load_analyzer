#!/bin/bash
set -e

# Start Apache
service apache2 start

# Start our application
python3 /var/www/apache-flask/dash_graph.py

# Keep container running
tail -f /var/log/apache2/access.log
