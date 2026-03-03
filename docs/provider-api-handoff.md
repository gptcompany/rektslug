# Provider API Reverse Engineering Handoff

## Date: 2026-03-03

## Objective

Reverse engineer the CoinGlass LiquidationMap frontend to replace the fragile
UI dropdown approach with a more robust, programmatic API capture strategy.

## Key Findings

### 1. CoinGlass `data` Query Parameter (FULLY DECODED)

The `data` parameter on `api/index/5/liqMap` (and other liqMap/liqHeatMap endpoints)
is generated client-side by a function in `_app-*.js`:

```javascript
function a() {
  var t = parseInt((new Date).getTime() / 1e3);   // Unix timestamp (seconds)
  var e = t + "," + authenticator.generate(
    "I65VU7K5ZQL7WB4E",                            // TOTP secret (base32)
    {time: t, step: 30}                             // 30-second TOTP window
  );
  return CryptoJS.AES.encrypt(
    e,
    CryptoJS.enc.Utf8.parse("1f68efd73f8d4921acc0dead41dd39bc"),  // AES-128 key
    {mode: CryptoJS.mode.ECB, padding: CryptoJS.pad.Pkcs7}
  ).toString();  // base64 output
}
```

**Python implementation** (now in `scripts/capture_provider_api.py`):

```python
import base64, time, pyotp
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

def generate_coinglass_data_param():
    ts = int(time.time())
    totp = pyotp.TOTP("I65VU7K5ZQL7WB4E", interval=30)
    otp_code = totp.at(ts)
    plaintext = f"{ts},{otp_code}"
    cipher = AES.new("1f68efd73f8d4921acc0dead41dd39bc".encode(), AES.MODE_ECB)
    encrypted = cipher.encrypt(pad(plaintext.encode(), AES.block_size))
    return base64.b64encode(encrypted).decode()
```

These are **public client-side constants** from the minified JS bundle.
They are anti-scraping measures, not secrets.

### 2. Timeframe to API Parameter Mapping (COMPLETE)

Source: `LiquidationMap-*.js` chunk, `onChangeTime` handler.

| UI Label   | Dropdown Value | `interval` | `limit` |
|-----------|---------------|-----------|---------|
| 1 day     | 1             | `1`       | 1500    |
| 7 day     | 7             | `5`       | 2000    |
| 30 day    | 30            | `30`      | 1440    |
| 90 day    | 90            | `90d`     | 1440    |
| 180 day   | 180           | `180d`    | 1440    |
| 1 year    | 365           | `365d`    | 1440    |

### 3. Authentication Mechanism

- Auth is via a **custom header** (not cookies).
- An axios request interceptor reads a token from storage (likely cookies-next or js-cookie)
  and attaches it as a header on every request.
- The interceptor is heavily obfuscated in the `_app` bundle.
- The token is set after successful login on `www.coinglass.com`.
- Cross-origin requests from `www.coinglass.com` to `capi.coinglass.com` work because
  the server returns `access-control-allow-headers: *`.
- **Direct programmatic API calls** (curl, urllib) cannot easily replicate this because
  the token extraction from the obfuscated interceptor is non-trivial.

### 4. Response Decryption

The response `data` field (when `encryption` header is present) is:

1. AES-ECB decrypted using the `user` response header as key
2. Pako-inflated (zlib decompressed)
3. Parsed as JSON

The existing `scripts/coinglass_decode_payload.js` handles this by loading
CryptoJS and pako from the saved `_app` bundle.

### 5. Can We Bypass the Dropdown?

**Partially YES.** The implemented solution uses Playwright route interception:

1. Login via Playwright (mandatory for auth token)
2. Navigate to LiquidationMap page
3. Intercept the page's own `liqMap` request via `page.route()`
4. Rewrite the `interval`, `limit`, and `data` parameters
5. The page's authenticated request goes through with our desired params
6. Page reload triggers a fresh request with the right parameters

This is **more robust** than the dropdown because:
- No DOM element searching/clicking
- No race conditions with dropdown animation
- Exact control over parameters
- Works even if CoinGlass changes the dropdown UI

**Full browser bypass is NOT feasible** because:
- The auth token is managed by an obfuscated axios interceptor
- Cross-origin CORS restrictions prevent direct fetch/XHR with custom headers
- The login API is server-rendered (next-auth) with no simple REST endpoint

## Implementation Changes

### Modified Files

1. **`scripts/capture_provider_api.py`**
   - Added `generate_coinglass_data_param()` - Python TOTP+AES generation
   - Added `resolve_coinglass_interval_limit()` - timeframe to API param mapping
   - Added `coinglass_direct_fetch()` - route interception for param rewriting
   - New deps: `pyotp`, `pycryptodome`

2. **`pyproject.toml`** (via `uv add`)
   - Added `pyotp` and `pycryptodome` dependencies

### Unchanged Files

- `scripts/coinglass_decode_payload.js` - response decoder (works as-is)
- `scripts/compare_provider_liquidations.py` - comparator (works as-is)

## Verified Captures

### CoinGlass 1w (route interception)
- Manifest: `data/validation/raw_provider_api/20260303T165247Z/manifest.json`
- Login: success
- Timeframe applied: true
- Captures: 2 liqMap requests (default interval=1 + rewritten interval=5)
- Both returned `success=true` with encrypted data

### CoinGlass 1d (route interception)
- Manifest: `data/validation/raw_provider_api/20260303T165345Z/manifest.json`
- Login: success
- Timeframe applied: true
- Captures: 1 liqMap request (interval=1, same as default)
- Returned `success=true` with encrypted data

## URL Reference

### CoinGlass
- Login: `https://www.coinglass.com/login?act=liqmap`
- Liquidation Map (liq-map equivalent): `https://www.coinglass.com/pro/futures/LiquidationMap`
- Liquidation HeatMap (heatmap): `https://www.coinglass.com/pro/futures/LiquidationHeatMapNew`
- Public Liquidity Heatmap: `https://www.coinglass.com/LiquidityHeatmap`

### CoinAnk
- Liq map: `https://coinank.com/chart/derivatives/liq-map/binance/btcusdt/{timeframe}`
- Liq heatmap: `https://coinank.com/chart/derivatives/liq-heat-map/binance/btcusdt/{timeframe}`

### API Endpoints
- CoinGlass liqMap: `https://capi.coinglass.com/api/index/5/liqMap?merge=true&symbol=Binance_BTCUSDT&interval={interval}&limit={limit}&data={data}`
- CoinGlass exLiqMap: `https://capi.coinglass.com/api/index/2/exLiqMap?merge=true&symbol=BTC&interval={interval}&limit={limit}`
- CoinAnk getLiqMap: `https://api.coinank.com/api/liqMap/getLiqMap?exchange=Binance&symbol=BTCUSDT&interval={timeframe}`

## Frontend Bundle References

| File | Hash | Purpose |
|------|------|---------|
| `_app-*.js` | `94ee9e72c1d2190a` | Main bundle with API functions and interceptors |
| `LiquidationMap-*.js` | `e61d9cea2e1db745` | Page component with onChangeTime handler |
| Chunk 33638 | `b2f137eab4511f73` | Exchange-specific liquidation map chart |
| Chunk 74267 | `5c8fab292b36814d` | Aggregate liquidation map chart |

## Next Steps

1. **Monitor bundle hash changes** - If CoinGlass updates the frontend, the TOTP
   secret and AES key may change. The bundle URL hash will change when this happens.
2. **Consider headless cookie extraction** - If a fully browserless approach is
   desired, extract the auth token from the obfuscated interceptor by running the
   webpack module in Node.js (similar to the decoder approach).
3. **Test all timeframes** - Currently verified 1d and 1w. Test 30d, 90d, 180d, 1y.

## Commit History

- `28ba2ea` Add end-to-end provider comparison workflow
- `60bbd39` Decode Coinglass payloads and add SQL reporting
- (this commit) Reverse engineer CoinGlass data param and add route interception
