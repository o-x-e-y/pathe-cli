"""The one exception type this package raises.

In its own module so `config` can raise it without importing `api`, which
would pull httpx in just to name an error.
"""


class PatheError(RuntimeError):
    pass
