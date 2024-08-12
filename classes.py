from enum import Enum


class Role(str, Enum):
    admin = "admin"
    owner = "owner"
    employee = "employee"