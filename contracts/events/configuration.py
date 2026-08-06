"""configuration (BC-04) domain events -- DDD Sec 6, the authoritative v1 event catalogue.

STATUS: frozen (Task P-01). Schema only: each class is the shared envelope
(`shared_kernel.EventEnvelope`) with `event_type` pinned to its own past-tense name. No
publishing logic, no handlers -- that is outbox/adapter work for a later task. Do not add an
event here that is not a row in DDD Sec 6 for this context; do not remove one either without an
ADR (Playbook Sec 18) amending the Domain Model.
"""

from __future__ import annotations

from typing import Literal

from shared_kernel import EventEnvelope


class ConfigurationChanged(EventEnvelope):
    """Emitted when: Any configuration publication (base envelope; see specialisations below).

    Principal consumers: All conforming contexts (snapshot refresh), Audit.
    """

    event_type: Literal["ConfigurationChanged"] = "ConfigurationChanged"


class CategoryCreated(EventEnvelope):
    """Specialisation of the `ConfigurationChanged` envelope shape (DDD Sec 6) -- same fields as
    `ConfigurationChanged`, own `event_type`. Not a Python subclass of `ConfigurationChanged`:
    mypy --strict correctly rejects narrowing an already-pinned `Literal["ConfigurationChanged"]`
    field to a different literal in a subclass (LSP), and the two are siblings semantically
    anyway -- both are one shape used for different configuration-entity changes, not a
    specific-IS-A-generic relationship. Emitted when: Category configuration publication.

    Principal consumers: All conforming contexts (snapshot refresh), Audit.
    """

    event_type: Literal["CategoryCreated"] = "CategoryCreated"


class CategoryChanged(EventEnvelope):
    """Specialisation of the `ConfigurationChanged` envelope shape (DDD Sec 6) -- same fields as
    `ConfigurationChanged`, own `event_type`. Not a Python subclass of `ConfigurationChanged`:
    mypy --strict correctly rejects narrowing an already-pinned `Literal["ConfigurationChanged"]`
    field to a different literal in a subclass (LSP), and the two are siblings semantically
    anyway -- both are one shape used for different configuration-entity changes, not a
    specific-IS-A-generic relationship. Emitted when: Category configuration publication.

    Principal consumers: All conforming contexts (snapshot refresh), Audit.
    """

    event_type: Literal["CategoryChanged"] = "CategoryChanged"


class CategoryRetired(EventEnvelope):
    """Specialisation of the `ConfigurationChanged` envelope shape (DDD Sec 6) -- same fields as
    `ConfigurationChanged`, own `event_type`. Not a Python subclass of `ConfigurationChanged`:
    mypy --strict correctly rejects narrowing an already-pinned `Literal["ConfigurationChanged"]`
    field to a different literal in a subclass (LSP), and the two are siblings semantically
    anyway -- both are one shape used for different configuration-entity changes, not a
    specific-IS-A-generic relationship. Emitted when: Category configuration publication.

    Principal consumers: All conforming contexts (snapshot refresh), Audit.
    """

    event_type: Literal["CategoryRetired"] = "CategoryRetired"


class FormDefinitionPublished(EventEnvelope):
    """Specialisation of the `ConfigurationChanged` envelope shape (DDD Sec 6) -- same fields as
    `ConfigurationChanged`, own `event_type`. Not a Python subclass of `ConfigurationChanged`:
    mypy --strict correctly rejects narrowing an already-pinned `Literal["ConfigurationChanged"]`
    field to a different literal in a subclass (LSP), and the two are siblings semantically
    anyway -- both are one shape used for different configuration-entity changes, not a
    specific-IS-A-generic relationship. Emitted when: Form configuration publication.

    Principal consumers: All conforming contexts (snapshot refresh), Audit.
    """

    event_type: Literal["FormDefinitionPublished"] = "FormDefinitionPublished"


class ProductDefinitionChanged(EventEnvelope):
    """Specialisation of the `ConfigurationChanged` envelope shape (DDD Sec 6) -- same fields as
    `ConfigurationChanged`, own `event_type`. Not a Python subclass of `ConfigurationChanged`:
    mypy --strict correctly rejects narrowing an already-pinned `Literal["ConfigurationChanged"]`
    field to a different literal in a subclass (LSP), and the two are siblings semantically
    anyway -- both are one shape used for different configuration-entity changes, not a
    specific-IS-A-generic relationship. Emitted when: Product configuration publication.

    Principal consumers: All conforming contexts (snapshot refresh), Audit.
    """

    event_type: Literal["ProductDefinitionChanged"] = "ProductDefinitionChanged"


class PlacementSlotDefined(EventEnvelope):
    """Specialisation of the `ConfigurationChanged` envelope shape (DDD Sec 6) -- same fields as
    `ConfigurationChanged`, own `event_type`. Not a Python subclass of `ConfigurationChanged`:
    mypy --strict correctly rejects narrowing an already-pinned `Literal["ConfigurationChanged"]`
    field to a different literal in a subclass (LSP), and the two are siblings semantically
    anyway -- both are one shape used for different configuration-entity changes, not a
    specific-IS-A-generic relationship. Emitted when: Placement-slot configuration publication.

    Principal consumers: All conforming contexts (snapshot refresh), Audit.
    """

    event_type: Literal["PlacementSlotDefined"] = "PlacementSlotDefined"


class RoleDefinitionChanged(EventEnvelope):
    """Specialisation of the `ConfigurationChanged` envelope shape (DDD Sec 6) -- same fields as
    `ConfigurationChanged`, own `event_type`. Not a Python subclass of `ConfigurationChanged`:
    mypy --strict correctly rejects narrowing an already-pinned `Literal["ConfigurationChanged"]`
    field to a different literal in a subclass (LSP), and the two are siblings semantically
    anyway -- both are one shape used for different configuration-entity changes, not a
    specific-IS-A-generic relationship. Emitted when: Role configuration publication.

    Principal consumers: All conforming contexts (snapshot refresh), Audit.
    """

    event_type: Literal["RoleDefinitionChanged"] = "RoleDefinitionChanged"


class SearchConfigurationChanged(EventEnvelope):
    """Specialisation of the `ConfigurationChanged` envelope shape (DDD Sec 6) -- same fields as
    `ConfigurationChanged`, own `event_type`. Not a Python subclass of `ConfigurationChanged`:
    mypy --strict correctly rejects narrowing an already-pinned `Literal["ConfigurationChanged"]`
    field to a different literal in a subclass (LSP), and the two are siblings semantically
    anyway -- both are one shape used for different configuration-entity changes, not a
    specific-IS-A-generic relationship. Emitted when: Search configuration publication.

    Principal consumers: All conforming contexts (snapshot refresh), Audit.
    """

    event_type: Literal["SearchConfigurationChanged"] = "SearchConfigurationChanged"


class NotificationTemplateChanged(EventEnvelope):
    """Specialisation of the `ConfigurationChanged` envelope shape (DDD Sec 6) -- same fields as
    `ConfigurationChanged`, own `event_type`. Not a Python subclass of `ConfigurationChanged`:
    mypy --strict correctly rejects narrowing an already-pinned `Literal["ConfigurationChanged"]`
    field to a different literal in a subclass (LSP), and the two are siblings semantically
    anyway -- both are one shape used for different configuration-entity changes, not a
    specific-IS-A-generic relationship. Emitted when: Notification-template configuration publication.

    Principal consumers: All conforming contexts (snapshot refresh), Audit.
    """

    event_type: Literal["NotificationTemplateChanged"] = "NotificationTemplateChanged"


class PlatformSettingsChanged(EventEnvelope):
    """Specialisation of the `ConfigurationChanged` envelope shape (DDD Sec 6) -- same fields as
    `ConfigurationChanged`, own `event_type`. Not a Python subclass of `ConfigurationChanged`:
    mypy --strict correctly rejects narrowing an already-pinned `Literal["ConfigurationChanged"]`
    field to a different literal in a subclass (LSP), and the two are siblings semantically
    anyway -- both are one shape used for different configuration-entity changes, not a
    specific-IS-A-generic relationship. Emitted when: Platform-settings configuration publication.

    Principal consumers: All conforming contexts (snapshot refresh), Audit.
    """

    event_type: Literal["PlatformSettingsChanged"] = "PlatformSettingsChanged"
