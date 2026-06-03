-- Runs once on first MariaDB startup (docker-entrypoint-initdb.d).
-- Matches typical local credentials: user `local`, password `secret` (set in compose).
--
-- DBs:
--   fluent          - Fluent (app principal) + Engine (partilham a mesma base)
--   fluent_express  - Express API
--   act             - ACT API

CREATE DATABASE IF NOT EXISTS fluent;
CREATE DATABASE IF NOT EXISTS fluent_express;
CREATE DATABASE IF NOT EXISTS act;

GRANT ALL PRIVILEGES ON fluent.* TO 'local'@'%';
GRANT ALL PRIVILEGES ON fluent_express.* TO 'local'@'%';
GRANT ALL PRIVILEGES ON act.* TO 'local'@'%';
FLUSH PRIVILEGES;
