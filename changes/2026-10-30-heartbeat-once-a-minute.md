# Patch

Scouts touch their heartbeat file once a minute instead of every 10 seconds, cutting idle file writes about sixfold. A scout that stops polling still counts as deaf after 120 seconds.
