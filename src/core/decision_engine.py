"""
DecisionEngine - Determines next actions based on worker profile and context.

Uses LLM to simulate realistic decision-making for an office worker,
considering time of day, current activity, and behavioral patterns.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional
from dataclasses import dataclass


@dataclass
class WorkerState:
    """Current state of the simulated worker."""
    current_time: datetime
    current_activity: Optional[str] = None
    active_applications: list = None
    minutes_since_last_break: int = 0
    emails_pending: int = 0
    focus_level: float = 1.0  # 0.0 to 1.0

    def __post_init__(self):
        if self.active_applications is None:
            self.active_applications = []


@dataclass
class Decision:
    """A decision about what action to take next."""
    action_type: str  # e.g., "open_application", "browse_web", "write_document"
    target: str       # e.g., "chrome", "linkedin.com", "Q1_Report.docx"
    parameters: dict  # Additional action-specific parameters
    reasoning: str    # Why this action was chosen (for debugging)

    def to_dict(self) -> dict:
        return {
            "action_type": self.action_type,
            "target": self.target,
            "parameters": self.parameters,
            "reasoning": self.reasoning
        }


class DecisionEngine:
    """
    Determines what action the simulated worker should take next.

    The decision engine considers:
    - Current time and work schedule
    - Worker's role and typical activities
    - Active applications and recent actions
    - Behavioral patterns (focus, breaks, etc.)
    """

    def __init__(self, profile_path: str):
        """
        Initialize with a worker profile.

        Args:
            profile_path: Path to the worker profile JSON file
        """
        self.profile = self._load_profile(profile_path)
        self.action_history: list[Decision] = []

    def _load_profile(self, profile_path: str) -> dict:
        """Load and validate worker profile from JSON."""
        path = Path(profile_path)
        if not path.exists():
            raise FileNotFoundError(f"Profile not found: {profile_path}")

        with open(path, 'r') as f:
            profile = json.load(f)

        # Validate required fields
        required = ["name", "role", "work_schedule", "applications", "activities"]
        missing = [field for field in required if field not in profile]
        if missing:
            raise ValueError(f"Profile missing required fields: {missing}")

        return profile

    def decide_next_action(self, state: WorkerState) -> Decision:
        """
        Determine the next action based on current state.

        Args:
            state: Current worker state including time, active apps, etc.

        Returns:
            Decision object describing what to do next
        """
        # Check if it's break time
        if self._is_break_time(state.current_time):
            return Decision(
                action_type="idle",
                target="break",
                parameters={"duration_minutes": 15},
                reasoning="Scheduled break time"
            )

        # Check if lunch time
        if self._is_lunch_time(state.current_time):
            return Decision(
                action_type="idle",
                target="lunch",
                parameters={"duration_minutes": 60},
                reasoning="Lunch break"
            )

        # Check if outside work hours
        if not self._is_work_hours(state.current_time):
            return Decision(
                action_type="end_day",
                target="shutdown",
                parameters={},
                reasoning="Outside work hours"
            )

        # TODO: Integrate with LLM for more sophisticated decisions
        # For now, use simple heuristic-based decisions
        return self._heuristic_decision(state)

    def _heuristic_decision(self, state: WorkerState) -> Decision:
        """Simple rule-based decision making (placeholder for LLM)."""

        # If no applications open, start with email
        if not state.active_applications:
            return Decision(
                action_type="open_application",
                target="outlook",
                parameters={},
                reasoning="Starting day with email check"
            )

        # Check email periodically
        if state.minutes_since_last_break > 30:
            return Decision(
                action_type="check_email",
                target="outlook",
                parameters={"action": "check_inbox"},
                reasoning="Regular email check"
            )

        # Default: browse related to work
        sites = self.profile["activities"]["browser"]["typical_sites"]
        import random
        site = random.choice(sites)
        return Decision(
            action_type="browse_web",
            target=site,
            parameters={"duration_seconds": 120},
            reasoning=f"Browsing {site} for work"
        )

    def _is_work_hours(self, current_time: datetime) -> bool:
        """Check if current time is within work hours."""
        schedule = self.profile["work_schedule"]
        start = datetime.strptime(schedule["start_time"], "%H:%M").time()
        end = datetime.strptime(schedule["end_time"], "%H:%M").time()
        return start <= current_time.time() <= end

    def _is_lunch_time(self, current_time: datetime) -> bool:
        """Check if current time is lunch break."""
        lunch = self.profile["work_schedule"]["lunch_break"]
        lunch_start = datetime.strptime(lunch["start"], "%H:%M").time()
        # Simple check - within first 5 minutes of lunch
        from datetime import timedelta
        current = current_time.time()
        return lunch_start <= current <= (datetime.combine(
            current_time.date(), lunch_start
        ) + timedelta(minutes=5)).time()

    def _is_break_time(self, current_time: datetime) -> bool:
        """Check if current time is a scheduled break."""
        breaks = self.profile["work_schedule"].get("coffee_breaks", [])
        current = current_time.strftime("%H:%M")
        return current in breaks
