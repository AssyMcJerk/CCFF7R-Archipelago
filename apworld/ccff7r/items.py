import json, pkgutil
from BaseClasses import Item, ItemClassification

ITEMS = json.loads(pkgutil.get_data(__name__, "data/items.json"))
ITEM_BY_NAME = {i["name"]: i for i in ITEMS}
GODDESS = {"Being Materia", "Ground Materia", "Heaven Materia", "Life Materia",
           "Light Materia", "Sabbath Materia", "Star Materia"}
CLASS = {"progression": ItemClassification.progression, "useful": ItemClassification.useful,
         "filler": ItemClassification.filler}


class CCFF7RItem(Item):
    game = "Crisis Core -Final Fantasy VII- Reunion"


item_name_to_id = {i["name"]: i["id"] for i in ITEMS}
item_name_groups = {
    "Mission Sets": {i["name"] for i in ITEMS if i["payload"].get("type") == "mission_set"},
    "Goddess Materia": GODDESS,
}
