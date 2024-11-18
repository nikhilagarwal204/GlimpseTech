from enum import Enum


class Source(Enum):
    COLD_CALL = "Cold Call"
    EVENT = "Event"
    REFERRAL = "Referral"
    WEBSITE = "Website"


class InterestLevel(Enum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class Status(Enum):
    CLOSED = "Closed"
    CONTACTED = "Contacted"
    NEW = "New"
    QUALIFIED = "Qualified"
