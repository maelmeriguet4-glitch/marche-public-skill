"""Adversarial Empirical Challenge Suite for Milestone 1 Go/No-Go Engine.

Tests specific stress dimensions requested by dispatch:
1. DOM-TOM distance separation (971 vs 974, 972 vs 973).
2. Distant intra-department locations (77 Meaux vs Nemours).
3. Extreme inter-department locations (59 Lille vs 13 Marseille).
4. Corsica (2A Ajaccio vs 2B Bastia, and mainland vs Corsica).
5. References sanity:
   - 10 micro-references of 100 € from 10 years ago vs 2 M€ market.
   - Unrelated trade references (painting vs roofing).
6. Operational availability vs gross headcount:
   - 50 employees total but "aucune equipe disponible".
   - 50 employees total but "0 equipe disponible".
   - 50 employees total but "indisponible".
   - 50 employees total but "saturation complete des equipes".
   - 50 employees total but structured equipes_disponibles=0.
"""

import sys
from pathlib import Path
import pytest

# Add project root and scripts to sys.path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from scripts.go_nogo import evaluer_go_nogo


@pytest.fixture
def base_analyse():
    return {
        "objet": "Travaux de couverture, toiture et zinguerie",
        "lieu_execution": "75001 Paris",
        "montant_estime_ht": 300000.0,
        "date_limite": "2026-12-31",
        "calendrier": {"date_limite_retenue": "2026-12-31"},
    }


@pytest.fixture
def base_profil():
    return {
        "identite": {"siege_social": {"code_postal": "75001"}},
        "qualifications_et_certifications": [{"code": "3101", "intitule": "Couverture"}],
        "capacites_financieres": {"exercices": [{"ca_ht": 2000000.0}]},
        "effectifs": {"total_salaries": 10},
        "structure_couts": {"marge_nette_cible_pct": 8.0},
        "assurances": {
            "decennale": {
                "numero_police": "POL-TEST-001",
                "activites_couvertes": ["couverture", "toiture", "zinguerie"],
            }
        },
    }


class TestGeographyStress:
    """Stress testing of geographic calculations, postal codes, and department centroids."""

    def test_dom_tom_separation_971_vs_974(self, base_analyse, base_profil):
        """Guadeloupe (971) vs Réunion (974) must NOT receive proximity points."""
        analyse = dict(base_analyse, lieu_execution="97400 Saint-Denis", code_postal="97400")
        profil = dict(base_profil, identite={"siege_social": {"code_postal": "97100"}})

        res = evaluer_go_nogo(analyse, profil)
        geo = next(c for c in res["criteres_eval"] if c["id"] == "localisation_eloignement")

        assert geo["points_obtenus"] == 0.0, "971 vs 974 is ~16,000 km, must receive 0.0 pts"
        assert "> 120 km" in geo["justification"] or "très éloigné" in geo["justification"]

    def test_dom_tom_separation_972_vs_973(self, base_analyse, base_profil):
        """Martinique (972) vs Guyane (973) must NOT receive proximity points."""
        analyse = dict(base_analyse, lieu_execution="97300 Cayenne", code_postal="97300")
        profil = dict(base_profil, identite={"siege_social": {"code_postal": "97200"}})

        res = evaluer_go_nogo(analyse, profil)
        geo = next(c for c in res["criteres_eval"] if c["id"] == "localisation_eloignement")

        assert geo["points_obtenus"] == 0.0, "972 vs 973 is ~1,700 km, must receive 0.0 pts"
        assert "> 120 km" in geo["justification"] or "très éloigné" in geo["justification"]

    def test_intra_dom_proximity_974(self, base_analyse, base_profil):
        """Intra-department in DOM (97400 vs 97410) should receive legitimate local proximity points."""
        analyse = dict(base_analyse, lieu_execution="97410 Saint-Pierre", code_postal="97410")
        profil = dict(base_profil, identite={"siege_social": {"code_postal": "97400"}})

        res = evaluer_go_nogo(analyse, profil)
        geo = next(c for c in res["criteres_eval"] if c["id"] == "localisation_eloignement")

        assert geo["points_obtenus"] == 10.0, "Same DOM department (974) should receive 10.0 pts"

    def test_intra_department_77_meaux_vs_nemours(self, base_analyse, base_profil):
        """77 Meaux (77100) vs Nemours (77140) is ~94 km, must NOT receive 10.0 proximity points (<40km)."""
        analyse = dict(base_analyse, lieu_execution="77140 Nemours", code_postal="77140")
        profil = dict(base_profil, identite={"siege_social": {"code_postal": "77100"}})

        res = evaluer_go_nogo(analyse, profil)
        geo = next(c for c in res["criteres_eval"] if c["id"] == "localisation_eloignement")

        assert geo["points_obtenus"] < 10.0, "77100 vs 77140 is ~94 km and must not receive 10.0 pts"
        assert geo["points_obtenus"] == 4.0, "Expected 4.0 pts for distance between 70 and 120 km"
        assert "Chantier éloigné" in geo["justification"]

    def test_intra_department_33_bordeaux_vs_le_verdon(self, base_analyse, base_profil):
        """33 Bordeaux (33000) vs Le Verdon (33123) is ~105 km, must reflect true distance."""
        analyse = dict(base_analyse, lieu_execution="33123 Le Verdon-sur-Mer", code_postal="33123")
        profil = dict(base_profil, identite={"siege_social": {"code_postal": "33000"}})

        res = evaluer_go_nogo(analyse, profil)
        geo = next(c for c in res["criteres_eval"] if c["id"] == "localisation_eloignement")

        assert geo["points_obtenus"] == 4.0, "Expected 4.0 pts for ~105 km distance within large dept 33"

    def test_inter_department_extreme_59_vs_13(self, base_analyse, base_profil):
        """Lille (59000) vs Marseille (13001) is ~1,000 km, must receive 0.0 pts."""
        analyse = dict(base_analyse, lieu_execution="13001 Marseille", code_postal="13001")
        profil = dict(base_profil, identite={"siege_social": {"code_postal": "59000"}})

        res = evaluer_go_nogo(analyse, profil)
        geo = next(c for c in res["criteres_eval"] if c["id"] == "localisation_eloignement")

        assert geo["points_obtenus"] == 0.0, "59 vs 13 is ~1,000 km, must receive 0.0 pts"

    def test_corsica_2a_vs_2b(self, base_analyse, base_profil):
        """Ajaccio (2A000) vs Bastia (2B000) is > 120 km road across mountains, must receive 0.0 pts."""
        analyse = dict(base_analyse, lieu_execution="2B000 Bastia", code_postal="2B000")
        profil = dict(base_profil, identite={"siege_social": {"code_postal": "2A000"}})

        res = evaluer_go_nogo(analyse, profil)
        geo = next(c for c in res["criteres_eval"] if c["id"] == "localisation_eloignement")

        assert geo["points_obtenus"] == 0.0, "2A vs 2B road distance is > 120 km, must receive 0.0 pts"

    def test_corsica_vs_mainland(self, base_analyse, base_profil):
        """Mainland Paris (75001) vs Corsica Ajaccio (2A000) must receive 0.0 pts."""
        analyse = dict(base_analyse, lieu_execution="2A000 Ajaccio", code_postal="2A000")
        profil = dict(base_profil, identite={"siege_social": {"code_postal": "75001"}})

        res = evaluer_go_nogo(analyse, profil)
        geo = next(c for c in res["criteres_eval"] if c["id"] == "localisation_eloignement")

        assert geo["points_obtenus"] == 0.0, "Mainland vs Corsica must receive 0.0 pts"


class TestReferencesStress:
    """Stress testing of qualitative references sizing, recency, and trade concordance."""

    def test_micro_ancient_references_vs_large_market(self, base_analyse, base_profil):
        """10 micro-references of 100 € from 10 years ago against a 2 M€ market must NOT receive full points."""
        analyse = dict(base_analyse, montant_estime_ht=2000000.0)
        profil = dict(base_profil)
        profil["references_chantiers"] = [
            {
                "intitule": f"Reparation toiturette {i}",
                "montant_ht_euros": 100.0,
                "annee_realisation": 2016,  # 10 years ago
                "maitre_ouvrage": "Particulier",
            }
            for i in range(10)
        ]

        res = evaluer_go_nogo(analyse, profil)
        crit = next(c for c in res["criteres_eval"] if c["id"] == "references_comparables")

        assert crit["points_obtenus"] < 15.0, "Micro ancient references must NOT receive full 15.0 pts"
        assert crit["points_obtenus"] <= 5.0, "Expected <= 5.0 pts (references eloignees/anciennes)"
        assert "ancienne(s)" in crit["justification"] or "éloignée" in crit["justification"]

    def test_unrelated_trades_references(self, base_analyse, base_profil):
        """References in painting for a roofing market must NOT receive full points."""
        profil = dict(base_profil)
        profil["references_chantiers"] = [
            {
                "intitule": f"Travaux de peinture et ravalement {i}",
                "montant_ht_euros": 150000.0,
                "annee_realisation": 2025,
                "maitre_ouvrage": "Bailleur social",
            }
            for i in range(5)
        ]

        res = evaluer_go_nogo(base_analyse, profil)
        crit = next(c for c in res["criteres_eval"] if c["id"] == "references_comparables")

        assert crit["points_obtenus"] < 15.0, "Unrelated trade references must NOT receive full points"
        assert crit["points_obtenus"] <= 5.0, "Expected <= 5.0 pts (references eloignees en nature)"


class TestOperationalAvailabilityStress:
    """Adversarial stress testing of operational availability vs gross headcount."""

    def test_unavailability_phrase_aucune_equipe_disponible(self, base_analyse, base_profil):
        """Headcount 50 with 'aucune equipe disponible' must NOT receive 15.0 pts."""
        profil = dict(base_profil)
        profil["effectif_total"] = 50
        profil["disponibilite_equipes"] = "aucune equipe disponible"

        res = evaluer_go_nogo(base_analyse, profil)
        crit = next(c for c in res["criteres_eval"] if c["id"] == "charge_travail_et_disponibilite")

        # The bug causes this to receive 15.0 pts with "Ressources déclarées disponibles immédiatement"
        assert crit["points_obtenus"] == 0.0, (
            f"VULNERABILITY: 'aucune equipe disponible' awarded {crit['points_obtenus']}/15 pts "
            f"with justification: {crit['justification']}"
        )

    def test_unavailability_phrase_zero_equipe_disponible(self, base_analyse, base_profil):
        """Headcount 50 with '0 equipe disponible' must NOT receive 15.0 pts."""
        profil = dict(base_profil)
        profil["effectif_total"] = 50
        profil["disponibilite_equipes"] = "0 equipe disponible"

        res = evaluer_go_nogo(base_analyse, profil)
        crit = next(c for c in res["criteres_eval"] if c["id"] == "charge_travail_et_disponibilite")

        assert crit["points_obtenus"] == 0.0, (
            f"VULNERABILITY: '0 equipe disponible' awarded {crit['points_obtenus']}/15 pts "
            f"with justification: {crit['justification']}"
        )

    def test_unavailability_phrase_indisponible(self, base_analyse, base_profil):
        """Headcount 50 with 'indisponible' must NOT receive 15.0 pts due to substring match on 'disponible'."""
        profil = dict(base_profil)
        profil["effectif_total"] = 50
        profil["disponibilite_equipes"] = "indisponible"

        res = evaluer_go_nogo(base_analyse, profil)
        crit = next(c for c in res["criteres_eval"] if c["id"] == "charge_travail_et_disponibilite")

        assert crit["points_obtenus"] == 0.0, (
            f"VULNERABILITY: 'indisponible' awarded {crit['points_obtenus']}/15 pts "
            f"with justification: {crit['justification']}"
        )

    def test_unavailability_phrase_saturation_complete(self, base_analyse, base_profil):
        """Headcount 50 with 'saturation complete' must NOT receive 15.0 pts due to match on 'complete'."""
        profil = dict(base_profil)
        profil["effectif_total"] = 50
        profil["disponibilite_equipes"] = "saturation complete des equipes"

        res = evaluer_go_nogo(base_analyse, profil)
        crit = next(c for c in res["criteres_eval"] if c["id"] == "charge_travail_et_disponibilite")

        assert crit["points_obtenus"] == 0.0, (
            f"VULNERABILITY: 'saturation complete' awarded {crit['points_obtenus']}/15 pts "
            f"with justification: {crit['justification']}"
        )

    def test_structured_available_teams_zero_with_large_headcount(self, base_analyse, base_profil):
        """Headcount 50 with structured equipes_disponibles=0 must NOT receive 15.0 pts."""
        profil = dict(base_profil)
        profil["effectif_total"] = 50
        profil["equipes_disponibles"] = 0
        profil["effectifs"] = {"total_salaries": 50, "equipes_disponibles": 0}

        res = evaluer_go_nogo(base_analyse, profil)
        crit = next(c for c in res["criteres_eval"] if c["id"] == "charge_travail_et_disponibilite")

        assert crit["points_obtenus"] == 0.0, (
            f"VULNERABILITY: Headcount 50 with equipes_disponibles=0 awarded {crit['points_obtenus']}/15 pts "
            f"with justification: {crit['justification']}"
        )
