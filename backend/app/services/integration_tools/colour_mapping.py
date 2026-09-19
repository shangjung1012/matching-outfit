"""Mappings between colour families shown in preferences and catalog values."""

AVOID_COLOUR_VALUES = {
    "Blue": {"Blue", "Dark Blue", "Light Blue", "Other Blue"},
    "Green": {"Green", "Dark Green", "Light Green", "Other Green", "Greenish Khaki"},
    "Red": {"Red", "Dark Red", "Light Red", "Other Red"},
    "Pink": {"Pink", "Dark Pink", "Light Pink", "Other Pink"},
    "Purple": {"Purple", "Dark Purple", "Light Purple", "Other Purple"},
    "Orange": {"Orange", "Dark Orange", "Light Orange", "Other Orange"},
    "Yellow": {"Yellow", "Dark Yellow", "Light Yellow", "Other Yellow", "Yellowish Brown"},
    "Turquoise": {"Turquoise", "Dark Turquoise", "Light Turquoise", "Other Turquoise"},
    "Beige": {"Beige", "Dark Beige", "Light Beige", "Greyish Beige"},
    "Grey": {"Grey", "Dark Grey", "Light Grey"},
    "White": {"White", "Off White"},
    "Black": {"Black"},
    "Metallic": {"Gold", "Silver", "Bronze/Copper"},
}

_FAMILY_BY_NORMALIZED_NAME = {
    family.casefold(): values for family, values in AVOID_COLOUR_VALUES.items()
}


def expand_avoid_colours(colours: list[str]) -> list[str]:
    """Expand supported colour families to exact ``clothes.base_colour`` values."""
    expanded: set[str] = set()
    for colour in colours:
        normalized = colour.strip().casefold()
        if values := _FAMILY_BY_NORMALIZED_NAME.get(normalized):
            expanded.update(values)
    return sorted(expanded, key=str.casefold)
