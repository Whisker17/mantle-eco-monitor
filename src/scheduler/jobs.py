from __future__ import annotations

import logging

from apscheduler import Scheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)


async def core_defillama_job():
    logger.info("Running core_defillama collection")


async def core_dune_job():
    logger.info("Running core_dune collection")


async def core_l2beat_job():
    logger.info("Running core_l2beat collection")


async def core_coingecko_job():
    logger.info("Running core_coingecko collection")


async def core_growthepie_fallback_job():
    logger.info("Running core_growthepie_fallback collection")


async def eco_protocols_job():
    logger.info("Running eco_protocols collection")


async def eco_aave_job():
    logger.info("Running eco_aave collection")


async def watchlist_refresh_job():
    logger.info("Running watchlist_refresh")


async def source_health_job():
    logger.info("Running source_health check")


SCHEDULE_CONFIG = [
    {"id": "core_defillama", "func": core_defillama_job, "trigger": CronTrigger(hour="*/4", minute=0)},
    {"id": "core_coingecko", "func": core_coingecko_job, "trigger": CronTrigger(hour="*/4", minute=5)},
    {"id": "eco_aave", "func": eco_aave_job, "trigger": CronTrigger(hour="*/4", minute=10)},
    {"id": "core_l2beat", "func": core_l2beat_job, "trigger": CronTrigger(hour="*/6", minute=15)},
    {"id": "core_dune", "func": core_dune_job, "trigger": CronTrigger(hour="*/6", minute=20)},
    {"id": "eco_protocols", "func": eco_protocols_job, "trigger": CronTrigger(hour="*/6", minute=30)},
    {"id": "watchlist_refresh", "func": watchlist_refresh_job, "trigger": CronTrigger(hour=4, minute=0)},
    {"id": "source_health", "func": source_health_job, "trigger": CronTrigger(hour="*", minute=45)},
]


def build_scheduler() -> Scheduler:
    scheduler = Scheduler()

    for cfg in SCHEDULE_CONFIG:
        scheduler.configure_task(cfg["id"], func=cfg["func"])
        scheduler.add_schedule(
            cfg["id"],
            trigger=cfg["trigger"],
            id=cfg["id"],
        )

    return scheduler
