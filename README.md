# load_analyzer

A realtime visualization of memory and CPU load for CAS servers:
- rosalindf
- alice
- tdobz


## Usage

This is run in two pieces:
1. The monitoring and database side is run on `ibss-central` using `docker-compose` and `docker`.
2. The dash based web url is run on `ibss-central` and reset via crontab on that machine.

To start the monitoring process, run as user `admin`, which has the keys set up correctly.
Execute 
```bash
launch-monitor.sh build
```
to rebuild the docker. Without `build` if you've just made code changes.

To start the dash graphs based portion execute
```bash
run.sh
```

## Debugging:
TODO: source a `.tsv` file of process information.

In `dash_graph.py` where the `Analyze` class is instantiated set `use_tsv=true`.

Unzip the file if compressed and run in the command line using:
```bash
gunzip processes.tsv.gz
python3 dash_graph.py
```

## Docker:
```bash
mkdir data
docker-compose build
docker-compose up
```

## Adding new servers:
- Edit docker-compose IP mapping.
- Edit monitor.py list of servers. E.g.:
```bash
HOSTS = ['rosalindf', 'alice', 'tdobz']
```

## Notes: 
Deployed in a docker container on `ibss-crontab` with only the dash app.
Monitoring is in docker on `ibss-central`. Why did I do it that way?!

## TODO:

- TODO: Make hosts configurable
- TODO: Make db password clean
- TODO: Should we pull any other stats? disk IO/ops?
- TODO: generate a per-user report - your core hours this month, top N processes, pie showing your %age ram 
and %age CPU.
- TODO: Generate real time alerts for the top N when the system is at or near capacity.
- TODO: track GPU usage
- TOOD: Extract a single process and trace its CPU/memory usage over the lifetime of the run

