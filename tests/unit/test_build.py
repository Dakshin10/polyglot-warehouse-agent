from pwa.transform.clean import parse_credits_info, safe_literal_eval


def test_parse_credits_info_director_and_lead_actor():
    """Director extraction picks first job=='Director', lead actor is order==0, cast_size matches."""
    cast_raw = "[{'id': 31, 'name': 'Tom Hanks', 'order': 0, 'gender': 2}, {'id': 1289, 'name': 'Tim Allen', 'order': 1, 'gender': 2}]"
    crew_raw = "[{'id': 7879, 'name': 'John Lasseter', 'job': 'Director', 'gender': 2}, {'id': 1284, 'name': 'Bonnie Arnold', 'job': 'Producer'}]"

    cast_parsed = safe_literal_eval(cast_raw)
    crew_parsed = safe_literal_eval(crew_raw)

    info = parse_credits_info(cast_parsed, crew_parsed)

    assert info["director_name"] == "John Lasseter"
    assert info["director_gender"] == 2
    assert info["lead_actor_name"] == "Tom Hanks"
    assert info["second_actor_name"] == "Tim Allen"
    assert info["producer_name"] == "Bonnie Arnold"
    assert info["cast_size"] == 2
    assert info["crew_size"] == 2
