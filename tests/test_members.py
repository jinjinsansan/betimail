import pytest
import members as mbr


def test_add_and_get_member():
    m = mbr.add_member(
        name="山田太郎", email="taro@example.com",
        nft_type="会員権NFT", joined_date="2024-01-15",
    )
    assert m["email"] == "taro@example.com"
    assert mbr.get_member_by_email("TARO@example.com")["name"] == "山田太郎"


def test_duplicate_email_rejected():
    mbr.add_member(name="A", email="a@example.com", nft_type="会員権NFT", joined_date="2024-01-01")
    with pytest.raises(ValueError, match="既に登録"):
        mbr.add_member(name="B", email="a@example.com", nft_type="会員権NFT", joined_date="2024-01-02")


def test_invalid_email_rejected():
    with pytest.raises(ValueError, match="メールアドレス"):
        mbr.add_member(name="A", email="not-an-email", nft_type="会員権NFT", joined_date="")


def test_invalid_nft_type_rejected():
    with pytest.raises(ValueError, match="NFT種別"):
        mbr.add_member(name="A", email="a@example.com", nft_type="不明NFT", joined_date="")


def test_invalid_date_rejected():
    with pytest.raises(ValueError, match="日付"):
        mbr.add_member(name="A", email="a@example.com", nft_type="会員権NFT", joined_date="2024/01/01")


def test_update_member():
    mbr.add_member(name="A", email="a@example.com", nft_type="会員権NFT", joined_date="")
    updated = mbr.update_member("a@example.com", name="B", notes="updated")
    assert updated["name"] == "B"
    assert updated["notes"] == "updated"


def test_update_unknown_returns_none():
    assert mbr.update_member("nobody@example.com", name="X") is None


def test_delete_member():
    mbr.add_member(name="A", email="a@example.com", nft_type="会員権NFT", joined_date="")
    assert mbr.delete_member("A@example.com") is True
    assert mbr.get_member_by_email("a@example.com") is None


def test_import_csv():
    csv_data = (
        "name,email,nft_type,joined_date,notes\n"
        "X,x@example.com,会員権NFT,2024-01-01,\n"
        "Y,bad-email,会員権NFT,2024-01-01,\n"  # invalid email
        "Z,z@example.com,不明NFT,2024-01-01,\n"  # invalid nft
    )
    r = mbr.import_csv(csv_data)
    assert r["added"] == 1
    assert len(r["skipped"]) == 2


def test_canonical_inbox_gmail_dots_and_plus():
    assert mbr.canonical_inbox("User@Gmail.com") == "user@gmail.com"
    assert mbr.canonical_inbox("u.s.e.r@gmail.com") == "user@gmail.com"
    assert mbr.canonical_inbox("user+tag@gmail.com") == "user@gmail.com"
    assert mbr.canonical_inbox("u.s.e.r+abc@gmail.com") == "user@gmail.com"
    assert mbr.canonical_inbox("user@googlemail.com") == "user@gmail.com"


def test_canonical_inbox_non_gmail_keeps_dots():
    # Yahoo/Outlook etc. はドットが意味を持つので残す
    assert mbr.canonical_inbox("foo.bar@example.com") == "foo.bar@example.com"
    # + タグは大半のメジャープロバイダで除外可能と扱う
    assert mbr.canonical_inbox("foo+tag@example.com") == "foo@example.com"


def test_dedupe_by_inbox_keeps_richest_record():
    members_list = [
        {"name": "A1", "email": "kaori+1@gmail.com",   "nft_type": "会員権NFT"},
        {"name": "A2", "email": "k.aori+2@gmail.com",  "nft_type": "会員権NFT, ラッキーマスタードNFT"},
        {"name": "A3", "email": "kaori@gmail.com",     "nft_type": "会員権NFT"},
        {"name": "B",  "email": "other@example.com",   "nft_type": "会員権NFT"},
    ]
    out = mbr.dedupe_by_inbox(members_list)
    inboxes = [mbr.canonical_inbox(m["email"]) for m in out]
    # kaori 系は 1 つにまとまる（最も NFT 種別が多い A2 が残る）
    assert len(out) == 2
    assert "other@example.com" in inboxes
    assert "kaori@gmail.com" in inboxes
    kaori = [m for m in out if mbr.canonical_inbox(m["email"]) == "kaori@gmail.com"][0]
    assert kaori["name"] == "A2"
