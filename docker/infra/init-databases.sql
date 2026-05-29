-- Runs once on first MariaDB startup (docker-entrypoint-initdb.d).
-- Matches typical local credentials: user `local`, password `secret` (set in compose).

CREATE DATABASE IF NOT EXISTS fluent;
CREATE DATABASE IF NOT EXISTS fluent_engine;
CREATE DATABASE IF NOT EXISTS act;

GRANT ALL PRIVILEGES ON fluent.* TO 'local'@'%';
GRANT ALL PRIVILEGES ON fluent_engine.* TO 'local'@'%';
GRANT ALL PRIVILEGES ON act.* TO 'local'@'%';
FLUSH PRIVILEGES;
