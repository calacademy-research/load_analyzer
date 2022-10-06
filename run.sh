#!/bin/bash
cd "$(dirname "$0")"
parentdir="$(dirname `pwd`)"
echo $parentdir
docker run \
-v `pwd`:/var/www/apache-flask/app \
-d -p 80:80 --name load_analyzer  -i -t apache-flask /bin/bash -restart
