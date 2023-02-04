# load_analyzer

Running in test mode:
gunzip processes.tsv.gz

python3 dash_graph.py


Change the line: 
analyer = Analyze(use_tsv=False, use_pickle=False)

to use_tsv = True

Notes: 
Deployed in a docker container on ibss-crontab with only the dash app
Monitoring is in docker on ibss-central. Why did I do it that way?!

 bbbd7a727571   load_analyzer_app                            "python monitor.py"      5 months ago    Up 3 days                                                                                        
load_analyzer_app_1

---


Docker:
mkdir data
docker-compose build
docker-compose up

Adding new servers:
Edit docker-compose IP mapping
edit monitor.py list of servers. E.g.:
HOSTS = ['rosalindf', 'alice', 'tdobz']


TODO: Make hosts configurable
Todo: Make db password clean


todo: Pull down to select server? or display all N servers at once?
todo: Should we pull any other stats? disk IO/ops?
TODO: Dockerize server and place online
todo: generate a per-user report - your core hours this month, top N processes, pie showing your %age ram 
and %age CPU.
TODO: Generate real time alerts for the top N when the system is at or near capacity.
TODO: track GPU usage
TOOD: Extract a single process and trace its CPU/memory usage over the lifetime of the run

