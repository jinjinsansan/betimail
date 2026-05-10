import csv
import os
from typing import Optional
from config import MEMBERS_CSV_PATH, NFT_TYPES


def _ensure_csv():
    if not os.path.exists(MEMBERS_CSV_PATH):
        os.makedirs(os.path.dirname(MEMBERS_CSV_PATH), exist_ok=True)
        with open(MEMBERS_CSV_PATH, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["name", "email", "nft_type", "joined_date", "notes"])
            writer.writeheader()


def get_all_members() -> list[dict]:
    _ensure_csv()
    with open(MEMBERS_CSV_PATH, "r", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def get_members_by_nft_type(nft_type: str) -> list[dict]:
    return [m for m in get_all_members() if m["nft_type"] == nft_type]


def get_member_by_email(email: str) -> Optional[dict]:
    for m in get_all_members():
        if m["email"].strip().lower() == email.strip().lower():
            return m
    return None


def add_member(name: str, email: str, nft_type: str, joined_date: str, notes: str = "") -> dict:
    if nft_type not in NFT_TYPES:
        raise ValueError(f"不正なNFT種別: {nft_type}")
    member = {"name": name, "email": email, "nft_type": nft_type, "joined_date": joined_date, "notes": notes}
    _ensure_csv()
    with open(MEMBERS_CSV_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["name", "email", "nft_type", "joined_date", "notes"])
        writer.writerow(member)
    return member


def delete_member(email: str) -> bool:
    members = get_all_members()
    new_members = [m for m in members if m["email"].strip().lower() != email.strip().lower()]
    if len(new_members) == len(members):
        return False
    with open(MEMBERS_CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["name", "email", "nft_type", "joined_date", "notes"])
        writer.writeheader()
        writer.writerows(new_members)
    return True


def update_member(email: str, **kwargs) -> Optional[dict]:
    members = get_all_members()
    updated = None
    for m in members:
        if m["email"].strip().lower() == email.strip().lower():
            m.update({k: v for k, v in kwargs.items() if k in m})
            updated = m
    if updated is None:
        return None
    with open(MEMBERS_CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["name", "email", "nft_type", "joined_date", "notes"])
        writer.writeheader()
        writer.writerows(members)
    return updated
