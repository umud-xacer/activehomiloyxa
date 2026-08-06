"""messaging/domain -- standalone domain policies (DDD Sec 5.7 `RateLimitPolicy [P]`).

`MESSAGE_RATE_LIMIT_MAX_PER_WINDOW`/`MESSAGE_RATE_LIMIT_WINDOW_SECONDS` are implementation-chosen
defaults: BR-MSG-03 and Security Sec 3.1 only specify a QUALITATIVE control ("per-user messaging
rate limits ... on both conversation initiation and message send") -- no literal number appears
anywhere in the approved documents. This is the exact same situation `identity.domain.policies.
OtpThrottlePolicy` already resolved for NFR-SEC-004 (that module's own docstring: "no literal
numbers appear in the approved documents"); this policy follows its precedent exactly rather than
inventing a fresh convention. Unlike identity's threshold, this one cannot be sourced from
`configuration` even in principle -- SAD Sec 8.1's static import matrix permits messaging to
import only `shared_kernel` + `identity`, not `configuration` -- so it is a fixed constant, not a
platform-settings snapshot.

`startConversation` sends its first message atomically (Message.send inside Conversation.start),
so ONE policy, applied per message-authored-by-a-user, covers both "conversation initiation" and
"message send" from BR-MSG-03's text -- there is no need for a second, separate threshold.
"""

from __future__ import annotations

from dataclasses import dataclass

from messaging.domain.exceptions import RateLimitExceededError

MESSAGE_RATE_LIMIT_MAX_PER_WINDOW = 20
"""Max messages (including conversation-starting ones) a single user may author within the
window below."""

MESSAGE_RATE_LIMIT_WINDOW_SECONDS = 60


@dataclass(frozen=True)
class MessageRateLimitPolicy:
    """BR-MSG-03. The calling use case resolves `recent_message_count` (via `ConversationRepository.
    count_recent_messages_by_author`, counted across every conversation the author has sent
    into, per-user not per-conversation) and passes it in; this policy makes the pure allow/deny
    decision -- mirrors `OtpThrottlePolicy.check`'s exact shape."""

    max_per_window: int = MESSAGE_RATE_LIMIT_MAX_PER_WINDOW
    window_seconds: int = MESSAGE_RATE_LIMIT_WINDOW_SECONDS

    def check(self, *, recent_message_count: int) -> None:
        if recent_message_count >= self.max_per_window:
            raise RateLimitExceededError(retry_after_seconds=self.window_seconds)
