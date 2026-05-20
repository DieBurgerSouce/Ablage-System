/**
 * PWA Icon Generator Script - Ablage-System
 * Generiert PNG-Icons aus dem SVG-Quellbild fuer alle PWA-Groessen.
 *
 * Voraussetzung: sharp muss installiert sein
 *   npm install sharp --save-dev
 *
 * Ausfuehrung:
 *   node scripts/generate-pwa-icons.js
 *
 * Generierte Assets:
 *   - Standard Icons: 72x72 bis 512x512
 *   - Maskable Icon: 512x512 mit Safe-Zone-Padding (10%)
 *   - Apple Touch Icon: 180x180
 *   - Shortcut Icons: 96x96 fuer Upload, Approve, Search
 *   - Splash Screens: Verschiedene iOS-Groessen
 */

import sharp from 'sharp';
import { readFileSync, writeFileSync, mkdirSync, existsSync } from 'fs';
import { join, dirname } from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const ICONS_DIR = join(__dirname, '../public/icons');
const SCREENSHOTS_DIR = join(__dirname, '../public/screenshots');
const SVG_SOURCE = join(ICONS_DIR, 'icon.svg');

// Standard PWA Icon Sizes (alle im manifest.json referenzierten Groessen)
const ICON_SIZES = [72, 96, 128, 144, 152, 192, 384, 512];

// Apple Touch Icon Size
const APPLE_TOUCH_SIZE = 180;

// Maskable icons need padding (safe zone is 80% of icon, so 10% padding each side)
const MASKABLE_SIZES = [512];

// iOS Splash Screen Sizes
const SPLASH_SIZES = [
  { width: 640, height: 1136 },   // iPhone 5
  { width: 750, height: 1334 },   // iPhone 6/7/8
  { width: 1242, height: 2208 },  // iPhone 6+/7+/8+
  { width: 1125, height: 2436 },  // iPhone X/XS
  { width: 1170, height: 2532 },  // iPhone 12/13
];

// Shortcut Icon Definitionen mit individuellen Farben
const SHORTCUT_ICONS = [
  { name: 'shortcut-upload', symbol: 'upload', color: '#4a9eff' },
  { name: 'shortcut-approve', symbol: 'check', color: '#22c55e' },
  { name: 'shortcut-search', symbol: 'search', color: '#f59e0b' },
];

/**
 * Generiert ein Shortcut-Icon SVG mit dem spezifizierten Symbol
 */
function generateShortcutSvg(symbol, color) {
  const symbolPath = {
    upload: '<path d="M48 16v40M28 36l20-20 20 20" stroke="white" stroke-width="6" stroke-linecap="round" stroke-linejoin="round" fill="none"/><rect x="24" y="64" width="48" height="8" rx="2" fill="white"/>',
    check: '<path d="M24 48l16 16 32-32" stroke="white" stroke-width="8" stroke-linecap="round" stroke-linejoin="round" fill="none"/>',
    search: '<circle cx="40" cy="40" r="20" stroke="white" stroke-width="6" fill="none"/><line x1="54" y1="54" x2="72" y2="72" stroke="white" stroke-width="8" stroke-linecap="round"/>',
  };

  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96">
    <circle cx="48" cy="48" r="44" fill="${color}"/>
    ${symbolPath[symbol] || ''}
  </svg>`;
}

async function generateIcons() {
  console.log('🚀 PWA Icon Generator - Ablage-System\n');

  // Ensure directories exist
  if (!existsSync(ICONS_DIR)) {
    mkdirSync(ICONS_DIR, { recursive: true });
  }
  if (!existsSync(SCREENSHOTS_DIR)) {
    mkdirSync(SCREENSHOTS_DIR, { recursive: true });
  }

  const svgBuffer = readFileSync(SVG_SOURCE);

  // 1. Generate standard icons
  console.log('📐 Generiere Standard-Icons...');
  for (const size of ICON_SIZES) {
    const outputPath = join(ICONS_DIR, `icon-${size}x${size}.png`);
    await sharp(svgBuffer)
      .resize(size, size)
      .png()
      .toFile(outputPath);
    console.log(`  ✓ icon-${size}x${size}.png`);
  }

  // 2. Generate Apple Touch Icon
  console.log('\n🍎 Generiere Apple Touch Icon...');
  const appleTouchPath = join(ICONS_DIR, 'apple-touch-icon.png');
  await sharp(svgBuffer)
    .resize(APPLE_TOUCH_SIZE, APPLE_TOUCH_SIZE)
    .png()
    .toFile(appleTouchPath);
  console.log(`  ✓ apple-touch-icon.png (${APPLE_TOUCH_SIZE}x${APPLE_TOUCH_SIZE})`);

  // 3. Generate maskable icons with safe zone padding
  console.log('\n🎭 Generiere Maskable Icons...');
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
    console.log(`  ✓ icon-maskable-${size}x${size}.png`);
  }

  // 4. Generate shortcut icons with individual symbols
  console.log('\n⚡ Generiere Shortcut-Icons...');
  for (const { name, symbol, color } of SHORTCUT_ICONS) {
    const outputPath = join(ICONS_DIR, `${name}.png`);
    const shortcutSvg = generateShortcutSvg(symbol, color);

    await sharp(Buffer.from(shortcutSvg))
      .resize(96, 96)
      .png()
      .toFile(outputPath);
    console.log(`  ✓ ${name}.png (96x96)`);
  }

  // 5. Generate splash screens (centered icon on background)
  console.log('\n📱 Generiere Splash Screens...');
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
    console.log(`  ✓ splash-${width}x${height}.png`);
  }

  // 6. Generate screenshot placeholders
  console.log('\n📸 Generiere Screenshot-Platzhalter...');
  const screenshots = [
    { name: 'desktop-1', width: 1920, height: 1080, label: 'Desktop' },
    { name: 'mobile-1', width: 750, height: 1334, label: 'Mobile' },
  ];
  for (const { name, width, height, label } of screenshots) {
    const outputPath = join(SCREENSHOTS_DIR, `${name}.png`);
    const iconSize = Math.min(width, height) * 0.3;

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
    console.log(`  ✓ ${name}.png (${width}x${height}) - ${label}`);
  }

  console.log('\n✅ Alle PWA Assets erfolgreich generiert!');
  console.log(`📁 Icons: ${ICONS_DIR}`);
  console.log(`📁 Screenshots: ${SCREENSHOTS_DIR}`);
}

generateIcons().catch(err => {
  console.error('❌ Fehler:', err.message);
  process.exit(1);
});
