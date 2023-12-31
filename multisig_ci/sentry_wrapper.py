import os

SENTRY_IMPORTED=False
try:
    import sentry_sdk
    sentry_dsn = os.environ.get("SENTRY_DSN")

    sentry_sdk.init(
        dsn=sentry_dsn,
        traces_sample_rate=1.0,
        profiles_sample_rate=1.0,
    )
    SENTRY_IMPORTED = True
except Exception:
    pass

def custom_sentry_trace(func=None):
    global SENTRY_IMPORTED
    if SENTRY_IMPORTED:
        return sentry_sdk.trace(func)
    return func
