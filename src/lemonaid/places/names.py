"""Persistent whimsical names for managed places."""

import re
import subprocess
import time
from collections import defaultdict
from collections.abc import Iterable, Sequence
from pathlib import Path

from ..inbox import db
from ..log import get_logger
from .ssa_top_names import SSA_TOP_1000_2024

_log = get_logger("places.names")

LEMON_NAME_ENV = "LEMON_NAME"
_WORDS = re.compile(r"[-_/]+")

# Candidates deliberately span ancient figures, unusual animals, plants,
# minerals, and other nouns. The exported pools below drop anything appearing
# in either sex's SSA top 1,000 for 2024.
_RAW_CANDIDATES = (
    "Axolotl Aardwolf Auk Archaeopteryx Ammonite Anole Archimedes Aristophanes Anaximander",
    "Bilby Binturong Blobfish Bonobo Bustard Basalt Brutus Bellerophon Bootes",
    "Capybara Coati Cuttlefish Caracal Cassowary Civet Cicero Calcite Cepheus",
    "Dikdik Dugong Dormouse Dodo Dragonet Daphnia Diogenes Demosthenes Dolomite",
    "Echidna Eland Ermine Egret Euclid Epictetus Euripides Empedocles Eocene Endive",
    "Fossa Ferret Firefly Feldspar Fulmar Frigatebird Fennec Ficus Flavius",
    "Gecko Galago Gerenuk Gibbon Goby Grouper Ginkgo Granite Glaucus Gypsum",
    "Hoatzin Hyrax Haddock Hagfish Hoopoe Horseshoe Hypatia Herodotus Hemlock",
    "Ibex Ibis Isopod Iguana Impala Indri Ichthyosaur Iamblichus Iridium",
    "Jerboa Jackdaw Jabiru Javelina Jellyfish Junco Juvenal Jute",
    "Kakapo Kinkajou Kookaburra Kob Krill Katydid Kudu Kea Kestrel Krypton",
    "Lemur Lamprey Loris Lungfish Lyrebird Lobster Lichen Lucretius Lapwing Lazuli",
    "Manatee Mantis Marmot Mudpuppy Muntjac Markhor Mole Maecenas Monazite Morel",
    "Numbat Narwhal Nuthatch Nudibranch Nautilus Nightjar Nematode Neoptolemus Nepenthe Nori",
    "Okapi Olingo Oarfish Osprey Octopus Onager Ovid Obsidian Oolite Oxpecker",
    "Pangolin Pika Puffin Platypus Porcupine Potoroo Pericles Pliny Plutarch Pyrite",
    "Quokka Quoll Quetzal Quelea Quahog Quagga Quipu Quartz Quince Quasar",
    "Ratel Rhea Rook Roach Rotifer Rockhopper Rhyolite Rhizome Romulus Rosetta",
    "Saiga Stoat Skink Spoonbill Sunbird Salamander Sculpin Sulla Strabo Scoria",
    "Tapir Tarsier Tern Tuatara Turaco Takin Trilobite Thucydides Tacitus Topaz",
    "Uakari Urial Umbrellabird Urchin Uromastyx Uintathere Ulna Umber Ulex Utopia",
    "Vaquita Vicuna Vole Vervet Viperfish Vampirefin Vitruvius Varro Vesuvianite Vorticella",
    "Wombat Wallaby Weevil Whimbrel Weta Wobbegong Waxwing Wolfram Wulfenite Wrasse",
    "Xerus Xenops Xeme Xantus Xiphias Xenophon Xylem Xenotime Xanthite Xerophyte",
    "Yapok Yabby Yak Yellowhammer Yeti Yaffle Yttrium Yarrow Yucca Ylem",
    "Zorilla Zebu Zokor Zander Zebrafinch Zooplankton Zeolite Zircon Ziggurat Zeno",
)


def _build_pools() -> dict[str, tuple[str, ...]]:
    by_letter: dict[str, list[str]] = defaultdict(list)
    for name in " ".join(_RAW_CANDIDATES).split():
        if name.casefold() not in SSA_TOP_1000_2024:
            by_letter[name[0].upper()].append(name)
    return {letter: tuple(names) for letter, names in sorted(by_letter.items())}


NAME_POOLS = _build_pools()
POOL_NAMES = tuple(name for names in NAME_POOLS.values() for name in names)


def live_session_names() -> list[str]:
    """All tmux session names; an unavailable server simply has no peers."""
    try:
        result = subprocess.run(
            ["tmux", "list-sessions", "-F", "#{session_name}"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    return [name for name in result.stdout.splitlines() if name]


def _words(session_name: str) -> list[str]:
    return [word for word in _WORDS.split(session_name) if any(c.isalpha() for c in word)]


def candidate_letters(session_name: str, peers: Iterable[str]) -> list[str]:
    """Letters preferred by the session's words, distinctive words first."""
    words = _words(session_name)
    if not words:
        return []

    other_words = {
        word.casefold()
        for peer in peers
        if peer != session_name
        for word in _words(peer)
    }
    distinctive = [word for word in words if word.casefold() not in other_words]
    ordered_words = distinctive or words[:1]
    ordered_words.extend(word for word in words if word not in ordered_words)

    letters: list[str] = []
    for word in ordered_words:
        letter = next((c.upper() for c in word if c.isalpha()), "")
        if letter and letter not in letters:
            letters.append(letter)
    return letters


def _choose_name(session_name: str, peers: Iterable[str], issued: set[str]) -> str:
    letters = candidate_letters(session_name, peers)
    for letter in letters:
        if name := next((n for n in NAME_POOLS.get(letter, ()) if n not in issued), ""):
            return name

    if name := next((n for n in POOL_NAMES if n not in issued), ""):
        return name

    number = 1
    while (name := f"Lemon-{number}") in issued:
        number += 1
    return name


def _directory_key(directory: str | Path) -> str:
    return str(Path(directory).expanduser().resolve())


def assign(
    directory: str | Path,
    session_name: str,
    peers: Sequence[str] | None = None,
) -> str:
    """Return the place's active name, atomically issuing one when absent."""
    directory_key = _directory_key(directory)
    peer_names = live_session_names() if peers is None else peers

    with db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            row = conn.execute(
                """
                SELECT name FROM lemon_name_issues
                WHERE directory = ? AND retired_at IS NULL
                """,
                (directory_key,),
            ).fetchone()
            if row:
                conn.commit()
                return str(row["name"])

            issued = {
                str(row["name"])
                for row in conn.execute("SELECT name FROM lemon_name_issues").fetchall()
            }
            name = _choose_name(session_name, peer_names, issued)
            conn.execute(
                """
                INSERT INTO lemon_name_issues(directory, name, issued_at)
                VALUES (?, ?, ?)
                """,
                (directory_key, name, time.time()),
            )
            conn.commit()
        except BaseException:
            conn.rollback()
            raise

    _log.info("issued lemon name %s for %s", name, directory_key)
    return name


def current_name(directory: str | Path) -> str:
    """The active name for a place, or an empty string if it has none."""
    return current_names([directory]).get(Path(directory), "")


def current_names(directories: Iterable[Path]) -> dict[Path, str]:
    """Active names for the requested directories, keyed by their input paths."""
    requested = list(directories)
    if not requested:
        return {}

    by_key = {_directory_key(directory): directory for directory in requested}
    placeholders = ", ".join("?" for _ in by_key)
    with db.connect() as conn:
        rows = conn.execute(
            f"""
            SELECT directory, name FROM lemon_name_issues
            WHERE retired_at IS NULL AND directory IN ({placeholders})
            """,
            tuple(by_key),
        ).fetchall()

    return {by_key[str(row["directory"])]: str(row["name"]) for row in rows}


def retire(directories: Iterable[str | Path]) -> None:
    """Retire active assignments while preserving every issued name forever."""
    keys = {_directory_key(directory) for directory in directories}
    if not keys:
        return

    placeholders = ", ".join("?" for _ in keys)
    with db.connect() as conn:
        conn.execute(
            f"""
            UPDATE lemon_name_issues SET retired_at = ?
            WHERE retired_at IS NULL AND directory IN ({placeholders})
            """,
            (time.time(), *keys),
        )
        conn.commit()
