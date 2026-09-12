import { useState } from "react";
import type { State } from "./types";

export type Action = { type: string; amount?: number; text?: string };

export function ActionControls({ state, ready, send }: {
  state: State; ready: boolean; send: (action: Action) => void;
}) {
  const me = state.players.find(p => p.id === state.you)!;
  const myTurn = state.running && state.actor === state.you;
  const minimum = Math.min(state.min_raise_to, state.max_raise_to);
  const [editing, setEditing] = useState(false);
  const [raiseTo, setRaiseTo] = useState(String(minimum));
  const [stack, setStack] = useState(String(me.stack));
  const amount = Number(raiseTo);
  const canRaise = ready && myTurn && state.can_raise;
  const valid = raiseTo.trim() !== "" && Number.isInteger(amount) && amount > state.target && amount <= state.max_raise_to && (amount >= state.min_raise_to || amount === state.max_raise_to);
  const sliderValue = Number.isFinite(amount) ? Math.max(minimum, Math.min(state.max_raise_to, amount)) : minimum;
  const betLabel = state.target === 0 ? "Bet" : "Raise";
  const selectAmount = (value: number) => setRaiseTo(String(Math.max(minimum, Math.min(state.max_raise_to, Math.round(value)))));
  // A pot-sized raise includes the call, then raises by the pot after calling.
  const potRaise = (fraction: number) => me.committed + state.call_amount + (state.pot + state.call_amount) * fraction;
  const eligible = state.players.filter(p => p.connected && p.stack > 0).length;
  return <section className={`action-controls ${state.running ? "is-playing" : ""} ${myTurn ? "is-your-turn" : ""}`} aria-label="Game controls">
    <div className="action-status" role="status">
      {state.running ? myTurn ? "Your turn" : `${state.players.find(p => p.id === state.actor)?.name || "Player"} to act` : "Between hands"}
      <span>{!ready ? "Waiting for connection or update…" : state.running && myTurn ? state.call_amount ? `${state.call_amount.toLocaleString()} to call${state.call_amount === me.stack ? " · all-in" : ""}` : "You can check" : state.running ? "Actions unlock on your turn" : state.host === state.you ? "You are the table host" : "Waiting for the host to deal"}</span>
    </div>
    {state.running ? <div className="betting-controls">
      {myTurn && editing ? <form className="raise-editor" onSubmit={e => {e.preventDefault(); if(canRaise && valid) send({type:"raise",amount});}} onKeyDown={e => {if (e.key === "Escape") {e.preventDefault(); setEditing(false);}}}>
        <div className="raise-sizing">
          <label className="raise-amount">{betLabel} to
            <input autoFocus aria-label={`${betLabel} to (total chips)`} type="number" step="1" min={minimum} max={state.max_raise_to} value={raiseTo} disabled={!canRaise} aria-invalid={!valid} aria-describedby="raise-help" onFocus={e => e.target.select()} onChange={e => setRaiseTo(e.target.value)} />
          </label>
          <input className="raise-slider" type="range" aria-label="Raise amount slider" aria-valuetext={`${sliderValue} total chips`} min={minimum} max={state.max_raise_to} step="1" value={sliderValue} disabled={!canRaise} onChange={e => setRaiseTo(e.target.value)} />
        </div>
        <div className="bet-presets" aria-label="Bet sizes">
          <button type="button" disabled={!canRaise} onClick={() => selectAmount(minimum)}>Min</button>
          <button type="button" disabled={!canRaise} onClick={() => selectAmount(potRaise(.5))}>½ pot</button>
          <button type="button" disabled={!canRaise} onClick={() => selectAmount(potRaise(1))}>Pot</button>
          <button type="button" disabled={!canRaise} onClick={() => selectAmount(state.max_raise_to)}>All-in</button>
        </div>
        <p id="raise-help" className="raise-help">{valid ? `${amount.toLocaleString()} total · ${(amount - me.committed).toLocaleString()} more chips${amount === state.max_raise_to ? " · all-in" : ""}` : `Enter ${minimum.toLocaleString()}–${state.max_raise_to.toLocaleString()} total chips.`}</p>
        <div className="raise-confirmation">
          <button type="button" className="cancel-action" onClick={() => setEditing(false)}>Cancel</button>
          <button className="confirm-action" disabled={!canRaise || !valid}>Confirm {betLabel.toLowerCase()}{valid ? ` ${amount.toLocaleString()}` : ""}</button>
        </div>
      </form> : myTurn ? <div className="primary-actions">
        <button className="call-action" disabled={!ready || !state.call_amount} onClick={() => send({type:"check_call"})}>Call{state.call_amount > 0 ? ` ${state.call_amount.toLocaleString()}` : ""}{state.call_amount > 0 && state.call_amount === me.stack && <small>All-in</small>}</button>
        <button className="raise-action" disabled={!canRaise} onClick={() => setEditing(true)}>{betLabel}</button>
        <button className="check-action" disabled={!ready || state.call_amount > 0} onClick={() => send({type:"check_call"})}>Check</button>
        <button className="fold-action" disabled={!ready} onClick={() => send({type:"fold"})}>Fold</button>
      </div> : null}
    </div> : <div className="between-controls">
      <button className="primary" disabled={!ready || state.host !== state.you || eligible < 2} onClick={() => send({type:"start"})}>Deal {state.hand_number ? "next" : "first"} hand</button>
      <form className="stack-editor" onSubmit={e => { e.preventDefault(); const value=Number(stack); if(ready && stack.trim() && Number.isInteger(value) && value>=0 && value<=1_000_000) send({type:"set_stack",amount:value}); }}>
        <label>Your stack <input type="number" min="0" max="1000000" step="1" required value={stack} onChange={e => setStack(e.target.value)} disabled={!ready} /></label>
        <button disabled={!ready}>Set stack</button>
      </form>
    </div>}
  </section>;
}
