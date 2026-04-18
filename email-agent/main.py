"""
Email Agent - HTTP Server for deployment

Purpose: Deploy email-agent as HTTP server on ConnectOnion Cloud
Usage: co deploy (uses this file as entrypoint)
"""

import inspect

from agent import agent
from connectonion import host

# trust="strict" requires signed requests with Ed25519 signature
# This prevents unauthorized access to email tools
first_param = next(iter(inspect.signature(host).parameters.values()))
if first_param.name == "create_agent":
    host(lambda: agent, trust="strict")
else:
    host(agent, trust="strict")
