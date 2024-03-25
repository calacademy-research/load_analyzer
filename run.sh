#!/bin/bash
cd "$(dirname "$0")"
parentdir="$(dirname `pwd`)"
echo $parentdir
docker run \
-v `pwd`:/var/www/apache-flask \
-d -p 80:80 --name load_analyzer -i -t load_analyzer --restart=always
