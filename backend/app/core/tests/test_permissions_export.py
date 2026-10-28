"""El contrato de permisos commiteado para el frontend debe coincidir con el
catalogo del backend."""

from app.core.permissions_export import (
    CONTRACT_PATH,
    MISALIGNED_MESSAGE,
    build_contract,
    is_aligned,
    main,
)


def test_contrato_commiteado_alineado_con_el_catalogo() -> None:
    assert is_aligned(), MISALIGNED_MESSAGE


def test_check_sale_con_1_si_el_archivo_difiere(tmp_path, monkeypatch, capsys) -> None:
    stale = tmp_path / "permissions.json"
    stale.write_text("{}\n", encoding="utf-8")
    monkeypatch.setattr("app.core.permissions_export.CONTRACT_PATH", stale)
    assert main(["--check"]) == 1
    assert MISALIGNED_MESSAGE in capsys.readouterr().out


def test_eventos_no_son_asignables() -> None:
    actions = {a["tag"]: a for m in build_contract()["modules"] for a in m["actions"]}
    assert actions["leo.auth.login"]["assignable"] is False
    assert actions["leo.users.view"]["assignable"] is True
    assert CONTRACT_PATH.name == "permissions.json"
