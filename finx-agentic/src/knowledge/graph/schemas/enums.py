from enum import Enum


class NodeLabel(str, Enum):
    TABLE = "Table"
    COLUMN = "Column"
    BUSINESS_ENTITY = "BusinessEntity"
    QUERY_PATTERN = "QueryPattern"
    DOMAIN = "Domain"
    BUSINESS_RULE = "BusinessRule"
    CODE_SET = "CodeSet"
