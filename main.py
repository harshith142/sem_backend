# main.py
import json
import re
import yaml
from typing import List, Dict, Any

from fastapi import FastAPI, HTTPException
import google.generativeai as genai

from google_ads import get_keywords_from_google
from schemas import (
    SEMInputs,
    SEMOutput,
    KeywordFull,
    PMaxTheme,
    ShoppingCPCSuggestion,
    BudgetAllocations,
)
from fastapi.middleware.cors import CORSMiddleware


# FastAPI setup

app = FastAPI(title="SEM Planning Tool")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # React frontend can connect
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Load Google Ads + Gemini API config

with open("google_ads.yaml", "r") as f:
    config = yaml.safe_load(f)

# Configure Gemini
if "google_llm_api_key" in config and config["google_llm_api_key"]:
    genai.configure(api_key=config["google_llm_api_key"])
    model = genai.GenerativeModel("gemini-1.5-flash")
else:
    model = None



# Utility functions

def clean_domain(url: str) -> str:
    if not url:
        return ""
    u = re.sub(r"https?://", "", url)
    u = u.replace("www.", "")
    return u.split(".")[0].lower()


def parse_llm_json(text: str) -> Dict[str, Any]:
    """Try to extract JSON out of LLM text safely."""
    if not text:
        return {}
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start:end+1])
            except Exception:
                pass
    return {}


def generate_pmax_themes_llm(keywords: List[str], locations: List[str]) -> Dict[str, PMaxTheme]:
    """
    Call Gemini to group keywords into PMax campaign themes.
    Returns dict with product, usecase, demographic, seasonal themes.
    """
    fallback = {
        "product": PMaxTheme(keywords=keywords, total_volume=0),
        "usecase": PMaxTheme(keywords=[kw for kw in keywords if len(kw.split()) >= 3], total_volume=0),
        "demographic": PMaxTheme(keywords=locations, total_volume=0),
        "seasonal": PMaxTheme(keywords=[f"{loc} seasonal trends" for loc in locations], total_volume=0),
    }

    if not model:
        return fallback

    prompt = f"""
You are a Google Ads strategist. Group the following keywords into up to 6 Performance Max campaign themes.
According to the keyword list and also generate some if they are empty , identify themes such as product types, use cases, demographics (locations), and seasonal trends.
For each theme, provide a name, a list of relevant keywords, and an estimated total monthly search volume (sum of individual keyword volumes).
group them as "product","seasonal","usecase","demographic". accoridng to their uses.fill them with proper keywords if they are empty .
Produce JSON ONLY in this format:

{{
  "themes": [
    {{
      "name": "Theme Name",
      "keywords": ["kw1", "kw2"],
      "total_volume": 12345
    }}
  ]
}}

Keywords:
{json.dumps(keywords)}

Also include seasonal groups if any, and list location-based themes if relevant.
"""

    try:
        resp = model.generate_content(prompt)
        resp_text = resp.text if hasattr(resp, "text") else str(resp)
    except Exception:
        return fallback

    parsed = parse_llm_json(resp_text)
    themes_list = parsed.get("themes") or []

    product_keywords, usecase_long, demographic_keywords, seasonal_keywords = [], [], [], []

    if isinstance(themes_list, list):
        for t in themes_list:
            name = t.get("name", "").lower() if isinstance(t, dict) else ""
            kws = t.get("keywords", []) if isinstance(t, dict) else []
            if not isinstance(kws, list):
                kws = []
            if any(w in name for w in ["product", "protein", "whey", "vegan", "organic"]):
                product_keywords.extend(kws)
            elif any(w in name for w in ["use", "recovery", "weight"]):
                usecase_long.extend(kws)
            elif any(w in name for w in ["city", "india", "delhi", "mumbai", "location"]):
                demographic_keywords.extend(kws)
            elif any(w in name for w in ["season", "summer", "winter", "holiday", "fest", "diwali", "xmas"]):
                seasonal_keywords.extend(kws)
            else:
                product_keywords.extend(kws)

    def uniq(seq):
        seen, out = set(), []
        for x in seq:
            if x not in seen:
                seen.add(x)
                out.append(x)
        return out

    return {
        "product": PMaxTheme(keywords=uniq(product_keywords) or uniq(keywords), total_volume=0),
        "usecase": PMaxTheme(keywords=uniq(usecase_long), total_volume=0),
        "demographic": PMaxTheme(keywords=uniq(demographic_keywords) or locations, total_volume=0),
        "seasonal": PMaxTheme(keywords=uniq(seasonal_keywords), total_volume=0),
    }


#
# Main endpoint

@app.post("/generate_sem_plan/", response_model=SEMOutput)
def generate_sem_plan(inputs: SEMInputs):
    """
    Generate SEM plan using Google Ads keyword ideas + Gemini clustering.
    """

    # 1) Fetch keywords from Google Ads
    try:
        keywords_data = get_keywords_from_google(
            customer_id=config.get("google_ads_customer_id", ""),
            seed_keywords=inputs.themes,
            page_url=inputs.brand_website or inputs.competitor_website,  # ✅ use competitor if brand missing
            location_ids=None,
            language_id="1000",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching keywords: {e}")

    # 2) Filter keywords (volume >= 500)
    keywords_data = [
        kw for kw in keywords_data if kw.get("search_volume") and kw["search_volume"] >= 500
    ]

    # Convert into KeywordFull objects
    keyword_objects: List[KeywordFull] = [
        KeywordFull(
            keyword=kw.get("keyword"),
            search_volume=kw.get("search_volume"),
            competition=kw.get("competition"),
            cpc_range=kw.get("cpc_range"),
        )
        for kw in keywords_data
    ]

    total_keywords = len(keyword_objects)
    total_volume = sum((k.search_volume or 0) for k in keyword_objects)

    # Average CPC
    cpc_midpoints = []
    for k in keyword_objects:
        if k.cpc_range:
            try:
                low, high = [float(p.strip().replace("$", "")) for p in k.cpc_range.split("-")]
                cpc_midpoints.append((low + high) / 2.0)
            except Exception:
                pass
    avg_cpc = round(sum(cpc_midpoints) / max(1, len(cpc_midpoints)), 2) if cpc_midpoints else 0.0

   
    # Build search ad groups with match type rules
    
    def suggest_match_types(group_name: str) -> List[str]:
        if "brand" in group_name.lower() or "competitor" in group_name.lower():
            return ["Exact", "Phrase"]
        elif "category" in group_name.lower():
            return ["Phrase", "Exact"]
        elif "informational" in group_name.lower():
            return ["Phrase", "Broad"]
        elif "location" in group_name.lower():
            return ["Exact", "Phrase"]
        return ["Exact"]

    brand_key = clean_domain(inputs.brand_website)
    competitor_key = clean_domain(inputs.competitor_website or "")

    search_groups: Dict[str, List[KeywordFull]] = {
        "Brand & Product Terms": [],
        "Category Terms": [],
        "Competitor Terms": [],
        "Informational Queries": [],
        "Location-based Queries": [],
    }

    for kw in keyword_objects:
        text = (kw.keyword or "").lower()
        if brand_key and brand_key in text:
            search_groups["Brand & Product Terms"].append(kw)
        elif competitor_key and competitor_key in text:
            search_groups["Competitor Terms"].append(kw)
        elif inputs.target_locations and any(
            loc.strip().lower() in text for loc in inputs.target_locations.split(",")
        ):
            search_groups["Location-based Queries"].append(kw)
        elif len(text.split()) >= 3:
            search_groups["Informational Queries"].append(kw)
        else:
            search_groups["Category Terms"].append(kw)

   
    # PMax themes with Gemini (fallback if not available)

    locations_list = [l.strip() for l in inputs.target_locations.split(",")] if inputs.target_locations else []
    pmax_map = generate_pmax_themes_llm([k.keyword for k in keyword_objects], locations_list)

    
    # Shopping CPC suggestions (ROI-driven)
   
    shopping_cpc: List[ShoppingCPCSuggestion] = []
    conversion_rate = 0.02
    total_budget = inputs.budget_allocations.cap + inputs.budget_allocations.bud + inputs.budget_allocations.pmax
    target_cpc = round((total_budget * conversion_rate) / max(1, total_volume), 2) if total_volume > 0 else 0.0

    for kw in keyword_objects:
        suggested = target_cpc
        if kw.cpc_range:
            try:
                low, high = [float(p.strip().replace("$", "")) for p in kw.cpc_range.split("-")]
                midpoint = (low + high) / 2.0
                suggested = round(min(midpoint, target_cpc), 2)
            except Exception:
                pass
        shopping_cpc.append(
            ShoppingCPCSuggestion(
                keyword=kw.keyword,
                search_volume=kw.search_volume,
                competition=kw.competition,
                suggested_cpc=suggested,
            )
        )

   
    # Final SEM Output
  
    return SEMOutput(
        brand=inputs.brand_website,
        competitor=inputs.competitor_website,
        locations=locations_list,
        budget_allocations=inputs.budget_allocations,
        total_budget=total_budget,
        total_keywords=total_keywords,
        total_volume=total_volume,
        avg_cpc=avg_cpc,
        themes=inputs.themes,
        searchAdGroups=search_groups,
        pmaxThemes=pmax_map,
        shoppingCPC=shopping_cpc,
    )
