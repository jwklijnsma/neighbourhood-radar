"""Sample payloads for charging points, DRIPs, RWS water levels and Overpass."""
from __future__ import annotations

import base64
import gzip
import json
import struct
import zlib


def ocpi_locations() -> bytes:
    locs = [
        {   # Heerenveen, fast, one free
            "id": "NLLOC001", "publish": True, "name": "Fastned Heerenveen", "address": "Kanaalweg 1",
            "city": "Heerenveen", "coordinates": {"latitude": "52.9650", "longitude": "5.9300"},
            "operator": {"name": "Fastned"}, "last_updated": "2026-11-07T11:58:00Z",
            "evses": [
                {"status": "AVAILABLE", "connectors": [{"max_electric_power": 300000}]},
                {"status": "CHARGING", "connectors": [{"max_electric_power": 300000}]},
            ],
        },
        {   # all occupied, slow
            "id": "NLLOC002", "name": "", "address": "Dracht 10", "city": "Heerenveen",
            "coordinates": {"latitude": "52.9600", "longitude": "5.9200"}, "operator": {"name": "Vattenfall"},
            "evses": [{"status": "CHARGING", "connectors": [{"max_electric_power": 11000}]}],
        },
        {   # unknown status
            "id": "NLLOC003", "name": "Joure centrum", "coordinates": {"latitude": "52.9650", "longitude": "5.8000"},
            "evses": [{"status": "UNKNOWN", "connectors": [{"max_electric_power": 22000}]}],
        },
        {   # only removed EVSEs -> dropped
            "id": "NLLOC004", "coordinates": {"latitude": "52.9700", "longitude": "5.9100"},
            "evses": [{"status": "REMOVED"}],
        },
        {   # not published -> dropped
            "id": "NLLOC005", "publish": False, "coordinates": {"latitude": "52.9700", "longitude": "5.9100"},
            "evses": [{"status": "AVAILABLE"}],
        },
        {   # Tesla under US country code but in region -> kept (select on position)
            "id": "NLLOC006", "country_code": "US", "name": "Tesla Supercharger Heerenveen",
            "coordinates": {"latitude": "52.9500", "longitude": "5.9500"}, "operator": {"name": "Tesla"},
            "evses": [{"status": "OUTOFORDER", "connectors": [{"max_electric_power": 250000}]}],
        },
        {   # Rotterdam -> outside region
            "id": "NLLOC007", "coordinates": {"latitude": "51.92", "longitude": "4.48"},
            "evses": [{"status": "AVAILABLE"}],
        },
    ]
    return gzip.compress(json.dumps(locs).encode())


def tiny_png() -> bytes:
    """A valid 1x1 PNG."""
    def chunk(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00")) + chunk(b"IEND", b""))


NS = ('xmlns="http://datex2.eu/schema/3/vms" xmlns:com="http://datex2.eu/schema/3/common" '
      'xmlns:loc="http://datex2.eu/schema/3/locationReferencing"')


def drip_table() -> bytes:
    return f"""<?xml version="1.0"?><payload {NS}>
<vmsControllerTable id="t" version="latest">
 <vmsController id="RWS01_DRIP_A7_1" version="1"><vms vmsIndex="1"><vmsRecord>
  <description><com:values><com:value lang="nl">A7 Re 85,3 Heerenveen</com:value></com:values></description>
  <vmsLocation><loc:pointByCoordinates><loc:pointCoordinates><loc:latitude>52.9800</loc:latitude><loc:longitude>5.9600</loc:longitude></loc:pointCoordinates></loc:pointByCoordinates></vmsLocation>
 </vmsRecord></vms></vmsController>
 <vmsController id="RWS01_DRIP_A32_2" version="1"><vms vmsIndex="1"><vmsRecord>
  <vmsLocation><loc:pointByCoordinates><loc:pointCoordinates><loc:latitude>52.9300</loc:latitude><loc:longitude>5.9000</loc:longitude></loc:pointCoordinates></loc:pointByCoordinates></vmsLocation>
 </vmsRecord></vms></vmsController>
 <vmsController id="RWS01_DRIP_A2_9" version="1"><vms vmsIndex="1"><vmsRecord>
  <vmsLocation><loc:pointByCoordinates><loc:pointCoordinates><loc:latitude>51.9</loc:latitude><loc:longitude>4.5</loc:longitude></loc:pointCoordinates></loc:pointByCoordinates></vmsLocation>
 </vmsRecord></vms></vmsController>
</vmsControllerTable></payload>""".encode()


def drip_status(*, png: bytes | None = None, bad_png: bool = False) -> bytes:
    png_b64 = base64.b64encode(png or tiny_png()).decode()
    bad = base64.b64encode(b"GIF89a not a png").decode()
    return f"""<?xml version="1.0"?><payload {NS}>
<vmsControllerStatus>
 <vmsControllerReference targetClass="VmsController" id="RWS01_DRIP_A7_1" version="1"/>
 <vmsStatus vmsIndex="1"><vmsStatus><workingStatus>working</workingStatus>
  <vmsMessage messageIndex="1"><vmsMessage><timeLastSet>2026-11-07T11:50:00Z</timeLastSet>
   <displayAreaSettings><textDisplayAreaSettings><textLine><textLine>FILE A7</textLine></textLine><textLine><textLine>Joure - Drachten 12 min</textLine></textLine></textDisplayAreaSettings></displayAreaSettings>
  </vmsMessage></vmsMessage>
 </vmsStatus></vmsStatus>
</vmsControllerStatus>
<vmsControllerStatus>
 <vmsControllerReference targetClass="VmsController" id="RWS01_DRIP_A32_2" version="1"/>
 <vmsStatus vmsIndex="1"><vmsStatus><workingStatus>working</workingStatus>
  <vmsMessage messageIndex="1"><vmsMessage><timeLastSet>2026-11-07T11:40:00Z</timeLastSet>
   <image><imageData>{bad if bad_png else png_b64}</imageData><imageFormat>png</imageFormat></image>
  </vmsMessage></vmsMessage>
 </vmsStatus></vmsStatus>
</vmsControllerStatus>
<vmsControllerStatus>
 <vmsControllerReference targetClass="VmsController" id="RWS01_DRIP_A2_9" version="1"/>
 <vmsStatus vmsIndex="1"><vmsStatus><vmsMessage messageIndex="1"><vmsMessage>
   <displayAreaSettings><textDisplayAreaSettings><textLine><textLine>Utrecht 25 min</textLine></textLine></textDisplayAreaSettings></displayAreaSettings>
 </vmsMessage></vmsMessage></vmsStatus></vmsStatus>
</vmsControllerStatus>
<vmsControllerStatus>
 <vmsControllerReference targetClass="VmsController" id="BLANK" version="1"/>
 <vmsStatus vmsIndex="1"><vmsStatus><workingStatus>working</workingStatus></vmsStatus></vmsStatus>
</vmsControllerStatus>
</payload>""".encode()


def drip_combined() -> bytes:
    """Table and status in one payload (one of the two layouts NDW may use)."""
    table = drip_table().decode().split("<payload", 1)[1].split(">", 1)[1].rsplit("</payload>", 1)[0]
    status = drip_status().decode().split("<payload", 1)[1].split(">", 1)[1].rsplit("</payload>", 1)[0]
    return gzip.compress(f'<?xml version="1.0"?><payload {NS}>{table}{status}</payload>'.encode())


def rws_catalogue() -> dict:
    return {
        "Succesvol": True,
        "AquoMetadataLijst": [
            {"AquoMetadata_MessageID": 1, "Compartiment": {"Code": "OW"}, "Grootheid": {"Code": "WATHTE"},
             "Eenheid": {"Code": "cm"}, "Hoedanigheid": {"Code": "NAP"}},
            {"AquoMetadata_MessageID": 2, "Compartiment": {"Code": "OW"}, "Grootheid": {"Code": "T"},
             "Eenheid": {"Code": "oC"}, "Hoedanigheid": {"Code": "NVT"}},
        ],
        "LocatieLijst": [
            {"Locatie_MessageID": 10, "Code": "lemmer", "Naam": "Lemmer", "Lat": 52.8410, "Lon": 5.7110},
            {"Locatie_MessageID": 11, "Code": "harlingen", "Naam": "Harlingen", "Lat": 53.1760, "Lon": 5.4090},
            {"Locatie_MessageID": 12, "Code": "hoekvanholland", "Naam": "Hoek van Holland", "Lat": 51.98, "Lon": 4.12},
            {"Locatie_MessageID": 13, "Code": "sneek.temp", "Naam": "Sneek (temp only)", "Lat": 53.03, "Lon": 5.66},
        ],
        "AquoMetadataLocatieLijst": [
            {"Locatie_MessageID": 10, "AquoMetaData_MessageID": 1},
            {"Locatie_MessageID": 11, "AquoMetaData_MessageID": 1},
            {"Locatie_MessageID": 12, "AquoMetaData_MessageID": 1},
            {"Locatie_MessageID": 13, "AquoMetaData_MessageID": 2},
        ],
    }


def rws_latest() -> dict:
    def w(code, name, lat, lon, value, t, proc="meting", qc="00"):
        return {
            "Locatie": {"Code": code, "Naam": name, "Lat": lat, "Lon": lon},
            "AquoMetadata": {"Grootheid": {"Code": "WATHTE"}, "ProcesType": proc},
            "MetingenLijst": [{"Tijdstip": t, "Meetwaarde": {"Waarde_Numeriek": value},
                               "WaarnemingMetadata": {"Kwaliteitswaardecode": qc}}],
        }
    return {
        "Succesvol": True,
        "WaarnemingenLijst": [
            w("lemmer", "Lemmer", 52.8410, 5.7110, -21.0, "2026-11-07T12:00:00.000+01:00"),
            w("lemmer", "Lemmer", 52.8410, 5.7110, -30.0, "2026-11-07T13:00:00.000+01:00", proc="verwachting"),
            w("harlingen", "Harlingen", 53.1760, 5.4090, 999999999, "2026-11-07T12:00:00.000+01:00"),
            w("harlingen", "Harlingen", 53.1760, 5.4090, 112.0, "2026-11-07T11:50:00.000+01:00"),
        ],
    }


def overpass() -> dict:
    return {"elements": [
        {"type": "node", "id": 1, "lat": 52.9610, "lon": 5.9220,
         "tags": {"emergency": "defibrillator", "defibrillator:location": "Naast de ingang",
                  "opening_hours": "24/7", "addr:street": "Dracht", "addr:housenumber": "1", "addr:city": "Heerenveen"}},
        {"type": "way", "id": 2, "center": {"lat": 52.9530, "lon": 5.9350},
         "tags": {"amenity": "hospital", "name": "Tjongerschans", "emergency": "yes"}},
        {"type": "node", "id": 3, "lat": 52.9580, "lon": 5.9150, "tags": {"amenity": "fire_station", "name": "Brandweer Heerenveen"}},
        {"type": "node", "id": 4, "lat": 52.9590, "lon": 5.9160, "tags": {"amenity": "police"}},
        {"type": "node", "id": 5, "lat": 52.9600, "lon": 5.9170, "tags": {"amenity": "cafe"}},
        {"type": "way", "id": 6, "tags": {"amenity": "hospital"}},  # no centre -> skipped
    ]}
