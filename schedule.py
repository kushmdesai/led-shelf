from datetime import datetime
from threading import Event, Lock, Thread

import db
from mqtt import send_message


POLL_SECONDS = 5

_scheduler_lock = Lock()
_scheduler_thread = None
_stop_event = Event()


def has_run_today(schedule, now):
    last_run_at = schedule.get("last_run_at")

    if not last_run_at:
        return False

    try:
        last_run = datetime.fromisoformat(last_run_at)
    except ValueError:
        return False

    return last_run.date() == now.date()


def is_due(schedule, now):
    if not schedule.get("enabled"):
        return False

    if schedule.get("time") != now.strftime("%H:%M"):
        return False

    return not has_run_today(schedule, now)


def run_due_schedules(now=None, state_lock=None):
    now = now or datetime.now()
    ran = []

    for schedule in db.get_schedules():
        if not is_due(schedule, now):
            continue

        action = schedule["action"]

        if state_lock is None:
            db.set_device_state("power", action)
            db.update_schedule(schedule["id"], last_run_at=now.isoformat(timespec="seconds"))
        else:
            with state_lock:
                db.set_device_state("power", action)
                db.update_schedule(schedule["id"], last_run_at=now.isoformat(timespec="seconds"))

        send_message("power", action)
        ran.append(schedule)

    return ran


def scheduler_loop(stop_event=None, state_lock=None, poll_seconds=POLL_SECONDS):
    stop_event = stop_event or _stop_event
    db.init_db()

    while not stop_event.is_set():
        run_due_schedules(state_lock=state_lock)
        stop_event.wait(poll_seconds)


def start_scheduler(state_lock=None):
    global _scheduler_thread

    with _scheduler_lock:
        if _scheduler_thread is not None and _scheduler_thread.is_alive():
            return _scheduler_thread

        _stop_event.clear()
        _scheduler_thread = Thread(
            target=scheduler_loop,
            kwargs={"state_lock": state_lock},
            daemon=True,
            name="schedule-runner",
        )
        _scheduler_thread.start()
        return _scheduler_thread


if __name__ == "__main__":
    scheduler_loop()
