FROM python:3.11
RUN  apt-get update && apt-get install -y apache2 \
    libapache2-mod-wsgi-py3 \
    build-essential \
     default-libmysqlclient-dev \
     python3 \
    python3-pymysql \
    python3-dev \
    python3-pip \
    python3-distutils \
    python3-numpy \
    python3-pandas \
     vim \
 && apt-get clean \
 && apt-get autoremove \
 && cd /usr/local/bin \
 && pip3 --no-cache-dir install --upgrade pip \
 && rm -rf /var/lib/apt/lists/*

RUN apt-get update
# apache2-threaded-dev
# libapache2-mod-wsgi
# Copy over the apache configuration file and enable the site
COPY ./apache-flask.conf /etc/apache2/sites-available/apache-flask.conf
RUN a2ensite apache-flask
RUN a2enmod headers

# Copy over the wsgi file
COPY ./apache-flask.wsgi /var/www/apache-flask/apache-flask.wsgi
COPY ./requirements.txt /var/www/apache-flask
COPY ./docker_start.sh /var/www/apache-flask
COPY *.py /var/www/apache-flask/
COPY ./requirements.txt /var/www/apache-flask

WORKDIR /var/www/apache-flask
RUN pip3 install -r /var/www/apache-flask/requirements.txt
RUN pip3 install --upgrade pandas

RUN a2dissite 000-default.conf
RUN a2ensite apache-flask.conf

# LINK apache config to docker logs.
RUN ln -sf /proc/self/fd/1 /var/log/apache2/access.log && \
    ln -sf /proc/self/fd/1 /var/log/apache2/error.log

ENV PYTHONPATH "${PYTHONPATH}:/var/www/apache-flask:/usr/local/lib/python3.8/site-packages"


ENV PORT 80
EXPOSE 80
# ENTRYPOINT
ENTRYPOINT /var/www/apache-flask/docker_start.sh


