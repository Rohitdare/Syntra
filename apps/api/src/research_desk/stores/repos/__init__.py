"""PostgreSQL repositories package."""

from research_desk.stores.repos.briefs import BriefRepo
from research_desk.stores.repos.claims import ClaimRepo
from research_desk.stores.repos.jobs import JobRepo
from research_desk.stores.repos.projects import ProjectRepo
from research_desk.stores.repos.sources import SourceRepo
from research_desk.stores.repos.usage import UsageRepo
from research_desk.stores.repos.users import UserRepo
from research_desk.stores.repos.verdicts import VerdictRepo

__all__ = [
    "BriefRepo",
    "ClaimRepo",
    "JobRepo",
    "ProjectRepo",
    "SourceRepo",
    "UsageRepo",
    "UserRepo",
    "VerdictRepo",
]
