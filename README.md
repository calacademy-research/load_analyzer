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


The problem is that I have no idea how often the servers are used, and for what, 
and by whom. I’d like a list that boils down to “servers are used, on average, 
at X% usage, with a peak of Y%. Here’s a list of users, sorted by activity level, 
and here are the processes they ran, sorted by frequency-of-use. Here is the biggest 
memory pig, here is the biggest CPU pig (latter two by user and by process).”

a sql database with a bunch of entries, each representing a snapshot in time of a 
given server and what it’s up to. Extract the above stats from it, then maybe 
spit out cute graphs that tells me who is doing what.