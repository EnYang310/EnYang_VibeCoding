#!/bin/sh
set -eu

# CloudBase Git deployments currently probe port 80 even when the service is
# configured to route to 8000. Keep the application on its unprivileged 8000
# port and bridge only the platform probe and any 80-based route to it.
socat TCP-LISTEN:80,reuseaddr,fork,keepalive TCP:127.0.0.1:8000 &
proxy_pid=$!

su -s /bin/sh -c 'exec python -m app.server' appuser &
app_pid=$!

shutdown() {
  kill -TERM "$app_pid" "$proxy_pid" 2>/dev/null || true
  wait "$app_pid" 2>/dev/null || true
  wait "$proxy_pid" 2>/dev/null || true
}

trap shutdown INT TERM
wait "$app_pid"
status=$?
shutdown
exit "$status"
