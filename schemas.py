# schemas.py
from pydantic import BaseModel
from typing import List, Dict, Optional


class KeywordFull(BaseModel):
    keyword: str
    search_volume: Optional[int] = None
    competition: Optional[str] = None
    cpc_range: Optional[str] = None


class ShoppingCPCSuggestion(BaseModel):
    keyword: str
    search_volume: Optional[int] = None
    competition: Optional[str] = None
    suggested_cpc: Optional[float] = None


# --- PMax theme model used for each theme key ---
class PMaxTheme(BaseModel):
    keywords: List[str]
    total_volume: int


class BudgetAllocations(BaseModel):
    cap: int
    bud: int
    pmax: int


class SEMInputs(BaseModel):
    brand_website: str
    competitor_website: Optional[str] = None
    target_locations: str
    themes: Optional[List[str]] = []
    budget_allocations: BudgetAllocations


class SEMOutput(BaseModel):
    brand: str
    competitor: Optional[str]
    locations: List[str]
    budget_allocations: BudgetAllocations
    total_budget: int

    # summary stats
    total_keywords: int
    total_volume: int
    avg_cpc: float

    themes: List[str]

    searchAdGroups: Dict[str, List[KeywordFull]]
    pmaxThemes: Dict[str, PMaxTheme]
    shoppingCPC: List[ShoppingCPCSuggestion]
