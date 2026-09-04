import numpy as np

from scripts.curate_catalog import parse_quotas, percentile_scale, select_balanced


def test_parse_quotas() -> None:
    assert parse_quotas("upper_body=10,lower_body=8") == {
        "upper_body": 10,
        "lower_body": 8,
    }


def test_percentile_scale_handles_identical_values() -> None:
    result = percentile_scale(np.asarray([1.0, 1.0, 1.0], dtype=np.float32))
    assert np.allclose(result, [0.5, 0.5, 0.5])


def test_balanced_selection_removes_duplicates_and_preserves_color_variety() -> None:
    rows = [
        {"id": "1", "garment_zone": "upper_body", "baseColour": "Black", "articleType": "Tshirts"},
        {"id": "2", "garment_zone": "upper_body", "baseColour": "Black", "articleType": "Tshirts"},
        {"id": "3", "garment_zone": "upper_body", "baseColour": "White", "articleType": "Shirts"},
        {"id": "4", "garment_zone": "lower_body", "baseColour": "Beige", "articleType": "Trousers"},
    ]
    embeddings = np.asarray(
        [
            [1.0, 0.0],
            [1.0, 0.0],
            [0.0, 1.0],
            [0.7, 0.7],
        ],
        dtype=np.float32,
    )
    embeddings /= np.linalg.norm(embeddings, axis=1, keepdims=True)
    scores = np.asarray([0.95, 0.90, 0.80, 0.85], dtype=np.float32)

    selected = select_balanced(
        rows,
        embeddings,
        scores,
        {"upper_body": 2, "lower_body": 1},
        duplicate_threshold=0.985,
        color_cap_ratio=0.5,
        article_cap_ratio=0.5,
    )

    assert {rows[index]["id"] for index in selected} == {"1", "3", "4"}
