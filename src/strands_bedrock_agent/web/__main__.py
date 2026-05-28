"""Entry point for ``python -m strands_bedrock_agent.web``.

Dispatches to :func:`strands_bedrock_agent.web.server.main` and exits
with the returned status code.

Requirements: 9.1
"""

from .server import main

raise SystemExit(main())
