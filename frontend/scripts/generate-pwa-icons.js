/**
 * PWA Icon Generator Script
 * Generiert PNG-Icons aus dem SVG-Quellbild fuer alle PWA-Groessen.
 *
 * Voraussetzung: sharp muss installiert sein
 *   npm install sharp --save-dev
 *
 * Ausfuehrung:
 *   node scripts/generate-pwa-icons.js
 */

import sharp from 'sharp';
import { readFileSync, mkdirSync, existsSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const ICONS_DIR = join(__dirname, '../public/icons');
const SVG_SOURCE = join(ICONS_DIR, 'icon.svg');

// Standard PWA Icon Sizes
const ICON_SIZES = [72, 96, 128, 144, 152, 192, 384, 512];

// Maskable icons need padding (safe zone is 80% of icon)
const MASKABLE_SIZES = [192, 512];

// iOS Splash Screen Sizes
const SPLASH_SIZES = [
  { width: 640, height: 1136 },   // iPhone 5
  { width: 750, height: 1334 },   // iPhone 6/7/8
  { width: 1242, height: 2208 },  // iPhone 6+/7+/8+
  { width: 1125, height: 2436 },  // iPhone X/XS
  { width: 1170, height: 2532 },  // iPhone 12/13
];

async function generateIcons() {
  console.log('Generiere PWA Icons...\n');

  // Ensure icons directory exists
  if (!existsSync(ICONS_DIR)) {
    mkdirSync(ICONS_DIR, { recursive: true });
  }

  const svgBuffer = readFileSync(SVG_SOURCE);

  // Generate standard icons
  for (const size of ICON_SIZES) {
    const outputPath = join(ICONS_DIR, `icon-${size}x${size}.png`);
    await sharp(svgBuffer)
      .resize(size, size)
      .png()
      .toFile(outputPath);
    console.log(`  Erstellt: icon-${size}x${size}.png`);
  }

  // Generate maskable icons with safe zone padding
  for (const size of MASKABLE_SIZES) {
    const outputPath = join(ICONS_DIR, `icon-maskable-${size}x${size}.png`);
    const innerSize = Math.round(size * 0.8); // 80% for safe zone
    const padding = Math.round((size - innerSize) / 2);

    await sharp(svgBuffer)
      .resize(innerSize, innerSize)
      .extend({
        top: padding,
        bottom: padding,
        left: padding,
        right: padding,
        background: { r: 26, g: 26, b: 26, alpha: 1 }, // #1a1a1a
      })
      .png()
      .toFile(outputPath);
    console.log(`  Erstellt: icon-maskable-${size}x${size}.png`);
  }

  // Generate splash screens (centered icon on background)
  for (const { width, height } of SPLASH_SIZES) {
    const outputPath = join(ICONS_DIR, `splash-${width}x${height}.png`);
    const iconSize = Math.min(width, height) * 0.3; // Icon is 30% of smaller dimension

    // Create background
    const background = await sharp({
      create: {
        width,
        height,
        channels: 4,
        background: { r: 26, g: 26, b: 26, alpha: 1 }, // #1a1a1a
      },
    }).png().toBuffer();

    // Resize icon
    const icon = await sharp(svgBuffer)
      .resize(Math.round(iconSize), Math.round(iconSize))
      .png()
      .toBuffer();

    // Composite icon onto background
    await sharp(background)
      .composite([
        {
          input: icon,
          gravity: 'centre',
        },
      ])
      .png()
      .toFile(outputPath);
    console.log(`  Erstellt: splash-${width}x${height}.png`);
  }

  // Generate shortcut icons
  const shortcuts = ['upload', 'search'];
  for (const shortcut of shortcuts) {
    const outputPath = join(ICONS_DIR, `shortcut-${shortcut}.png`);
    // Use same icon for shortcuts (can be customized later)
    await sharp(svgBuffer)
      .resize(96, 96)
      .png()
      .toFile(outputPath);
    console.log(`  Erstellt: shortcut-${shortcut}.png`);
  }

  // Generate screenshot placeholders
  const screenshots = [
    { name: 'screenshot-wide', width: 1280, height: 720 },
    { name: 'screenshot-mobile', width: 390, height: 844 },
  ];
  for (const { name, width, height } of screenshots) {
    const outputPath = join(ICONS_DIR, `${name}.png`);
    const iconSize = Math.min(width, height) * 0.4;

    const background = await sharp({
      create: {
        width,
        height,
        channels: 4,
        background: { r: 26, g: 26, b: 26, alpha: 1 },
      },
    }).png().toBuffer();

    const icon = await sharp(svgBuffer)
      .resize(Math.round(iconSize), Math.round(iconSize))
      .png()
      .toBuffer();

    await sharp(background)
      .composite([{ input: icon, gravity: 'centre' }])
      .png()
      .toFile(outputPath);
    console.log(`  Erstellt: ${name}.png`);
  }

  console.log('\nAlle PWA Icons erfolgreich generiert!');
}

generateIcons().catch(console.error);
