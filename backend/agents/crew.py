from __future__ import annotations

from pathlib import Path

import yaml
from crewai import Agent, Crew, Process, Task

CONFIG_DIR = Path(__file__).parent / "config"


def build_application_crew() -> Crew:
    """Build the bounded, sequential crew. Domain services remain the policy authority."""
    agents = yaml.safe_load((CONFIG_DIR / "agents.yaml").read_text())
    tasks = yaml.safe_load((CONFIG_DIR / "tasks.yaml").read_text())
    orchestrator = Agent(**agents["orchestrator"])
    analyst = Agent(**agents["analysis"])
    dispatcher = Agent(**agents["dispatch"])
    routing_task = Task(agent=orchestrator, **tasks["validate_and_route"])
    analysis_task = Task(agent=analyst, context=[routing_task], **tasks["analyze_evidence"])
    dispatch_task = Task(agent=dispatcher, context=[analysis_task], **tasks["preview_or_dispatch"])
    return Crew(
        agents=[orchestrator, analyst, dispatcher], tasks=[routing_task, analysis_task, dispatch_task],
        process=Process.sequential, memory=False, max_rpm=30,
    )
