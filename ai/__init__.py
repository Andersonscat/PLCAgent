"""AI integration for OpenPLC Editor (plc-cursor fork).

Adds a Claude-powered chat panel and an agent that can read/edit POUs,
trigger compile, and inspect simulation state via the standard
ProjectController / PLCControler public APIs.
"""

from ai.chat_panel import ChatPanel
from ai.agent import Agent
from ai.hmi_panel import HMIPanel

__all__ = ["ChatPanel", "Agent", "HMIPanel"]
