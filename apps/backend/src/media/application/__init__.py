"""media/application -- use cases + ports (Task P-06). Depends only on `media.domain`,
`shared_kernel`, and `contracts.events.media`."""

from __future__ import annotations

from media.application.exceptions import (
    MediaApplicationError,
    MediaAssetNotFoundError,
    NotAssetOwnerError,
)
from media.application.intake_use_cases import MediaIntakeUseCases
from media.application.ports import (
    GeneratedVariant,
    ImageProcessingPort,
    MalwareScanPort,
    MalwareScanResult,
    MediaAssetRepository,
    PresignedUpload,
    ProcessedImage,
    StoragePort,
)
from media.application.processing_use_cases import MediaProcessingUseCases

__all__ = [
    "GeneratedVariant",
    "ImageProcessingPort",
    "MalwareScanPort",
    "MalwareScanResult",
    "MediaApplicationError",
    "MediaAssetNotFoundError",
    "MediaAssetRepository",
    "MediaIntakeUseCases",
    "MediaProcessingUseCases",
    "NotAssetOwnerError",
    "PresignedUpload",
    "ProcessedImage",
    "StoragePort",
]
