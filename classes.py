import datetime
from enum import Enum

from pydantic import BaseModel


class Role(str, Enum):
    admin = "admin"
    owner = "owner"
    employee = "employee"


class FirebaseTableType(BaseModel):
    lastUpdated: datetime.datetime
    name: str
    # todo: 複数形に統一(seats)
    numOfSeat: int
    vacancy: int
