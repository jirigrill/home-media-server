#!/bin/sh

NAME=$1

docker stop $NAME && docker rm $NAME
docker image rm $NAME:latest
docker build -t $NAME .
docker run -d --name $NAME --network media_server -p 5001:5001 --env-file .env $NAME