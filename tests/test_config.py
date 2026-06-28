from editorial.config import load_publication_config
def test_load_bis_config():
    config = load_publication_config("examples/bis/publication.yaml")
    assert config.publication.name == "BIS Newsletter"
    assert len(config.providers) == 1
    assert config.providers[0].type == "static"
    assert len(config.providers[0].settings["articles"]) == 2
