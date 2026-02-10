"""
DecisionEngine - Determines next actions based on worker profile and context.

Uses LLM API to simulate realistic decision-making for an office worker,
considering time of day, current activity, and behavioral patterns.
"""

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


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

    def __init__(self, profile_path: str, use_llm: bool = True):
        """
        Initialize with a worker profile.

        Args:
            profile_path: Path to the worker profile JSON file
            use_llm: Whether to use LLM API for decisions (default True)
        """
        self.profile = self._load_profile(profile_path)
        self.action_history: list[Decision] = []
        self.use_llm = use_llm
        self.llm_client = None

        if use_llm:
            self._init_llm_client()

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

    def _init_llm_client(self):
        """Initialize the Anthropic LLM client."""
        try:
            import anthropic
            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if not api_key:
                logger.warning("ANTHROPIC_API_KEY not set, falling back to heuristics")
                self.use_llm = False
                return
            self.llm_client = anthropic.Anthropic(api_key=api_key)
            logger.info("LLM API client initialized")
        except ImportError:
            logger.warning("anthropic package not installed, falling back to heuristics")
            self.use_llm = False
        except Exception as e:
            logger.warning(f"Failed to initialize LLM client: {e}")
            self.use_llm = False

    def _build_llm_prompt(self, state: WorkerState) -> str:
        """Build the prompt for the LLM to decide the next action."""
        # Recent action history (last 5)
        recent_actions = [
            f"- {d.action_type}: {d.target} ({d.reasoning})"
            for d in self.action_history[-5:]
        ]
        history_str = "\n".join(recent_actions) if recent_actions else "None yet (just started)"

        prompt = f"""You are simulating {self.profile['name']}, a {self.profile['role']} at work.

Current time: {state.current_time.strftime('%H:%M')} ({state.current_time.strftime('%A')})
Minutes since last break: {state.minutes_since_last_break}
Active applications: {', '.join(state.active_applications) if state.active_applications else 'None'}

Recent actions:
{history_str}

Worker's typical activities:
- Primary apps: {', '.join(self.profile['applications']['primary'])}
- Typical websites: {', '.join(self.profile['activities']['browser']['typical_sites'][:5])}
- Document tasks: {', '.join(self.profile['activities']['documents']['common_tasks'])}

Available action types:
- open_application: Open an app (target: outlook, edge, notepad, calculator)
- browse_web: Visit a website for research (target: URL like linkedin.com, canva.com)
- check_email: Check email inbox (target: outlook)
- edit_spreadsheet: Create/edit a budget or data spreadsheet (target: spreadsheet)
- create_document: Write meeting notes, reports, or memos (target: document)
- create_presentation: Draft a presentation outline (target: presentation)
- file_operation: File task (target: create_file, copy_file, move_file, delete_file)
- download_file: Download a resource file from the web (target: url or empty for default)
- idle: Take a break (target: micro_break)

IMPORTANT: A marketing coordinator spends most time on documents, spreadsheets, and presentations - NOT constantly browsing. Only browse when researching specific topics. Vary activities naturally.

Based on the time, recent activity, and what a {self.profile['role']} would realistically do next, decide the next action.

Think about natural task flow - don't just randomly switch activities. Consider:
- Did you just finish something that needs follow-up?
- Is there a natural next step in your current work?
- Have you been working continuously and need a break?

Respond with ONLY a JSON object (no markdown, no explanation):
{{"action_type": "...", "target": "...", "duration_minutes": N, "reasoning": "brief explanation"}}"""

        return prompt

    def _llm_decision(self, state: WorkerState) -> Optional[Decision]:
        """Use LLM to decide the next action."""
        if not self.llm_client:
            return None

        try:
            prompt = self._build_llm_prompt(state)

            message = self.llm_client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=256,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )

            response_text = message.content[0].text.strip()

            # Parse JSON response
            # Handle potential markdown code blocks
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
                response_text = response_text.strip()

            decision_data = json.loads(response_text)

            return Decision(
                action_type=decision_data.get("action_type", "idle"),
                target=decision_data.get("target", "micro_break"),
                parameters={
                    "duration_minutes": decision_data.get("duration_minutes", 5)
                },
                reasoning=decision_data.get("reasoning", "LLM decision")
            )

        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse LLM response: {e}")
            return None
        except Exception as e:
            logger.warning(f"LLM API error: {e}")
            return None

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

        # Try LLM API for intelligent decisions
        if self.use_llm:
            decision = self._llm_decision(state)
            if decision:
                return decision
            logger.debug("LLM decision failed, falling back to heuristics")

        # Fallback to heuristic-based decisions
        return self._heuristic_decision(state)

    def _heuristic_decision(self, state: WorkerState) -> Decision:
        """Rule-based decision making with realistic variety."""
        import random

        hour = state.current_time.hour
        minute = state.current_time.minute
        actions_count = len(self.action_history)

        # Morning routine: Start with email
        if hour == 9 and minute < 15 and actions_count < 3:
            state.active_applications.append("outlook")
            return Decision(
                action_type="open_application",
                target="outlook",
                parameters={"duration_minutes": 5},
                reasoning="Starting day with email check"
            )

        # Weight activities based on time of day and profile
        weights = self._calculate_activity_weights(state, hour)

        # Select activity based on weights
        activity = random.choices(
            list(weights.keys()),
            weights=list(weights.values()),
            k=1
        )[0]

        return self._create_activity_decision(activity, state)

    def _calculate_activity_weights(self, state: WorkerState, hour: int) -> dict:
        """Calculate weighted probabilities for each activity type."""
        # Balanced weights favoring document work (typical marketing coordinator)
        weights = {
            "email": 18,
            "browse": 10,  # Reduced - browsing should be occasional, not dominant
            "spreadsheet": 15,  # Budget reports, data analysis
            "document": 18,  # Meeting notes, memos, reports
            "presentation": 10,  # Presentation drafts
            "application": 8,
            "file_operation": 9,
            "download": 5,  # Occasional file downloads (templates, resources)
            "idle": 10,
        }

        # Adjust weights based on time of day
        if hour < 10:  # Early morning: email and planning
            weights["email"] += 15
            weights["spreadsheet"] += 5
        elif 10 <= hour < 12:  # Mid-morning: productive document work
            weights["document"] += 12
            weights["spreadsheet"] += 8
            weights["presentation"] += 5
        elif 12 <= hour < 14:  # Around lunch: lighter tasks
            weights["browse"] += 5
            weights["idle"] += 5
        elif 14 <= hour < 16:  # Afternoon: continued work with some breaks
            weights["document"] += 8
            weights["presentation"] += 5
            weights["idle"] += 3
        elif hour >= 16:  # Late afternoon: wrapping up, file organization
            weights["email"] += 10
            weights["file_operation"] += 8

        # Reduce email weight if checked recently
        recent_emails = sum(1 for d in self.action_history[-5:]
                          if d.action_type in ["check_email", "open_application"]
                          and d.target == "outlook")
        if recent_emails > 1:
            weights["email"] = max(5, weights["email"] - 15)

        # Reduce browse weight if browsed recently (prevent browse loops)
        recent_browse = sum(1 for d in self.action_history[-5:]
                          if d.action_type == "browse_web")
        if recent_browse > 1:
            weights["browse"] = max(3, weights["browse"] - 10)

        # Increase idle weight if working continuously
        if state.minutes_since_last_break > 45:
            weights["idle"] += 15

        return weights

    def _create_activity_decision(self, activity: str, state: WorkerState) -> Decision:
        """Create a decision for the selected activity type."""
        import random

        if activity == "email":
            if "outlook" not in state.active_applications:
                state.active_applications.append("outlook")
                return Decision(
                    action_type="open_application",
                    target="outlook",
                    parameters={"duration_minutes": 5},
                    reasoning="Opening email client"
                )
            return Decision(
                action_type="check_email",
                target="outlook",
                parameters={"action": "check_inbox", "duration_minutes": 3},
                reasoning="Checking inbox for new messages"
            )

        elif activity == "browse":
            sites = self.profile["activities"]["browser"]["typical_sites"]
            site = random.choice(sites)
            # Use Edge instead of Chrome (matches lean Windows 11)
            if "edge" not in state.active_applications:
                state.active_applications.append("edge")
            return Decision(
                action_type="browse_web",
                target=site,
                parameters={"duration_minutes": random.randint(2, 5)},
                reasoning=f"Researching on {site}"
            )

        elif activity == "spreadsheet":
            # Use the new edit_spreadsheet action
            content_types = ["budget", "contacts", "data"]
            content_type = random.choice(content_types)
            tasks = ["quarterly budget review", "updating contact list", "analyzing campaign data"]
            task = random.choice(tasks)
            return Decision(
                action_type="edit_spreadsheet",
                target="spreadsheet",
                parameters={"content_type": content_type, "duration_minutes": random.randint(5, 15)},
                reasoning=f"Working on {task}"
            )

        elif activity == "document":
            # Use the new create_document action
            doc_types = ["meeting_notes", "report", "memo"]
            doc_type = random.choice(doc_types)
            tasks = self.profile["activities"]["documents"]["common_tasks"]
            task = random.choice(tasks) if tasks else "drafting document"
            return Decision(
                action_type="create_document",
                target="document",
                parameters={"doc_type": doc_type, "duration_minutes": random.randint(5, 12)},
                reasoning=f"Working on {task}"
            )

        elif activity == "presentation":
            # Use the new create_presentation action
            topics = ["Q4 Review", "Campaign Update", "Team Meeting", "Strategy Overview"]
            topic = random.choice(topics)
            return Decision(
                action_type="create_presentation",
                target="presentation",
                parameters={"topic": topic, "slides": random.randint(5, 10), "duration_minutes": random.randint(8, 15)},
                reasoning=f"Drafting {topic} presentation"
            )

        elif activity == "application":
            apps = self.profile["applications"]["primary"]
            # Filter out already open apps for variety
            available = [a for a in apps if a not in state.active_applications]
            if not available:
                available = apps
            app = random.choice(available)
            state.active_applications.append(app)
            return Decision(
                action_type="open_application",
                target=app,
                parameters={"duration_minutes": 5},
                reasoning=f"Opening {app} for work"
            )

        elif activity == "file_operation":
            operations = ["create_file", "copy_file", "move_file"]
            op = random.choice(operations)
            return Decision(
                action_type="file_operation",
                target=op,
                parameters={
                    "path": self.profile["file_paths"]["documents"],
                    "duration_minutes": 2
                },
                reasoning=f"Organizing files ({op})"
            )

        elif activity == "download":
            # Download resources - templates, stock images, data files
            resources = [
                ("marketing template", ""),
                ("stock image", ""),
                ("data file", ""),
                ("report template", ""),
            ]
            resource_name, url = random.choice(resources)
            return Decision(
                action_type="download_file",
                target=url,  # Empty uses safe defaults in ActionExecutor
                parameters={"duration_minutes": random.randint(1, 3)},
                reasoning=f"Downloading {resource_name}"
            )

        else:  # idle
            state.minutes_since_last_break = 0
            return Decision(
                action_type="idle",
                target="micro_break",
                parameters={"duration_minutes": random.randint(2, 5)},
                reasoning="Taking a short break"
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
