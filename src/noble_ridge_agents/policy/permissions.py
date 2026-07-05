from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PermissionPolicy:
    permissions: dict[str, frozenset[str]]

    @classmethod
    def default(cls) -> "PermissionPolicy":
        return cls(
            permissions={
                "iris": frozenset(
                    {
                        "gmail.search",
                        "gmail.thread_read",
                        "gmail.summarize",
                        "gmail.draft_reply",
                        "discord.post_approval",
                        "audit.record",
                    }
                ),
                "artemis": frozenset({"request.classify", "job.route", "audit.record"}),
                "themis": frozenset({"policy.check", "audit.review", "permission.validate", "audit.record"}),
                "calliope": frozenset({"website.audit", "website.draft", "audit.record"}),
                "thalia": frozenset({"ads.draft", "campaign.plan", "social.draft", "audit.record"}),
            }
        )

    def is_allowed(self, agent: str, capability: str) -> bool:
        return capability in self.permissions.get(agent, frozenset())
