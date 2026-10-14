from matchwise.teams import canonical

KNOWN = {"Man United", "Tottenham", "Bayern Munich", "Real Madrid"}


def test_identical_name_passes_through():
    assert canonical("Real Madrid", KNOWN) == "Real Madrid"


def test_alias_maps_to_football_data_name():
    assert canonical("Man Utd", KNOWN) == "Man United"
    assert canonical("FC Bayern München", KNOWN) == "Bayern Munich"


def test_unknown_name_is_not_guessed():
    assert canonical("Manchester Utd FC", KNOWN) is None
    # An alias whose target isn't in this league is rejected too.
    assert canonical("Internazionale", KNOWN) is None
