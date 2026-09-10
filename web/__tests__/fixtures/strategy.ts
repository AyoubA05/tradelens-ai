import type { StrategyResponse } from "@/lib/app/strategy";

/**
 * A typed `StrategyResponse`, so `tsc` fails the moment the backend contract
 * and these fixtures disagree about a field.
 *
 * `written: 3` is deliberately NOT what the profile text alone would give if
 * someone recomputed it in the browser with a different rule — the page must
 * print the server's number, and tests below rely on that.
 */

export const BLANK_FIELDS: StrategyResponse["starter"] = {
  name: null,
  trading_style: null,
  markets: null,
  timeframes: null,
  entry_rules: null,
  stop_rules: null,
  take_profit_rules: null,
  risk_rules: null,
  setups_traded: null,
  setups_avoided: null,
  news_session_rules: null,
  common_mistakes: null,
};

export const STARTER: StrategyResponse["starter"] = {
  ...BLANK_FIELDS,
  name: "ICT/SMC Day Trading",
  trading_style: "ICT / SMC",
  markets: "NQ, ES, EURUSD, GBP/USD",
  timeframes: "15m entry, 1H/4H HTF",
  entry_rules: "Wait for HTF POI, confirm BOS or CHoCH on LTF, enter on FVG or OB retest",
  stop_rules: "Place SL below/above the swing that caused the BOS",
  take_profit_rules: "TP at next liquidity level or opposing HTF POI",
  risk_rules: "Max 1% per trade, max 2 trades per session, no revenge trading",
  setups_traded: "Liquidity Sweep + FVG, BOS + OB Retest, CHoCH Entry",
  setups_avoided: "Counter-trend without BOS, news candle entries, off-session trades",
  common_mistakes: "FOMO entry, moving SL, off-session trades, overtrading",
};

const LIMITS: StrategyResponse["limits"] = {
  name: 100,
  trading_style: 500,
  markets: 500,
  timeframes: 500,
  entry_rules: 500,
  stop_rules: 500,
  take_profit_rules: 500,
  risk_rules: 500,
  setups_traded: 500,
  setups_avoided: 500,
  news_session_rules: 500,
  common_mistakes: 500,
};

export const REVISION = "2026-09-10T12:00:00.000000+00:00";

export function strategyFixture(overrides: Partial<StrategyResponse> = {}): StrategyResponse {
  return {
    profile: {
      ...BLANK_FIELDS,
      name: "London Killzone Playbook",
      markets: "NQ, ES",
      timeframes: "1m entry, 15m HTF",
      stop_rules: "Behind the OB wick",
      setups_traded: "FVG, OB retest",
    },
    revision: REVISION,
    updated_at: REVISION,
    sections: [
      { id: "identity", label: "Identity", written: true },
      { id: "entry", label: "Entry Rules", written: false },
      { id: "exit", label: "Exit Rules", written: true },
      { id: "risk", label: "Risk Rules", written: false },
      { id: "setups", label: "Setups", written: true },
      { id: "self_awareness", label: "Self-Awareness", written: false },
    ],
    written: 3,
    total: 6,
    facets: {
      markets: ["NQ", "ES"],
      entry_timeframe: "1m",
      htf_timeframe: "15m",
      setups: ["FVG", "OB retest"],
    },
    over_limit: [],
    limits: LIMITS,
    starter: STARTER,
    suggestions: [],
    first_run: false,
    ...overrides,
  };
}

export function emptyStrategyFixture(overrides: Partial<StrategyResponse> = {}): StrategyResponse {
  return strategyFixture({
    profile: null,
    revision: null,
    updated_at: null,
    sections: strategyFixture().sections.map((s) => ({ ...s, written: false })),
    written: 0,
    facets: { markets: [], entry_timeframe: null, htf_timeframe: null, setups: [] },
    ...overrides,
  });
}
