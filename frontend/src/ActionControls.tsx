import { useState } from "react";
import type { State } from "./types";

export type Action = { type: string; amount?: number; text?: string };

export function ActionControls({ state, ready, send }: {
  state: State; ready: boolean; send: (action: Action) => void;
}) {
  const me = state.players.find(p => p.id === state.you)!;
  const myTurn = state.actor === state.you;
  const minimum = Math.min(state.min_raise_to, state.max_raise_to);
  const [raiseTo, setRaiseTo] = useState(String(minimum));
  const [stack, setStack] = useState(String(me.stack));
  const amount = Number(raiseTo);
  const canRaise = ready && myTurn && state.can_raise;
  const valid = raiseTo.trim() !== "" && Number.isInteger(amount) && amount > state.target && amount <= state.max_raise_to && (amount >= state.min_raise_to || amount === state.max_raise_to);
  const sliderValue = Number.isFinite(amount) ? Math.max(minimum, Math.min(state.max_raise_to, amount)) : minimum;
  const eligible = state.players.filter(p => p.connected && p.stack > 0).length;
  return <section className="action-controls" aria-label="Game controls">
    <div className="action-status" role="status">
      {state.running ? myTurn ? "Your turn" : `${state.players.find(p => p.id === state.actor)?.name || "Player"} to act` : "Between hands"}
      <span>{!ready ? "Waiting for connection or update…" : state.running && myTurn ? state.call_amount ? `${state.call_amount.toLocaleString()} to call${state.call_amount === me.stack ? " · all-in" : ""}` : "You can check" : state.running ? "Actions unlock on your turn" : state.host === state.you ? "You are the table host" : "Waiting for the host to deal"}</span>
    </div>
    {state.running ? <div className="betting-controls">
      <div className="primary-actions">
        <button className="fold-action" disabled={!ready || !myTurn} onClick={() => send({type:"fold"})}>Fold</button>
        <button className="primary" disabled={!ready || !myTurn} onClick={() => send({type:"check_call"})}>{state.call_amount ? `Call ${state.call_amount.toLocaleString()}` : "Check"}</button>
        <button className="raise-action" disabled={!canRaise || !valid} onClick={() => send({type:"raise",amount})}>Raise to {valid ? amount.toLocaleString() : "—"}</button>
      </div>
      <form className="raise-editor" onSubmit={e => {e.preventDefault(); if(canRaise && valid) send({type:"raise",amount});}}>
        <label className="raise-amount">Raise to <input aria-label="Raise to (total chips)" type="number" step="1" min={minimum} max={state.max_raise_to} value={raiseTo} disabled={!canRaise} onChange={e => setRaiseTo(e.target.value)} /></label>
        <input className="raise-slider" type="range" aria-label="Raise amount slider" aria-valuetext={`${sliderValue} total chips`} min={minimum} max={state.max_raise_to} step="1" value={sliderValue} disabled={!canRaise} onChange={e => setRaiseTo(e.target.value)} />
        <button type="button" className="all-in-action" disabled={!canRaise} onClick={() => send({type:"raise",amount:state.max_raise_to})}>All-in</button>
      </form>
    </div> : <div className="between-controls">
      <button className="primary" disabled={!ready || state.host !== state.you || eligible < 2} onClick={() => send({type:"start"})}>Deal {state.hand_number ? "next" : "first"} hand</button>
      <form className="stack-editor" onSubmit={e => { e.preventDefault(); const value=Number(stack); if(ready && stack.trim() && Number.isInteger(value) && value>=0 && value<=1_000_000) send({type:"set_stack",amount:value}); }}>
        <label>Your stack <input type="number" min="0" max="1000000" step="1" required value={stack} onChange={e => setStack(e.target.value)} disabled={!ready} /></label>
        <button disabled={!ready}>Set stack</button>
      </form>
    </div>}
  </section>;
}
