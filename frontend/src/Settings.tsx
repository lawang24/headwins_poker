import { useState } from "react";
import type { State } from "./types";
import type { Action } from "./ActionControls";
import { inputAmount, parseAmount } from "./amounts";

export function Settings({ state, ready, send, back }: {
  state: State; ready: boolean; send: (action: Action) => void; back: () => void;
}) {
  const [cents, setCents] = useState(state.cents);
  const [sb, setSb] = useState(inputAmount(state.small_blind, state.cents));
  const [bb, setBb] = useState(inputAmount(state.big_blind, state.cents));
  const [autoDeal, setAutoDeal] = useState(state.auto_deal);
  const small = parseAmount(sb, cents), big = parseAmount(bb, cents);
  const valid = small > 0 && big >= small && big <= 1_000_000;
  const changed = small !== state.small_blind || big !== state.big_blind || cents !== state.cents || autoDeal !== state.auto_deal;
  return <section className="settings-page panel" aria-labelledby="settings-title">
    <button type="button" onClick={back}>← Back to table</button>
    <p className="eyebrow">SHARED LOBBY</p>
    <h2 id="settings-title">Settings</h2>
    <p className="hint">Anyone at the table can change these settings. Changes apply to every player.</p>
    <form onSubmit={e => {
      e.preventDefault();
      if (ready && valid && changed) send({ type: "settings", small_blind: small, big_blind: big, auto_deal: autoDeal, cents });
    }}>
      <fieldset disabled={!ready || state.running}>
        <legend>Denominations</legend>
        <label className="setting-toggle">
          <span>Use cents<small>Use 0.01 increments for blinds, bets, and stacks. 100 whole units become 1.00 when enabled.</small></span>
          <input type="checkbox" role="switch" checked={cents} onChange={e => {
            const next = e.target.checked;
            if (Number.isFinite(small)) setSb(inputAmount(small, next));
            if (Number.isFinite(big)) setBb(inputAmount(big, next));
            setCents(next);
          }} />
        </label>
        <div className="blind-inputs">
          <label>Small blind (SB)<input type="number" required min={cents ? .01 : 1} max={cents ? 10000 : 1000000} step={cents ? .01 : 1} value={sb} onChange={e => setSb(e.target.value)} /></label>
          <label>Big blind (BB)<input type="number" required min={cents ? .01 : 1} max={cents ? 10000 : 1000000} step={cents ? .01 : 1} value={bb} onChange={e => setBb(e.target.value)} /></label>
        </div>
        <p className="hint">{state.running ? "Finish the current hand to change denominations." : "Blinds must be positive, with the big blind at least as large as the small blind."}</p>
      </fieldset>
      <label className="setting-toggle">
        <span>Auto-deal next hand<small>Deal automatically five seconds after a hand ends, when at least two players have chips. Deal the first hand manually.</small></span>
        <input type="checkbox" role="switch" checked={autoDeal} disabled={!ready} onChange={e => setAutoDeal(e.target.checked)} />
      </label>
      <div className="settings-save">
        <button className="primary" disabled={!ready || !valid || !changed}>Save settings</button>
        <span role="status">{!ready ? "Waiting for connection or update…" : changed ? "Unsaved changes" : "Lobby settings are up to date"}</span>
      </div>
    </form>
  </section>;
}
