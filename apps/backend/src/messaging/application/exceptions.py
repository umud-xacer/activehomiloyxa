"""messaging/application -- exceptions for facts the domain layer cannot know (not-found
lookups, uniqueness conflicts already-persisted state reveals). Mirrors `billing.application.
exceptions`'s style."""

from __future__ import annotations

from uuid import UUID


class MessagingApplicationError(Exception):
    """Base for every typed exception raised by messaging's application/ layer."""


class ConversationNotFoundError(MessagingApplicationError):
    def __init__(self, conversation_id: UUID) -> None:
        self.conversation_id = conversation_id
        super().__init__(f"no conversation {conversation_id}")


class ConversationAlreadyExistsError(MessagingApplicationError):
    """Physical DB `UNIQUE(listing_id, initiator_user_id)`: one conversation per initiator per
    listing. Maps to 409 (`startConversation`'s own documented response)."""

    def __init__(self, existing_conversation_id: UUID) -> None:
        self.existing_conversation_id = existing_conversation_id
        super().__init__(
            f"a conversation already exists for this listing and initiator: {existing_conversation_id}"
        )


class BlockAlreadyExistsError(MessagingApplicationError):
    """Physical DB `UNIQUE(blocker_user_id, blocked_user_id)`. Maps to 409 (`blockUser`'s own
    documented response)."""

    def __init__(self, blocked_user_id: UUID) -> None:
        self.blocked_user_id = blocked_user_id
        super().__init__(f"user {blocked_user_id} is already blocked")


class ListingOwnerUnknownError(MessagingApplicationError):
    """`startConversation`'s own server-side recipient resolution has not yet observed this
    listing's `ListingCreated` event in messaging's local projection (`ListingOwnerReaderPort`)
    -- messaging may not import `catalog` to ask directly (AIR-10), so a not-yet-projected
    listing fails closed rather than guessing a recipient. Maps to 503 DEPENDENCY_DEGRADED,
    mirroring `billing.domain.exceptions.UnsupportedProductTypeError`'s own "the referenced
    cross-module data isn't in the shape/state this module needs" disposition."""

    def __init__(self, listing_id: UUID) -> None:
        self.listing_id = listing_id
        super().__init__(f"no known owner for listing {listing_id}")
