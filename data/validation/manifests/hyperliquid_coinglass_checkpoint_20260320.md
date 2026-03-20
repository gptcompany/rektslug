# Hyperliquid / CoinGlass checkpoint - 2026-03-20

## Scope
Checkpoint di handoff per la discovery `spec-026` su:
- distinzione CoinGlass per-exchange vs aggregata vs Hyperliquid
- parità CoinGlass Hyperliquid vs Rektslug/Hyperliquid-node
- discovery del timeframe implicito per la vista Hyperliquid
- verifica di modelli più efficaci per dati `L4` / fills / liquidations del nodo Hyperliquid

## Artifact principali da aprire per primi in una nuova sessione
- `specs/026-liqmap-model-calibration/spec.md`
- `data/validation/manifests/coinglass_hyperliquid_capture_manifest_20260320.md`
- `data/validation/manifests/coinglass_hyperliquid_live_findings_20260320.md`
- `data/validation/manifests/hyperliquid_filtered_candidate_windows_20260320.json`
- `data/validation/raw_provider_api/20260320T170833Z/manifest.json`

## Stato della spec
La `spec-026` è già stata estesa localmente per chiarire che CoinGlass espone tre viste distinte:
1. per-exchange
2. aggregata cross-exchange
3. Hyperliquid-specific

È stato anche aggiunto `P5` per Hyperliquid parity / timeframe discovery con open questions e investigation plan.

## Lato Hyperliquid-node: cosa è stato verificato
### Repo e dati
- Il repo locale del nodo è: `/media/sam/1TB/hyperliquid-node`
- I dati filtrati permanenti del nodo sono documentati in:
  - `/media/sam/1TB/hyperliquid-node/docs/ARCHITECTURE-infra.md`
  - `/media/sam/1TB/hyperliquid-node/ARCHITECTURE.md`
- I path rilevanti sono:
  - `/media/sam/4TB-NVMe/hyperliquid/filtered/node_raw_book_diffs_by_block/`
  - `/media/sam/4TB-NVMe/hyperliquid/filtered/node_fills_by_block/`
  - `/media/sam/4TB-NVMe/hyperliquid/filtered/node_order_statuses_by_block/`

### Significato dei dati
- `node_fills_by_block` è documentato come `fills + liquidations`.
- Nei docs del nodo compare il campo `liquidation` con `liquidatedUser`, `markPx`, `method`.
- `ARCHITECTURE.md` parla di retention filtrata almeno per `BTC/ETH/HYPE`; per la repo `rektslug` il focus operativo resta `BTC/ETH`.
- In `rektslug`, `scripts/ingest_hl_fills.py` costruisce `hl_fills_l4`, mentre `hl_liquidations_l4` deriva da:
  - `direction in ('Close Long', 'Close Short')`
  - `closed_pnl < 0`
  - `crossed = true`

## Lato CoinGlass: capture browser locale
### Run salvato
È stato eseguito un capture locale Playwright del repo con:
- provider `coinglass`
- coin richiesto `ETH`
- timeframe richiesto `1w`
- page URL `https://www.coinglass.com/pro/futures/LiquidationMap`

Artifact:
- `data/validation/raw_provider_api/20260320T170833Z/manifest.json`

### Finding chiave
Il run è riproducibile ma NON è ancora un vero capture Hyperliquid `ETH` end-to-end.

Il manifest mostra:
- `args.coin = ETH`
- `requested_ui_timeframe = 7 day`
- `symbol_applied = None`
- `timeframe_applied = false`
- URLs catturate:
  - `https://capi.coinglass.com/api/index/5/liqMap?merge=true&symbol=Binance_BTCUSDT&interval=1&limit=1500&data=REDACTED`
  - `https://capi.coinglass.com/api/hyperliquid/topPosition/liqMap?symbol=BTC`

Conclusione:
- passare `--coin ETH` non basta, nello stato attuale, a ottenere un capture Hyperliquid `ETH` valido
- l’automazione attuale resta agganciata al default `BTC` della pagina
- l’harness CoinGlass Hyperliquid non è ancora corretto

## Perché lo script CoinGlass oggi sbaglia widget
Analizzando `scripts/capture_provider_api.py`:
- `build_targets()` salva `coin` e `ui_timeframe`, ma non usa `--exchange` per differenziare il comportamento Hyperliquid
- `apply_coinglass_symbol()` cerca il combobox con testo che contiene `Perpetual`, quindi il widget Binance per-exchange
- `coinglass_direct_fetch()` riscrive solo `**/api/index/5/liqMap*`, cioè il path CoinGlass per-exchange/Binance

Conclusione:
- lo script è costruito attorno alla vista principale per-exchange
- non ha ancora un path dedicato per il widget `Hyperliquid Liquidation Map`

## Probe Playwright locale sulla pagina CoinGlass
Un probe locale separato ha restituito:
- URL: `https://www.coinglass.com/pro/futures/LiquidationMap`
- Titolo: `Cryptocurrency Liquidation Map, Crypto Liquidation Map, Bitcoin Liquidation Map, BTC Liquidation Levels | CoinGlass`
- H1 visibili:
  - `Binance BTC/USDT Liquidation Map`
  - `Bitcoin Exchange Liquidation Map`
  - `Hyperliquid Liquidation Map`
- Combobox visibili:
  - indice `1`: `Binance BTC/USDT Perpetual`
  - indice `3`: `BTC`
  - indice `4`: combobox vicino alla sezione aggregata
  - indice `5`: `BTC`

Interpretazione operativa:
- la pagina ha davvero tre widget distinti
- il combobox `Perpetual` è quello della vista Binance per-exchange
- il combobox Hyperliquid sembra un controllo separato vicino alla sezione `Hyperliquid Liquidation Map`
- la patch futura deve agganciarsi al widget relativo all’heading `Hyperliquid Liquidation Map`, non al primo combobox globale con testo `Perpetual`

## Decode storico Hyperliquid CoinGlass
L’audit storico già svolto mostra che i decode riusciti del payload Hyperliquid producono un oggetto con:
- chiavi top-level: `price`, `list`
- nella `list`: campi come `coin`, `entryPrice`, `leverage`, `liquidationPrice`, `margin`, `positionUsd`, `size`, `type`, `unrealizedPnl`, `updateTime`, `userId`

Interpretazione:
- l’endpoint Hyperliquid CoinGlass sembra più un feed di `top positions / position risk` che una heatmap già bucketizzata
- per confrontarlo con Rektslug probabilmente serve una trasformazione ulteriore da lista-posizioni a superficie/mappa

## Risultati raw dal lato nostro: finestra 1d / 7d
Artifact:
- `data/validation/manifests/hyperliquid_filtered_candidate_windows_20260320.json`

Filtro usato:
- coin: `BTC`, `ETH`
- sorgente: `/media/sam/4TB-NVMe/hyperliquid/filtered/node_fills_by_block/hourly`
- condizioni evento:
  - `direction in ('Close Long', 'Close Short')`
  - `closed_pnl < 0`
  - `crossed = true`
- bucketizzazione:
  - `BTC`: step `100`
  - `ETH`: step `10`

### 1d
- Files letti: `61`
- BTC:
  - `fills_seen = 2,909,740`
  - `liq_events = 69`
  - top bucket per notional: `70700`, `70300`, `70500`, `70400`, `70000`
- ETH:
  - `fills_seen = 1,200,254`
  - `liq_events = 17`
  - top bucket per notional: `2140`, `2150`, `2130`

### 7d
- Files letti: `181`
- BTC:
  - `fills_seen = 8,137,854`
  - `liq_events = 711`
  - top bucket per notional: `70700`, `69600`, `73600`, `71300`, `73800`
- ETH:
  - `fills_seen = 3,239,352`
  - `liq_events = 224`
  - top bucket per notional: `2260`, `2310`, `2320`, `2300`, `2340`

Lettura pratica:
- la finestra `7d` lato nostro produce già una struttura abbastanza ricca da poter essere confrontata con una vista vendor-style
- la finestra `1d` è molto più sparsa, soprattutto su `ETH`
- questo non prova che CoinGlass usi `7d`, ma rende `7d` una candidata sensata da testare per il discovery Hyperliquid

## Verifica con fonti ufficiali / primarie
### Hyperliquid docs ufficiali
Fonti usate:
- `https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint`
- `https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint/perpetuals`
- `https://hyperliquid.gitbook.io/hyperliquid-docs/trading/liquidations`

Cosa emerge:
- l’endpoint `info` / perpetuals può esporre stato posizione per utente/account noto, inclusi `leverage`, `marginUsed`, `positionValue`, `liquidationPx`
- le superfici ufficiali di book data (`l2book` e simili) sono dati di profondità di mercato, non stato account/levas/liquidation-price di tutti i partecipanti

### Repo Hyperliquid-dex `order_book_server`
Fonte usata:
- `https://github.com/hyperliquid-dex/order_book_server`

Cosa emerge:
- quel repo dice di offrire `l2book` e `trades` in stile API ufficiale
- introduce un endpoint separato `l4Book`
- `l4Book` richiede un nodo non-validating che scriva `fills`, `order statuses` e `raw book diffs`

Caveat importante:
- il repo dichiara esplicitamente di NON essere scritto dal core team Hyperliquid Labs
- resta però utile come riferimento dell’org `hyperliquid-dex` per mostrare che una ricostruzione L4 richiede output del nodo, non il solo `L2`

## Risposta tecnica provvisoria alla domanda “CoinGlass sta usando per pigrizia il solo L2 pubblico?”
Questa è un’inferenza, non un fatto confermato.

L’evidenza attuale va contro l’ipotesi “solo L2 pubblico”:
- i payload Hyperliquid CoinGlass decodificati contengono campi account/position-level come `margin`, `leverage`, `liquidationPrice`, `positionUsd`, `userId`
- il solo `L2` pubblico non contiene quel tipo di stato
- le docs Hyperliquid mostrano che `liquidationPx` e stato posizione esistono lato account-state / posizione, non come semplice informazione di orderbook

Ipotesi più difendibile allo stato attuale:
- CoinGlass Hyperliquid sembra basarsi su ricostruzione o aggregazione di stato posizione/account, oppure su una sorgente equivalente più ricca del puro `L2`

## Risposta tecnica provvisoria alla domanda “Esistono modelli più effettivi per i dati del nodo Hyperliquid?”
Sì, in termini di modellazione sono più promettenti dei semplici istogrammi di liquidazioni recenti.

Modelli candidati più forti:
1. `Position-state reconstruction`
   - ricostruire stato posizione per utente o per coorti a partire da `fills + order statuses + mark/oracle`
   - poi calcolare bande/superficie di liquidazione
2. `Position-cohort risk surface`
   - raggruppare posizioni per lato, leva, entry band, recency
   - derivare bande di liquidazione aggregate
3. `Book-aware impact overlay`
   - combinare bande di liquidazione con profondità `L4` del book
   - stimare dove una cascata di liquidazioni incontra o svuota liquidità

Modello più debole:
- usare solo gli eventi di liquidazione già avvenuti o i soli fill come mappa futura del rischio

## Prossimi passi raccomandati
1. patchare `scripts/capture_provider_api.py` con un path esplicito per il widget Hyperliquid
2. rilanciare il capture locale e verificare che la URL salvata sia davvero `api/hyperliquid/topPosition/liqMap?symbol=ETH`
3. scegliere se confrontare CoinGlass vs Rektslug a livello:
   - `position list`
   - oppure `surface/map` derivata
4. usare i risultati `1d/7d` già salvati come baseline lato nostro per il confronto iniziale

## Avvertenza finale
Non assumere che CoinGlass Hyperliquid sia limitato globalmente a `BTC/ETH`:
- i run storici salvati nella repo erano `BTC`-only
- un precedente spot-check live aveva mostrato più simboli nel selector Hyperliquid
- per questa repo stiamo scegliendo `BTC/ETH` per coerenza di scope, non perché CoinGlass sembri limitato a quei due asset
