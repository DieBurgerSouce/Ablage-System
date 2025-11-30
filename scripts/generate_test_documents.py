#!/usr/bin/env python
"""
Generate synthetic German test documents for OCR validation.

Creates images with known text content for ground-truth comparison.
Generates 30+ documents across multiple categories.

Usage:
    python scripts/generate_test_documents.py
    python scripts/generate_test_documents.py --output tests/fixtures/german_docs
    python scripts/generate_test_documents.py --category invoices --count 6
"""

import argparse
import json
import os
import random
import string
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# Try to import PIL for image generation
try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("Warning: PIL not installed. Run: pip install Pillow")


@dataclass
class GroundTruth:
    """Ground truth for a generated document."""
    filename: str
    category: str
    source: str = "synthetic"
    expected_text: str = ""
    expected_entities: dict = None
    has_umlauts: bool = False
    has_tables: bool = False
    language: str = "de"
    license: str = "CC0"

    def __post_init__(self):
        if self.expected_entities is None:
            self.expected_entities = {}


class GermanTextGenerator:
    """Generate realistic German text content."""

    # German company names with umlauts
    COMPANY_NAMES = [
        "Müller GmbH & Co. KG",
        "Schröder Technik AG",
        "Böhm Elektrotechnik",
        "Günther & Söhne",
        "Köhler Maschinenbau",
        "Jäger Systemtechnik GmbH",
        "Größmann Consulting",
        "Früh Logistik",
        "Nürnberger Software Solutions",
        "Lübecker Handelshaus",
    ]

    # German street names
    STREETS = [
        "Musterstraße",
        "Hauptstraße",
        "Industrieweg",
        "Bahnhofstraße",
        "Königsallee",
        "Schillerplatz",
        "Goethestraße",
        "Münchner Straße",
        "Düsseldorfer Allee",
        "Kölner Ring",
    ]

    # German cities
    CITIES = [
        "München", "Berlin", "Hamburg", "Köln", "Frankfurt",
        "Stuttgart", "Düsseldorf", "Dortmund", "Essen", "Leipzig",
        "Bremen", "Dresden", "Nürnberg", "Hannover", "Bonn",
    ]

    # German first names
    FIRST_NAMES = [
        "Hans", "Jürgen", "Klaus", "Wolfgang", "Peter",
        "Günther", "Heinrich", "Friedrich", "Karl", "Werner",
        "Sabine", "Ursula", "Ingrid", "Monika", "Petra",
        "Bärbel", "Kätchen", "Gisela", "Renate", "Helga",
    ]

    # German last names
    LAST_NAMES = [
        "Müller", "Schmidt", "Schneider", "Fischer", "Weber",
        "Meyer", "Wagner", "Becker", "Schulz", "Hoffmann",
        "Schäfer", "Koch", "Bauer", "Richter", "Klein",
        "Schröder", "Neumann", "Schwarz", "Zimmermann", "Braun",
    ]

    # German product descriptions
    PRODUCTS = [
        "Softwareentwicklung",
        "IT-Beratung",
        "Systemintegration",
        "Hardwarelieferung",
        "Schulungsmaßnahmen",
        "Wartungsvertrag",
        "Projektmanagement",
        "Qualitätssicherung",
        "Netzwerkinstallation",
        "Datenbankoptimierung",
    ]

    @classmethod
    def random_company(cls) -> str:
        return random.choice(cls.COMPANY_NAMES)

    @classmethod
    def random_address(cls) -> tuple[str, str, str]:
        street = f"{random.choice(cls.STREETS)} {random.randint(1, 200)}"
        plz = f"{random.randint(10000, 99999)}"
        city = random.choice(cls.CITIES)
        return street, plz, city

    @classmethod
    def random_person(cls) -> str:
        return f"{random.choice(cls.FIRST_NAMES)} {random.choice(cls.LAST_NAMES)}"

    @classmethod
    def random_iban(cls) -> str:
        """Generate a valid-looking German IBAN."""
        bank_code = f"{random.randint(10000000, 99999999)}"
        account = f"{random.randint(1000000000, 9999999999)}"
        return f"DE{random.randint(10, 99)}{bank_code}{account}"

    @classmethod
    def random_vat_id(cls) -> str:
        """Generate a valid-looking German VAT ID."""
        return f"DE{random.randint(100000000, 999999999)}"

    @classmethod
    def random_date(cls, days_back: int = 365) -> str:
        """Generate a random date in German format."""
        delta = timedelta(days=random.randint(0, days_back))
        date = datetime.now() - delta
        return date.strftime("%d.%m.%Y")

    @classmethod
    def random_currency(cls, min_val: float = 10.0, max_val: float = 10000.0) -> str:
        """Generate a random currency amount in German format."""
        value = random.uniform(min_val, max_val)
        return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " EUR"


class DocumentGenerator:
    """Generate test document images."""

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.text_gen = GermanTextGenerator()

        # Create output directories
        self.categories = [
            "invoices", "fraktur", "tables", "contracts",
            "forms", "handwritten", "mixed"
        ]
        for cat in self.categories:
            (output_dir / cat).mkdir(parents=True, exist_ok=True)

    def _get_font(self, size: int = 16, bold: bool = False) -> ImageFont.FreeTypeFont:
        """Get a font for text rendering."""
        # Try common fonts
        font_names = [
            "arial.ttf", "Arial.ttf",
            "DejaVuSans.ttf",
            "LiberationSans-Regular.ttf",
            "FreeSans.ttf",
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/consola.ttf",
        ]

        for font_name in font_names:
            try:
                return ImageFont.truetype(font_name, size)
            except (OSError, IOError):
                continue

        # Fallback to default
        return ImageFont.load_default()

    def generate_invoice(self, index: int) -> GroundTruth:
        """Generate a German invoice image."""
        filename = f"invoice_{index:03d}.png"
        filepath = self.output_dir / "invoices" / filename

        # Generate invoice content
        company = self.text_gen.random_company()
        street, plz, city = self.text_gen.random_address()
        date = self.text_gen.random_date(90)
        invoice_nr = f"2024-{random.randint(1000, 9999)}"
        iban = self.text_gen.random_iban()
        vat_id = self.text_gen.random_vat_id()

        # Generate line items
        items = []
        total_net = 0.0
        for _ in range(random.randint(2, 5)):
            product = random.choice(self.text_gen.PRODUCTS)
            price = round(random.uniform(100, 2000), 2)
            items.append((product, price))
            total_net += price

        vat = round(total_net * 0.19, 2)
        total_gross = total_net + vat

        # Build text content
        lines = [
            f"RECHNUNG Nr. {invoice_nr}",
            "",
            company,
            street,
            f"{plz} {city}",
            "",
            f"Datum: {date}",
            f"USt-IdNr.: {vat_id}",
            "",
            "Positionen:",
            "-" * 40,
        ]

        for product, price in items:
            price_str = f"{price:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
            lines.append(f"{product:<30} {price_str:>10} EUR")

        lines.extend([
            "-" * 40,
            f"Summe Netto:{total_net:>28,.2f} EUR".replace(",", "X").replace(".", ",").replace("X", "."),
            f"MwSt. 19%:{vat:>30,.2f} EUR".replace(",", "X").replace(".", ",").replace("X", "."),
            f"Summe Brutto:{total_gross:>27,.2f} EUR".replace(",", "X").replace(".", ",").replace("X", "."),
            "",
            f"IBAN: {iban}",
            "",
            "Zahlbar innerhalb 14 Tagen.",
            "",
            "Mit freundlichen Gruessen",
            company,
        ])

        text = "\n".join(lines)

        # Create image
        self._create_text_image(filepath, text)

        # Create ground truth
        return GroundTruth(
            filename=filename,
            category="invoices",
            expected_text=text,
            expected_entities={
                "invoice_number": [invoice_nr],
                "iban": [iban],
                "vat_id": [vat_id],
                "date": [date],
                "total_gross": [f"{total_gross:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")],
            },
            has_umlauts=True,
            has_tables=False,
        )

    def generate_table(self, index: int) -> GroundTruth:
        """Generate a German table document."""
        filename = f"table_{index:03d}.png"
        filepath = self.output_dir / "tables" / filename

        # Table headers
        headers = ["Artikelnr.", "Bezeichnung", "Menge", "Einzelpreis", "Gesamt"]

        # Generate table data
        rows = []
        total = 0.0
        for i in range(random.randint(4, 8)):
            art_nr = f"ART-{random.randint(1000, 9999)}"
            bezeichnung = random.choice(self.text_gen.PRODUCTS)
            menge = random.randint(1, 10)
            einzelpreis = round(random.uniform(50, 500), 2)
            gesamt = round(menge * einzelpreis, 2)
            total += gesamt
            rows.append([art_nr, bezeichnung, str(menge), f"{einzelpreis:.2f}", f"{gesamt:.2f}"])

        # Format table
        col_widths = [12, 25, 8, 12, 12]

        def format_row(cells: list[str]) -> str:
            return " | ".join(c.ljust(w) for c, w in zip(cells, col_widths))

        lines = [
            "ARTIKELLISTE",
            "",
            format_row(headers),
            "-" * sum(col_widths) + "-" * (len(col_widths) * 3),
        ]

        for row in rows:
            lines.append(format_row(row))

        lines.extend([
            "-" * sum(col_widths) + "-" * (len(col_widths) * 3),
            f"Gesamtsumme: {total:.2f} EUR",
        ])

        text = "\n".join(lines)
        self._create_text_image(filepath, text, width=900)

        return GroundTruth(
            filename=filename,
            category="tables",
            expected_text=text,
            expected_entities={
                "total": [f"{total:.2f}"],
                "row_count": [str(len(rows))],
            },
            has_umlauts=True,
            has_tables=True,
        )

    def generate_contract(self, index: int) -> GroundTruth:
        """Generate a German contract document."""
        filename = f"contract_{index:03d}.png"
        filepath = self.output_dir / "contracts" / filename

        company1 = self.text_gen.random_company()
        company2 = self.text_gen.random_company()
        date = self.text_gen.random_date(30)
        person1 = self.text_gen.random_person()
        person2 = self.text_gen.random_person()

        text = f"""DIENSTLEISTUNGSVERTRAG

zwischen

{company1}
vertreten durch {person1}
- nachfolgend "Auftraggeber" genannt -

und

{company2}
vertreten durch {person2}
- nachfolgend "Auftragnehmer" genannt -

wird folgender Vertrag geschlossen:

Paragraph 1 - Vertragsgegenstand
Der Auftragnehmer verpflichtet sich zur Erbringung
von IT-Dienstleistungen gemaess Leistungsbeschreibung.

Paragraph 2 - Verguetung
Die Verguetung betraegt 150,00 EUR pro Stunde.
Rechnungsstellung erfolgt monatlich.

Paragraph 3 - Laufzeit
Der Vertrag beginnt am {date} und wird auf
unbestimmte Zeit geschlossen.

Paragraph 4 - Kuendigung
Der Vertrag kann mit einer Frist von 3 Monaten
zum Monatsende gekuendigt werden.

Paragraph 5 - Gerichtsstand
Gerichtsstand ist Muenchen.


{person1:<30} {person2:>30}
Auftraggeber                           Auftragnehmer

Datum: {date}
"""

        self._create_text_image(filepath, text, width=700)

        return GroundTruth(
            filename=filename,
            category="contracts",
            expected_text=text,
            expected_entities={
                "company1": [company1],
                "company2": [company2],
                "date": [date],
            },
            has_umlauts=True,
            has_tables=False,
        )

    def generate_form(self, index: int) -> GroundTruth:
        """Generate a German form document."""
        filename = f"form_{index:03d}.png"
        filepath = self.output_dir / "forms" / filename

        person = self.text_gen.random_person()
        street, plz, city = self.text_gen.random_address()
        date = self.text_gen.random_date(30)

        text = f"""ANTRAGSFORMULAR

Antragsteller:
Name: {person}
Strasse: {street}
PLZ/Ort: {plz} {city}

Antragsdatum: {date}

Antragsgrund (bitte ankreuzen):
[X] Neuantrag
[ ] Verlaengerung
[ ] Aenderung

Begruendung:
_____________________________________________
_____________________________________________
_____________________________________________

Anlagen:
[ ] Personalausweis (Kopie)
[ ] Einkommensnachweis
[ ] Meldebescheinigung

Unterschrift: _______________________________

Datum: {date}
"""

        self._create_text_image(filepath, text, width=600)

        return GroundTruth(
            filename=filename,
            category="forms",
            expected_text=text,
            expected_entities={
                "name": [person],
                "date": [date],
                "city": [city],
            },
            has_umlauts=True,
            has_tables=False,
        )

    def generate_fraktur(self, index: int) -> GroundTruth:
        """Generate a Fraktur-style text (simulated with standard font)."""
        filename = f"fraktur_{index:03d}.png"
        filepath = self.output_dir / "fraktur" / filename

        # Historical German text samples
        texts = [
            """Vorrede

Es ist dem Menschen angeboren, dass er sich mit der
Geschichte seiner Vorfahren beschaeftiget, und die
Schicksale derselben zu erforschen suchet.

Dies ist der erste Theil unserer Abhandlung ueber
die deutschen Tugenden und Gebräuche.""",

            """Bekanntmachung

Allen Buergern und Einwohnern dieser Stadt wird
hiermit kundgethan, dass am kommenden Sonntage
ein grosses Fest stattfinden wird.

Die Obrigkeit ersucht alle Anwohner um ruehige
Theilnahme an den Feierlichkeiten.""",

            """Brief an einen Freund

Mein theurer Freund!

Ich ergreife die Feder, um Dir von den wundersamen
Ereignissen zu berichten, die sich jüngst in unserer
Stadt zugetragen haben.

Mit herzlichstem Grusse
Dein ergebener Diener""",
        ]

        text = random.choice(texts)
        self._create_text_image(filepath, text, width=600)

        return GroundTruth(
            filename=filename,
            category="fraktur",
            expected_text=text,
            expected_entities={},
            has_umlauts=True,
            has_tables=False,
        )

    def generate_handwritten(self, index: int) -> GroundTruth:
        """Generate simulated handwritten text."""
        filename = f"handwritten_{index:03d}.png"
        filepath = self.output_dir / "handwritten" / filename

        person = self.text_gen.random_person()
        date = self.text_gen.random_date(180)
        city = random.choice(self.text_gen.CITIES)

        texts = [
            f"""{city}, den {date}

Liebe Familie,

vielen Dank fuer euren Brief. Es freut
mich sehr, von euch zu hoeren.

Hier ist alles in Ordnung. Das Wetter
ist schoen und die Arbeit macht Spass.

Herzliche Gruesse
{person}""",

            f"""{city}, {date}

Notizen vom Meeting:
- Budget fuer Q4 genehmigt
- Neue Mitarbeiter ab Januar
- Projektstart am 15. naechsten Monats

TODO:
1. Angebot erstellen
2. Kunden anrufen
3. Unterlagen vorbereiten

{person}""",
        ]

        text = random.choice(texts)
        self._create_text_image(filepath, text, width=500, font_size=18)

        return GroundTruth(
            filename=filename,
            category="handwritten",
            expected_text=text,
            expected_entities={
                "date": [date],
                "city": [city],
            },
            has_umlauts=True,
            has_tables=False,
        )

    def generate_mixed(self, index: int) -> GroundTruth:
        """Generate a mixed content document."""
        filename = f"mixed_{index:03d}.png"
        filepath = self.output_dir / "mixed" / filename

        company = self.text_gen.random_company()
        date = self.text_gen.random_date(60)

        text = f"""GESCHAEFTSBERICHT 2024

{company}

Datum: {date}

1. Zusammenfassung

Das Geschaeftsjahr 2024 war erfolgreich.
Der Umsatz stieg um 15% gegenueber dem Vorjahr.

2. Umsatzentwicklung

| Quartal | Umsatz (EUR) | Wachstum |
|---------|--------------|----------|
| Q1      | 1.250.000    | +12%     |
| Q2      | 1.480.000    | +18%     |
| Q3      | 1.320.000    | +14%     |
| Q4      | 1.550.000    | +16%     |

Gesamtumsatz: 5.600.000 EUR

3. Ausblick

Fuer 2025 erwarten wir ein weiteres Wachstum
von 10-12%. Neue Maerkte in Oesterreich und
der Schweiz werden erschlossen.

gez. Geschaeftsfuehrung
"""

        self._create_text_image(filepath, text, width=700)

        return GroundTruth(
            filename=filename,
            category="mixed",
            expected_text=text,
            expected_entities={
                "company": [company],
                "date": [date],
                "total_revenue": ["5.600.000"],
            },
            has_umlauts=True,
            has_tables=True,
        )

    def _create_text_image(
        self,
        filepath: Path,
        text: str,
        width: int = 800,
        font_size: int = 14,
        padding: int = 40,
    ):
        """Create an image from text content."""
        if not PIL_AVAILABLE:
            # Create placeholder JSON only
            print(f"  [SKIP] {filepath.name} (PIL not available)")
            return

        font = self._get_font(font_size)

        # Calculate image dimensions
        lines = text.split("\n")
        line_height = font_size + 4
        height = len(lines) * line_height + padding * 2

        # Create image
        img = Image.new("RGB", (width, height), color="white")
        draw = ImageDraw.Draw(img)

        # Draw text
        y = padding
        for line in lines:
            draw.text((padding, y), line, fill="black", font=font)
            y += line_height

        # Add some noise/texture for realism
        # (optional - can make OCR more challenging)

        # Save image
        img.save(filepath)
        print(f"  [OK] {filepath.name}")

    def generate_all(
        self,
        counts: Optional[dict[str, int]] = None,
    ) -> list[GroundTruth]:
        """Generate all test documents."""
        if counts is None:
            counts = {
                "invoices": 6,
                "fraktur": 6,
                "tables": 6,
                "contracts": 6,
                "forms": 3,
                "handwritten": 3,
                "mixed": 3,
            }

        results = []

        print("\nGenerating test documents...")
        print("=" * 50)

        generators = {
            "invoices": self.generate_invoice,
            "fraktur": self.generate_fraktur,
            "tables": self.generate_table,
            "contracts": self.generate_contract,
            "forms": self.generate_form,
            "handwritten": self.generate_handwritten,
            "mixed": self.generate_mixed,
        }

        for category, count in counts.items():
            print(f"\n{category.upper()} ({count} documents):")
            generator = generators.get(category)
            if generator:
                for i in range(1, count + 1):
                    gt = generator(i)
                    results.append(gt)

                    # Save ground truth JSON
                    gt_path = self.output_dir / category / f"{gt.filename.replace('.png', '.json')}"
                    with open(gt_path, "w", encoding="utf-8") as f:
                        json.dump(asdict(gt), f, indent=2, ensure_ascii=False)

        print("\n" + "=" * 50)
        print(f"Generated {len(results)} documents total.")

        # Create README
        self._create_readme(results)

        return results

    def _create_readme(self, results: list[GroundTruth]):
        """Create README for the test documents."""
        readme = f"""# German Test Documents for OCR Validation

Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Summary

| Category | Count | Has Umlauts | Has Tables |
|----------|-------|-------------|------------|
"""

        for cat in self.categories:
            cat_results = [r for r in results if r.category == cat]
            if cat_results:
                umlauts = all(r.has_umlauts for r in cat_results)
                tables = any(r.has_tables for r in cat_results)
                readme += f"| {cat} | {len(cat_results)} | {'Yes' if umlauts else 'No'} | {'Yes' if tables else 'No'} |\n"

        readme += f"""
## Total: {len(results)} documents

## Categories

### Invoices
German invoices with IBAN, VAT ID, dates, and currency amounts.

### Fraktur
Historical German text in Fraktur style (simulated).

### Tables
Documents containing structured table data.

### Contracts
Formal German contract documents.

### Forms
Government-style form documents.

### Handwritten
Simulated handwritten German text.

### Mixed
Documents combining multiple element types.

## Ground Truth Format

Each document has a corresponding JSON file with ground truth:

```json
{{
  "filename": "invoice_001.png",
  "category": "invoices",
  "source": "synthetic",
  "expected_text": "...",
  "expected_entities": {{
    "iban": ["DE89..."],
    "date": ["22.11.2024"]
  }},
  "has_umlauts": true,
  "has_tables": false,
  "language": "de",
  "license": "CC0"
}}
```

## License

All documents are synthetic and licensed under CC0 (Public Domain).
"""

        readme_path = self.output_dir / "README.md"
        with open(readme_path, "w", encoding="utf-8") as f:
            f.write(readme)

        print(f"\nREADME created: {readme_path}")


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate synthetic German test documents for OCR validation"
    )
    parser.add_argument(
        "--output", "-o",
        type=Path,
        default=Path("tests/fixtures/german_docs"),
        help="Output directory (default: tests/fixtures/german_docs)"
    )
    parser.add_argument(
        "--category", "-c",
        type=str,
        choices=["invoices", "fraktur", "tables", "contracts", "forms", "handwritten", "mixed", "all"],
        default="all",
        help="Category to generate (default: all)"
    )
    parser.add_argument(
        "--count", "-n",
        type=int,
        default=None,
        help="Number of documents per category (default: varies by category)"
    )
    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_args()

    if not PIL_AVAILABLE:
        print("ERROR: Pillow is required for image generation.")
        print("Install it with: pip install Pillow")
        sys.exit(1)

    generator = DocumentGenerator(args.output)

    if args.category == "all":
        counts = None  # Use defaults
        if args.count:
            counts = {cat: args.count for cat in generator.categories}
        generator.generate_all(counts)
    else:
        counts = {args.category: args.count or 6}
        generator.generate_all(counts)


if __name__ == "__main__":
    main()
