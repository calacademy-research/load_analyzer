#!/bin/bash
cd "$(dirname "$0")"
docker stop load_analyzer
docker rm load_analyzer
rm -rf dataframe_pickle.pkl
./run.sh
sleep 100
wget http://ibss-crontab:80
node headless-chrome.js http://127.0.0.1 > results
#sleep 100
#wget http://ibss-crontab:80
#node headless-chrome.js http://127.0.0.1 > results2
#wget http://ibss-crontab:80
#node headless-chrome.js http://127.0.0.1 > results3
#node headless-chrome.js http://127.0.0.1 > results4
rm -rf index.html*
rm -rf results*
