FROM python:3.11
RUN apt-get update && apt-get install -y \
    apache2 \
    libapache2-mod-wsgi-py3 \
    build-essential \
    default-libmysqlclient-dev \
    vim \
    cron \
 && rm -rf /var/lib/apt/lists/*

# Setup Apache
RUN a2enmod wsgi headers
COPY ./apache-flask.conf /etc/apache2/sites-available/apache-flask.conf
RUN a2ensite apache-flask
RUN a2dissite 000-default.conf

# Setup Logging
RUN ln -sf /proc/self/fd/1 /var/log/apache2/access.log && \
    ln -sf /proc/self/fd/1 /var/log/apache2/error.log

WORKDIR /var/www/apache-flask

ENV PYTHONPATH "${PYTHONPATH}:/var/www/apache-flask:/usr/local/lib/python3.8/site-packages"
ENV PORT 80
EXPOSE 80

# Leverage layer cache for deps
COPY requirements.txt /tmp/requirements.txt
RUN pip install --upgrade pip \
 && pip install --no-cache-dir -r /tmp/requirements.txt

# Copy the application code
COPY . /var/www/apache-flask/
RUN chmod +x /var/www/apache-flask/docker_start.sh

ENTRYPOINT ["/var/www/apache-flask/docker_start.sh"]
