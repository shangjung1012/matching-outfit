from pathlib import Path

import pytest

import single_inference


def test_cli_requires_at_least_one_reference() -> None:
    with pytest.raises(SystemExit):
        single_inference.parse_args(
            ["--person", "person.png", "--output", "out.png"]
        )


def test_cli_rejects_overall_with_upper_or_lower() -> None:
    with pytest.raises(SystemExit):
        single_inference.parse_args(
            [
                "--person",
                "person.png",
                "--output",
                "out.png",
                "--overall",
                "dress.png",
                "--upper",
                "top.png",
            ]
        )


def test_cli_collects_canonical_reference_paths() -> None:
    args = single_inference.parse_args(
        [
            "--person",
            "person.png",
            "--output",
            "out.png",
            "--bag",
            "bag.png",
            "--lower",
            "pants.png",
        ]
    )

    assert args.person == Path("person.png")
    assert args.output == Path("out.png")
    assert args.upper is None
    assert args.lower == Path("pants.png")
    assert args.overall is None
    assert args.shoe is None
    assert args.bag == Path("bag.png")
