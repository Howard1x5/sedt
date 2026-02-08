"""
DetectionSimAgent - Main orchestrator for simulated worker activity.

Manages the simulation loop, time compression, and coordination between
the DecisionEngine (local) and ActionExecutor (remote Windows VM).

Architecture:
    This agent runs on a Linux host and sends action commands to
    a Windows VM via SSH using RemoteExecutor.
"""

import logging
import os
from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass, field

from .decision_engine import DecisionEngine, WorkerState, Decision
from .remote_executor import RemoteExecutor, ExecutionResult

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class SimulationConfig:
    """Configuration for the simulation."""
    profile_path: str
    time_compression: float = 1.0  # 1.0 = real-time, 60.0 = 1 min = 1 hour
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    dry_run: bool = False  # If True, don't execute real actions

    # Remote Windows VM configuration (use environment variables)
    windows_host: str = field(default_factory=lambda: os.environ.get("SEDT_WINDOWS_HOST", "192.168.1.100"))
    windows_user: str = field(default_factory=lambda: os.environ.get("SEDT_WINDOWS_USER", "analyst"))
    windows_password: Optional[str] = field(default_factory=lambda: os.environ.get("SEDT_WINDOWS_PASSWORD"))
    windows_ssh_port: int = 22
    windows_ssh_key: Optional[str] = None
    windows_python_path: str = r"C:\Users\analyst\AppData\Local\Programs\Python\Python311\python.exe"
    windows_executor_path: str = r"C:\sedt\action_executor.py"

    def __post_init__(self):
        if self.start_time is None:
            # Default: today at 9 AM
            today = datetime.now().date()
            self.start_time = datetime.combine(today, datetime.strptime("09:00", "%H:%M").time())
        if self.end_time is None:
            # Default: today at 5 PM
            today = datetime.now().date()
            self.end_time = datetime.combine(today, datetime.strptime("17:00", "%H:%M").time())


@dataclass
class SimulationStats:
    """Statistics from a simulation run."""
    total_decisions: int = 0
    actions_executed: int = 0
    actions_failed: int = 0
    simulated_duration: timedelta = field(default_factory=timedelta)
    real_duration: timedelta = field(default_factory=timedelta)
    action_counts: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "total_decisions": self.total_decisions,
            "actions_executed": self.actions_executed,
            "actions_failed": self.actions_failed,
            "simulated_duration_minutes": self.simulated_duration.total_seconds() / 60,
            "real_duration_seconds": self.real_duration.total_seconds(),
            "compression_achieved": (
                self.simulated_duration.total_seconds() / self.real_duration.total_seconds()
                if self.real_duration.total_seconds() > 0 else 0
            ),
            "action_breakdown": self.action_counts
        }


class DetectionSimAgent:
    """
    Main simulation agent that orchestrates worker activity.

    The agent:
    1. Maintains simulated time (with compression)
    2. Asks DecisionEngine what to do next
    3. Executes actions via ActionExecutor
    4. Tracks statistics for validation
    """

    def __init__(self, config: SimulationConfig):
        """
        Initialize the simulation agent.

        Args:
            config: Simulation configuration
        """
        self.config = config
        self.decision_engine = DecisionEngine(config.profile_path)
        self.remote_executor: Optional[RemoteExecutor] = None

        self.simulated_time = config.start_time
        self.state = WorkerState(current_time=self.simulated_time)
        self.stats = SimulationStats()
        self.running = False

        logger.info(f"Agent initialized for profile: {config.profile_path}")
        logger.info(f"Time compression: {config.time_compression}x")
        logger.info(f"Simulating: {config.start_time} to {config.end_time}")

        # Initialize remote executor if not dry run
        if not config.dry_run:
            self._init_remote_executor()

    def _init_remote_executor(self):
        """Initialize connection to Windows VM."""
        try:
            self.remote_executor = RemoteExecutor(
                windows_host=self.config.windows_host,
                windows_user=self.config.windows_user,
                windows_password=self.config.windows_password,
                ssh_port=self.config.windows_ssh_port,
                ssh_key_path=self.config.windows_ssh_key,
                python_path=self.config.windows_python_path,
                executor_path=self.config.windows_executor_path
            )
            logger.info(f"Connected to Windows VM at {self.config.windows_host}")
        except ConnectionError as e:
            logger.warning(f"Could not connect to Windows VM: {e}")
            logger.warning("Running in dry-run mode")
            self.config.dry_run = True

    def run(self) -> SimulationStats:
        """
        Run the simulation until end_time or interrupted.

        Returns:
            SimulationStats with run statistics
        """
        import time

        self.running = True
        real_start = datetime.now()

        logger.info("Starting simulation...")

        try:
            while self.running and self.simulated_time < self.config.end_time:
                # Get next decision
                decision = self.decision_engine.decide_next_action(self.state)
                self.decision_engine.action_history.append(decision)
                self.stats.total_decisions += 1

                # Log decision
                logger.info(
                    f"[{self.simulated_time.strftime('%H:%M')}] "
                    f"{decision.action_type}: {decision.target} "
                    f"({decision.reasoning})"
                )

                # Execute action
                if decision.action_type == "end_day":
                    logger.info("End of workday reached")
                    break

                success = self._execute_action(decision)
                if success:
                    self.stats.actions_executed += 1
                else:
                    self.stats.actions_failed += 1

                # Track action types
                action_type = decision.action_type
                self.stats.action_counts[action_type] = (
                    self.stats.action_counts.get(action_type, 0) + 1
                )

                # Advance simulated time
                action_duration = decision.parameters.get("duration_minutes", 5)
                self._advance_time(minutes=action_duration)

                # Apply time compression for real wait
                real_wait = action_duration * 60 / self.config.time_compression
                if real_wait > 0.1:  # Minimum wait to prevent CPU spinning
                    time.sleep(real_wait)

        except KeyboardInterrupt:
            logger.info("Simulation interrupted by user")
        finally:
            self.running = False
            real_end = datetime.now()
            self.stats.real_duration = real_end - real_start
            self.stats.simulated_duration = self.simulated_time - self.config.start_time

        logger.info(f"Simulation complete: {self.stats.to_dict()}")
        return self.stats

    def _execute_action(self, decision: Decision) -> bool:
        """
        Execute a decision's action on the remote Windows VM.

        Args:
            decision: The decision to execute

        Returns:
            True if successful, False otherwise
        """
        if self.config.dry_run:
            logger.debug(f"DRY RUN: Would execute {decision.action_type}")
            return True

        if self.remote_executor is None:
            # No executor configured, log only
            logger.debug(f"No executor: {decision.action_type} -> {decision.target}")
            return True

        try:
            result: ExecutionResult = self.remote_executor.execute(
                action_type=decision.action_type,
                target=decision.target,
                parameters=decision.parameters
            )

            if result.success:
                logger.debug(f"Action succeeded: {result.output}")
            else:
                logger.warning(f"Action failed: {result.error}")

            return result.success

        except Exception as e:
            logger.error(f"Action failed: {decision.action_type} - {e}")
            return False

    def _advance_time(self, minutes: int):
        """Advance the simulated time."""
        self.simulated_time += timedelta(minutes=minutes)
        self.state.current_time = self.simulated_time
        self.state.minutes_since_last_break += minutes

    def stop(self):
        """Stop the simulation gracefully."""
        logger.info("Stopping simulation...")
        self.running = False
