#!/usr/bin/env python3
"""
SEDT Agent Runner

Run the simulated worker agent to generate benign Windows telemetry.

Usage:
    python run_agent.py                    # Run with defaults
    python run_agent.py --dry-run          # Test without Windows connection
    python run_agent.py --compression 60   # 1 real minute = 1 simulated hour
    python run_agent.py --profile alex_marketing.json

Environment Variables:
    ANTHROPIC_API_KEY  - Required for LLM-based decisions (future)
    SEDT_WINDOWS_HOST  - Windows VM IP (default: 192.168.1.100)
    SEDT_WINDOWS_USER  - Windows SSH user (default: analyst)
"""

import argparse
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from core import DetectionSimAgent, SimulationConfig


def setup_logging(verbose: bool = False):
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%H:%M:%S'
    )


def main():
    parser = argparse.ArgumentParser(
        description="SEDT - Simulated Enterprise Detection Testing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        "--profile",
        default="config/profiles/alex_marketing.json",
        help="Path to worker profile JSON"
    )
    parser.add_argument(
        "--compression",
        type=float,
        default=60.0,
        help="Time compression factor (60 = 1 real min = 1 sim hour)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Don't connect to Windows VM, just simulate decisions"
    )
    parser.add_argument(
        "--start-time",
        help="Simulation start time (HH:MM format, default: 09:00)"
    )
    parser.add_argument(
        "--end-time",
        help="Simulation end time (HH:MM format, default: 17:00)"
    )
    parser.add_argument(
        "--windows-host",
        default=os.environ.get("SEDT_WINDOWS_HOST", "192.168.1.100"),
        help="Windows VM IP address"
    )
    parser.add_argument(
        "--windows-user",
        default=os.environ.get("SEDT_WINDOWS_USER", "analyst"),
        help="Windows SSH username"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable debug logging"
    )

    args = parser.parse_args()

    setup_logging(args.verbose)
    logger = logging.getLogger("sedt")

    # Resolve profile path
    profile_path = Path(args.profile)
    if not profile_path.is_absolute():
        profile_path = Path(__file__).parent / profile_path

    if not profile_path.exists():
        logger.error(f"Profile not found: {profile_path}")
        sys.exit(1)

    # Parse times
    today = datetime.now().date()
    start_time = None
    end_time = None

    if args.start_time:
        start_time = datetime.combine(
            today,
            datetime.strptime(args.start_time, "%H:%M").time()
        )
    if args.end_time:
        end_time = datetime.combine(
            today,
            datetime.strptime(args.end_time, "%H:%M").time()
        )

    # Create configuration
    config = SimulationConfig(
        profile_path=str(profile_path),
        time_compression=args.compression,
        start_time=start_time,
        end_time=end_time,
        dry_run=args.dry_run,
        windows_host=args.windows_host,
        windows_user=args.windows_user,
    )

    logger.info("=" * 60)
    logger.info("SEDT - Simulated Enterprise Detection Testing")
    logger.info("=" * 60)
    logger.info(f"Profile: {profile_path.name}")
    logger.info(f"Time compression: {args.compression}x")
    logger.info(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    if not args.dry_run:
        logger.info(f"Windows VM: {args.windows_host}")
    logger.info("=" * 60)

    # Create and run agent
    agent = DetectionSimAgent(config)

    try:
        stats = agent.run()
        logger.info("=" * 60)
        logger.info("Simulation Complete")
        logger.info("=" * 60)
        logger.info(f"Total decisions: {stats.total_decisions}")
        logger.info(f"Actions executed: {stats.actions_executed}")
        logger.info(f"Actions failed: {stats.actions_failed}")
        logger.info(f"Simulated time: {stats.simulated_duration}")
        logger.info(f"Real time: {stats.real_duration}")
        logger.info(f"Action breakdown: {stats.action_counts}")

    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        agent.stop()


if __name__ == "__main__":
    main()
