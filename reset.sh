#!/bin/bash
cd "$(dirname "$0")"
docker stop load_analyzer
docker rm load_analyzer
rm -rf dataframe_pickle.pkl
./run.sh
rm -rf index.html*
rm -rf results*
