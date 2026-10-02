from fastapi import HTTPException, status


class VisionQCException(Exception):
    """Base application exception."""
    def __init__(self, message: str, code: str = "INTERNAL_ERROR"):
        self.message = message
        self.code = code
        super().__init__(message)


class InvalidImageError(VisionQCException):
    def __init__(self, message: str = "Invalid or unsupported image format."):
        super().__init__(message, "INVALID_IMAGE")


class ImageTooLargeError(VisionQCException):
    def __init__(self, max_mb: int = 15):
        super().__init__(f"Image exceeds the maximum allowed size of {max_mb}MB.", "IMAGE_TOO_LARGE")


class ProductNotFoundError(VisionQCException):
    def __init__(self, product_id: str = ""):
        super().__init__(f"Product not found.", "PRODUCT_NOT_FOUND")


class InspectionNotFoundError(VisionQCException):
    def __init__(self):
        super().__init__("Inspection record not found.", "INSPECTION_NOT_FOUND")


class InspectionFailedError(VisionQCException):
    def __init__(self, message: str = "Inspection could not be completed. Please try again."):
        super().__init__(message, "INSPECTION_FAILED")


class StorageError(VisionQCException):
    def __init__(self, message: str = "File storage operation failed."):
        super().__init__(message, "STORAGE_ERROR")


class AllProvidersFailedError(VisionQCException):
    def __init__(self):
        super().__init__(
            "Inspection could not be completed. Please try again.",
            "ALL_PROVIDERS_FAILED"
        )


# Map to HTTP exceptions for FastAPI
EXCEPTION_STATUS_MAP = {
    "INVALID_IMAGE": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "IMAGE_TOO_LARGE": status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
    "PRODUCT_NOT_FOUND": status.HTTP_404_NOT_FOUND,
    "INSPECTION_NOT_FOUND": status.HTTP_404_NOT_FOUND,
    "INSPECTION_FAILED": status.HTTP_503_SERVICE_UNAVAILABLE,
    "STORAGE_ERROR": status.HTTP_503_SERVICE_UNAVAILABLE,
    "ALL_PROVIDERS_FAILED": status.HTTP_503_SERVICE_UNAVAILABLE,
    "INTERNAL_ERROR": status.HTTP_500_INTERNAL_SERVER_ERROR,
}


def visionqc_exception_to_http(exc: VisionQCException) -> HTTPException:
    status_code = EXCEPTION_STATUS_MAP.get(exc.code, 500)
    return HTTPException(status_code=status_code, detail=exc.message)
