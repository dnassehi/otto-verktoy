"""Navnet på agenten som vises i appen. Sett SKRIVEAPP_AGENT_NAME til det du har kalt din egen agent."""
import os

AGENT_NAME = os.environ.get("SKRIVEAPP_AGENT_NAME", "Assistenten").strip() or "Assistenten"
