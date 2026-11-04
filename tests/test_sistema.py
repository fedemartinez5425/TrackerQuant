from core.sistema import version_deploy, versiones_paquetes


def test_version_deploy_con_ref_suelto(tmp_path):
    (tmp_path / ".git" / "refs" / "heads").mkdir(parents=True)
    (tmp_path / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    (tmp_path / ".git" / "refs" / "heads" / "main").write_text("da828f58f91c05c880e3a22e272da1981cfc9fe6\n")
    assert version_deploy(tmp_path) == {"rama": "main", "commit": "da828f5"}


def test_version_deploy_con_packed_refs(tmp_path):
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    (tmp_path / ".git" / "packed-refs").write_text(
        "# pack-refs with: peeled\nabc1234def refs/heads/main\n"
    )
    assert version_deploy(tmp_path) == {"rama": "main", "commit": "abc1234"}


def test_version_deploy_sin_git(tmp_path):
    assert version_deploy(tmp_path) is None


def test_versiones_paquetes_incluye_python_y_streamlit():
    v = versiones_paquetes()
    assert v["python"] and v["streamlit"] != "no instalado"
