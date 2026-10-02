from celery.contrib.testing.worker import start_worker

from kredpare.core.worker import celery_app, ping


def test_ping_round_trip_through_redis() -> None:
    # A real worker thread consuming from the Redis broker, not eager mode.
    with start_worker(celery_app, perform_ping_check=False, pool="solo"):
        result = ping.delay()
        assert result.get(timeout=10) == "pong"


def test_beat_schedules_ping() -> None:
    entry = celery_app.conf.beat_schedule["ping-every-minute"]

    assert entry["task"] == ping.name
    assert entry["schedule"] == 60.0
