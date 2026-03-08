// MEME COIN LP AUTO-SCREENER V2 - FILTER-FIRST SEARCH
// Fetches pools by chain (no predetermined token list), then applies filters and scoring
// Refreshes every X minutes with live filtered data

// ==================== CONFIGURATION ====================
const CONFIG = {
  // ---------- SET YOUR OWN VALUES BELOW (no defaults - choose your strategy) ----------
  // MINIMUM SAFETY FILTERS (pools below these are excluded)
  MIN_ABSOLUTE_LIQUIDITY: 0,   // Set your minimum liquidity in $ (e.g. 50000)
  MIN_ABSOLUTE_VOLUME: 0,      // Set your minimum 24h volume in $ (e.g. 50000)
  MIN_ABSOLUTE_TRANSACTIONS: 0, // Set your minimum 24h transaction count (e.g. 3000)

  // SCORING THRESHOLDS (used only for score calculation, not hard filters)
  GOOD_VOLUME_24H: 0,         // Set $ for "good" volume (e.g. 50000)
  GREAT_VOLUME_24H: 0,        // Set $ for "great" volume (e.g. 100000)
  GOOD_TVL: 0,                // Set $ for "good" TVL (e.g. 30000)
  GREAT_TVL: 0,               // Set $ for "great" TVL (e.g. 100000)

  // DISPLAY SETTINGS
  MIN_SCORE_TO_SHOW: 0,       // Show pools with score >= this (0-100, e.g. 20)
  MIN_ADJUSTED_APR_TO_SHOW: 0,// Show pools with adjusted APR >= this % (e.g. 30)
  MAX_RESULTS: 20,            // Max number of rows to show (e.g. 20)

  // SCORE WEIGHTS (must sum to 1.0)
  WEIGHT_POOL_QUALITY: 0.5,   // Weight for pool quality score (e.g. 0.6)
  WEIGHT_APR: 0.5,            // Weight for APR (e.g. 0.4)

  // Filter-first search: one query per chain (no token list)
    // Data sources: both DexScreener and GeckoTerminal for many pairs per chain
  CHAINS: ['solana', 'base'],
  USE_DEXSCREENER: true,
  USE_GECKOTERMINAL: true,
  // DexScreener: search by tokens → add your own tokens per chain (find pools that fit your strategy)
  DEXSCREENER_SEARCH_TOKENS: {
    solana: ['SOL', 'USDC'],
    base: ['WETH', 'USDC']
  },
  // GeckoTerminal: top pools by network (paginated); rate limit ~10/min
  GECKO_PAGES_PER_NETWORK: 3,
  GECKO_DELAY_MS: 7000,
  TOP_PAIRS_TOTAL: 500,
  REFRESH_TIME: 15,                 // Auto-refresh interval in minutes (trigger)
  // Email alert settings (set your own thresholds)
  EMAIL_ALERTS_ENABLED: true,
  EMAIL_ADDRESS: '',  // Set in Apps Script: File > Project properties, or use script property. See README.
  EMAIL_MIN_FINAL_SCORE: 0,   // Min combined score to send email (e.g. 65)
  EMAIL_MIN_APR: 0,            // Min APR % to send email (e.g. 100)

  // DEXs to exclude from results (e.g. private DEXs)
  EXCLUDED_DEX_IDS: [],

  // Sheet settings
  SHEET_NAME: 'LP Screener',
  DATA_START_ROW: 4
};

// ==================== MAIN FUNCTIONS ====================

/**
 * Main function - fetches and updates sheet
 */
function updateLPScreener() {
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(CONFIG.SHEET_NAME);
  if (!sheet) {
    Logger.log('Sheet not found: ' + CONFIG.SHEET_NAME);
    return;
  }

  Logger.log('Starting filter-first LP screener update...');
 const allPairs = fetchAllPools();
  const filteredPairs = filterPairs(allPairs);

  Logger.log('Found ' + allPairs.length + ' pairs, ' + filteredPairs.length + ' match criteria');

  updateSheet(sheet, filteredPairs);

  // Update last refresh timestamp
  sheet.getRange('A2').setValue('Last Update: ' + new Date().toLocaleString());
}

/**
 * Fetch from DexScreener: multiple token searches per chain to get many pairs.
 */
/**
 * Fetch from both DexScreener and GeckoTerminal, merge, dedupe by chain+address, sort by volume.
 */
 /**
 * Convert one DexScreener API pair to our internal pair format.
 */
function dexScreenerPairToPair(apiPair) {
  var vol = apiPair.volume || {};
  var txns = apiPair.txns || {};
  var liq = apiPair.liquidity || {};
  var pc = apiPair.priceChange || {};
  var base = apiPair.baseToken || {};
  var quote = apiPair.quoteToken || {};
  var h24Txns = txns.h24 || {};
  var h6Txns = txns.h6 || {};
  var h1Txns = txns.h1 || {};

  return {
    chainId: apiPair.chainId || '',
    pairAddress: apiPair.pairAddress || '',
    dexId: apiPair.dexId || 'unknown',
    baseToken: { symbol: base.symbol || 'BASE', address: base.address || '' },
    quoteToken: { symbol: quote.symbol || 'QUOTE', address: quote.address || '' },
    volume: {
      h24: vol.h24 != null ? String(vol.h24) : '',
      h6: vol.h6 != null ? String(vol.h6) : '',
      h1: vol.h1 != null ? String(vol.h1) : '',
      m5: vol.m5 != null ? String(vol.m5) : ''
    },
    liquidity: {
      usd: liq.usd != null ? String(liq.usd) : '',
      change24h: liq.change24h != null ? parseFloat(liq.change24h) : 0
    },
    txns: {
      h24: { buys: parseInt(h24Txns.buys, 10) || 0, sells: parseInt(h24Txns.sells, 10) || 0 },
      h6: { buys: parseInt(h6Txns.buys, 10) || 0, sells: parseInt(h6Txns.sells, 10) || 0 },
      h1: { buys: parseInt(h1Txns.buys, 10) || 0, sells: parseInt(h1Txns.sells, 10) || 0 }
    },
    priceChange: {
      h24: pc.h24 != null ? String(pc.h24) : '',
      h6: pc.h6 != null ? String(pc.h6) : '',
      h1: pc.h1 != null ? String(pc.h1) : ''
    },
    fdv: apiPair.fdv != null ? apiPair.fdv : null,
    pairCreatedAt: apiPair.pairCreatedAt != null ? (typeof apiPair.pairCreatedAt === 'number' ? apiPair.pairCreatedAt : new Date(apiPair.pairCreatedAt).getTime()) : 0,
    feeTier: 0.3
  };
}
/**
 * Fetch from DexScreener: multiple token searches per chain to get many pairs.
 */
function fetchDexScreenerPools() {
  var allPairs = [];
  var baseUrl = 'https://api.dexscreener.com/latest/dex/tokens/';
  
  CONFIG.CHAINS.forEach(function(chain) {
    var tokens = CONFIG.DEXSCREENER_SEARCH_TOKENS[chain] || [];
    tokens.forEach(function(tokenSymbol) {
      try {
        // DexScreener API: search by token address or symbol
        // For Solana, we need token addresses; for Base, we can use symbols
        var url = baseUrl + tokenSymbol;
        var response = UrlFetchApp.fetch(url, {
          muteHttpExceptions: true,
          headers: { 'Accept': 'application/json' }
        });
        
        if (response.getResponseCode() === 200) {
          var data = JSON.parse(response.getContentText());
          if (data.pairs && Array.isArray(data.pairs)) {
            data.pairs.forEach(function(pair) {
              var convertedPair = dexScreenerPairToPair(pair, chain);
              if (convertedPair && convertedPair.pairAddress) {
                allPairs.push(convertedPair);
              }
            });
          }
        }
        Utilities.sleep(1000); // Rate limiting
      } catch (e) {
        Logger.log('DexScreener error for ' + chain + '/' + tokenSymbol + ': ' + e.message);
      }
    });
  });
  
  return allPairs;
}

/**
 * Convert DexScreener pair format to our internal format
 */
function dexScreenerPairToPair(dxPair, chain) {
  try {
    var chainId = dxPair.chainId || chain;
    var baseToken = dxPair.baseToken || {};
    var quoteToken = dxPair.quoteToken || {};
    var volume = dxPair.volume || {};
    var liquidity = dxPair.liquidity || 0;
    var priceChange = dxPair.priceChange || {};
    var txns = dxPair.txns || {};
    var pairCreatedAt = dxPair.pairCreatedAt ? new Date(dxPair.pairCreatedAt).getTime() : 0;
    
    return {
      chainId: chainId.toLowerCase(),
      pairAddress: dxPair.pairAddress || '',
      dexId: dxPair.dexId || 'dexscreener',
      baseToken: {
        symbol: baseToken.symbol || 'UNKNOWN',
        address: baseToken.address || ''
      },
      quoteToken: {
        symbol: quoteToken.symbol || 'UNKNOWN',
        address: quoteToken.address || ''
      },
      volume: {
        h24: volume.h24 || 0,
        h6: volume.h6 || 0,
        h1: volume.h1 || 0,
        m5: volume.m5 || 0
      },
      liquidity: {
        usd: parseFloat(liquidity) || 0,
        change24h: 0
      },
      txns: {
        h24: {
          buys: txns.h24 ? (txns.h24.buys || 0) : 0,
          sells: txns.h24 ? (txns.h24.sells || 0) : 0
        },
        h6: {
          buys: txns.h6 ? (txns.h6.buys || 0) : 0,
          sells: txns.h6 ? (txns.h6.sells || 0) : 0
        },
        h1: {
          buys: txns.h1 ? (txns.h1.buys || 0) : 0,
          sells: txns.h1 ? (txns.h1.sells || 0) : 0
        }
      },
      priceChange: {
        h24: priceChange.h24 || 0,
        h6: priceChange.h6 || 0,
        h1: priceChange.h1 || 0
      },
      fdv: dxPair.fdv || 0,
      pairCreatedAt: pairCreatedAt,
      feeTier: dxPair.feeTier || 0.3
    };
  } catch (e) {
    Logger.log('Error converting DexScreener pair: ' + e.message);
    return null;
  }
}

/**
 * Search DexScreener: for each chain, search by each token in DEXSCREENER_SEARCH_TOKENS.
 * Returns pairs in our internal format.
 */
function fetchDexScreenerPools() {
  var allPairs = [];
  var baseUrl = 'https://api.dexscreener.com/latest/dex/search';
  var delayMs = 250;

  CONFIG.CHAINS.forEach(function(chain) {
    var tokens = CONFIG.DEXSCREENER_SEARCH_TOKENS && CONFIG.DEXSCREENER_SEARCH_TOKENS[chain];
    if (!tokens || !tokens.length) return;

    tokens.forEach(function(symbol) {
      try {
        var url = baseUrl + '?q=' + encodeURIComponent(symbol);
        var response = UrlFetchApp.fetch(url, {
          muteHttpExceptions: true,
          headers: { 'Accept': 'application/json' }
        });
        if (response.getResponseCode() !== 200) return;

        var data = JSON.parse(response.getContentText());
        var pairs = data.pairs || [];
        pairs.forEach(function(apiPair) {
          if ((apiPair.chainId || '').toLowerCase() !== (chain || '').toLowerCase()) return;
          var pair = dexScreenerPairToPair(apiPair);
          if (pair.pairAddress) allPairs.push(pair);
        });
        Utilities.sleep(delayMs);
      } catch (e) {
        Logger.log('DexScreener ' + chain + ' ' + symbol + ': ' + e.message);
      }
    });
  });

  return allPairs;
}
/**
 * Convert one DexScreener API pair to our internal pair format.
 */
function dexScreenerPairToPair(apiPair) {
  var vol = apiPair.volume || {};
  var txns = apiPair.txns || {};
  var liq = apiPair.liquidity || {};
  var pc = apiPair.priceChange || {};
  var base = apiPair.baseToken || {};
  var quote = apiPair.quoteToken || {};
  var h24Txns = txns.h24 || {};
  var h6Txns = txns.h6 || {};
  var h1Txns = txns.h1 || {};
  // DexScreener may return baseToken.flagged / quoteToken.flagged for malicious tokens
  var tokenFlagged = !!(base.flagged || quote.flagged);

  return {
    chainId: apiPair.chainId || '',
    pairAddress: apiPair.pairAddress || '',
    dexId: apiPair.dexId || 'unknown',
    tokenFlagged: tokenFlagged,
    baseToken: { symbol: base.symbol || 'BASE', address: base.address || '' },
    quoteToken: { symbol: quote.symbol || 'QUOTE', address: quote.address || '' },
    volume: {
      h24: vol.h24 != null ? String(vol.h24) : '',
      h6: vol.h6 != null ? String(vol.h6) : '',
      h1: vol.h1 != null ? String(vol.h1) : '',
      m5: vol.m5 != null ? String(vol.m5) : ''
    },
    liquidity: {
      usd: liq.usd != null ? String(liq.usd) : '',
      change24h: liq.change24h != null ? parseFloat(liq.change24h) : 0
    },
    txns: {
      h24: { buys: parseInt(h24Txns.buys, 10) || 0, sells: parseInt(h24Txns.sells, 10) || 0 },
      h6: { buys: parseInt(h6Txns.buys, 10) || 0, sells: parseInt(h6Txns.sells, 10) || 0 },
      h1: { buys: parseInt(h1Txns.buys, 10) || 0, sells: parseInt(h1Txns.sells, 10) || 0 }
    },
    priceChange: {
      h24: pc.h24 != null ? String(pc.h24) : '',
      h6: pc.h6 != null ? String(pc.h6) : '',
      h1: pc.h1 != null ? String(pc.h1) : ''
    },
    fdv: apiPair.fdv != null ? apiPair.fdv : null,
    pairCreatedAt: apiPair.pairCreatedAt != null ? (typeof apiPair.pairCreatedAt === 'number' ? apiPair.pairCreatedAt : new Date(apiPair.pairCreatedAt).getTime()) : 0,
    feeTier: 0.3
  };
}

/**
 * Fetch from DexScreener: search by token symbol per chain, then map to our pair format.
 */
function fetchDexScreenerPools() {
  var allPairs = [];
  var baseUrl = 'https://api.dexscreener.com/latest/dex/search';
  var delayMs = 250;

  CONFIG.CHAINS.forEach(function(chain) {
    var tokens = CONFIG.DEXSCREENER_SEARCH_TOKENS && CONFIG.DEXSCREENER_SEARCH_TOKENS[chain];
    if (!tokens || !tokens.length) return;

    tokens.forEach(function(symbol) {
      try {
        var url = baseUrl + '?q=' + encodeURIComponent(symbol);
        var response = UrlFetchApp.fetch(url, {
          muteHttpExceptions: true,
          headers: { 'Accept': 'application/json' }
        });
        if (response.getResponseCode() !== 200) return;

        var data = JSON.parse(response.getContentText());
        var pairs = data.pairs || [];
        pairs.forEach(function(apiPair) {
          if ((apiPair.chainId || '').toLowerCase() !== (chain || '').toLowerCase()) return;
          var pair = dexScreenerPairToPair(apiPair);
          if (pair.pairAddress) allPairs.push(pair);
        });
        Utilities.sleep(delayMs);
      } catch (e) {
        Logger.log('DexScreener ' + chain + ' ' + symbol + ': ' + e.message);
      }
    });
  });

  return allPairs;
} 
function fetchAllPools() {
  var allPairs = [];

  // Search DexScreener (by token symbol per chain)
  if (CONFIG.USE_DEXSCREENER) {
    var dx = fetchDexScreenerPools();
    allPairs.push.apply(allPairs, dx);
    Logger.log('DexScreener search total: ' + dx.length + ' pairs');
  }
  // Search GeckoTerminal (top pools per network, paginated)
  if (CONFIG.USE_GECKOTERMINAL) {
    var gk = fetchGeckoTerminalPools();
    allPairs.push.apply(allPairs, gk);
    Logger.log('GeckoTerminal search total: ' + gk.length + ' pairs');
  }

  var seen = {};
  var unique = [];
  allPairs.forEach(function(p) {
    var key = (p.chainId || '').toLowerCase() + '_' + (p.pairAddress || '');
    if (!key || seen[key]) return;
    seen[key] = true;
    unique.push(p);
  });

  // Exclude DEXs in EXCLUDED_DEX_IDS (e.g. Humidifi - private)
  var excluded = CONFIG.EXCLUDED_DEX_IDS || [];
  if (excluded.length > 0) {
    unique = unique.filter(function(p) {
      var dex = (p.dexId || '').toLowerCase();
      return !excluded.some(function(id) { return dex.indexOf(id.toLowerCase()) !== -1; });
    });
  }

  var sorted = unique
    .filter(function(p) { return p.volume && p.volume.h24 && parseFloat(p.volume.h24) > 0; })
    .sort(function(a, b) { return parseFloat(b.volume.h24) - parseFloat(a.volume.h24); })
    .slice(0, CONFIG.TOP_PAIRS_TOTAL);

  Logger.log('Total unique pairs: ' + sorted.length);
  return sorted;
}

/**
 * Convert one GeckoTerminal pool (data item) to our pair format.
 */
function geckoPoolToPair(item, network) {
  var att = item.attributes || {};
  var rel = item.relationships || {};
  var name = (att.name || '').trim();
  var parts = name.split('/').map(function(s) { return s.trim(); });
  var baseSymbol = (parts[0] || 'BASE').replace(/\s*[\d.]+\s*%?\s*$/i, '').trim();
  var quoteSymbol = (parts[1] || 'QUOTE').replace(/\s*[\d.]+\s*%?\s*$/i, '').trim();
  var baseId = (rel.base_token && rel.base_token.data && rel.base_token.data.id) || '';
  var quoteId = (rel.quote_token && rel.quote_token.data && rel.quote_token.data.id) || '';
  var baseAddress = baseId.indexOf('_') >= 0 ? baseId.split('_').slice(1).join('_') : baseId;
  var quoteAddress = quoteId.indexOf('_') >= 0 ? quoteId.split('_').slice(1).join('_') : quoteId;
  var vol = att.volume_usd || {};
  var tx = att.transactions || {};
  var pc = att.price_change_percentage || {};
  var feeMatch = (name || '').match(/([\d.]+)\s*%/);
  var feeTier = feeMatch ? parseFloat(feeMatch[1]) : 0.3;
  var createdAt = att.pool_created_at ? new Date(att.pool_created_at).getTime() : 0;

  // GeckoTerminal may expose token scam/flag in attributes - default false if not present
  var tokenFlagged = !!(att.scam || att.flagged);

  return {
    chainId: network,
    pairAddress: att.address || item.id || '',
    dexId: (rel.dex && rel.dex.data && rel.dex.data.id) || 'geckoterminal',
    tokenFlagged: tokenFlagged,
    baseToken: { symbol: baseSymbol || 'BASE', address: baseAddress || '' },
    quoteToken: { symbol: quoteSymbol || 'QUOTE', address: quoteAddress || '' },
    volume: { h24: vol.h24, h6: vol.h6, h1: vol.h1, m5: vol.m5 },
    liquidity: { usd: att.reserve_in_usd, change24h: 0 },
    txns: {
      h24: (tx.h24 && { buys: tx.h24.buys, sells: tx.h24.sells }) || { buys: 0, sells: 0 },
      h6: (tx.h6 && { buys: tx.h6.buys, sells: tx.h6.sells }) || { buys: 0, sells: 0 },
      h1: (tx.h1 && { buys: tx.h1.buys, sells: tx.h1.sells }) || { buys: 0, sells: 0 }
    },
    priceChange: { h24: pc.h24, h6: pc.h6, h1: pc.h1 },
    fdv: att.fdv_usd,
    pairCreatedAt: createdAt,
    feeTier: feeTier
  };
}

/**
 * Search GeckoTerminal: top pools by network with pagination (all CONFIG.CHAINS, GECKO_PAGES_PER_NETWORK pages each).
 */
function fetchGeckoTerminalPools() {
  var allPairs = [];
  var baseUrl = 'https://api.geckoterminal.com/api/v2/networks/';
  var delay = CONFIG.GECKO_DELAY_MS || 7000;
  var pages = CONFIG.GECKO_PAGES_PER_NETWORK || 2;

  CONFIG.CHAINS.forEach(function(network) {
    for (var page = 1; page <= pages; page++) {
      try {
        var url = baseUrl + network + '/pools?page=' + page;
        var response = UrlFetchApp.fetch(url, {
          muteHttpExceptions: true,
          headers: { 'Accept': 'application/json;version=20230203' }
        });
        if (response.getResponseCode() === 200) {
          var data = JSON.parse(response.getContentText());
          if (data.data && data.data.length > 0) {
            data.data.forEach(function(item) {
              var pair = geckoPoolToPair(item, network);
              if (pair.pairAddress) allPairs.push(pair);
            });
            Logger.log('GeckoTerminal ' + network + ' page ' + page + ': ' + data.data.length + ' pools');
          }
        }
        if (page < pages) Utilities.sleep(delay);
      } catch (e) {
        Logger.log('GeckoTerminal ' + network + ' page ' + page + ': ' + e.message);
      }
    }
  });

  return allPairs;
}
/**
 * Minimum safety check - only reject truly dangerous/dead pools
 */
function passesMinimumSafety(pair) {
  try {
    var volume24h = parseFloat(pair.volume && pair.volume.h24 ? pair.volume.h24 : 0);
    var tvl = parseFloat(pair.liquidity && pair.liquidity.usd ? pair.liquidity.usd : 0);
    var txn_h24_buys = parseInt(pair.txns && pair.txns.h24 && pair.txns.h24.buys ? pair.txns.h24.buys : 0, 10);
    var txn_h24_sells = parseInt(pair.txns && pair.txns.h24 && pair.txns.h24.sells ? pair.txns.h24.sells : 0, 10);
    var totalTxns = txn_h24_buys + txn_h24_sells;

    if (tvl < CONFIG.MIN_ABSOLUTE_LIQUIDITY) return false;
    if (volume24h < CONFIG.MIN_ABSOLUTE_VOLUME) return false;
    if (totalTxns < CONFIG.MIN_ABSOLUTE_TRANSACTIONS) return false;
    if (!pair.baseToken || !pair.baseToken.symbol || !pair.quoteToken || !pair.quoteToken.symbol) return false;

    return true;
  } catch (e) {
    return false;
  }
}

/**
 * Calculate pool quality score (0-100) based on multiple factors
 */
function calculatePoolQualityScore(pair) {
  var score = 0;
  var flags = [];

  var volume24h = parseFloat(pair.volume && pair.volume.h24 ? pair.volume.h24 : 0);
  var volume6h = parseFloat(pair.volume && pair.volume.h6 ? pair.volume.h6 : 0);
  var volume1h = parseFloat(pair.volume && pair.volume.h1 ? pair.volume.h1 : 0);
  var tvl = parseFloat(pair.liquidity && pair.liquidity.usd ? pair.liquidity.usd : 0);
  var txn_h1_total = (parseInt(pair.txns && pair.txns.h1 && pair.txns.h1.buys ? pair.txns.h1.buys : 0, 10) +
    parseInt(pair.txns && pair.txns.h1 && pair.txns.h1.sells ? pair.txns.h1.sells : 0, 10));
  var txn_h6_total = (parseInt(pair.txns && pair.txns.h6 && pair.txns.h6.buys ? pair.txns.h6.buys : 0, 10) +
    parseInt(pair.txns && pair.txns.h6 && pair.txns.h6.sells ? pair.txns.h6.sells : 0, 10));

  if (volume24h >= 100000) {
    score += 10;
    flags.push('💰 High volume');
  } else if (volume24h >= 50000) {
    score += 7;
  } else if (volume24h >= 25000) {
    score += 4;
  } else if (volume24h >= 10000) {
    score += 2;
  }

  if (volume24h > 0) {
    var recentRatio = (volume1h + volume6h) / volume24h;
    if (recentRatio >= 0.60) {
      score += 15;
      flags.push('🔥 Very recent volume');
    } else if (recentRatio >= 0.45) {
      score += 12;
      flags.push('✅ Recent volume');
    } else if (recentRatio >= 0.30) {
      score += 8;
    } else if (recentRatio >= 0.20) {
      score += 4;
    } else {
      score += 1;
      flags.push('⚠ Old volume');
    }
  }

  if (volume24h > 0 && volume1h > 0) {
    var acceleration = (volume1h * 24) / volume24h;
    if (acceleration >= 2.0) {
      score += 12;
      flags.push('🚀 Strong acceleration');
    } else if (acceleration >= 1.5) {
      score += 10;
      flags.push('📈 Accelerating');
    } else if (acceleration >= 1.2) {
      score += 7;
    } else if (acceleration >= 0.8) {
      score += 4;
    } else {
      score += 1;
      flags.push('📉 Slowing down');
    }
  }

  if (txn_h1_total >= 100) {
    score += 8;
    flags.push('💎 Very active');
  } else if (txn_h1_total >= 50) {
    score += 6;
  } else if (txn_h1_total >= 25) {
    score += 4;
  } else if (txn_h1_total >= 10) {
    score += 2;
  }

  if (tvl >= 100000) {
    score += 10;
  } else if (tvl >= 50000) {
    score += 8;
  } else if (tvl >= 30000) {
    score += 6;
  } else if (tvl >= 15000) {
    score += 4;
  } else if (tvl >= 5000) {
    score += 2;
  }

  if (tvl > 0) {
    var volTvlRatio = volume24h / tvl;
    if (volTvlRatio >= 2.0) {
      score += 10;
      flags.push('⚡ High efficiency');
    } else if (volTvlRatio >= 1.0) {
      score += 8;
    } else if (volTvlRatio >= 0.5) {
      score += 6;
    } else if (volTvlRatio >= 0.3) {
      score += 4;
    } else {
      score += 2;
    }
  }

  var vol_6h = Math.abs(parseFloat(pair.priceChange && pair.priceChange.h6 ? pair.priceChange.h6 : 0));
  var vol_1h = Math.abs(parseFloat(pair.priceChange && pair.priceChange.h1 ? pair.priceChange.h1 : 0));

  if (vol_6h >= 3 && vol_6h <= 15) {
    score += 12;
    flags.push('🎯 Ideal volatility');
  } else if (vol_6h >= 1 && vol_6h <= 25) {
    score += 8;
  } else if (vol_6h < 1) {
    score += 5;
  } else {
    score += 3;
  }

  if (vol_1h <= 5) {
    score += 8;
  } else if (vol_1h <= 10) {
    score += 6;
  } else if (vol_1h <= 20) {
    score += 3;
  } else {
    score += 1;
  }

  var vol_m5 = parseFloat(pair.volume && pair.volume.m5 ? pair.volume.m5 : 0);
  if (vol_m5 > 0 && volume1h > 0) {
    var ultraRecent = (vol_m5 * 12) / volume1h;
    if (ultraRecent >= 1.2) {
      score += 8;
      flags.push('⚡ Active NOW');
    } else if (ultraRecent >= 0.8) {
      score += 5;
    }
  }

  var marketCap = parseFloat(pair.fdv || 0);
  if (marketCap >= 500000) {
    score += 5;
  } else if (marketCap >= 100000) {
    score += 3;
  }

  var pairCreatedAt = pair.pairCreatedAt || 0;
  if (pairCreatedAt > 0) {
    var ageHours = (Date.now() - pairCreatedAt) / (1000 * 60 * 60);
    if (ageHours < 2) {
      score -= 5;
      flags.push('🆕 Very new');
    } else if (ageHours < 6) {
      score -= 2;
    }
  }

  var liqChange = parseFloat(pair.liquidity && pair.liquidity.change24h ? pair.liquidity.change24h : 0);
  if (liqChange < -20) {
    score -= 8;
    flags.push('🚨 Liquidity draining');
  } else if (liqChange < -10) {
    score -= 4;
  }

  score = Math.max(0, Math.min(100, score));
  var grade = score >= 80 ? 'S' : score >= 65 ? 'A' : score >= 50 ? 'B' :
    score >= 35 ? 'C' : score >= 20 ? 'D' : 'F';

  return { score: score, flags: flags, grade: grade };
}

/**
 * Filter pairs - only minimum safety; scoring drives display
 */
function filterPairs(pairs) {
  var safePairs = pairs.filter(passesMinimumSafety);
  Logger.log('Pools after safety filter: ' + safePairs.length + '/' + pairs.length);
  return safePairs;
}

/**
 * Update Google Sheet with filtered pairs
 */
function updateSheet(sheet, pairs) {
  var lastRow = sheet.getLastRow();
  if (lastRow >= CONFIG.DATA_START_ROW) {
    var numRowsToClear = lastRow - CONFIG.DATA_START_ROW + 1;
    // getRange(startRow, startCol, numRows, numCols)
    sheet.getRange(CONFIG.DATA_START_ROW, 1, numRowsToClear, 29).clearContent();
  }

  if (pairs.length === 0) {
    sheet.getRange(CONFIG.DATA_START_ROW, 1).setValue('No pairs match criteria - try relaxing filters');
    return;
  }

  pairs = pairs.map(function(pair) {
    var baseAPR = calculateAPR(pair);
    var poolQuality = calculatePoolQualityScore(pair);
    var aprOptimized = calculateOptimizedAPR(pair, baseAPR);
    var finalScore = (poolQuality.score * CONFIG.WEIGHT_POOL_QUALITY) +
      (Math.min(parseFloat(aprOptimized.adjustedAPR), 500) / 5 * CONFIG.WEIGHT_APR);
    pair.poolQualityScore = poolQuality.score;
    pair.poolGrade = poolQuality.grade;
    pair.poolFlags = poolQuality.flags;
    pair.baseAPR = aprOptimized.baseAPR;
    pair.optimizedAPR = aprOptimized.optimizedAPR;
    pair.adjustedAPR = aprOptimized.adjustedAPR;
    pair.recommendedRange = aprOptimized.recommendedRange;
    pair.safetyScore = aprOptimized.safetyScore;
    pair.expectedDuration = aprOptimized.expectedDuration;
    pair.riskLevel = aprOptimized.riskLevel;
    pair.finalScore = finalScore;
    return pair;
  });

  pairs = pairs.filter(function(pair) {
    return pair.finalScore >= CONFIG.MIN_SCORE_TO_SHOW &&
      parseFloat(pair.adjustedAPR) >= CONFIG.MIN_ADJUSTED_APR_TO_SHOW;
  });

  Logger.log(pairs.length + ' pools after scoring (score >= ' + CONFIG.MIN_SCORE_TO_SHOW + ', APR >= ' + CONFIG.MIN_ADJUSTED_APR_TO_SHOW + '%)');

  if (pairs.length === 0) {
    sheet.getRange(CONFIG.DATA_START_ROW, 1).setValue('No pools found - try lowering MIN_SCORE_TO_SHOW or MIN_ADJUSTED_APR_TO_SHOW in CONFIG');
    return;
  }

  pairs.sort(function(a, b) { return b.finalScore - a.finalScore; });
  pairs = pairs.slice(0, CONFIG.MAX_RESULTS);

  if (CONFIG.EMAIL_ALERTS_ENABLED) {
    sendEmailAlerts(pairs);
  }

  var rows = pairs.map(function(pair) {
    var volume24h = parseFloat(pair.volume && pair.volume.h24 ? pair.volume.h24 : 0);
    var tvl = parseFloat(pair.liquidity && pair.liquidity.usd ? pair.liquidity.usd : 0);
    var volumeTvlRatio = tvl > 0 ? volume24h / tvl : 0;
    var feeTier = pair.feeTier ? parseFloat(pair.feeTier) / 100 : 0.003;
    var marketCap = parseFloat(pair.fdv || 0);
    var priceChange1h = parseFloat(pair.priceChange && pair.priceChange.h1 ? pair.priceChange.h1 : 0);
    var pairAge = (Date.now() - (pair.pairCreatedAt || 0)) / (1000 * 60 * 60);
    var liquidityChange24h = parseFloat(pair.liquidity && pair.liquidity.change24h ? pair.liquidity.change24h : 0);
    var poolScore = pair.poolQualityScore || 0;
    var poolGrade = pair.poolGrade || 'F';
    var finalScore = pair.finalScore || 0;
    var baseAPR = pair.baseAPR || 0;
    var optimizedAPR = pair.optimizedAPR || baseAPR;
    var adjustedAPR = pair.adjustedAPR || baseAPR;
    var recommendedRange = pair.recommendedRange || 'Full Range';
    var safetyScore = pair.safetyScore || 0;
    var expectedDuration = pair.expectedDuration || 'N/A';
    var riskLevel = pair.riskLevel || 'UNKNOWN';

    var status = '✓';
    if (poolGrade === 'S' && safetyScore >= 70) status = '🔥🔥';
    else if (poolGrade === 'S') status = '🔥';
    else if (poolGrade === 'A' && safetyScore >= 70) status = '⭐⭐';
    else if (poolGrade === 'A') status = '⭐';
    else if (poolGrade === 'B') status = '✓✓';
    else if (poolGrade === 'C') status = '⚠';
    else if (poolGrade === 'D') status = '⚠⚠';
    else status = '❌';

    var notes = pair.poolFlags ? pair.poolFlags.slice(0, 4).join(' | ') : '';
    if (pair.tokenFlagged) {
      notes = '🚨 TOKEN FLAGGED / MALICIOUS | ' + notes;
    }
    if (adjustedAPR > baseAPR * 5) {
      notes = '💎 ' + Math.round(adjustedAPR / baseAPR) + 'x APR | ' + notes;
    }

    var link = getDexLink(pair);
    if (!link && pair.pairAddress && pair.chainId) {
      link = 'https://dexscreener.com/' + (pair.chainId || '').toLowerCase().replace(/\s/g, '') + '/' + pair.pairAddress;
    }

    // A=Chain, B=Pair, C=Base, D=Quote, E=DEX, F=Pool Score, G=Grade, H–K=AdjAPR,Range,Safety,Duration, L=Link, then addresses & rest
    return [
      capitalizeChain(pair.chainId),
      pair.baseToken.symbol + '/' + pair.quoteToken.symbol,
      pair.baseToken.symbol,
      pair.quoteToken.symbol,
      pair.dexId || 'Unknown',
      poolScore,
      poolGrade,
      adjustedAPR,
      recommendedRange,
      safetyScore,
      expectedDuration,
      link || '',
      pair.pairAddress || 'N/A',
      pair.baseToken.address || 'N/A',
      pair.quoteToken.address || 'N/A',
      volume24h,
      tvl,
      volumeTvlRatio,
      feeTier * 100,
      baseAPR,
      optimizedAPR,
      riskLevel,
      marketCap,
      pairAge,
      liquidityChange24h,
      priceChange1h,
      finalScore,
      status,
      notes
    ];
  });

  if (rows.length > 0) {
    var startRow = CONFIG.DATA_START_ROW;
    var numRows = rows.length;
    var numCols = 29;
    // getRange(startRow, startCol, numRows, numCols) - writes rows.length rows
    sheet.getRange(startRow, 1, numRows, numCols).setValues(rows);
    formatDataRange(sheet, startRow, numRows);
  }
}

/**
 * Send email alerts for high-APR opportunities
 */
function sendEmailAlerts(pairs) {
  if (!pairs || !Array.isArray(pairs) || pairs.length === 0) {
    Logger.log('⚠️ No pairs to alert - skipping email alerts');
    return;
  }

  Logger.log('📧 Checking ' + pairs.length + ' pairs for email alerts (Score ≥' + CONFIG.EMAIL_MIN_FINAL_SCORE + ', APR ≥' + CONFIG.EMAIL_MIN_APR + '%)...');

  var props = PropertiesService.getScriptProperties();
  var alertedPairsJson = props.getProperty('ALERTED_PAIRS') || '{}';
  var alertedPairs = {};
  try {
    alertedPairs = JSON.parse(alertedPairsJson);
  } catch (e) {
    alertedPairs = {};
  }
  var now = Date.now();
  var ALERT_COOLDOWN = 4 * 60 * 60 * 1000;
  var alertsSent = 0;
  var alertsSkipped = 0;

  pairs.forEach(function(pair) {
    var dailyAPR = parseFloat(pair.adjustedAPR || 0);
    var volume24h = parseFloat(pair.volume && pair.volume.h24 ? pair.volume.h24 : 0);
    var finalScore = pair.finalScore || 0;
    var poolGrade = pair.poolGrade || 'F';
    var pairKey = pair.chainId + '_' + pair.pairAddress;

    if (finalScore >= CONFIG.EMAIL_MIN_FINAL_SCORE && dailyAPR > CONFIG.EMAIL_MIN_APR) {
      var lastAlert = alertedPairs[pairKey] || 0;
      if (now - lastAlert < ALERT_COOLDOWN) {
        alertsSkipped++;
        return;
      }
      try {
        var subject = '🔥 [Grade ' + poolGrade + '] ' + pair.baseToken.symbol + '/' + pair.quoteToken.symbol + ' - ' + dailyAPR.toFixed(0) + '% APR | Score: ' + finalScore.toFixed(0);
        var emailLink = getDexLink(pair);
        if (!emailLink && pair.pairAddress && pair.chainId) {
          emailLink = 'https://dexscreener.com/' + (pair.chainId || '').toLowerCase().replace(/\s/g, '') + '/' + pair.pairAddress;
        }
        var body = [
          '🔥 HIGH-QUALITY OPPORTUNITY DETECTED! 🔥',
          '',
          (pair.tokenFlagged ? '⚠️ AVISO: Token marcado como malicioso/flagged. Verifique antes de fornecer liquidez.\n\n' : ''),
          '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━',
          'PAIR: ' + pair.baseToken.symbol + '/' + pair.quoteToken.symbol,
          '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━',
          '',
          'Chain: ' + capitalizeChain(pair.chainId),
          'DEX: ' + (pair.dexId || 'Unknown'),
          '',
          '🏆 QUALITY GRADE: ' + poolGrade + '/S',
          '📊 FINAL SCORE: ' + finalScore.toFixed(1) + '/100',
          '',
          '📋 CONTRACT ADDRESSES:',
          '• Pair Contract: ' + (pair.pairAddress || 'Not available'),
          '• ' + pair.baseToken.symbol + ' Contract: ' + (pair.baseToken.address || 'Not available'),
          '• ' + pair.quoteToken.symbol + ' Contract: ' + (pair.quoteToken.address || 'Not available'),
          '',
          '📊 APR BREAKDOWN:',
          '• Base APR (Full Range): ' + parseFloat(pair.baseAPR || 0).toFixed(1) + '%',
          '• Optimized APR (Concentrated): ' + parseFloat(pair.optimizedAPR || 0).toFixed(1) + '%',
          '• Adjusted APR (Risk-Adjusted): ' + dailyAPR.toFixed(1) + '% ⭐',
          '',
          '🎯 RANGE SETUP:',
          '• Recommended Range: ' + (pair.recommendedRange || 'Full Range'),
          '• Safety Score: ' + (pair.safetyScore || 0) + '/100',
          '• Expected Duration: ' + (pair.expectedDuration || 'N/A'),
          '• Risk Level: ' + (pair.riskLevel || 'UNKNOWN'),
          '',
          '💰 POOL METRICS:',
          '• 24h Volume: $' + volume24h.toLocaleString(),
          '• TVL: $' + parseFloat(pair.liquidity && pair.liquidity.usd ? pair.liquidity.usd : 0).toLocaleString(),
          '• Volume/TVL Ratio: ' + (volume24h / parseFloat(pair.liquidity && pair.liquidity.usd ? pair.liquidity.usd : 1)).toFixed(2) + 'x',
          '• Market Cap: $' + parseFloat(pair.fdv || 0).toLocaleString(),
          '',
          '📈 ACTIVITY INDICATORS:',
          (pair.poolFlags || []).join('\n'),
          '',
          '⚠️ RISK FACTORS:',
          '• Price Change 1h: ' + parseFloat(pair.priceChange && pair.priceChange.h1 ? pair.priceChange.h1 : 0).toFixed(1) + '%',
          '• Liquidity Change 24h: ' + parseFloat(pair.liquidity && pair.liquidity.change24h ? pair.liquidity.change24h : 0).toFixed(1) + '%',
          '• Pair Age: ' + ((Date.now() - (pair.pairCreatedAt || 0)) / (1000 * 60 * 60)).toFixed(1) + ' hours',
          '',
          '🔗 QUICK LINKS:',
          'Link (DexScreener): ' + (emailLink || ('https://dexscreener.com/' + (pair.chainId || '') + '/' + (pair.pairAddress || ''))),
          'DexScreener: https://dexscreener.com/' + pair.chainId + '/' + pair.pairAddress,
          '',
          '📋 ADD LIQUIDITY:',
          getDexLink(pair),
          '',
          '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━',
          '',
          'This is an automated alert from your LP Screener. Always DYOR!'
        ].join('\n');

        MailApp.sendEmail(CONFIG.EMAIL_ADDRESS, subject, body);
        alertedPairs[pairKey] = now;
        alertsSent++;
        Logger.log('✅ Alert sent for ' + pair.baseToken.symbol + '/' + pair.quoteToken.symbol);
      } catch (e) {
        Logger.log('❌ Error sending email alert: ' + e.message);
      }
    }
  });

  Logger.log('📧 Email alerts: ' + alertsSent + ' sent, ' + alertsSkipped + ' skipped (cooldown)');

  Object.keys(alertedPairs).forEach(function(key) {
    if (now - alertedPairs[key] > 24 * 60 * 60 * 1000) delete alertedPairs[key];
  });
  props.setProperty('ALERTED_PAIRS', JSON.stringify(alertedPairs));
}

/**
 * Analyze volatility and recommend optimal concentrated range
 */
function analyzeVolatilityForConcentratedLP(pair) {
  var vol_1h = Math.abs(parseFloat(pair.priceChange && pair.priceChange.h1 ? pair.priceChange.h1 : 0));
  var vol_6h = Math.abs(parseFloat(pair.priceChange && pair.priceChange.h6 ? pair.priceChange.h6 : 0));
  var vol_24h = Math.abs(parseFloat(pair.priceChange && pair.priceChange.h24 ? pair.priceChange.h24 : 0));
  var avgVolatility = vol_1h * 0.5 + vol_6h * 0.3 + vol_24h * 0.2;

  if (avgVolatility < 5) {
    return { recommendedRange: 1.5, riskLevel: 'LOW', aprMultiplier: 15, color: 'green' };
  }
  if (avgVolatility < 15) {
    return { recommendedRange: 3.0, riskLevel: 'MEDIUM', aprMultiplier: 8, color: 'yellow' };
  }
  if (avgVolatility < 30) {
    return { recommendedRange: 5.0, riskLevel: 'HIGH', aprMultiplier: 5, color: 'orange' };
  }
  return { recommendedRange: null, riskLevel: 'EXTREME', aprMultiplier: 1, color: 'red', warning: 'Too volatile for concentrated range' };
}

/**
 * Calculate probability of staying within range
 */
function calculateRangeRisk(pair, rangePercent) {
  var vol_1h = Math.abs(parseFloat(pair.priceChange && pair.priceChange.h1 ? pair.priceChange.h1 : 0));
  var vol_6h = Math.abs(parseFloat(pair.priceChange && pair.priceChange.h6 ? pair.priceChange.h6 : 0));
  var exitProb_1h = vol_1h > rangePercent ? ((vol_1h - rangePercent) / vol_1h) * 100 : 0;
  var maxMove_6h = vol_6h;
  var exitProb_6h = maxMove_6h > rangePercent ? ((maxMove_6h - rangePercent) / maxMove_6h) * 100 : 0;
  var safetyScore = 100 - (exitProb_1h + exitProb_6h) / 2;
  return {
    exitProb_1h: Math.min(100, exitProb_1h),
    exitProb_6h: Math.min(100, exitProb_6h),
    safetyScore: Math.max(0, safetyScore),
    recommendation: safetyScore >= 70 ? 'SAFE' : safetyScore >= 50 ? 'MODERATE' : 'RISKY'
  };
}

function estimatePositionDuration(riskAnalysis) {
  var exitProb = riskAnalysis.exitProb_1h;
  if (exitProb < 10) return '6+ hrs';
  if (exitProb < 20) return '4-6 hrs';
  if (exitProb < 35) return '2-4 hrs';
  if (exitProb < 50) return '1-2 hrs';
  return '<1 hr';
}

/**
 * Calculate optimized APR with concentrated range
 */
function calculateOptimizedAPR(pair, baseAPR) {
  var rangeAnalysis = analyzeVolatilityForConcentratedLP(pair);
  if (!rangeAnalysis.recommendedRange) {
    return {
      baseAPR: baseAPR,
      optimizedAPR: baseAPR,
      adjustedAPR: baseAPR,
      recommendedRange: 'Full Range',
      riskLevel: rangeAnalysis.riskLevel,
      safetyScore: 0,
      expectedDuration: 'N/A',
      aprMultiplier: 1
    };
  }
  var optimizedAPR = baseAPR * rangeAnalysis.aprMultiplier;
  var riskAnalysis = calculateRangeRisk(pair, rangeAnalysis.recommendedRange);
  var adjustedAPR = optimizedAPR * (riskAnalysis.safetyScore / 100);
  return {
    baseAPR: baseAPR,
    optimizedAPR: optimizedAPR,
    adjustedAPR: adjustedAPR,
    recommendedRange: '±' + rangeAnalysis.recommendedRange + '%',
    riskLevel: rangeAnalysis.riskLevel,
    safetyScore: riskAnalysis.safetyScore,
    expectedDuration: estimatePositionDuration(riskAnalysis),
    aprMultiplier: rangeAnalysis.aprMultiplier
  };
}

/**
 * Calculate estimated daily APR for a pair
 */
function calculateAPR(pair) {
  var volume24h = parseFloat(pair.volume && pair.volume.h24 ? pair.volume.h24 : 0);
  var tvl = parseFloat(pair.liquidity && pair.liquidity.usd ? pair.liquidity.usd : 0);
  if (tvl === 0) return 0;
  var volumeTvlRatio = volume24h / tvl;
  var feeTier = pair.feeTier ? parseFloat(pair.feeTier) / 100 : 0.003;
  return ((volume24h * volumeTvlRatio * feeTier) / tvl) * 365;
}

/**
 * Format data cells - uses correct getRange(row, column, numRows, numColumns).
 * All ranges: startRow + numRows rows, specified columns.
 */
function formatDataRange(sheet, startRow, numRows) {
  if (numRows <= 0) return;
  // Columns: 1-7 Chain..Grade | 8-11 AdjAPR,Range,Safety,Duration | 12=Link | 13-15=addresses | 16+ metrics
  sheet.getRange(startRow, 12, numRows, 1).setHorizontalAlignment('left');   // col 12: Link
  sheet.getRange(startRow, 12, numRows, 1).setFontSize(8);
  sheet.getRange(startRow, 16, numRows, 2).setNumberFormat('$#,##0');   // cols 16-17: Volume, TVL
  sheet.getRange(startRow, 18, numRows, 1).setNumberFormat('0.00');     // col 18: Volume/TVL
  sheet.getRange(startRow, 19, numRows, 1).setNumberFormat('0.0');      // col 19: Fee tier
  sheet.getRange(startRow, 8, numRows, 1).setNumberFormat('0.0');       // col 8: AdjAPR
  sheet.getRange(startRow, 20, numRows, 2).setNumberFormat('0.0');       // cols 20-21: BaseAPR, OptAPR
  sheet.getRange(startRow, 10, numRows, 1).setNumberFormat('0');        // col 10: Safety score
  sheet.getRange(startRow, 23, numRows, 1).setNumberFormat('$#,##0');   // col 23: Market cap
  sheet.getRange(startRow, 24, numRows, 1).setNumberFormat('0.0');      // col 24: Pair age
  sheet.getRange(startRow, 25, numRows, 2).setNumberFormat('0.0');     // cols 25-26: Liq change, Price change
  sheet.getRange(startRow, 6, numRows, 1).setNumberFormat('0');         // col 6: Pool score
  sheet.getRange(startRow, 27, numRows, 1).setNumberFormat('0.0');    // col 27: Final score

  sheet.getRange(startRow, 10, numRows, 1).setHorizontalAlignment('center');  // Safety
  sheet.getRange(startRow, 22, numRows, 1).setHorizontalAlignment('center');    // Risk
  sheet.getRange(startRow, 6, numRows, 1).setHorizontalAlignment('center');
  sheet.getRange(startRow, 7, numRows, 1).setHorizontalAlignment('center');
  sheet.getRange(startRow, 8, numRows, 1).setHorizontalAlignment('center');   // AdjAPR
  sheet.getRange(startRow, 27, numRows, 1).setHorizontalAlignment('center');
  sheet.getRange(startRow, 28, numRows, 1).setHorizontalAlignment('center');
  sheet.getRange(startRow, 6, numRows, 1).setFontWeight('bold');
  sheet.getRange(startRow, 27, numRows, 1).setFontWeight('bold');
  sheet.getRange(startRow, 13, numRows, 3).setFontSize(8);   // cols 13-15: PairAddress, Base, Quote
  sheet.getRange(startRow, 13, numRows, 3).setHorizontalAlignment('left');
}

function capitalizeChain(chain) {
  if (chain.toLowerCase() === 'solana') return 'Solana';
  if (chain.toLowerCase() === 'base') return 'Base';
  return chain.charAt(0).toUpperCase() + chain.slice(1);
}

function getDexLink(pair) {
  var chain = pair.chainId.toLowerCase();
  var dex = (pair.dexId || '').toLowerCase();
  var address = pair.pairAddress;
  if (chain === 'solana') {
    if (dex.indexOf('raydium') !== -1) return 'https://raydium.io/liquidity/increase/?pool_id=' + address;
    if (dex.indexOf('orca') !== -1) return 'https://www.orca.so/pools?address=' + address;
    // Meteora: API pairAddress may not open in app.meteora.ag; use DexScreener pair page then Add Liquidity
    if (dex.indexOf('meteora') !== -1 || dex.indexOf('meteoro') !== -1) return 'Meteora (open pair on DexScreener, then Add Liquidity): https://dexscreener.com/solana/' + address;
    return 'Solana Pool: ' + address;
  }
  if (chain === 'base') {
    if (dex.indexOf('uniswap') !== -1) return 'Uniswap: https://app.uniswap.org/add/' + address;
    if (dex.indexOf('aerodrome') !== -1) return 'Aerodrome: https://aerodrome.finance/liquidity/' + address;
    return 'Base Pool: ' + address;
  }
  return 'Pool Address: ' + address;
}

// ==================== SETUP FUNCTIONS ====================

function setupAutoRefresh() {
  var triggers = ScriptApp.getProjectTriggers();
  triggers.forEach(function(trigger) {
    if (trigger.getHandlerFunction() === 'updateLPScreener') ScriptApp.deleteTrigger(trigger);
  });
  ScriptApp.newTrigger('updateLPScreener').timeBased().everyMinutes(CONFIG.REFRESH_TIME).create();
  Logger.log('Auto-refresh trigger created - updates every ' + CONFIG.REFRESH_TIME + ' minutes');
  updateLPScreener();
}

function stopAutoRefresh() {
  var triggers = ScriptApp.getProjectTriggers();
  triggers.forEach(function(trigger) {
    if (trigger.getHandlerFunction() === 'updateLPScreener') ScriptApp.deleteTrigger(trigger);
  });
  Logger.log('Auto-refresh stopped');
}

function manualRefresh() {
  updateLPScreener();
}

function clearAlertHistory() {
  PropertiesService.getScriptProperties().deleteProperty('ALERTED_PAIRS');
  Logger.log('Alert history cleared');
}
