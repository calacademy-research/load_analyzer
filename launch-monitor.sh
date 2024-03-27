#!/bin/bash

# Determine the current directory
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Check for "build" argument
if [[ $1 == "build" ]]; then
    # Dynamically generate Dockerfile-monitor
    cat <<EOL > Dockerfile-monitor
FROM python:3.9-slim
WORKDIR /code
COPY ./requirements-monitor.txt .
RUN apt-get update && apt-get install -y openssh-client && apt-get clean
RUN pip install -r requirements-monitor.txt
CMD ["python", "/code/monitor.py"]
EOL

    # Build the Docker image
    sudo docker build -t monitor_app_image -f Dockerfile-monitor .
fi

# Stop existing Docker container if it's running
if sudo docker ps -a | grep load_analyzer_app_1; then
    sudo docker rm -f load_analyzer_app_1
fi
if sudo docker ps | grep load_analyzer_app_1; then
    sudo docker stop load_analyzer_app_1
    sudo docker rm load_analyzer_app_1
fi

# Run the Docker container, mounting the current directory as /code, SSH keys, and using host network
sudo docker run -d --restart unless-stopped --network host -v $DIR:/code -v ~/.ssh/id_rsa:/root/.ssh/id_rsa -v ~/.ssh/id_rsa.pub:/root/.ssh/id_rsa.pub --name load_analyzer_app_1 monitor_app_image

