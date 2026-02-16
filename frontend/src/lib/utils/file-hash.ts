/**
 * Client-seitige SHA-256 Hash-Berechnung via Web Crypto API.
 * Keine externen Abhaengigkeiten.
 */

export async function computeFileHash(file: File): Promise<string> {
  const buffer = await file.arrayBuffer();
  const hashBuffer = await crypto.subtle.digest('SHA-256', buffer);
  return Array.from(new Uint8Array(hashBuffer))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}
