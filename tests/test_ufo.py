from pathlib import Path

from app.geo import bbox
from app.sources import ufo

FX = Path(__file__).parent.parent / "app" / "demo" / "data"
BOX = bbox(52.9594, 5.9189, 60)


def test_nuforc_layout():
    feats = ufo.parse((FX / "ufo.csv").read_text(), BOX)
    # Texas is outside the region; the "wy" row is a mis-geocoded US report.
    assert len(feats) == 4
    props = [f["properties"] for f in feats]
    assert props[0]["time"] == "2011-03-12T19:39:00"           # newest first
    assert props[0]["title"] == "UFO: formatie"
    assert "Heerenveen (netherlands)" in props[0]["detail"]
    assert "not on the same height, moving" in props[0]["detail"]  # &#44 unescaped
    joure = next(p for p in props if "Joure" in p["detail"])
    assert joure["time"] == "2009-07-04T00:00:00" and joure["category"] == "disk"   # 24:00 handled
    assert "duur 30 sec" in joure["detail"]


def test_headered_csv():
    text = (
        "id,date,location,shape,description,latitude,longitude,url\n"
        "a1,2024-06-01 23:10,Sneek,triangle,Three lights,53.03,5.66,https://example.org/a1\n"
        "a2,2024-06-02,Leeuwarden,,No shape given,53.20,5.80,javascript:alert(1)\n"
        "a3,2024-06-03,Nowhere,light,No coordinates,,,\n"
    )
    feats = ufo.parse(text, BOX)
    assert [f["properties"]["id"] for f in feats] == ["ufo:a2", "ufo:a1"]
    a1 = feats[1]["properties"]
    assert a1["title"] == "UFO: driehoek" and a1["url"] == "https://example.org/a1"
    assert a1["time"] == "2024-06-01T23:10:00"
    a2 = feats[0]["properties"]
    assert a2["title"] == "UFO" and a2["category"] == "unknown" and "url" not in a2
