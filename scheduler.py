"""Background reminder loop running inside the Flask process.

Every SCHEDULER_INTERVAL_SECONDS it creates due reminders and sends Web Push.
Reminders therefore require the BalanceAI server to be running; the browser
tab can be closed (the browser itself must be running to display pushes)."""
from __future__ import annotations

import logging
import threading
import time

import config
import notifications

log = logging.getLogger("balanceai.scheduler")
_started = False


def _loop() -> None:
    while True:
        try:
            res = notifications.tick()
            if res["created"]:
                log.info("Reminders created: %s, pushes sent: %s", res["created"], res["pushed"])
        except Exception:
            log.exception("Scheduler tick failed")
        time.sleep(config.SCHEDULER_INTERVAL_SECONDS)


def start() -> bool:
    global _started
    if _started or not config.SCHEDULER_ENABLED:
        return False
    threading.Thread(target=_loop, name="balanceai-scheduler", daemon=True).start()
    _started = True
    return True
