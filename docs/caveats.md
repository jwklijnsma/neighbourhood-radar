# Caveats

* The P2000 feed is a volunteer-run service, not an official API. If it goes
  away, point `OL_P2000_URL` at another RSS feed with the same item fields
  (`message`, `regcode`, `dienst`, `code`, `lat`, `lon`), or run your own
  RTL-SDR + multimon-ng receiver.
* OpenSky and airplanes.live data are for non-commercial use under their terms;
  adsb.lol data is ODbL (attribution shown in the app).
* P2000 messages are public broadcasts, but they describe real emergencies at
  real addresses. Think before exposing this publicly.
