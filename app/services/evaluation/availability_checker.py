# -*- coding: utf-8 -*-
"""
Availability Checker für PaddleOCR-VL Evaluierung.

Prüft die Verfügbarkeit von PaddleOCR-VL und dessen Abhängigkeiten
auf PyPI, PaddlePaddle Repositories und GitHub.

Features:
- Package-Verfügbarkeitsprüfung (PyPI, PaddlePaddle, GitHub)
- Semantische Versionierung und Vergleich
- Vollständiger Abhängigkeitsbericht
- Graceful Fallback-Dokumentation

Feinpoliert und durchdacht - Enterprise-grade Availability Checking.
"""

import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from functools import lru_cache
from typing import Optional, List, Dict, Any, Tuple

import structlog

logger = structlog.get_logger(__name__)


# =============================================================================
# Data Models
# =============================================================================

class PackageSource(Enum):
    """Quelle eines Python-Packages."""
    PYPI = "pypi"
    PADDLEPADDLE = "paddlepaddle"
    GITHUB = "github"
    LOCAL = "local"
    UNKNOWN = "unknown"


@dataclass
class AvailabilityResult:
    """Ergebnis der Verfügbarkeitsprüfung für ein Package."""
    package_name: str
    available: bool
    version: Optional[str] = None
    source: Optional[PackageSource] = None
    error_message: Optional[str] = None
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary für Serialisierung."""
        return {
            "package_name": self.package_name,
            "available": self.available,
            "version": self.version,
            "source": self.source.value if self.source else None,
            "error_message": self.error_message,
            "checked_at": self.checked_at.isoformat(),
        }


@dataclass
class DependencyReport:
    """Vollständiger Bericht über alle Abhängigkeiten."""
    paddleocr_vl: AvailabilityResult
    paddlepaddle_gpu: AvailabilityResult
    paddleocr: AvailabilityResult
    cuda: AvailabilityResult
    all_satisfied: bool
    fallback_available: bool
    fallback_version: Optional[str] = None
    recommendations: List[str] = field(default_factory=list)
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> Dict[str, Any]:
        """Konvertiert zu Dictionary für Serialisierung."""
        return {
            "paddleocr_vl": self.paddleocr_vl.to_dict(),
            "paddlepaddle_gpu": self.paddlepaddle_gpu.to_dict(),
            "paddleocr": self.paddleocr.to_dict(),
            "cuda": self.cuda.to_dict(),
            "all_satisfied": self.all_satisfied,
            "fallback_available": self.fallback_available,
            "fallback_version": self.fallback_version,
            "recommendations": self.recommendations,
            "generated_at": self.generated_at.isoformat(),
        }


# =============================================================================
# Version Comparison
# =============================================================================

class SemanticVersion:
    """Semantische Versionierung nach SemVer 2.0.0."""

    # Regex für semantische Versionen (major.minor.patch mit optionalen pre-release/build)
    VERSION_PATTERN = re.compile(
        r'^(?P<major>0|[1-9]\d*)'
        r'\.(?P<minor>0|[1-9]\d*)'
        r'\.(?P<patch>0|[1-9]\d*)'
        r'(?:-(?P<prerelease>(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)'
        r'(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?'
        r'(?:\+(?P<buildmetadata>[0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$'
    )

    def __init__(self, version_string: str):
        """
        Initialisiert SemanticVersion aus String.

        Args:
            version_string: Version im Format "major.minor.patch[-prerelease][+build]"

        Raises:
            ValueError: Wenn Version nicht geparst werden kann
        """
        self.original = version_string
        self._parse(version_string)

    def _parse(self, version_string: str) -> None:
        """Parst Version-String in Komponenten."""
        # Entferne führendes 'v' falls vorhanden
        clean_version = version_string.lstrip('v').strip()

        match = self.VERSION_PATTERN.match(clean_version)
        if not match:
            # Versuche einfaches Format (z.B. "3.3.2" oder "2.6.0")
            simple_match = re.match(r'^(\d+)\.(\d+)\.(\d+)', clean_version)
            if simple_match:
                self.major = int(simple_match.group(1))
                self.minor = int(simple_match.group(2))
                self.patch = int(simple_match.group(3))
                self.prerelease = None
                self.build = None
                return
            raise ValueError(f"Ungültiges Versionsformat: {version_string}")

        self.major = int(match.group('major'))
        self.minor = int(match.group('minor'))
        self.patch = int(match.group('patch'))
        self.prerelease = match.group('prerelease')
        self.build = match.group('buildmetadata')

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SemanticVersion):
            return NotImplemented
        return (self.major, self.minor, self.patch, self.prerelease) == \
               (other.major, other.minor, other.patch, other.prerelease)

    def __lt__(self, other: 'SemanticVersion') -> bool:
        if not isinstance(other, SemanticVersion):
            return NotImplemented

        # Vergleiche major.minor.patch
        if (self.major, self.minor, self.patch) != (other.major, other.minor, other.patch):
            return (self.major, self.minor, self.patch) < (other.major, other.minor, other.patch)

        # Pre-release Versionen sind kleiner als Release-Versionen
        if self.prerelease is None and other.prerelease is not None:
            return False
        if self.prerelease is not None and other.prerelease is None:
            return True
        if self.prerelease is None and other.prerelease is None:
            return False

        # Vergleiche Pre-release Identifier
        return self._compare_prerelease(self.prerelease, other.prerelease) < 0

    def __le__(self, other: 'SemanticVersion') -> bool:
        return self == other or self < other

    def __gt__(self, other: 'SemanticVersion') -> bool:
        return not self <= other

    def __ge__(self, other: 'SemanticVersion') -> bool:
        return not self < other

    def _compare_prerelease(self, a: str, b: str) -> int:
        """Vergleicht Pre-release Identifier."""
        parts_a = a.split('.')
        parts_b = b.split('.')

        for pa, pb in zip(parts_a, parts_b):
            # Numerische Identifier werden numerisch verglichen
            if pa.isdigit() and pb.isdigit():
                if int(pa) != int(pb):
                    return int(pa) - int(pb)
            # Alphanumerische werden lexikographisch verglichen
            elif pa != pb:
                return -1 if pa < pb else 1

        # Längere Pre-release hat höhere Priorität
        return len(parts_a) - len(parts_b)

    def __str__(self) -> str:
        result = f"{self.major}.{self.minor}.{self.patch}"
        if self.prerelease:
            result += f"-{self.prerelease}"
        if self.build:
            result += f"+{self.build}"
        return result

    def __repr__(self) -> str:
        return f"SemanticVersion('{self}')"


def compare_versions(version_a: str, version_b: str) -> int:
    """
    Vergleicht zwei Versionen.

    Args:
        version_a: Erste Version
        version_b: Zweite Version

    Returns:
        -1 wenn a < b, 0 wenn a == b, 1 wenn a > b

    Raises:
        ValueError: Wenn eine Version nicht geparst werden kann
    """
    va = SemanticVersion(version_a)
    vb = SemanticVersion(version_b)

    if va < vb:
        return -1
    elif va > vb:
        return 1
    return 0


def version_meets_requirement(installed: str, minimum: str) -> bool:
    """
    Prüft ob installierte Version Mindestanforderung erfüllt.

    Args:
        installed: Installierte Version
        minimum: Mindestens erforderliche Version

    Returns:
        True wenn installed >= minimum
    """
    return compare_versions(installed, minimum) >= 0


# =============================================================================
# Availability Checker
# =============================================================================

class AvailabilityChecker:
    """
    Prüft PaddleOCR-VL Verfügbarkeit und Abhängigkeiten.

    Unterstützt Prüfung auf:
    - PyPI (pip)
    - PaddlePaddle Repositories
    - GitHub Releases
    - Lokale Installation
    """

    # Bekannte Package-Namen und ihre Quellen
    KNOWN_PACKAGES = {
        "paddleocr-vl": PackageSource.PADDLEPADDLE,
        "paddleocr": PackageSource.PYPI,
        "paddlepaddle": PackageSource.PYPI,
        "paddlepaddle-gpu": PackageSource.PYPI,
    }

    # Mindestversionen für PaddleOCR-VL Evaluierung
    MIN_VERSIONS = {
        "paddleocr": "3.3.2",
        "paddlepaddle": "2.6.0",
        "paddlepaddle-gpu": "2.6.0",
    }

    def __init__(self):
        """Initialisiert AvailabilityChecker."""
        self._cache: Dict[str, AvailabilityResult] = {}
        logger.info("availability_checker_initialized")

    def check_package_availability(self, package_name: str) -> AvailabilityResult:
        """
        Prüft ob ein Package verfügbar ist.

        Prüft in folgender Reihenfolge:
        1. Lokale Installation (importierbar)
        2. PyPI (pip index)
        3. PaddlePaddle Repository (für paddle-spezifische Packages)

        Args:
            package_name: Name des zu prüfenden Packages

        Returns:
            AvailabilityResult mit Status, Version und Quelle
        """
        # Cache-Check
        if package_name in self._cache:
            cached = self._cache[package_name]
            # Cache für 5 Minuten gültig
            age = (datetime.now(timezone.utc) - cached.checked_at).total_seconds()
            if age < 300:
                return cached

        logger.info("checking_package_availability", package=package_name)

        # 1. Prüfe lokale Installation
        local_result = self._check_local_installation(package_name)
        if local_result.available:
            self._cache[package_name] = local_result
            return local_result

        # 2. Prüfe PyPI
        pypi_result = self._check_pypi(package_name)
        if pypi_result.available:
            self._cache[package_name] = pypi_result
            return pypi_result

        # 3. Für PaddlePaddle-spezifische Packages: Prüfe PaddlePaddle Repo
        if package_name in self.KNOWN_PACKAGES:
            if self.KNOWN_PACKAGES[package_name] == PackageSource.PADDLEPADDLE:
                paddle_result = self._check_paddlepaddle_repo(package_name)
                self._cache[package_name] = paddle_result
                return paddle_result

        # Package nicht gefunden
        result = AvailabilityResult(
            package_name=package_name,
            available=False,
            error_message=f"Package '{package_name}' nicht auf PyPI oder PaddlePaddle gefunden"
        )
        self._cache[package_name] = result
        return result

    def _check_local_installation(self, package_name: str) -> AvailabilityResult:
        """Prüft ob Package lokal installiert ist."""
        # Mapping von Package-Namen zu Import-Namen
        import_names = {
            "paddleocr": "paddleocr",
            "paddleocr-vl": "paddleocr_vl",
            "paddlepaddle": "paddle",
            "paddlepaddle-gpu": "paddle",
        }

        import_name = import_names.get(package_name, package_name.replace("-", "_"))

        try:
            # Versuche Import
            module = __import__(import_name)

            # Versuche Version zu ermitteln
            version = None
            if hasattr(module, "__version__"):
                version = module.__version__
            elif hasattr(module, "VERSION"):
                version = module.VERSION
            elif hasattr(module, "version"):
                if callable(module.version):
                    version = module.version()
                else:
                    version = module.version

            logger.info(
                "package_found_locally",
                package=package_name,
                version=version
            )

            return AvailabilityResult(
                package_name=package_name,
                available=True,
                version=version,
                source=PackageSource.LOCAL
            )
        except ImportError:
            return AvailabilityResult(
                package_name=package_name,
                available=False,
                error_message=f"Package '{package_name}' nicht lokal installiert"
            )

    def _check_pypi(self, package_name: str) -> AvailabilityResult:
        """Prüft Package-Verfügbarkeit auf PyPI."""
        try:
            # Verwende pip index versions (schneller als API-Aufruf)
            result = subprocess.run(
                [sys.executable, "-m", "pip", "index", "versions", package_name],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0:
                # Parse Version aus Output
                # Format: "package_name (x.y.z)"
                output = result.stdout.strip()
                version_match = re.search(r'\(([^)]+)\)', output)
                version = version_match.group(1) if version_match else None

                # Extrahiere neueste Version aus "Available versions:" Zeile
                versions_match = re.search(r'Available versions:\s*([^\n]+)', output)
                if versions_match:
                    versions = versions_match.group(1).split(',')
                    if versions:
                        version = versions[0].strip()

                logger.info(
                    "package_found_on_pypi",
                    package=package_name,
                    version=version
                )

                return AvailabilityResult(
                    package_name=package_name,
                    available=True,
                    version=version,
                    source=PackageSource.PYPI
                )

            return AvailabilityResult(
                package_name=package_name,
                available=False,
                error_message=f"Package '{package_name}' nicht auf PyPI gefunden"
            )

        except subprocess.TimeoutExpired:
            return AvailabilityResult(
                package_name=package_name,
                available=False,
                error_message="PyPI-Anfrage Timeout"
            )
        except Exception as e:
            logger.warning(
                "pypi_check_failed",
                package=package_name,
                error=str(e)
            )
            return AvailabilityResult(
                package_name=package_name,
                available=False,
                error_message=f"PyPI-Prüfung fehlgeschlagen: {str(e)}"
            )

    def _check_paddlepaddle_repo(self, package_name: str) -> AvailabilityResult:
        """
        Prüft Package-Verfügbarkeit im PaddlePaddle Repository.

        PaddleOCR-VL ist noch nicht öffentlich verfügbar (Stand Dezember 2025).
        Diese Methode dokumentiert den Status.
        """
        # PaddleOCR-VL 0.9B ist noch nicht öffentlich verfügbar
        if package_name == "paddleocr-vl":
            logger.info(
                "paddleocr_vl_not_available",
                message="PaddleOCR-VL 0.9B ist noch nicht öffentlich verfügbar"
            )
            return AvailabilityResult(
                package_name=package_name,
                available=False,
                source=PackageSource.PADDLEPADDLE,
                error_message=(
                    "PaddleOCR-VL 0.9B ist noch nicht öffentlich verfügbar. "
                    "Fallback zu PaddleOCR 3.3.2 empfohlen."
                )
            )

        return AvailabilityResult(
            package_name=package_name,
            available=False,
            error_message=f"Package '{package_name}' nicht im PaddlePaddle Repository gefunden"
        )

    def verify_version_requirements(
        self,
        installed_version: str,
        min_version: str
    ) -> bool:
        """
        Vergleicht installierte Version mit Mindestanforderung.

        Verwendet semantische Versionierung (SemVer 2.0.0).

        Args:
            installed_version: Aktuell installierte Version
            min_version: Mindestens erforderliche Version

        Returns:
            True wenn installed_version >= min_version

        Raises:
            ValueError: Wenn eine Version nicht geparst werden kann
        """
        return version_meets_requirement(installed_version, min_version)

    def _check_cuda_availability(self) -> AvailabilityResult:
        """Prüft CUDA-Verfügbarkeit."""
        try:
            import torch
            if torch.cuda.is_available():
                cuda_version = torch.version.cuda
                device_name = torch.cuda.get_device_name(0)

                logger.info(
                    "cuda_available",
                    version=cuda_version,
                    device=device_name
                )

                return AvailabilityResult(
                    package_name="cuda",
                    available=True,
                    version=cuda_version,
                    source=PackageSource.LOCAL
                )
            else:
                return AvailabilityResult(
                    package_name="cuda",
                    available=False,
                    error_message="CUDA nicht verfügbar (torch.cuda.is_available() = False)"
                )
        except ImportError:
            return AvailabilityResult(
                package_name="cuda",
                available=False,
                error_message="PyTorch nicht installiert"
            )
        except Exception as e:
            return AvailabilityResult(
                package_name="cuda",
                available=False,
                error_message=f"CUDA-Prüfung fehlgeschlagen: {str(e)}"
            )

    def get_dependency_report(self) -> DependencyReport:
        """
        Erstellt vollständigen Abhängigkeitsbericht.

        Prüft alle für PaddleOCR-VL erforderlichen Abhängigkeiten
        und gibt Empfehlungen für Fallback-Strategien.

        Returns:
            DependencyReport mit Status aller Abhängigkeiten
        """
        logger.info("generating_dependency_report")

        # Prüfe alle Abhängigkeiten
        paddleocr_vl = self.check_package_availability("paddleocr-vl")
        paddlepaddle_gpu = self.check_package_availability("paddlepaddle-gpu")
        paddleocr = self.check_package_availability("paddleocr")
        cuda = self._check_cuda_availability()

        # Prüfe Versionsanforderungen
        paddleocr_version_ok = False
        if paddleocr.available and paddleocr.version:
            try:
                paddleocr_version_ok = self.verify_version_requirements(
                    paddleocr.version,
                    self.MIN_VERSIONS["paddleocr"]
                )
            except ValueError:
                pass

        # Bestimme ob alle Anforderungen erfüllt sind
        all_satisfied = (
            paddleocr_vl.available and
            cuda.available and
            (paddlepaddle_gpu.available or paddleocr.available)
        )

        # Prüfe Fallback-Verfügbarkeit (PaddleOCR 3.3.2)
        fallback_available = paddleocr.available and paddleocr_version_ok
        fallback_version = paddleocr.version if fallback_available else None

        # Generiere Empfehlungen
        recommendations = []

        if not paddleocr_vl.available:
            recommendations.append(
                "PaddleOCR-VL 0.9B ist nicht verfügbar. "
                "Verwende PaddleOCR 3.3.2 als Fallback."
            )

        if not cuda.available:
            recommendations.append(
                "CUDA ist nicht verfügbar. GPU-basierte OCR-Backends "
                "werden nicht funktionieren."
            )

        if paddleocr.available and not paddleocr_version_ok:
            recommendations.append(
                f"PaddleOCR Version {paddleocr.version} ist veraltet. "
                f"Mindestens Version {self.MIN_VERSIONS['paddleocr']} erforderlich."
            )

        if fallback_available:
            recommendations.append(
                f"Fallback zu PaddleOCR {fallback_version} ist verfügbar und empfohlen."
            )

        report = DependencyReport(
            paddleocr_vl=paddleocr_vl,
            paddlepaddle_gpu=paddlepaddle_gpu,
            paddleocr=paddleocr,
            cuda=cuda,
            all_satisfied=all_satisfied,
            fallback_available=fallback_available,
            fallback_version=fallback_version,
            recommendations=recommendations
        )

        logger.info(
            "dependency_report_generated",
            all_satisfied=all_satisfied,
            fallback_available=fallback_available,
            recommendations_count=len(recommendations)
        )

        return report

    def clear_cache(self) -> None:
        """Leert den internen Cache."""
        self._cache.clear()
        logger.info("availability_cache_cleared")


# =============================================================================
# Singleton
# =============================================================================

_availability_checker: Optional[AvailabilityChecker] = None


@lru_cache(maxsize=1)
def get_availability_checker() -> AvailabilityChecker:
    """
    Gibt AvailabilityChecker-Singleton zurück (thread-safe).

    Returns:
        AvailabilityChecker Instanz
    """
    return AvailabilityChecker()
