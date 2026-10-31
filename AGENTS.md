# home-media-server

The stack runs on the remote host `jellyfin-server`, not here. Do not look at
local files, `localhost`, or local Docker for the running services — use
`ssh jellyfin-server '...'`. This checkout is for editing config/code; deploy
and inspect on the host.

Load the `jellyfin-server` skill before anything non-trivial there.
