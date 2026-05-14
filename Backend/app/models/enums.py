from enum import Enum


class DeviationShift(str, Enum):
    shift_a = "Shift A"
    shift_b = "Shift B"
    shift_c = "Shift C"
    shift_d = "Shift D"


class DeviationCategory(str, Enum):
    equipments = "Equipment"
    flow = "Flow"
    planning = "Planning"
    yard = "Yard"
    human = "Human"
    others = "Others"



class DeviationStatus(str, Enum):
    done = "Done"
    on_going = "On going"
    not_yet = "Not Yet"


def enum_values(enum):
    return [item.value for item in enum]
