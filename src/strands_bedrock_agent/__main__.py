"""Entry point for ``python -m strands_bedrock_agent``.

Dispatches to :func:`strands_bedrock_agent.cli.main` and exits with
the returned exit code.

Requirements: 6.1
"""

from strands_bedrock_agent.cli import main

raise SystemExit(main())
