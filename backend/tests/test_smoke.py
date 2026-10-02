import kredpare.core
import kredpare.domains.lending


def test_packages_import() -> None:
    assert kredpare.core.__name__ == "kredpare.core"
    assert kredpare.domains.lending.__name__ == "kredpare.domains.lending"
