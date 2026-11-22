import json

from tahoe_snow import avybundle

PHOTO = lambda name: {"type": "image", "url": {"thumbnail": f"https://media/{name}-thumbnail.jpg", "large": f"https://media/{name}-large.jpg"}}
PRODUCT = {"weather_data": {"weather_product_id": 77},
           "forecast_avalanche_problems": [{"media": PHOTO("slab")}, {"media": {"type": "video", "url": {"thumbnail": "https://media/v.jpg"}}}],
           "media": [PHOTO("slab"), {"type": "video", "url": {"thumbnail": "https://media/v.jpg"}}] + [PHOTO(f"shot{n}") for n in range(12)]}


def answers(url):
    if url.endswith("/map-layer/SAC"):
        return {"features": [{"id": 5, "properties": {"name": "Central"}}]}
    if "center_id=SAC" in url:
        return PRODUCT
    if url.endswith("/product/77"):
        return {"weather_discussion": "Cold."}
    raise OSError("down")


def test_a_forecasts_photographs_are_its_problems_and_its_first_few_without_repeats_or_videos():
    found = avybundle.photos_of(PRODUCT)
    assert found[0] == "https://media/slab-thumbnail.jpg" and len(found) == avybundle.GALLERY
    assert not any("v.jpg" in url for url in found) and len(set(found)) == len(found)


def test_every_answer_is_kept_under_the_address_the_page_asks_at_and_a_center_that_is_down_is_left_out():
    found = avybundle.gather(answers)
    assert list(found["entries"]) == [f"{avybundle.API}/products/map-layer/SAC", f"{avybundle.API}/product?type=forecast&center_id=SAC&zone_id=5",
                                      f"{avybundle.API}/product/77"]
    assert found["photos"] == avybundle.photos_of(PRODUCT)


def test_the_file_is_rewritten_only_when_a_forecast_changes(tmp_path, monkeypatch):
    monkeypatch.setattr(avybundle, "get", answers)
    assert avybundle.main(str(tmp_path)) == 0
    first = json.loads((tmp_path / "bundle.json").read_text())
    assert avybundle.main(str(tmp_path)) == 0
    assert json.loads((tmp_path / "bundle.json").read_text())["built"] == first["built"] and len(first["entries"]) == 3
