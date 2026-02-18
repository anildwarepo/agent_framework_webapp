# create a reusable volume
docker volume create pg_age_data

# start container with the volume attached
docker run -d --name pg-age \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_DB=appdb \
  -p 5432:5432 \
  -v pg_age_data:/var/lib/postgresql/data \
  --restart unless-stopped \
  apache/age:latest
