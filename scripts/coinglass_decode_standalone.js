#!/usr/bin/env node
"use strict";

/**
 * Standalone CoinGlass payload decoder.
 * Uses crypto-js + pako directly (no bundle needed).
 *
 * Usage:
 *   node coinglass_decode_standalone.js --summary <summary.json>
 *   node coinglass_decode_standalone.js --ciphertext-file <file> --user <user_header> --time <time_header>
 */

const fs = require("fs");
const path = require("path");
const CryptoJS = require("crypto-js");
const pako = require("pako");

const STATIC_SEED_SOURCES = {
  "55": "170b070da9654622",
  "66": "d6537d845a964081",
  "77": "863f08689c97435b",
};

function parseArgs(argv) {
  const parsed = { summary: "", ciphertextFile: "", user: "", time: "" };
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    const next = argv[i + 1];
    if (arg === "--summary" && next) { parsed.summary = next; i++; }
    if (arg === "--ciphertext-file" && next) { parsed.ciphertextFile = next; i++; }
    if (arg === "--user" && next) { parsed.user = next; i++; }
    if (arg === "--time" && next) { parsed.time = next; i++; }
  }
  return parsed;
}

function deriveKey(timeHeader) {
  return Buffer.from(timeHeader, "utf-8").toString("base64").slice(0, 16);
}

function decrypt(ciphertext, key) {
  const decrypted = CryptoJS.AES.decrypt(
    ciphertext,
    CryptoJS.enc.Utf8.parse(key),
    { mode: CryptoJS.mode.ECB, padding: CryptoJS.pad.Pkcs7 }
  ).toString(CryptoJS.enc.Hex);

  if (!decrypted) return null;

  const bytes = new Uint8Array(
    decrypted.match(/[\da-f]{2}/gi).map((h) => parseInt(h, 16))
  );
  const inflated = pako.inflate(bytes);
  let text = Buffer.from(inflated).toString("utf8");
  if (text.startsWith('"')) text = text.slice(1);
  if (text.endsWith('"')) text = text.slice(0, -1);
  return text;
}

function isEncryptedCapture(capture) {
  const encryption = String(capture?.response_headers?.encryption || "").toLowerCase();
  return encryption === "true" || encryption === "1";
}

function isLiqMapCapture(capture) {
  const haystacks = [capture?.source_url, capture?.saved_file]
    .filter(Boolean)
    .map((value) => String(value).toLowerCase());
  return haystacks.some((value) => value.includes("/liqmap") || value.includes("liqmap"));
}

function selectSummaryCapture(summary) {
  const captures = Array.isArray(summary?.captures) ? summary.captures : [];
  if (!captures.length) return null;

  const encrypted = captures.filter(
    (capture) => isEncryptedCapture(capture) && capture?.response_headers?.user
  );
  const liqMapCaptures = encrypted.filter(isLiqMapCapture);

  return liqMapCaptures[0] || encrypted[0] || captures[0];
}

function resolveCaptureSeedSource(capture) {
  const version = String(capture?.response_headers?.v || capture?.request_headers?.v || "");
  if (!version) {
    return (
      capture?.response_headers?.time ||
      capture?.request_headers?.time ||
      capture?.request_headers?.["cache-ts-v2"] ||
      ""
    );
  }
  if (version === "0") {
    return capture?.request_headers?.["cache-ts-v2"] || "";
  }
  if (version === "2") {
    return capture?.response_headers?.time || capture?.request_headers?.time || "";
  }
  if (STATIC_SEED_SOURCES[version]) {
    return STATIC_SEED_SOURCES[version];
  }

  try {
    const sourceUrl = String(capture?.source_url || "");
    if (sourceUrl) {
      return new URL(sourceUrl).pathname || "";
    }
  } catch (_error) {
    // Fall back to empty string below.
  }

  return "";
}

function resolveCaptureTime(capture) {
  return resolveCaptureSeedSource(capture);
}

function resolveSavedFile(summaryPath, savedFile) {
  if (!savedFile) return "";
  if (fs.existsSync(savedFile)) return savedFile;
  return path.resolve(path.dirname(summaryPath), savedFile);
}

function main() {
  const args = parseArgs(process.argv.slice(2));

  let userHeader, timeHeader, ciphertext;

  if (args.summary) {
    const summary = JSON.parse(fs.readFileSync(args.summary, "utf8"));
    const capture = selectSummaryCapture(summary);
    if (!capture) {
      process.stderr.write("No captures found in summary\n");
      process.exit(1);
    }

    userHeader = capture.response_headers?.user;
    timeHeader = resolveCaptureSeedSource(capture);
    const dataFile = resolveSavedFile(args.summary, capture.saved_file);
    const payload = JSON.parse(fs.readFileSync(dataFile, "utf8"));
    ciphertext = payload.data;
  } else {
    userHeader = args.user;
    timeHeader = args.time;
    ciphertext = fs.readFileSync(args.ciphertextFile, "utf8");
  }

  if (!userHeader || !timeHeader || !ciphertext) {
    process.stderr.write("Missing required: user header, time header, ciphertext\n");
    process.exit(1);
  }

  // Stage 1: derive seed key from time header
  const seedKey = deriveKey(timeHeader);

  // Stage 2: decrypt user header to get payload key
  const payloadKey = decrypt(userHeader, seedKey);
  if (!payloadKey) {
    process.stderr.write("Failed to decrypt user header (empty result)\n");
    process.exit(1);
  }

  // Stage 3: decrypt data payload with payload key
  const result = decrypt(ciphertext, payloadKey.trim());
  if (!result) {
    process.stderr.write("Failed to decrypt data payload (empty result)\n");
    process.exit(1);
  }

  process.stdout.write(result);
}

if (require.main === module) {
  main();
}

module.exports = {
  decrypt,
  deriveKey,
  parseArgs,
  resolveCaptureSeedSource,
  resolveCaptureTime,
  resolveSavedFile,
  selectSummaryCapture,
};
