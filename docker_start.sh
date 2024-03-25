#!/usr/bin/env bash
echo "Installing Python dependencies from requirements.txt..."
pip3 install -r /var/www/apache-flask/requirements.txt


echo "Starting internal launch script...."
apachectl -D FOREGROUND
