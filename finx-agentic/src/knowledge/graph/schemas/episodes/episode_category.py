from enum import Enum


class EpisodeCategory(str, Enum):
    SCHEMA_DEFINITION = "schema_definition"
    QUERY_EXECUTION = "query_execution"
    USER_FEEDBACK = "user_feedback"
    PATTERN_LEARNED = "pattern_learned"
    SCHEMA_CHANGE = "schema_change"
