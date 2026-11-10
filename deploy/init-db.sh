#!/bin/sh
set -eu
JOB_AGENT_DB_PASSWORD=$(cat /run/secrets/db_password)
export JOB_AGENT_DB_PASSWORD
psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --set=ON_ERROR_STOP=1 <<'SQL'
\getenv app_password JOB_AGENT_DB_PASSWORD
CREATE ROLE job_agent LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD :'app_password';
ALTER DATABASE job_agent OWNER TO job_agent;
ALTER SCHEMA public OWNER TO job_agent;
SQL
unset JOB_AGENT_DB_PASSWORD
