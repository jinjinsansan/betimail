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
