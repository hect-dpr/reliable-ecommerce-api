class AppError(Exception):
    """App error that the API turns into an HTTP response."""

    def __init__(self, status_code, error, detail):
        self.status_code = status_code
        self.error = error
        self.detail = detail
        super().__init__(detail)


def not_found(error, detail):
    return AppError(404, error, detail)


def bad_request(error, detail):
    return AppError(400, error, detail)


def conflict(error, detail):
    return AppError(409, error, detail)
