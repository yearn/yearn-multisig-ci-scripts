import os

SENTRY_IMPORTED=False
try:
    import sentry_sdk
    import sentry_sdk.integrations.excepthook
    sentry_dsn = os.environ.get("SENTRY_DSN")
    debug_from_env = os.environ.get("SENTRY_DEBUG", False)
    sentry_sdk.init(
        dsn=sentry_dsn,
        sample_rate=1.0,
        traces_sample_rate=1.0,
        profiles_sample_rate=1.0,
        integrations=[sentry_sdk.integrations.excepthook.ExcepthookIntegration(always_run=True)],
        debug=debug_from_env,
    )
    SENTRY_IMPORTED = True
except Exception as e:
    print(e)
    pass

def custom_sentry_trace(func=None):
    global SENTRY_IMPORTED
    if SENTRY_IMPORTED:
        return sentry_sdk.trace(func)
    return func

class CustomSentryTransaction:
    def __init__(self, op, name):
        self.op = op
        self.name = name
        self.tx = None

    def __enter__(self):
        global SENTRY_IMPORTED
        if SENTRY_IMPORTED:
            self.tx = sentry_sdk.start_transaction(op=self.op, name=self.name)
            self.tx.__enter__()

        return self.tx

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.tx is not None:
            self.tx.__exit__(exc_type, exc_val, exc_tb)

class CustomSentrySpan:
    def __init__(self, description):
        self.description = description
        self.span = None

    def __enter__(self):
        global SENTRY_IMPORTED
        if SENTRY_IMPORTED:
            self.span = sentry_sdk.start_span(description=self.description)
            self.span.__enter__()

        return self.span

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.span is not None:
            self.span.__exit__(exc_type, exc_val, exc_tb)
