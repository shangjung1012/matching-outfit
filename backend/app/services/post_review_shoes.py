"""Attach conservative shoe retrieval results after the clothing ranking is final."""

from sqlalchemy.orm import Session

from app.models.user_preference import UserHardRule
from app.schemas import (
    OutfitRecommendation,
    RequirementSummary,
    ShoeRetrievalDebug,
    ShoeSpec,
    ShoeSuggestion,
)
from app.services.catalog_search import search_shoe_candidates


_SAFE_COLOURS = ("black", "white", "off-white", "light grey", "dark grey", "beige", "dark brown", "navy")
_NEUTRAL_COLOURS = {"black", "white", "off-white", "grey", "gray", "beige", "brown", "navy", "khaki", "camel", "tan"}
_COLOUR_WORDS = (
    ("black", ("black", "黑色")),
    ("white", ("white", "白色")),
    ("off-white", ("off-white", "off white", "米白", "象牙白")),
    ("light grey", ("light grey", "light gray", "淺灰")),
    ("dark grey", ("dark grey", "dark gray", "深灰")),
    ("beige", ("beige", "米色")),
    ("dark brown", ("dark brown", "深棕", "深咖")),
    ("navy", ("navy", "深藍")),
)


def _colour_family(value: str | None) -> str:
    text = (value or "").lower().replace("-", " ")
    if "black" in text or "黑" in text:
        return "black"
    if "navy" in text or "深藍" in text:
        return "navy"
    if "grey" in text or "gray" in text or "灰" in text:
        return "grey"
    if "white" in text or "白" in text:
        return "off-white" if "off" in text or "米白" in text else "white"
    if "beige" in text or "米色" in text:
        return "beige"
    if any(word in text for word in ("brown", "棕", "咖", "camel", "tan", "khaki", "卡其")):
        return "brown"
    return ""


def _explicit_shoe_colour(user_input: str) -> str:
    text = user_input.lower()
    if not any(term in text for term in ("shoe", "shoes", "鞋", "球鞋", "樂福", "靴")):
        return ""
    return next((colour for colour, words in _COLOUR_WORDS if any(word in text for word in words)), "")


def choose_shoe_color(
    outfit: OutfitRecommendation,
    requirements: RequirementSummary | None,
    user_input: str,
) -> str:
    """Small, explainable neutral-colour policy for post-review footwear."""
    explicit = _explicit_shoe_colour(user_input)
    if explicit:
        return explicit

    lower_colours = [_colour_family(item.base_colour) for item in outfit.items if item.garment_zone in {"lower_body", "one_piece"}]
    outfit_colours = [_colour_family(item.base_colour) for item in outfit.items]
    colours = [colour for colour in [*lower_colours, *outfit_colours] if colour]
    formality = " ".join(requirements.formalities).lower() if requirements else ""
    is_formal = "formal" in formality or "正式" in formality
    warm_earth = any(colour in {"beige", "brown"} for colour in colours)
    dark = bool(colours) and all(colour in {"black", "navy", "grey", "brown"} for colour in colours)
    light = bool(colours) and all(colour in {"white", "off-white", "beige", "grey"} for colour in colours)
    existing_neutral = next((colour for colour in colours if colour in _NEUTRAL_COLOURS), "")
    has_strong_colour = any(
        item.base_colour and not _colour_family(item.base_colour)
        for item in outfit.items
    )

    if is_formal:
        if warm_earth:
            return "dark brown"
        if dark:
            return "black"
        return "beige" if light else "black"
    if has_strong_colour:
        return existing_neutral or "off-white"
    if warm_earth:
        return "beige"
    if dark:
        return "black"
    return "off-white"


def _prepared_spec(outfit: OutfitRecommendation, spec: ShoeSpec, requirements: RequirementSummary | None, user_input: str) -> ShoeSpec:
    colour = choose_shoe_color(outfit, requirements, user_input)
    if _colour_family(spec.shoe_query) == _colour_family(colour):
        query = " ".join(spec.shoe_query.split()[:12])
    else:
        terms = [colour, spec.shoe_type, spec.material_appearance, spec.profile]
        query = " ".join(" ".join(terms).split()[:12])
    return spec.model_copy(update={"shoe_color": colour, "shoe_query": query})


def attach_post_review_shoes(
    db: Session,
    outfits: list[OutfitRecommendation],
    shoe_specs: dict[str, ShoeSpec],
    *,
    audience: str | None,
    hard: UserHardRule | None,
    requirements: RequirementSummary | None = None,
    user_input: str = "",
    include_debug: bool = False,
) -> list[OutfitRecommendation] | tuple[list[OutfitRecommendation], list[ShoeRetrievalDebug]]:
    """Never change ranking: leave an outfit untouched when its shoe cannot be retrieved."""
    indexed = [
        (index, outfit, shoe_specs.get(outfit.id))
        for index, outfit in enumerate(outfits)
        if shoe_specs.get(outfit.id) is not None
        and shoe_specs[outfit.id].shoe_type.strip()
        and shoe_specs[outfit.id].shoe_query.strip()
    ]
    if not indexed:
        return (outfits, []) if include_debug else outfits

    # Query Planner has already produced the retrieval-ready sentence for each
    # A-G direction. Search it verbatim after the reviewer selects the winners.
    original_specs = [spec for _, _, spec in indexed]
    prepared = original_specs
    # Repeated direction queries should share one ranked candidate list.  This
    # avoids running identical vector searches and lets later outfits advance
    # to the next unused shoe in that same ranking.
    unique_specs_by_query: dict[str, ShoeSpec] = {}
    for spec in prepared:
        unique_specs_by_query.setdefault(spec.shoe_query.strip().lower(), spec)
    unique_specs = list(unique_specs_by_query.values())
    try:
        unique_candidate_groups = search_shoe_candidates(
            db,
            unique_specs,
            audience=audience,
            hard=hard,
            top_k=max(5, len(indexed)),
        )
    except Exception:
        # Shoes are an optional post-review enhancement, never a reason to
        # discard an otherwise valid clothing recommendation.
        return (outfits, []) if include_debug else outfits
    candidates_by_query = {
        spec.shoe_query.strip().lower(): candidates
        for spec, candidates in zip(unique_specs, unique_candidate_groups, strict=True)
    }
    updated = list(outfits)
    debug_rows: list[ShoeRetrievalDebug] = []
    used_shoe_ids: set[int] = set()
    for ((index, outfit, _), original_spec, spec) in zip(
        indexed, original_specs, prepared, strict=True
    ):
        candidates = candidates_by_query.get(spec.shoe_query.strip().lower(), [])
        outfit_item_ids = {item.id for item in outfit.items}
        shoe = next(
            (
                candidate
                for candidate in candidates
                if candidate.id not in used_shoe_ids
                and candidate.id not in outfit_item_ids
            ),
            None,
        )
        debug_rows.append(ShoeRetrievalDebug(
            outfit_id=outfit.id,
            original_query=original_spec.shoe_query,
            query=spec.shoe_query,
            requested_type=spec.shoe_type,
            requested_color=spec.shoe_color,
            candidates=candidates,
            selected_item_id=shoe.id if shoe is not None else None,
        ))
        if shoe is None:
            continue
        used_shoe_ids.add(shoe.id)
        updated[index] = outfit.model_copy(update={
            "items": [*outfit.items, shoe],
            "shoe_suggestion": ShoeSuggestion(
                query=spec.shoe_query,
                item_id=shoe.id,
                retrieval_score=shoe.similarity,
                added_after_review=True,
            ),
        })
    return (updated, debug_rows) if include_debug else updated
