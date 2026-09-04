from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.user_preference import UserPreference
from app.schemas import QueryDraft
from app.schemas.styling import FormulaCatalogMatch, OutfitFormula
from app.services.catalog_search import search_catalog
from app.services.outfit_ranker import rank_outfits


def formula_queries(formula: OutfitFormula) -> list[QueryDraft]:
    specs_by_zone = {spec.garment_zone: spec for spec in formula.search_specs}
    if len(specs_by_zone) != len(formula.search_specs):
        raise ValueError(f"Outfit formula '{formula.name}' contains duplicate garment zones")
    zones = set(specs_by_zone)
    valid_separates = {"upper_body", "lower_body"}.issubset(zones) and "one_piece" not in zones
    valid_one_piece = "one_piece" in zones and not zones.intersection({"upper_body", "lower_body"})
    if not (valid_separates or valid_one_piece):
        raise ValueError(
            f"Outfit formula '{formula.name}' must use upper+lower or one_piece, not both"
        )
    queries: list[QueryDraft] = []
    for spec in formula.search_specs:
        if not any(character.isascii() and character.isalpha() for character in spec.query):
            raise ValueError(
                f"FashionCLIP query for {spec.garment_zone} must contain an English visual description"
            )
        queries.append(
            QueryDraft(
                id=str(uuid4()),
                text=spec.query.strip(),
                garment_zone=spec.garment_zone,
                rationale=spec.rationale,
            )
        )
    return queries


def search_formula_catalog(
    db: Session,
    formula: OutfitFormula,
    *,
    candidates_per_zone: int,
    outfits_per_formula: int,
    preference: UserPreference | None,
    audience: str | None = None,
) -> FormulaCatalogMatch:
    groups = search_catalog(
        db, formula_queries(formula), candidates_per_zone, audience=audience
    )
    return FormulaCatalogMatch(
        formula=formula,
        recommendations=rank_outfits(
            groups,
            outfits_per_formula,
            preference,
            user_context=f"{formula.context_fit} {formula.why_it_works}",
        ),
    )
