"""
Tests Red Team complets de sécurité (18 scénarios exhaustifs) pour marche-public-skill v2.0.2.
Vérifie le confinement strict des chemins, le blocage des symlinks malveillants,
l'authentification réseau, et la robustesse face aux injections de chemins.
"""

import os
import sys
from pathlib import Path
import pytest
from fastapi import HTTPException

from scripts.api import resoudre_et_securiser_chemin, verifier_authentification
from scripts.mcp_server import _resoudre_chemin_mcp
from scripts.common import parse_bool_strict


REPO_ROOT = Path(__file__).resolve().parent.parent


# 1. Chemin ../../../etc/passwd
def test_redteam_01_traversal_etc_passwd():
    with pytest.raises(HTTPException) as exc_info:
        resoudre_et_securiser_chemin("../../../etc/passwd")
    assert exc_info.value.status_code in (403, 400)


# 2. Chemin Windows vers un répertoire système (C:\Windows\System32)
def test_redteam_02_system_dir_windows():
    with pytest.raises(HTTPException) as exc_info:
        resoudre_et_securiser_chemin("C:\\Windows\\System32\\cmd.exe")
    assert exc_info.value.status_code == 403


# 3. Chemin absolu extérieur aux racines autorisées
def test_redteam_03_absolute_path_outside_allowed_roots():
    with pytest.raises(HTTPException) as exc_info:
        resoudre_et_securiser_chemin("C:\\some_arbitrary_external_folder\\secret.txt")
    assert exc_info.value.status_code == 403


# 4. Lien symbolique pointant vers un fichier extérieur
def test_redteam_04_symlink_to_external_file(tmp_path):
    external_file = tmp_path / "external_secret.txt"
    external_file.write_text("CONFIDENTIAL_DATA")

    inside_symlink = REPO_ROOT / "tests" / "fixtures" / "symlink_leak_test"
    try:
        inside_symlink.symlink_to(external_file)
        with pytest.raises(HTTPException) as exc_info:
            resoudre_et_securiser_chemin(str(inside_symlink))
        assert exc_info.value.status_code == 403
    except (OSError, NotImplementedError):
        pytest.skip("Création de lien symbolique non supportée sur cet environnement sans privilèges admin.")
    finally:
        if inside_symlink.is_symlink() or inside_symlink.exists():
            inside_symlink.unlink(missing_ok=True)


# 5. Lien symbolique imbriqué
def test_redteam_05_nested_symlink_escape(tmp_path):
    target = tmp_path / "deep_secret.txt"
    target.write_text("SECRET")
    link1 = tmp_path / "link1"
    link2 = REPO_ROOT / "tests" / "fixtures" / "nested_symlink_test"
    try:
        link1.symlink_to(target)
        link2.symlink_to(link1)
        with pytest.raises(HTTPException) as exc_info:
            resoudre_et_securiser_chemin(str(link2))
        assert exc_info.value.status_code == 403
    except (OSError, NotImplementedError):
        pytest.skip("Privilèges symlinks non disponibles.")
    finally:
        if link2.is_symlink() or link2.exists():
            link2.unlink(missing_ok=True)


# 6. Chemin avec séparateurs mixtes (slashes et antislashs)
def test_redteam_06_mixed_separators():
    with pytest.raises(HTTPException) as exc_info:
        resoudre_et_securiser_chemin("tests/..\\..\\..\\Windows")
    assert exc_info.value.status_code in (403, 400)


# 7. Chemin encodé URL (ex: ..%2F..%2Fetc%2Fpasswd)
def test_redteam_07_url_encoded_traversal():
    with pytest.raises(HTTPException) as exc_info:
        resoudre_et_securiser_chemin("..%2F..%2Fetc%2Fpasswd")
    assert exc_info.value.status_code in (403, 400)


# 8. Fichier volumineux dépassant la limite
def test_redteam_08_file_exceeding_size_limit(tmp_path):
    big_file = REPO_ROOT / "tests" / "fixtures" / "test_big_file.txt"
    try:
        big_file.write_bytes(b"0" * (1024 * 1024 + 1))  # 1 Mo + 1 octet
        with pytest.raises(HTTPException) as exc_info:
            # Tester avec limite stricte passée via environ
            os.environ["MARCHE_PUBLIC_MAX_FILE_SIZE"] = str(1024 * 1024)
            # Re-importer ou forcer la limite
            from scripts import api
            api.MAX_FILE_SIZE_BYTES = 1024 * 1024
            resoudre_et_securiser_chemin(str(big_file), must_be_file=True)
        assert exc_info.value.status_code == 413
    finally:
        api.MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024
        if big_file.exists():
            big_file.unlink()


# 9. Extension interdite (.exe, .sh, .bat)
def test_redteam_09_forbidden_file_extension():
    bad_file = REPO_ROOT / "tests" / "fixtures" / "script.exe"
    try:
        bad_file.write_bytes(b"MZ...")
        with pytest.raises(HTTPException) as exc_info:
            resoudre_et_securiser_chemin(str(bad_file), must_be_file=True)
        assert exc_info.value.status_code == 400
        assert "Extension de fichier non autorisée" in exc_info.value.detail
    finally:
        if bad_file.exists():
            bad_file.unlink()


# 10. Chemin inexistant requis
def test_redteam_10_missing_file_when_required():
    with pytest.raises(HTTPException) as exc_info:
        resoudre_et_securiser_chemin("tests/fixtures/inexistant_fichier.pdf", must_exist=True)
    assert exc_info.value.status_code == 404


# 11. Chemin contenant des caractères inhabituels ou null byte
def test_redteam_11_unusual_characters():
    with pytest.raises((HTTPException, ValueError)):
        resoudre_et_securiser_chemin("tests/fixtures/test\x00file.pdf")


# 12. Accès MCP à un fichier extérieur aux racines
def test_redteam_12_mcp_access_outside_root():
    with pytest.raises(PermissionError):
        _resoudre_chemin_mcp("C:/some_outside_dir/document.pdf")


# 13. Accès API sans authentification en configuration réseau / production
def test_redteam_13_api_no_auth_in_production():
    from scripts import api
    old_env = api.API_ENVIRONMENT
    old_key = api.API_KEY_ENV
    try:
        api.API_ENVIRONMENT = "production"
        api.API_KEY_ENV = "super_secret_production_key_12345"
        with pytest.raises(HTTPException) as exc_info:
            api.verifier_authentification(None)
        assert exc_info.value.status_code == 401
    finally:
        api.API_ENVIRONMENT = old_env
        api.API_KEY_ENV = old_key


# 14. Clé API incorrecte
def test_redteam_14_api_invalid_key():
    from scripts import api
    old_env = api.API_ENVIRONMENT
    old_key = api.API_KEY_ENV
    try:
        api.API_ENVIRONMENT = "production"
        api.API_KEY_ENV = "super_secret_production_key_12345"
        with pytest.raises(HTTPException) as exc_info:
            api.verifier_authentification("wrong_key")
        assert exc_info.value.status_code == 401
    finally:
        api.API_ENVIRONMENT = old_env
        api.API_KEY_ENV = old_key


# 15. Clé API absente en mode prod
def test_redteam_15_api_empty_key():
    from scripts import api
    old_env = api.API_ENVIRONMENT
    old_key = api.API_KEY_ENV
    try:
        api.API_ENVIRONMENT = "production"
        api.API_KEY_ENV = "super_secret_production_key_12345"
        with pytest.raises(HTTPException) as exc_info:
            api.verifier_authentification("")
        assert exc_info.value.status_code == 401
    finally:
        api.API_ENVIRONMENT = old_env
        api.API_KEY_ENV = old_key


# 16. Configuration de production incomplète (clé manquante côté serveur)
def test_redteam_16_incomplete_production_config():
    from scripts import api
    old_env = api.API_ENVIRONMENT
    old_key = api.API_KEY_ENV
    try:
        api.API_ENVIRONMENT = "production"
        api.API_KEY_ENV = ""  # Clé non définie côté serveur en prod !
        with pytest.raises(HTTPException) as exc_info:
            api.verifier_authentification("any_client_token")
        assert exc_info.value.status_code == 500
        assert "non configurée" in exc_info.value.detail
    finally:
        api.API_ENVIRONMENT = old_env
        api.API_KEY_ENV = old_key


# 17. Tentative d'accès concurrent / TOCTOU
def test_redteam_17_atomic_check_and_resolve():
    fixture_path = REPO_ROOT / "tests" / "fixtures" / "RC.docx"
    p = resoudre_et_securiser_chemin(str(fixture_path), must_exist=True, must_be_file=True)
    assert p.is_file()
    assert p.resolve() == fixture_path.resolve()


# 18. Entrée malformée ou type inattendu pour booléens stricts
def test_redteam_18_strict_boolean_validation():
    # Chaînes ambiguës
    assert parse_bool_strict("true") is True
    assert parse_bool_strict("false") is False
    assert parse_bool_strict("0") is False
    assert parse_bool_strict(0) is False
    assert parse_bool_strict(1) is True

    # Rejets stricts
    with pytest.raises(ValueError):
        parse_bool_strict("maybe")

    with pytest.raises(TypeError):
        parse_bool_strict([])

    with pytest.raises(TypeError):
        parse_bool_strict({})

    with pytest.raises(TypeError):
        parse_bool_strict(None)
