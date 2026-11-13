"""Write data/places.json: the one list of places both halves search.

    python3 tests/make_places.py [zoneinfo dir, default /usr/share/zoneinfo]     (from the plugin folder)

zones: every row of the tz database's zone.tab (public domain), zone name -> country name from
iso3166.tab. cities: places people search for that are not zone names, written by hand below.
names: display names where the zone's last segment reads wrong. The script checks that every zone
loads with zoneinfo and that no city repeats a zone's own name.
"""
import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

ZI = Path(sys.argv[1] if len(sys.argv) > 1 else "/usr/share/zoneinfo")
OUT = Path(__file__).resolve().parents[1] / "data" / "places.json"

COUNTRY_FIX = {"Britain (UK)": "United Kingdom", "Korea (South)": "South Korea", "Korea (North)": "North Korea",
               "Czech Republic": "Czechia", "Congo (Dem. Rep.)": "DR Congo", "Congo (Rep.)": "Congo",
               "Russia": "Russia", "Virgin Islands (US)": "US Virgin Islands", "Virgin Islands (UK)": "British Virgin Islands"}
NAMES = {"America/Sao_Paulo": "São Paulo", "Asia/Ho_Chi_Minh": "Ho Chi Minh City", "America/Bogota": "Bogotá",
         "America/St_Johns": "St. John's", "America/Asuncion": "Asunción", "Europe/Zurich": "Zurich",
         "America/Argentina/Buenos_Aires": "Buenos Aires", "Asia/Kolkata": "Kolkata", "Europe/Kyiv": "Kyiv",
         "Asia/Qatar": "Qatar", "Africa/Sao_Tome": "São Tomé", "America/Port-au-Prince": "Port-au-Prince"}
US, CA, DE, GB, IN, CN, JP = "United States", "Canada", "Germany", "United Kingdom", "India", "China", "Japan"
CITIES = [
    ["San Francisco", "America/Los_Angeles", US], ["Seattle", "America/Los_Angeles", US], ["Portland", "America/Los_Angeles", US],
    ["San Diego", "America/Los_Angeles", US], ["San Jose", "America/Los_Angeles", US], ["Las Vegas", "America/Los_Angeles", US],
    ["Salt Lake City", "America/Denver", US], ["Dallas", "America/Chicago", US], ["Houston", "America/Chicago", US],
    ["Austin", "America/Chicago", US], ["Minneapolis", "America/Chicago", US], ["Nashville", "America/Chicago", US],
    ["Boston", "America/New_York", US], ["Washington DC", "America/New_York", US], ["Miami", "America/New_York", US],
    ["Atlanta", "America/New_York", US], ["Philadelphia", "America/New_York", US], ["Pittsburgh", "America/New_York", US],
    ["Montreal", "America/Toronto", CA], ["Ottawa", "America/Toronto", CA], ["Quebec City", "America/Toronto", CA],
    ["Calgary", "America/Edmonton", CA], ["Guadalajara", "America/Mexico_City", "Mexico"],
    ["Rio de Janeiro", "America/Sao_Paulo", "Brazil"], ["Brasilia", "America/Sao_Paulo", "Brazil"],
    ["Medellin", "America/Bogota", "Colombia"], ["Quito", "America/Guayaquil", "Ecuador"],
    ["Munich", "Europe/Berlin", DE], ["Hamburg", "Europe/Berlin", DE], ["Frankfurt", "Europe/Berlin", DE],
    ["Cologne", "Europe/Berlin", DE], ["Stuttgart", "Europe/Berlin", DE], ["Düsseldorf", "Europe/Berlin", DE],
    ["Leipzig", "Europe/Berlin", DE], ["Barcelona", "Europe/Madrid", "Spain"], ["Valencia", "Europe/Madrid", "Spain"],
    ["Milan", "Europe/Rome", "Italy"], ["Naples", "Europe/Rome", "Italy"], ["Turin", "Europe/Rome", "Italy"],
    ["Geneva", "Europe/Zurich", "Switzerland"], ["Basel", "Europe/Zurich", "Switzerland"], ["Bern", "Europe/Zurich", "Switzerland"],
    ["Lyon", "Europe/Paris", "France"], ["Marseille", "Europe/Paris", "France"],
    ["Edinburgh", "Europe/London", GB], ["Manchester", "Europe/London", GB], ["Glasgow", "Europe/London", GB],
    ["Birmingham", "Europe/London", GB], ["Belfast", "Europe/London", GB],
    ["Rotterdam", "Europe/Amsterdam", "Netherlands"], ["The Hague", "Europe/Amsterdam", "Netherlands"],
    ["Antwerp", "Europe/Brussels", "Belgium"], ["Porto", "Europe/Lisbon", "Portugal"], ["Gothenburg", "Europe/Stockholm", "Sweden"],
    ["Krakow", "Europe/Warsaw", "Poland"], ["Salzburg", "Europe/Vienna", "Austria"], ["Graz", "Europe/Vienna", "Austria"],
    ["St Petersburg", "Europe/Moscow", "Russia"], ["Thessaloniki", "Europe/Athens", "Greece"], ["Ankara", "Europe/Istanbul", "Türkiye"],
    ["Cork", "Europe/Dublin", "Ireland"], ["Bergen", "Europe/Oslo", "Norway"], ["Aarhus", "Europe/Copenhagen", "Denmark"],
    ["Mumbai", "Asia/Kolkata", IN], ["Delhi", "Asia/Kolkata", IN], ["New Delhi", "Asia/Kolkata", IN], ["Bengaluru", "Asia/Kolkata", IN],
    ["Bangalore", "Asia/Kolkata", IN], ["Chennai", "Asia/Kolkata", IN], ["Hyderabad", "Asia/Kolkata", IN], ["Pune", "Asia/Kolkata", IN],
    ["Beijing", "Asia/Shanghai", CN], ["Shenzhen", "Asia/Shanghai", CN], ["Guangzhou", "Asia/Shanghai", CN],
    ["Chengdu", "Asia/Shanghai", CN], ["Hangzhou", "Asia/Shanghai", CN],
    ["Osaka", "Asia/Tokyo", JP], ["Kyoto", "Asia/Tokyo", JP], ["Yokohama", "Asia/Tokyo", JP], ["Busan", "Asia/Seoul", "South Korea"],
    ["Hanoi", "Asia/Ho_Chi_Minh", "Vietnam"], ["Abu Dhabi", "Asia/Dubai", "United Arab Emirates"], ["Doha", "Asia/Qatar", "Qatar"],
    ["Tel Aviv", "Asia/Jerusalem", "Israel"], ["Islamabad", "Asia/Karachi", "Pakistan"], ["Lahore", "Asia/Karachi", "Pakistan"],
    ["Cebu", "Asia/Manila", "Philippines"], ["Bali", "Asia/Makassar", "Indonesia"], ["Surabaya", "Asia/Jakarta", "Indonesia"],
    ["Jeddah", "Asia/Riyadh", "Saudi Arabia"], ["Astana", "Asia/Almaty", "Kazakhstan"],
    ["Cape Town", "Africa/Johannesburg", "South Africa"], ["Durban", "Africa/Johannesburg", "South Africa"],
    ["Pretoria", "Africa/Johannesburg", "South Africa"], ["Abuja", "Africa/Lagos", "Nigeria"],
    ["Marrakech", "Africa/Casablanca", "Morocco"], ["Rabat", "Africa/Casablanca", "Morocco"],
    ["Alexandria", "Africa/Cairo", "Egypt"], ["Mombasa", "Africa/Nairobi", "Kenya"],
    ["Canberra", "Australia/Sydney", "Australia"], ["Gold Coast", "Australia/Brisbane", "Australia"],
    ["Wellington", "Pacific/Auckland", "New Zealand"], ["Christchurch", "Pacific/Auckland", "New Zealand"],
]


def city_name(zone: str) -> str:
    return NAMES.get(zone) or zone.split("/")[-1].replace("_", " ")


def main() -> None:
    countries = {}
    for line in (ZI / "iso3166.tab").read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            code, name = line.split("\t")[:2]
            countries[code] = COUNTRY_FIX.get(name, name)
    zones = {}
    for line in (ZI / "zone.tab").read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            code, _coords, zone = line.split("\t")[:3]
            ZoneInfo(zone)
            zones[zone] = countries[code]
    zones = dict(sorted(zones.items()))
    own = {city_name(z).lower() for z in zones}
    for city, zone, _country in CITIES:
        assert zone in zones, f"{city}: {zone} is not in zone.tab"
        assert city.lower() not in own, f"{city} is already a zone name"
    assert len({c[0].lower() for c in CITIES}) == len(CITIES), "a city is listed twice"
    names = {z: n for z, n in NAMES.items() if z in zones and n != z.split("/")[-1].replace("_", " ")}
    doc = {"source": "tz database zone.tab and iso3166.tab (public domain), plus a hand-written city list; "
                     "written by tests/make_places.py",
           "zones": zones, "names": names, "cities": CITIES}
    OUT.write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(json.dumps({"zones": len(zones), "cities": len(CITIES), "names": len(names), "bytes": OUT.stat().st_size}))


main()
