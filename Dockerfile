FROM python:3.11
RUN apt-get update && apt-get install -y apache2 \
    libapache2-mod-wsgi-py3 \
    build-essential \
    default-libmysqlclient-dev \
    python3-pymysql \
    python3-dev \
    python3-pip \
    python3-distutils \
    python3-numpy \
    python3-pandas \
    vim \
    cron \
 && apt-get clean \
 && apt-get autoremove \
 && cd /usr/local/bin \
 && pip3 --no-cache-dir install --upgrade pip \
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
ENV PORT 9092
EXPOSE 9092

# Copy the startup script
COPY . /var/www/apache-flask/
RUN chmod +x /var/www/apache-flask/docker_start.sh
RUN pip install -r requirements.txt

ENTRYPOINT ["/var/www/apache-flask/docker_start.sh"]
