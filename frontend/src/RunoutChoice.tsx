import { useEffect, useRef, useState } from "react";
import type { Action } from "./ActionControls";
import type { State } from "./types";
import "./Runouts.css";

export function RunoutChoice({ state, ready, send }: {
  state: State; ready: boolean; send: (action: Action) => void;
}) {
  const vote = state.runout_vote!;
  const dialog = useRef<HTMLDialogElement>(null);
  const [now, setNow] = useState(Date.now);
  const involved = vote.eligible.includes(state.you);
  const chosen = vote.votes[state.you];
  const remaining = Math.max(0, Math.ceil((Date.parse(vote.deadline) - now) / 1000));
  const waiting = vote.eligible.filter(id => vote.votes[id] === undefined);
  useEffect(() => {
    const element = dialog.current;
    element?.showModal();
    const timer = setInterval(() => setNow(Date.now()), 250);
    return () => { clearInterval(timer); element?.close(); };
  }, []);
  const choose = (count: number) => send({ type: "runout", count, hand_id: vote.hand_id });
  return <dialog ref={dialog} className="runout-dialog" aria-labelledby="runout-title"
    aria-describedby="runout-description" onCancel={event => event.preventDefault()}>
    <p className="eyebrow">BETTING COMPLETE</p>
    <h2 id="runout-title">Run it once or twice?</h2>
    <p id="runout-description">Two runs split each pot across two boards. Cards already on the table stay the same. Everyone still in the hand must agree.</p>
    {involved ? <div className="runout-actions">
      <button autoFocus disabled={!ready || chosen !== undefined || remaining === 0} onClick={() => choose(1)}>Run once</button>
      <button className="primary" disabled={!ready || chosen !== undefined || remaining === 0} onClick={() => choose(2)}>Run twice</button>
    </div> : <p className="runout-spectator">The players still in this hand are choosing.</p>}
    <p className="runout-progress" role="status">{chosen === 2 ? "You chose twice. " : ""}{waiting.length} of {vote.eligible.length} players still choosing.</p>
    <ul className="runout-players">
      {vote.eligible.map(id => <li key={id}>
        <span>{state.players.find(p => p.id === id)?.name}{id === state.you ? " (you)" : ""}</span>
        <strong>{vote.votes[id] === 2 ? "Twice" : "Choosing…"}</strong>
      </li>)}
    </ul>
    <p className="runout-timeout">{remaining > 0 ? `Runs once in ${remaining}s unless everyone chooses twice.` : "Resolving the runout…"}</p>
    {!ready && <p role="status">Waiting for connection or update…</p>}
  </dialog>;
}
