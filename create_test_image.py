"""Create a test image with German text for OCR testing."""

from PIL import Image, ImageDraw, ImageFont
import os
from pathlib import Path

# Create test documents directory
test_dir = Path("test_documents")
test_dir.mkdir(exist_ok=True)

# Create an image with German text
width = 800
height = 1000
background_color = (255, 255, 255)  # White
text_color = (0, 0, 0)  # Black

# Create image
img = Image.new('RGB', (width, height), color=background_color)
draw = ImageDraw.Draw(img)

# Try to use a font with better German character support
try:
    # Try to use Arial or similar
    font_large = ImageFont.truetype("arial.ttf", 24)
    font_normal = ImageFont.truetype("arial.ttf", 16)
    font_small = ImageFont.truetype("arial.ttf", 14)
except (OSError, IOError):
    # Fallback to default font
    font_large = ImageFont.load_default()
    font_normal = ImageFont.load_default()
    font_small = ImageFont.load_default()

# Text content with German characters
text_lines = [
    ("RECHNUNG", font_large, 50),
    ("", font_normal, 80),
    ("Müller GmbH & Co. KG", font_normal, 110),
    ("Hauptstraße 123", font_normal, 130),
    ("80331 München", font_normal, 150),
    ("Deutschland", font_normal, 170),
    ("", font_normal, 190),
    ("USt-IdNr.: DE123456789", font_small, 210),
    ("HRB München 98765", font_small, 230),
    ("", font_normal, 250),
    ("Rechnungsnummer: 2024-001", font_normal, 270),
    ("Datum: 26.11.2024", font_normal, 290),
    ("", font_normal, 310),
    ("An:", font_normal, 330),
    ("Schmidt AG", font_normal, 350),
    ("Bahnhofstraße 45", font_normal, 370),
    ("10115 Berlin", font_normal, 390),
    ("", font_normal, 410),
    ("Leistungsbeschreibung:", font_normal, 430),
    ("", font_normal, 450),
    ("1. Softwareentwicklung für Ablage-System", font_normal, 470),
    ("   - OCR-Integration mit GPU-Beschleunigung", font_small, 490),
    ("   - Deutsche Texterkennung (ä, ö, ü, ß)", font_small, 510),
    ("   - Frakturschrift-Unterstützung", font_small, 530),
    ("   Einzelpreis: 15.000,00 €", font_normal, 550),
    ("", font_normal, 570),
    ("2. Beratungsleistungen", font_normal, 590),
    ("   - Architektur-Design", font_small, 610),
    ("   - Implementierungsberatung", font_small, 630),
    ("   Einzelpreis: 3.500,00 €", font_normal, 650),
    ("", font_normal, 670),
    ("Zwischensumme: 18.500,00 €", font_normal, 690),
    ("MwSt. 19%: 3.515,00 €", font_normal, 710),
    ("", font_normal, 730),
    ("GESAMTBETRAG: 22.015,00 €", font_large, 750),
    ("", font_normal, 780),
    ("Zahlbar innerhalb von 30 Tagen ohne Abzug.", font_small, 800),
    ("", font_normal, 820),
    ("IBAN: DE89 3704 0044 0532 0130 00", font_small, 840),
    ("BIC: COBADEFFXXX", font_small, 860),
    ("", font_normal, 880),
    ("Mit freundlichen Grüßen", font_normal, 900),
    ("Müller GmbH & Co. KG", font_normal, 920),
]

# Draw text
for text, font, y_pos in text_lines:
    if text:  # Only draw non-empty lines
        # Center text for title
        if text == "RECHNUNG":
            bbox = draw.textbbox((0, 0), text, font=font)
            text_width = bbox[2] - bbox[0]
            x_pos = (width - text_width) // 2
        else:
            x_pos = 50  # Left margin

        draw.text((x_pos, y_pos), text, fill=text_color, font=font)

# Save as PNG (easier to process than PDF for now)
output_path = test_dir / "test_invoice.png"
img.save(output_path, "PNG")
print(f"Test image created: {output_path}")

# Also create a simpler test image with just umlauts
img2 = Image.new('RGB', (600, 400), color=background_color)
draw2 = ImageDraw.Draw(img2)

simple_text = [
    ("Test für deutsche Umlaute:", font_large, 50),
    ("", font_normal, 100),
    ("Ä ä - Ö ö - Ü ü - ß", font_large, 150),
    ("Müller, Schröder, Größe", font_normal, 200),
    ("Überprüfung, Änderung, Öffnungszeiten", font_normal, 250),
    ("Straße, Maßnahme, außerdem", font_normal, 300),
]

for text, font, y_pos in simple_text:
    if text:
        draw2.text((50, y_pos), text, fill=text_color, font=font)

output_path2 = test_dir / "test_umlauts.png"
img2.save(output_path2, "PNG")
print(f"Umlaut test image created: {output_path2}")

print("\nTest images created successfully!")