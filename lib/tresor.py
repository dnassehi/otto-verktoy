"""Sti-hjelper for det krypterte tresoret (~/tresor, gocryptfs).

Pasientdata og annet sensitivt materiale skal ligge her, aldri i workspace.
`tresor_path()` feiler tydelig hvis tresoret ikke er montert, slik at
pipelines aldri skriver klartekst til den ukrypterte disken ved en feil.
"""
from pathlib import Path

TRESOR = Path.home() / "tresor"


class TresorNotMounted(RuntimeError):
    pass


def tresor_path(*parts: str) -> Path:
    if not TRESOR.is_mount():
        raise TresorNotMounted(
            f"{TRESOR} er ikke montert - avbryter (systemctl --user status tresor)"
        )
    p = TRESOR.joinpath(*parts)
    p.mkdir(parents=True, exist_ok=True)
    return p
