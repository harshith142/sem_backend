# google_ads.py
from google.ads.googleads.client import GoogleAdsClient


def get_keywords_from_google(customer_id: str,
                             seed_keywords=None,
                             page_url=None,
                             location_ids=None,
                             language_id="1000"):
    """
    Calls KeywordPlanIdeaService to generate keyword ideas.
    Returns a list of dicts with keys:
      - keyword
      - search_volume
      - competition
      - match_types
      - cpc_range
    """

    client = GoogleAdsClient.load_from_storage("google_ads.yaml")
    service = client.get_service("KeywordPlanIdeaService")

    request = client.get_type("GenerateKeywordIdeasRequest")
    request.customer_id = customer_id
    request.language = f"languageConstants/{language_id}"

    if location_ids:
        request.geo_target_constants.extend([f"geoTargetConstants/{loc}" for loc in location_ids])

    if seed_keywords:
        request.keyword_seed.keywords.extend(seed_keywords)

    if page_url:
        request.url_seed.url = page_url

    response = service.generate_keyword_ideas(request=request)

    keywords = []
    for idea in response:
        metrics = idea.keyword_idea_metrics
        # safe extraction of bids (micros -> currency)
        low_bid = (metrics.low_top_of_page_bid_micros / 1e6) if getattr(metrics, "low_top_of_page_bid_micros", None) else None
        high_bid = (metrics.high_top_of_page_bid_micros / 1e6) if getattr(metrics, "high_top_of_page_bid_micros", None) else None

        cpc_range = None
        if low_bid and high_bid:
            cpc_range = f"${low_bid:.2f} - ${high_bid:.2f}"

        keywords.append({
            "keyword": idea.text,
            "search_volume": int(metrics.avg_monthly_searches) if getattr(metrics, "avg_monthly_searches", None) is not None else None,
            "competition": metrics.competition.name if getattr(metrics, "competition", None) else None,
            "match_types": ["Exact", "Phrase"],   # default placeholder
            "cpc_range": cpc_range,
            "top_of_page_bid_low": low_bid,
            "top_of_page_bid_high": high_bid,
        })

    return keywords
