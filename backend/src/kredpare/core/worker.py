from celery import Celery

from kredpare.core.settings import get_settings

_redis_url = get_settings().redis_url

celery_app = Celery("kredpare", broker=_redis_url, backend=_redis_url)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    broker_connection_retry_on_startup=True,
    beat_schedule={
        # Proves Beat schedules tasks end to end; replaced by real schedules later.
        "ping-every-minute": {"task": "kredpare.ping", "schedule": 60.0},
    },
)


@celery_app.task(name="kredpare.ping")
def ping() -> str:
    return "pong"
