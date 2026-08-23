import { StatTile } from "@/components/app/overview/stat-tile";
import { money, NO_VALUE } from "@/lib/app/format";
import type { TradeDetail } from "@/lib/app/trades";

/** A trade a client sent no number for. Absent is never zero. */
function text(v: string | null | undefined): string {
  return v === null || v === undefined || v === "" ? NO_VALUE : v;
}

function moneyOrNone(v: number | null | undefined): string {
  return v === null || v === undefined ? NO_VALUE : money(v);
}

function rrOrNone(v: number | null | undefined): string {
  return v === null || v === undefined ? NO_VALUE : `${v.toFixed(2)}R`;
}

/**
 * SMC/ICT confirmations (`bos`, `choch`, `liquidity_sweep`, `order_block_used`,
 * `fvg_used`) and `followed_rules` are stored as `0`/`1`/`null`, not a proper
 * boolean — `null` is "not recorded", `0` is a recorded "No", and collapsing
 * them would misreport an unrecorded field as a negative one.
 */
function flagOrNone(v: number | null | undefined): string {
  if (v === null || v === undefined) return NO_VALUE;
  return v ? "Yes" : "No";
}

function toneFor(result: TradeDetail["result"]): "positive" | "negative" | "neutral" {
  if (result === "Win") return "positive";
  if (result === "Loss") return "negative";
  return "neutral";
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">{label}</dt>
      <dd className="mt-1 text-sm text-text">{value}</dd>
    </div>
  );
}

function FieldGroup({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-8">
      <h2 className="font-display text-sm font-semibold text-text">{title}</h2>
      <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-3">{children}</dl>
    </section>
  );
}

/**
 * The Trade Detail read view: a header of the figures that matter first,
 * then every recorded field grouped by what it describes.
 *
 * Every field renders through `text`/`moneyOrNone`/`rrOrNone`/`flagOrNone`
 * above rather than a bare `??` fallback, so a genuinely recorded `0` (a
 * scratch trade, a flat P&L) and a field nobody filled in read differently —
 * "not recorded" is never spelled the same as a zero.
 */
export function TradeReadView({ trade }: { trade: TradeDetail }) {
  return (
    <div>
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h1 className="font-display text-3xl font-bold">{text(trade.asset)}</h1>
          <p className="mt-1 text-sm text-muted">{text(trade.trade_date)}</p>
        </div>
        <span
          className={`font-mono text-sm font-semibold ${
            trade.result === "Win"
              ? "text-positive"
              : trade.result === "Loss"
                ? "text-negative"
                : "text-muted"
          }`}
        >
          {text(trade.result)}
        </span>
      </div>

      <div className="mt-6 flex flex-wrap rounded-xl border border-line bg-surface px-4 py-2">
        <StatTile label="P&L" value={moneyOrNone(trade.pnl)} tone={toneFor(trade.result)} />
        <StatTile label="R Realized" value={rrOrNone(trade.rr_realized)} />
        <StatTile label="R Planned" value={rrOrNone(trade.rr_planned)} />
        <StatTile
          label="Rules Followed"
          value={flagOrNone(trade.followed_rules)}
          tone={trade.followed_rules === 0 ? "negative" : "neutral"}
        />
      </div>

      <FieldGroup title="Setup">
        <Field label="Asset class" value={text(trade.asset_class)} />
        <Field label="Direction" value={text(trade.direction)} />
        <Field label="Session" value={text(trade.session)} />
        <Field label="Killzone" value={text(trade.killzone)} />
        <Field label="Setup type" value={text(trade.setup_type)} />
        <Field label="Strategy used" value={text(trade.strategy_used)} />
        <Field label="Timeframe" value={text(trade.timeframe)} />
        <Field label="Bias" value={text(trade.bias)} />
        <Field label="HTF bias" value={text(trade.htf_bias)} />
        <Field label="Entry type" value={text(trade.entry_type)} />
        <Field label="Confirmation model" value={text(trade.confirmation_model)} />
        <Field label="Day of week" value={text(trade.day_of_week)} />
      </FieldGroup>

      <FieldGroup title="SMC / ICT confirmations">
        <Field label="Break of structure" value={flagOrNone(trade.bos)} />
        <Field label="Change of character" value={flagOrNone(trade.choch)} />
        <Field label="Liquidity sweep" value={flagOrNone(trade.liquidity_sweep)} />
        <Field label="Order block used" value={flagOrNone(trade.order_block_used)} />
        <Field label="FVG used" value={flagOrNone(trade.fvg_used)} />
      </FieldGroup>

      <FieldGroup title="Prices and size">
        <Field label="Entry price" value={moneyOrNone(trade.entry_price)} />
        <Field label="Stop price" value={moneyOrNone(trade.stop_price)} />
        <Field label="TP price" value={moneyOrNone(trade.tp_price)} />
        <Field label="Exit price" value={moneyOrNone(trade.exit_price)} />
        <Field label="Position size" value={trade.position_size === null ? NO_VALUE : String(trade.position_size)} />
        <Field label="Risk amount" value={moneyOrNone(trade.risk_amount)} />
        <Field label="Reward amount" value={moneyOrNone(trade.reward_amount)} />
      </FieldGroup>

      <FieldGroup title="Reflection">
        <Field label="Emotions before" value={text(trade.emotions_before)} />
        <Field label="Emotions during" value={text(trade.emotions_during)} />
        <Field label="Emotions after" value={text(trade.emotions_after)} />
        <Field label="Mistake tags" value={text(trade.mistake_tags)} />
      </FieldGroup>

      <section className="mt-8">
        <h2 className="font-display text-sm font-semibold text-text">Notes</h2>
        <p className="mt-3 whitespace-pre-wrap text-sm text-text">{text(trade.notes)}</p>
      </section>

      <section className="mt-8">
        <h2 className="font-display text-sm font-semibold text-text">Trade process notes</h2>
        <p className="mt-3 whitespace-pre-wrap text-sm text-text">{text(trade.trade_process_notes)}</p>
      </section>

      <FieldGroup title="Review">
        <Field label="AI grade" value={text(trade.ai_grade)} />
        <Field label="Your grade" value={text(trade.user_grade)} />
      </FieldGroup>

      <FieldGroup title="Record">
        <Field label="Created" value={text(trade.created_at)} />
        <Field label="Last updated" value={text(trade.updated_at)} />
      </FieldGroup>
    </div>
  );
}
