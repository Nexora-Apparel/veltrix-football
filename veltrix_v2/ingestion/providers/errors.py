"""Provider-neutral transport and response failure classifications."""


class ProviderResponseError(ValueError):
    def __init__(
        self,
        reason_code: str,
        *,
        retryable: bool = False,
        retry_after_seconds: int | None = None,
    ):
        super().__init__(reason_code)
        self.reason_code = reason_code
        self.retryable = retryable
        self.retry_after_seconds = retry_after_seconds
