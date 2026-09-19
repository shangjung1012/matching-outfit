from itertools import combinations, product
from typing import Literal
from uuid import uuid4

from app.schemas import ClothResult, OutfitRecommendation, OutfitScoreBreakdown, QuerySearchResult

NEUTRAL_COLORS = {
    "black", "white", "grey", "gray", "charcoal", "beige", "cream",
    "navy blue", "navy", "brown", "tan",
}
CLASHING_COLOR_PAIRS = {
    # 原本的規則
    frozenset(("orange", "green")),
    frozenset(("red", "green")),
    frozenset(("pink", "red")),
    frozenset(("purple", "orange")),

    # 新增：高對比配色
    frozenset(("blue", "orange")),
    frozenset(("purple", "yellow")),
    frozenset(("pink", "green")),
    frozenset(("purple", "green")),

    # 新增：雙高彩度組合
    frozenset(("red", "yellow")),
    frozenset(("green", "yellow")),
    frozenset(("orange", "pink")),
    frozenset(("red", "blue")),
}
STRICT_CONTEXT_TERMS = {
    "formal", "gala", "fine dining", "luxury restaurant", "wedding", "interview",
    "高級餐廳", "正式", "晚宴", "婚禮", "面試",
}
CASUAL_ARTICLE_TYPES = {"tshirts", "shorts", "track pants", "sweatshirts", "leggings"}
FORMAL_ARTICLE_TYPES = {"blazers", "shirts", "trousers", "dresses", "sarees", "waistcoat"}


def parse_color(color: str | None) -> tuple[str, str]:
    """Split a catalog colour label into its lightness modifier and base family."""
    normalized = (color or "").strip().lower()
    for modifier in ("light", "dark"):
        prefix = f"{modifier} "
        if normalized.startswith(prefix):
            return modifier, normalized[len(prefix):].strip()
    return "normal", normalized


def _color_pair_score(first: str | None, second: str | None) -> float:
    left_tone, left_family = parse_color(first)
    right_tone, right_family = parse_color(second)
    if not left_family or not right_family:
        return 0.65
    if left_tone == right_tone and left_family == right_family:
        return 0.86
    if left_family == right_family:
        return 0.90
    if left_family in NEUTRAL_COLORS or right_family in NEUTRAL_COLORS:
        return 0.95
    if frozenset((left_family, right_family)) in CLASHING_COLOR_PAIRS:
        modified_count = sum(tone != "normal" for tone in (left_tone, right_tone))
        if modified_count == 0:
            return 0.35
        if modified_count == 1:
            return 0.65
        return 0.72
    return 0.72


def _compatibility_score(items: list[ClothResult]) -> float:
    if len(items) == 1:
        return 0.82
    color_scores = [
        _color_pair_score(first.base_colour, second.base_colour)
        for first, second in combinations(items, 2)
    ]
    usages = {(item.usage or "").strip().lower() for item in items if item.usage}
    formality_consistency = 0.45 if {"formal", "casual"}.issubset(usages) else 1.0
    return 0.7 * (sum(color_scores) / len(color_scores)) + 0.3 * formality_consistency


def _context_fit_score(items: list[ClothResult], user_context: str) -> tuple[float, list[str]]:
    strict = any(term in user_context.lower() for term in STRICT_CONTEXT_TERMS)
    if not strict:
        return 0.85, ["Context treated as a light constraint"]
    penalties = 0.0
    formal_signals = 0
    for item in items:
        article_type = (item.article_type or "").strip().lower()
        usage = (item.usage or "").strip().lower()
        if article_type in CASUAL_ARTICLE_TYPES or usage == "casual":
            penalties += 0.22
        if article_type in FORMAL_ARTICLE_TYPES or usage == "formal":
            formal_signals += 1
    score = max(0.0, min(1.0, 0.72 + 0.12 * formal_signals - penalties))
    reasons = ["Strict-context formality gate applied"]
    if penalties:
        reasons.append("Casual garment penalty applied")
    return score, reasons


def _recommendation(
    kind: Literal["separates", "one_piece"],
    items: list[ClothResult],
    coverage_reason: str,
    user_context: str,
    direction_id: str | None = None,
) -> OutfitRecommendation:
    # A user-uploaded reference is fixed, not a search result. Its placeholder
    # similarity must not inflate or deflate the catalog candidate's relevance.
    catalog_items = [item for item in items if not item.is_reference]
    similarity = sum(item.similarity for item in catalog_items) / len(catalog_items)
    compatibility = _compatibility_score(items)
    context_fit, context_reasons = _context_fit_score(items, user_context)
    match_score = max(
        0.0,
        min(1.0, 0.5 * similarity + 0.3 * compatibility + 0.2 * context_fit),
    )
    references = list({reference.url: reference for item in items for reference in item.references}.values())
    preference_references = list(dict.fromkeys(
        sentence for item in items for sentence in item.preference_references
    ))
    return OutfitRecommendation(
        id=str(uuid4()),
        kind=kind,
        direction_id=direction_id,
        items=items,
        score=round(match_score, 4),
        score_breakdown=OutfitScoreBreakdown(
            fashion_clip=round(similarity, 4),
            compatibility=round(compatibility, 4),
            context_fit=round(context_fit, 4),
        ),
        reasons=[
            "FashionCLIP candidate relevance", coverage_reason,
            *context_reasons,
        ],
        references=references,
        preference_references=preference_references,
    )


def _within_outfit_budget(
    recommendation: OutfitRecommendation, outfit_budget_max: float | None
) -> bool:
    if outfit_budget_max is None:
        return True
    return sum(item.price for item in recommendation.items) <= outfit_budget_max


def rank_outfits(
    groups: list[QuerySearchResult],
    limit: int = 20,
    user_context: str = "",
    reference_item: ClothResult | None = None,
    outfit_budget_max: float | None = None,
) -> list[OutfitRecommendation]:
    pooled_by_zone: dict[str, dict[int, ClothResult]] = {}
    pooled_by_direction: dict[str, dict[str, dict[int, ClothResult]]] = {}
    one_piece_directions: dict[int, tuple[str, float]] = {}
    for group in groups:
        zone_pool = pooled_by_zone.setdefault(group.query.garment_zone, {})
        for item in group.clothes:
            current = zone_pool.get(item.id)
            if current is None:
                zone_pool[item.id] = item
                continue
            preferred = item if item.similarity > current.similarity else current
            zone_pool[item.id] = preferred
        direction_id = group.query.direction_id
        if direction_id and group.query.garment_zone == "one_piece":
            for item in group.clothes:
                current = one_piece_directions.get(item.id)
                if current is None or item.similarity > current[1]:
                    one_piece_directions[item.id] = (direction_id, item.similarity)
        if direction_id and group.query.garment_zone in {"upper_body", "lower_body"}:
            direction_pool = pooled_by_direction.setdefault(direction_id, {}).setdefault(
                group.query.garment_zone, {}
            )
            for item in group.clothes:
                current = direction_pool.get(item.id)
                if current is None or item.similarity > current.similarity:
                    direction_pool[item.id] = item
    by_zone = {
        zone: sorted(pool.values(), key=lambda item: item.similarity, reverse=True)[:40]
        for zone, pool in pooled_by_zone.items()
    }
    recommendations: list[OutfitRecommendation] = []
    if reference_item is not None:
        counterpart_zone = (
            "lower_body" if reference_item.garment_zone == "upper_body" else "upper_body"
        )
        for candidate in by_zone.get(counterpart_zone, []):
            items = (
                [reference_item, candidate]
                if reference_item.garment_zone == "upper_body"
                else [candidate, reference_item]
            )
            recommendations.append(
                _recommendation(
                    "separates",
                    items,
                    "User-uploaded garment paired with catalog candidate",
                    user_context,
                )
            )
        return _balanced_direction_candidates(
            sorted(
                (
                    result for result in recommendations
                    if _within_outfit_budget(result, outfit_budget_max)
                ),
                key=lambda result: result.score,
                reverse=True,
            ),
            limit,
        )
    matched_directions = {
        direction_id: pools
        for direction_id, pools in pooled_by_direction.items()
        if pools.get("upper_body") and pools.get("lower_body")
    }
    if matched_directions:
        for direction_id, pools in matched_directions.items():
            uppers = sorted(
                pools["upper_body"].values(), key=lambda item: item.similarity, reverse=True
            )[:20]
            lowers = sorted(
                pools["lower_body"].values(), key=lambda item: item.similarity, reverse=True
            )[:20]
            for upper, lower in product(uppers, lowers):
                items = [upper, lower]
                recommendations.append(
                    _recommendation(
                        "separates",
                        items,
                        f"Matched styling direction: {direction_id}",
                        user_context,
                        direction_id,
                    )
                )
    else:
        # Backward-compatible fallback for manually edited or older query plans.
        for upper, lower in product(
            by_zone.get("upper_body", []), by_zone.get("lower_body", [])
        ):
            items = [upper, lower]
            recommendations.append(
                _recommendation(
                    "separates", items,
                    "Upper and lower body candidate coverage", user_context,
                )
            )
    for item in by_zone.get("one_piece", []):
        items = [item]
        direction_id = one_piece_directions.get(item.id, (None, 0.0))[0]
        recommendations.append(
            _recommendation(
                "one_piece", items,
                "One-piece candidate coverage", user_context, direction_id,
            )
        )
    # Price is a whole-outfit gate, so apply it only after garments have been
    # combined rather than prematurely excluding an otherwise useful item.
    recommendations = [
        result for result in recommendations
        if _within_outfit_budget(result, outfit_budget_max)
    ]
    ranked = sorted(recommendations, key=lambda result: result.score, reverse=True)
    separates = [result for result in ranked if result.kind == "separates"]
    one_pieces = [result for result in ranked if result.kind == "one_piece"]
    quality_floor = ranked[0].score - 0.12 if ranked else 0.0
    viable_separates = [result for result in separates if result.score >= quality_floor]
    viable_one_pieces = [result for result in one_pieces if result.score >= quality_floor]
    if limit >= 2 and viable_separates and viable_one_pieces:
        one_piece_limit = min(limit // 2, len(viable_one_pieces))
        separates_limit = min(limit - one_piece_limit, len(viable_separates))
        balanced_pool = [
            *_balanced_direction_candidates(viable_separates, separates_limit),
            *viable_one_pieces[:one_piece_limit],
        ]
        if len(balanced_pool) < limit:
            balanced_pool.extend(
                result
                for result in ranked
                if result not in balanced_pool
            )
        return sorted(balanced_pool, key=lambda result: result.score, reverse=True)[:limit]
    return _balanced_direction_candidates(ranked, limit)


def _balanced_direction_candidates(
    recommendations: list[OutfitRecommendation], limit: int
) -> list[OutfitRecommendation]:
    """Keep strong candidates from every separates direction before global ranking."""
    if limit <= 0:
        return []
    by_direction: dict[str, list[OutfitRecommendation]] = {}
    without_direction: list[OutfitRecommendation] = []
    for recommendation in recommendations:
        if recommendation.kind == "separates" and recommendation.direction_id:
            by_direction.setdefault(recommendation.direction_id, []).append(recommendation)
        else:
            without_direction.append(recommendation)
    if len(by_direction) < 2:
        return recommendations[:limit]

    ordered_directions = sorted(
        by_direction,
        key=lambda direction: by_direction[direction][0].score,
        reverse=True,
    )
    selected: list[OutfitRecommendation] = []
    selected_ids: set[str] = set()
    base_quota, extra = divmod(limit, len(ordered_directions))
    for index, direction in enumerate(ordered_directions):
        quota = base_quota + (1 if index < extra else 0)
        for recommendation in by_direction[direction][:quota]:
            selected.append(recommendation)
            selected_ids.add(recommendation.id)

    if len(selected) < limit:
        selected.extend(
            recommendation
            for recommendation in recommendations
            if recommendation.id not in selected_ids
        )
    return sorted(selected[:limit], key=lambda result: result.score, reverse=True)


def select_diverse(
    recommendations: list[OutfitRecommendation], limit: int
) -> list[OutfitRecommendation]:
    selected: list[OutfitRecommendation] = []
    used_item_ids: set[int] = set()
    used_assets: set[str] = set()
    used_outfit_styles: set[tuple] = set()
    used_color_profiles: set[tuple] = set()
    used_combinations: set[tuple[str, ...]] = set()

    def normalized(value: str | None) -> str:
        return (value or "unknown").strip().lower()

    def identities(recommendation: OutfitRecommendation) -> set[str]:
        return {
            normalized(item.image_path or item.image_url)
            for item in recommendation.items
            if not item.is_reference
        }

    def style_signature(recommendation: OutfitRecommendation) -> tuple:
        return (
            recommendation.kind,
            *sorted(
                (
                    item.garment_zone,
                    normalized(item.article_type),
                    normalized(item.base_colour),
                )
                for item in recommendation.items
            ),
        )

    def color_profile(recommendation: OutfitRecommendation) -> tuple:
        return tuple(
            sorted(
                (item.garment_zone, normalized(item.base_colour))
                for item in recommendation.items
            )
        )

    def add(recommendation: OutfitRecommendation) -> None:
        selected.append(recommendation)
        used_item_ids.update(item.id for item in recommendation.items if not item.is_reference)
        used_assets.update(identities(recommendation))
        used_outfit_styles.add(style_signature(recommendation))
        used_color_profiles.add(color_profile(recommendation))
        used_combinations.add(tuple(sorted(identities(recommendation))))

    best_score = max((recommendation.score for recommendation in recommendations), default=0.0)
    quality_floor = best_score - 0.10

    def is_suitable(recommendation: OutfitRecommendation) -> bool:
        review = recommendation.aesthetic_review
        return recommendation.score >= quality_floor and not (
            review is not None and review.fatal_issues
        )

    suitable_counts = {
        kind: sum(
            recommendation.kind == kind and is_suitable(recommendation)
            for recommendation in recommendations
        )
        for kind in ("separates", "one_piece")
    }
    if limit >= 2 and all(suitable_counts.values()):
        one_piece_target = min(limit // 2, suitable_counts["one_piece"])
        separates_target = min(limit - one_piece_target, suitable_counts["separates"])
        remaining = limit - separates_target - one_piece_target
        if remaining:
            extra_one_piece = min(
                remaining, suitable_counts["one_piece"] - one_piece_target
            )
            one_piece_target += extra_one_piece
            remaining -= extra_one_piece
        separates_target += min(
            remaining, suitable_counts["separates"] - separates_target
        )
        kind_targets = {
            "separates": separates_target,
            "one_piece": one_piece_target,
        }
    else:
        kind_targets = {
            "separates": min(limit, suitable_counts["separates"]),
            "one_piece": min(limit, suitable_counts["one_piece"]),
        }
    available_kinds = {recommendation.kind for recommendation in recommendations}
    kind_counts = {kind: 0 for kind in available_kinds}

    def within_kind_target(recommendation: OutfitRecommendation) -> bool:
        return kind_counts[recommendation.kind] < kind_targets[recommendation.kind]

    def add_with_count(recommendation: OutfitRecommendation) -> None:
        add(recommendation)
        kind_counts[recommendation.kind] += 1

    # Give every viable A-E styling direction a chance to reach the visual reviewer.
    # This is coverage, not a final-result quota: the reviewer may still reject it.
    separates_directions = sorted(
        {
            recommendation.direction_id
            for recommendation in recommendations
            if recommendation.kind == "separates"
            and recommendation.direction_id
            and is_suitable(recommendation)
        }
    )
    if len(separates_directions) > 1:
        for direction_id in separates_directions:
            if len(selected) >= limit or not within_kind_target(
                next(
                    recommendation
                    for recommendation in recommendations
                    if recommendation.direction_id == direction_id
                    and recommendation.kind == "separates"
                    and is_suitable(recommendation)
                )
            ):
                break
            candidates = [
                recommendation
                for recommendation in recommendations
                if recommendation.direction_id == direction_id
                and recommendation.kind == "separates"
                and is_suitable(recommendation)
                and tuple(sorted(identities(recommendation))) not in used_combinations
            ]
            if not candidates:
                continue
            non_repeating = [
                recommendation
                for recommendation in candidates
                if {item.id for item in recommendation.items if not item.is_reference}.isdisjoint(used_item_ids)
                and identities(recommendation).isdisjoint(used_assets)
            ]
            add_with_count((non_repeating or candidates)[0])

    # Prefer different products, images, garment/color combinations, and color profiles.
    # Later passes relax one condition at a time only when the catalog cannot fill the limit.
    for require_new_colors, require_new_items in ((True, True), (False, True), (False, False)):
        for recommendation in recommendations:
            if recommendation in selected:
                continue
            if not is_suitable(recommendation):
                continue
            if not within_kind_target(recommendation):
                continue
            item_ids = {item.id for item in recommendation.items if not item.is_reference}
            if require_new_items and (
                not item_ids.isdisjoint(used_item_ids)
                or not identities(recommendation).isdisjoint(used_assets)
            ):
                continue
            if style_signature(recommendation) in used_outfit_styles:
                continue
            if require_new_colors and color_profile(recommendation) in used_color_profiles:
                continue
            add_with_count(recommendation)
            if len(selected) >= limit:
                return selected
    # Satisfy the separates/one-piece target even if a repeated style profile is needed.
    for recommendation in recommendations:
        combination = tuple(sorted(identities(recommendation)))
        if (
            recommendation not in selected
            and combination not in used_combinations
            and within_kind_target(recommendation)
            and is_suitable(recommendation)
        ):
            add_with_count(recommendation)
        if len(selected) >= limit:
            return selected
    # If one category lacks enough suitable items, let suitable items from the other fill the gap.
    for recommendation in recommendations:
        combination = tuple(sorted(identities(recommendation)))
        if (
            recommendation not in selected
            and combination not in used_combinations
            and is_suitable(recommendation)
        ):
            add_with_count(recommendation)
        if len(selected) >= limit:
            return selected
    # Only dip below the relative quality floor when there are not enough suitable results.
    for recommendation in recommendations:
        combination = tuple(sorted(identities(recommendation)))
        review = recommendation.aesthetic_review
        if (
            recommendation not in selected
            and combination not in used_combinations
            and not (review is not None and review.fatal_issues)
        ):
            add_with_count(recommendation)
        if len(selected) >= limit:
            return selected
    # Fatal candidates are a last resort to preserve the requested result count.
    for recommendation in recommendations:
        combination = tuple(sorted(identities(recommendation)))
        if recommendation not in selected and combination not in used_combinations:
            add_with_count(recommendation)
        if len(selected) >= limit:
            return selected
    return selected
