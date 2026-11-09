import json, pkgutil
from BaseClasses import Location

LOCATIONS = json.loads(pkgutil.get_data(__name__, "data/locations.json"))
location_name_to_id = {l["name"]: l["id"] for l in LOCATIONS}

# rank -> chapter the logic expects before the mission is "in logic"
RANK_CHAPTER = {1: 1, 2: 1, 3: 3, 4: 4, 5: 5, 6: 7, 7: 8, 8: 9, 9: 10, 10: 10}


class CCFF7RLocation(Location):
    game = "Crisis Core -Final Fantasy VII- Reunion"
