# load_analyzer

mkdir data
docker-compose build
docker-compose up

Adding new servers:
Edit docker-compose IP mapping
edit monitor.py list of servers. E.g.:
HOSTS = ['rosalindf', 'alice', 'tdobz']


TODO: Make hosts configurable
Todo: Make db password clean
