class GeoFileError(Exception):
    """Client-fixable problem with the uploaded file -> HTTP 422."""
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message
