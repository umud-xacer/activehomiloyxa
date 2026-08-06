"""media/infrastructure -- SQLAlchemy repository, MinIO/ClamAV/Pillow adapters, and the intake
worker (Task P-06). Never imported by `media.interfaces`/`application`/`domain`
(`no-infra-inbound-media`, tools/importlinter.cfg) -- only the composition root (outside every
module's package tree) wires these concrete classes behind the ports `application/` declares."""

from __future__ import annotations

from media.infrastructure.image_processing import PillowImageProcessingAdapter
from media.infrastructure.malware_scan import ClamAvMalwareScanAdapter
from media.infrastructure.object_storage import MinioStorageAdapter
from media.infrastructure.persistence import SqlalchemyMediaAssetRepository
from media.infrastructure.worker import MediaIntakeWorker

__all__ = [
    "ClamAvMalwareScanAdapter",
    "MediaIntakeWorker",
    "MinioStorageAdapter",
    "PillowImageProcessingAdapter",
    "SqlalchemyMediaAssetRepository",
]
