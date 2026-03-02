# /validate-liqmap - Liquidation Map Coinank Validation

Validate our liquidation map (`/liquidations/levels`) against Coinank `liq-map` for a single exchange.
Target: **1:1 visual match** with Coinank native chart download. Threshold: **>= 95%**.

## Usage
```bash
/validate-liqmap [--exchange binance] [--timeframe 1w] [--headed]
```

## Repo Context

- **Local BTC page**: `http://localhost:8002/chart/derivatives/liq-map/binance/btcusdt/1w`
- **Local ETH page**: `http://localhost:8002/chart/derivatives/liq-map/binance/ethusdt/1w`
- **Frontend source**: `frontend/liq_map_1w.html` (reads `?symbol=` from query string)
- **Pipeline script**: `scripts/validate_liqmap_visual.py`
- **Coinank reference dependency**: `scripts/coinank_screenshot.py --product map`
- **Output directory**: `data/validation/liqmap/`
- **Manifest directory**: `data/validation/manifests/`
- **API endpoint**: `/liquidations/levels?symbol=BTCUSDT&model=openinterest&timeframe=7`

## Coinank Reference URLs

- **BTC liq-map 1w**: `https://coinank.com/chart/derivatives/liq-map/binance/btcusdt/1w`
- **ETH liq-map 1w**: `https://coinank.com/chart/derivatives/liq-map/binance/ethusdt/1w`

## Orchestration Flow

1. Run the full pipeline with dotenvx credentials injection:
   ```bash
   dotenvx run -f /media/sam/1TB/.env -- \
     uv run python scripts/validate_liqmap_visual.py \
     --exchange binance --coin BTC --coinank-timeframe 1w
   ```
2. The script will:
   - start FastAPI if needed
   - preflight `/liquidations/levels`
   - capture local screenshot (`/liq_map_1w.html`)
   - capture Coinank screenshot (native download when logged in, crop fallback)
   - write manifest JSON (including `visual_element_checklist`) under `data/validation/manifests/`
3. Pass the two output screenshots **and the manifest** to `alpha-visual` for element-by-element comparison

## Visual Element Checklist (1:1 Reference)

Every element below MUST be present and match the Coinank native chart download.
The checklist is also embedded in the manifest JSON for automated scoring.

### TIER 1 - BLOCKERS (any fail = FAIL immediately, score 0)

| ID | Element | What to verify |
|----|---------|----------------|
| T1-01 | Chart renders | No blank page, no "loading", no JS errors |
| T1-02 | Bars visible both sides | Stacked bars left of current price (long) AND right (short) |
| T1-03 | Current price marker | Red dashed vertical line present at correct price |
| T1-04 | Cumulative lines present | Red/pink line (long, descending L→R) AND green/cyan line (short, ascending L→R) |
| T1-05 | Price range contains current price | X-axis range includes current BTC/ETH price with margin on both sides |

### TIER 2 - STRUCTURAL ELEMENTS (each worth points toward 95% threshold)

| ID | Element | Coinank reference | What to verify |
|----|---------|-------------------|----------------|
| T2-01 | Chart type | Stacked vertical **bars** | Must be bars, NOT area/line chart |
| T2-02 | Leverage groups | **3 groups**: Low (blue), Medium (purple), High (orange/salmon) | Exactly 3 color groups, NOT 5 individual tiers |
| T2-03 | Leverage colors | Low=#5B8FF9-like blue, Medium=#B37FEB-like purple, High=#FF9C6E-like orange | Colors visually distinguishable and in correct family |
| T2-04 | Bar stacking order | Low (bottom) → Medium → High (top) | Stacking order matches Coinank |
| T2-05 | Cumulative Long fill | **Filled area** below red line (light pink, semi-transparent) | Area between red line and X-axis is filled, not just a line |
| T2-06 | Cumulative Short fill | **Filled area** below green line (light green/cyan, semi-transparent) | Area between green line and X-axis is filled, not just a line |
| T2-07 | Cumulative Long direction | Starts high at left edge, descends toward current price | Monotonically decreasing from left |
| T2-08 | Cumulative Short direction | Starts near zero at current price, ascends toward right edge | Monotonically increasing toward right |
| T2-09 | Current price label | Text "Current Price：XXXXX" above chart area | Label visible with price value, positioned above the dashed line |
| T2-10 | Current price arrow | Red upward-pointing arrow/triangle at top of dashed line | Arrow or triangle marker at the top of the vertical line |
| T2-11 | Current price dot | Red circle/dot at bottom of dashed line | Marker at the baseline of the vertical line |
| T2-12 | Y-axis left | Liquidation volume scale (M suffix) | Numbers with M suffix, no axis title text |
| T2-13 | Y-axis right | Cumulative scale (M or B suffix) | Numbers with M/B suffix, no axis title text |
| T2-14 | X-axis prices | Plain numbers without comma separator or $ sign | e.g. "60160" not "60,160" or "$60,160" |
| T2-15 | No axis title labels | No "Liquidation Volume", "Price Level (USD)" etc. | Only tick numbers, no descriptive axis labels |
| T2-16 | No chart title | No title text above chart | Coinank download has no title; legend only |
| T2-17 | Legend position | Horizontal, centered, above chart area | 3 items: "Low leverage", "Medium leverage", "High leverage" |
| T2-18 | Legend content | Only 3 leverage group entries | No cumulative lines or current price in legend |
| T2-19 | Background | White/light (#ffffff or near-white) | NOT dark/black background |
| T2-20 | Range slider | Horizontal zoom/pan slider at bottom of chart | Coinank has a range slider below the X-axis |
| T2-21 | Grid lines | Light horizontal grid lines on white background | Subtle, not prominent |

### TIER 3 - MAGNITUDE MATCH (data accuracy, not visual style)

| ID | Element | What to verify | Tolerance |
|----|---------|----------------|-----------|
| T3-01 | Volume order of magnitude | Y-axis left scale same order (both M or both B) | Same order of magnitude |
| T3-02 | Cumulative order of magnitude | Y-axis right scale same order | Same order of magnitude |
| T3-03 | Long/Short volume ratio | Both sides have meaningful volume | Ratio within 2x of Coinank |
| T3-04 | Top volume price zones | Highest bars at similar price levels | Top-5 levels within +-2% price |
| T3-05 | Price range coverage | Similar min/max prices on X-axis | Within +-10% of Coinank range |
| T3-06 | Leverage distribution | Dominant tier matches (typically Low > Medium > High) | Same ordering of dominance |

## Alpha-Visual Delegation Prompt

```text
Compare these two liquidation map screenshots element-by-element:
- Local map: <ours_screenshot_path>
- Coinank reference: <coinank_screenshot_path>
- Manifest with checklist: <manifest_path>

IMPORTANT: The target is a 1:1 visual copy of Coinank's native chart download.
Threshold for PASS: >= 95 similarity score.

Score each element from the checklist in the manifest:

TIER 1 - BLOCKERS (if ANY fails → score = 0, FAIL immediately):
- T1-01: Chart renders without errors
- T1-02: Stacked bars visible on BOTH sides of current price
- T1-03: Red dashed vertical current price line present
- T1-04: Both cumulative lines present (red descending, green ascending)
- T1-05: Price range includes current price

TIER 2 - STRUCTURAL MATCH (each element = ~4 points, 21 elements = 84 points max):
For each T2-XX element, score:
- MATCH (full points): Element present and visually identical to Coinank
- PARTIAL (half points): Element present but visually different (wrong color, position, style)
- MISSING (0 points): Element absent

Check specifically:
- T2-01: Bar chart (NOT area chart)
- T2-02: 3 leverage color groups (NOT 5 individual tiers)
- T2-03: Colors match Coinank (blue/purple/orange families)
- T2-04: Stacking order (low bottom, high top)
- T2-05 + T2-06: Filled area under BOTH cumulative curves (NOT just lines)
- T2-07 + T2-08: Cumulative curve directions correct
- T2-09 + T2-10 + T2-11: Current price label + arrow + dot
- T2-12 to T2-16: Axis formatting (no titles, plain numbers, M/B suffixes)
- T2-17 + T2-18: Legend (3 items, centered, horizontal)
- T2-19: White background
- T2-20: Range slider present
- T2-21: Light grid lines

TIER 3 - MAGNITUDE (each element = ~2.7 points, 6 elements = 16 points max):
- T3-01 to T3-06: Data magnitude comparison

SCORING:
- Total = TIER 2 score + TIER 3 score (TIER 1 is pass/fail gate)
- PASS if total >= 95 AND all TIER 1 pass
- FAIL otherwise

OUTPUT FORMAT:
```
### Liquidation Map Validation Result
- Exchange: {exchange}
- Timeframe: {timeframe}
- Local screenshot: `<path>`
- Coinank screenshot: `<path>`

#### TIER 1 - Blockers
| ID | Element | Result |
|----|---------|--------|
| T1-01 | Chart renders | PASS/FAIL |
| ... | ... | ... |

#### TIER 2 - Structure (X/84 points)
| ID | Element | Result | Points | Notes |
|----|---------|--------|--------|-------|
| T2-01 | Bar chart | MATCH/PARTIAL/MISSING | X/4 | ... |
| ... | ... | ... | ... | ... |

#### TIER 3 - Magnitude (X/16 points)
| ID | Element | Result | Points | Notes |
|----|---------|--------|--------|-------|
| T3-01 | Volume scale | MATCH/PARTIAL/MISSING | X/2.7 | ... |
| ... | ... | ... | ... | ... |

#### Summary
- TIER 1: ALL PASS / BLOCKED
- TIER 2: XX/84
- TIER 3: XX/16
- **Total: XX/100**
- **Decision: PASS / FAIL**

#### Top Mismatches
1. [T2-XX] Description of mismatch
2. ...
```

Important:
- Our map uses Binance-only data. Coinank liq-map for binance should match closely.
- Volume magnitudes may differ slightly due to timing; this is tolerated in TIER 3.
- TIER 2 structural elements must be near-identical for >= 95.
- If our chart still uses 5 individual leverage tiers, area chart, dark background,
  or missing cumulative fills, those are FAIL items in TIER 2.
```

## Validation Metrics

| Metric | Expected | Tolerance | Tier |
|--------|----------|-----------|------|
| Chart type | Stacked bars | Exact: bars not area | T2-01 |
| Leverage groups | 3 groups (Low, Medium, High) | Exact: 3 not 5 | T2-02 |
| Leverage colors | Blue, Purple, Orange | Same color family | T2-03 |
| Cumulative Long fill | Filled red/pink area | Fill present | T2-05 |
| Cumulative Short fill | Filled green/cyan area | Fill present | T2-06 |
| Current price marker | Dashed line + arrow + dot + label | All 4 sub-elements | T2-09..11 |
| Background | White | Not dark | T2-19 |
| Axis labels | Numbers only, no titles | No text labels | T2-12..16 |
| Legend | 3 items, centered, horizontal | Exact count and position | T2-17..18 |
| Range slider | Present at bottom | Visible | T2-20 |
| Price range | Within +-10% of Coinank | Covers current price | T3-05 |
| Volume magnitude | Same order of magnitude (M or B) | Not off by 10x+ | T3-01 |
| Long/Short ratio | Both present | Within 2x | T3-03 |

## Result Format

```markdown
### Liquidation Map Validation Result
- Exchange: binance
- Timeframe: 1w
- Local screenshot: `<ours_screenshot_path>`
- Coinank screenshot: `<coinank_screenshot_path>`
- Manifest: `<manifest_path>`
- TIER 1: ALL PASS / BLOCKED
- TIER 2: XX/84
- TIER 3: XX/16
- **Total: XX/100**
- **Decision: PASS (>= 95) / FAIL (< 95)**
- Top mismatches:
  1. ...
  2. ...
```

## Notes

- The `/liquidations/levels` endpoint is marked DEPRECATED but still functional.
- MMR is now computed per-bucket using official Binance tiers (not flat 0.4%).
- Leverage weights are parameterized (default: 15/30/25/20/10%).
- Coinank liq-map is per-exchange, making direct comparison with our Binance data possible.
- Credentials for Coinank login are read from `COINANK_USER` and `COINANK_PASSWORD` via dotenvx.
- The manifest JSON contains the full `visual_element_checklist` for automated/scripted scoring.
- Previous threshold was >= 70% (too low). Current target: >= 95% for 1:1 match.
