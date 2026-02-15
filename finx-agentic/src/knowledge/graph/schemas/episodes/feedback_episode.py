import json
from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel
from graphiti_core.nodes import EpisodicNode, EpisodeType


class FeedbackEpisode(BaseModel):
    """Records user feedback on a generated query."""

    natural_language: str
    generated_sql: str
    feedback: str
    rating: Optional[int] = None
    corrected_sql: str = ""
    success: bool = True

    def to_episodic_node(self, group_id: str) -> EpisodicNode:
        content = json.dumps({
            "category": "user_feedback",
            "natural_language": self.natural_language,
            "generated_sql": self.generated_sql,
            "feedback": self.feedback,
            "rating": self.rating,
            "corrected_sql": self.corrected_sql,
            "success": self.success,
        })
        return EpisodicNode(
            name=f"feedback_{self.natural_language[:50]}",
            group_id=group_id,
            source=EpisodeType.json,
            source_description=f"User feedback: {self.feedback[:100]}",
            content=content,
            valid_at=datetime.now(timezone.utc),
        )

    @classmethod
    def from_episodic_node(cls, node: EpisodicNode) -> "FeedbackEpisode":
        data = json.loads(node.content) if node.content else {}
        return cls(
            natural_language=data.get("natural_language", ""),
            generated_sql=data.get("generated_sql", ""),
            feedback=data.get("feedback", ""),
            rating=data.get("rating"),
            corrected_sql=data.get("corrected_sql", ""),
            success=data.get("success", True),
        )
