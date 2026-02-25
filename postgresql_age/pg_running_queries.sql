SELECT
  pid,
  usename,
  datname,
  client_addr,
  application_name,
  state,
  wait_event_type,
  wait_event,
  now() - query_start AS runtime,
  query
FROM pg_stat_activity
WHERE state = 'active'
  AND pid <> pg_backend_pid()
ORDER BY query_start ASC;

SELECT pg_cancel_backend(<pid>);