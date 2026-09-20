import { useRef, useState, type CSSProperties } from "react";
import type { Action } from "./ActionControls";
import { formatAmount, inputAmount, parseAmount } from "./amounts";
import { Cards } from "./Cards";
import type { Player, State } from "./types";

// Portrait seats use two side rails, with seat 1 below the board.
function portraitPosition(index: number, count: number): [number, number] {
  if (index === 0) return [50, 86];
  if (count === 2) return [50, 10];
  const leftCount = Math.floor((count - 1) / 2);
  const rightCount = count - 1 - leftCount;
  // Leave room for stacked cards and nameplates on short portrait tables.
  const rails: Record<number, number[]> = { 1: [24], 2: [18, 76], 3: [14, 32, 78], 4: [17, 33, 58, 74] };
  if (index <= leftCount) return [14, [...rails[leftCount]].reverse()[index - 1]];
  return [86, rails[rightCount][index - leftCount - 1]];
}

function Seat({ player, state, index, count, select }: {
  player: Player; state: State; index: number; count: number; select: () => void;
}) {
  const angle = (index * Math.PI * 2) / Math.max(count, 2);
  const x = 50 - 40 * Math.sin(angle);
  const y = 50 + 37 * Math.cos(angle);
  const [mx, my] = portraitPosition(index, count);
  const mine = player.id === state.you;
  const cards = mine ? state.hand : state.result?.hands[player.id] || [];
  const covered = !mine && state.running && player.in_hand && !player.folded;
  const acting = state.actor === player.id;
  const payout = state.result?.payouts[player.id] || 0;
  const label = !player.connected ? "Disconnected" : player.folded ? "Folded"
    : player.all_in && state.running ? "All-in" : acting ? "To act"
    : !player.in_hand && state.running ? "Next hand" : "";
  return <article
    className={`table-seat ${mine ? "is-you" : ""} ${acting ? "is-acting" : ""} ${player.folded ? "is-folded" : ""} ${!player.connected ? "is-disconnected" : ""} ${payout ? "is-winner" : ""}`}
    style={{ "--seat-x": `${x}%`, "--seat-y": `${y}%`, "--mobile-x": `${mx}%`, "--mobile-y": `${my}%` } as CSSProperties}
    data-seat={index + 1}
    aria-label={`${player.name}${mine ? ", you" : ""}, ${formatAmount(player.stack, state.cents)} chips${label ? `, ${label}` : ""}`}
  >
    <div className="seat-body">
      <div className="seat-cards">
        {cards.length ? <Cards cards={cards} hole /> : covered ? <div className="card-backs" aria-label="Two hidden cards"><span /><span /></div> : <div className="empty-cards" aria-hidden="true">{player.folded ? "×" : ""}</div>}
      </div>
      <button type="button" className="nameplate" onClick={select} aria-label={`Player options for ${player.name}`}>
        <strong title={player.name}>{player.name}</strong>
        <span className="seat-balance">{formatAmount(player.stack, state.cents)}</span>
        {payout > 0 && <span className="seat-payout">+{formatAmount(payout, state.cents)}</span>}
        {label && !payout && <span className="player-status">{label}</span>}
      </button>
      {player.id === state.dealer && <span className="dealer-marker" title="Dealer" aria-label="Dealer">D</span>}
    </div>
  </article>;
}

function PlayerStackEditor({ player, state, ready, send, close }: {
  player: Player; state: State; ready: boolean; send: (action: Action) => void; close: () => void;
}) {
  const [stack, setStack] = useState(inputAmount(player.stack, state.cents));
  const amount = parseAmount(stack, state.cents);
  const editable = ready && !state.running;
  const valid = Number.isInteger(amount) && amount >= 0 && amount <= 1_000_000;
  const unit = state.cents ? 100 : 1;
  return <form onSubmit={event => {
    event.preventDefault();
    if (!editable || !valid) return;
    send({ type: "set_stack", amount });
    close();
  }}>
    <label>Your stack
      <input type="number" min="0" max={1_000_000 / unit} step={1 / unit}
        required value={stack} disabled={!editable}
        onChange={event => setStack(event.target.value)} aria-describedby="player-stack-help" />
    </label>
    <p id="player-stack-help" className="hint">{state.running
      ? "Finish the current hand before changing your stack."
      : `Set your total stack from 0 to ${formatAmount(1_000_000, state.cents)} chips.`}</p>
    <button className="primary" disabled={!editable || !valid}>Set stack</button>
  </form>;
}

export function PokerTable({ state, ready, send }: {
  state: State; ready: boolean; send: (action: Action) => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [editorVersion, setEditorVersion] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const player = state.players.find(p => p.id === selected);
  const players = state.players;

  const eligible = players.filter(p => p.connected && p.stack > 0).length;
  const runouts = state.result?.runouts;
  const twice = runouts && runouts.length > 1;
  return <div className={`table-stage ${twice ? "has-two-runouts" : ""}`} data-player-count={9}>
    <div className="felt">
      <div className="board-content">
        <div className="pot" aria-label={`Pot ${formatAmount(state.pot, state.cents)} chips`}><span>Pot</span> {formatAmount(state.pot, state.cents)}</div>
        {twice ? <div className="runout-boards" aria-label="Two runout results">
          {runouts.map((runout, index) => <section key={index} aria-label={`Run ${index + 1}`}>
            <h3>Run {index + 1}</h3>
            <div className="community-cards"><Cards cards={runout.board} /></div>
            <p className="runout-winners">{Object.entries(runout.payouts).filter(([, amount]) => amount > 0).map(([id, amount]) => `${players.find(p => p.id === id)?.name || "Player"}: +${formatAmount(amount, state.cents)}`).join(" · ")}</p>
          </section>)}
        </div> : <div className="community-cards">
          <Cards cards={state.board} />
        </div>}
        <p className="table-caption">{state.runout_vote ? "Choosing runouts" : state.running ? `${players.find(p => p.id === state.actor)?.name || "Table"} to act` : eligible < 2 ? "Waiting for players with chips" : state.street === "complete" ? "Next hand starting soon" : "First hand starting soon"}</p>
        <p className="board-meta">Hand #{state.hand_number} · {state.street} · {formatAmount(state.small_blind, state.cents)} / {formatAmount(state.big_blind, state.cents)}</p>
      </div>
      <span className="felt-brand" aria-hidden="true">HEADWINS <b>POKER</b></span>
    </div>
    {Array.from({ length: 9 }, (_, index) => {
      const occupant = players.find(p => p.seat === index);
      const [mx, my] = portraitPosition(index, 9);
      const angle = index * Math.PI * 2 / 9;
      return occupant ? <Seat key={index} player={occupant} state={state} index={index} count={9} select={() => {
        setSelected(occupant.id);
        setEditorVersion(version => version + 1);
        dialog.current?.showModal();
      }} /> : <button key={index} className="table-seat empty-seat" data-seat={index + 1} aria-label={`Seat ${index + 1}`} type="button"
        style={{ "--seat-x": `${50 - 40 * Math.sin(angle)}%`, "--seat-y": `${50 + 37 * Math.cos(angle)}%`, "--mobile-x": `${mx}%`, "--mobile-y": `${my}%` } as CSSProperties}
        disabled={!ready || state.running} title={state.running ? "Change seats between hands" : `Move to seat ${index + 1}`}
        onClick={() => send({ type: "move_seat", seat: index })}>
        <span className="empty-seat-number" aria-hidden="true">{index + 1}</span><span aria-hidden="true">Sit</span><span className="sr-only">Seat {index + 1}</span>
      </button>;
    })}
    <dialog ref={dialog} className="feedback-modal player-modal" aria-labelledby="player-title">
      <h2 id="player-title">{player?.name || "Player has left"}</h2>
      {player && <p>Seat {player.seat + 1} · {formatAmount(player.stack, state.cents)} chips</p>}
      {player?.id === state.you
        ? <>
          <PlayerStackEditor key={`${editorVersion}:${player.stack}:${state.cents}:${state.running}`}
            player={player} state={state} ready={ready} send={send} close={() => dialog.current?.close()} />
          <p className="hint">Click an empty seat to move between hands.</p>
        </>
        : player && <p>Remove this player from the table? Their remaining chips will be cashed out. They can join again manually.</p>}
      {state.running && <p className="hint">Finish the current hand before moving seats or removing players.</p>}
      <div className="feedback-actions">
        <button autoFocus onClick={() => dialog.current?.close()}>Cancel</button>
        {player && player.id !== state.you && <button className="danger" disabled={!ready || state.running} onClick={() => {
          send({ type: "kick", player_id: player.id });
          dialog.current?.close();
        }}>Kick player</button>}
      </div>
    </dialog>
    {players.map((player) => {
      const index = player.seat;
      const angle = index * Math.PI * 2 / 9;
      const [mx, my] = portraitPosition(index, 9);
      return state.running && player.committed > 0 ? <div key={player.id} className="table-bet" style={{left: `${50 - 22 * Math.sin(angle)}%`, top: `${50 + 22 * Math.cos(angle)}%`, "--desktop-bet-x": `${50 - 22 * Math.sin(angle)}%`, "--desktop-bet-y": `${50 + 22 * Math.cos(angle)}%`, "--mobile-bet-x": `${50 + (mx - 50) * .58}%`, "--mobile-bet-y": `${my + (my < 50 ? 8 : -3)}%`} as CSSProperties} aria-label={`${player.name} bet ${formatAmount(player.committed, state.cents)}`}><i aria-hidden="true" />{formatAmount(player.committed, state.cents)}</div> : null;
    })}
  </div>;
}
