"""Tiny shared base. Agents own one job and run it on a SessionState."""
from __future__ import annotations

from abc import ABC, abstractmethod

from core.session_state import SessionState
from llm.llm_client import LLMClient


class BaseAgent(ABC):
    name: str = "base"

    def __init__(self, client: LLMClient):
        self.client = client

    @abstractmethod
    def run(self, state: SessionState) -> SessionState:
        """Mutate `state` in place AND return it. Caller stores the result."""
