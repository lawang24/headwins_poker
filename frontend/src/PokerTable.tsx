import { useRef, useState, type CSSProperties } from "react";
import type { Action } from "./ActionControls";
import { formatAmount } from "./amounts";
import { Cards } from "./Cards";
import type { Player, State } from "./types";

// Portrait seats use two side rails, with seat 1 below the board.
function portraitPosition(index: number, count: number): [number, number] {
  if (index === 0) return [50, 91];
  if (count === 2) return [50, 10];
  const leftCount = Math.floor((count - 1) / 2);
  const rightCount = count - 1 - leftCount;
  const rails: Record<number, number[]> = { 1: [24], 2: [18, 76], 3: [14, 32, 78], 4: [14, 32, 66, 84] };
  if (index <= leftCount) return [20, [...rails[leftCount]].reverse()[index - 1]];
  return [80, rails[rightCount][index - leftCount - 1]];
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
    : !player.in_hand && state.running ? "Next hand" : mine ? "You" : "";
  return <article
    className={`table-seat ${mine ? "is-you" : ""} ${acting ? "is-acting" : ""} ${player.folded ? "is-folded" : ""} ${!player.connected ? "is-disconnected" : ""} ${payout ? "is-winner" : ""}`}
    style={{ "--seat-x": `${x}%`, "--seat-y": `${y}%`, "--mobile-x": `${mx}%`, "--mobile-y": `${my}%` } as CSSProperties}
    aria-label={`${player.name}${mine ? ", you" : ""}, ${formatAmount(player.stack, state.cents)} chips${label ? `, ${label}` : ""}`}
  >
    <div className="seat-body">
      <div className="seat-cards">
        {cards.length ? <Cards cards={cards} /> : covered ? <div className="card-backs" aria-label="Two hidden cards"><span /><span /></div> : <div className="empty-cards" aria-hidden="true">{player.folded ? "×" : ""}</div>}
      </div>
      <button type="button" className="nameplate" onClick={select} aria-label={`Player options for ${player.name}`}>
        <strong title={player.name}>{player.name}</strong>
        <span className="seat-balance">{formatAmount(player.stack, state.cents)}</span>
        <span className="player-status">{label || `Seat ${player.seat + 1}`}</span>
      </button>
      {player.id === state.dealer && <span className="dealer-marker" title="Dealer" aria-label="Dealer">D</span>}
      {payout > 0 && <span className="seat-payout">+{formatAmount(payout, state.cents)}</span>}
    </div>
  </article>;
}

export function PokerTable({ state, ready, send }: {
  state: State; ready: boolean; send: (action: Action) => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const player = state.players.find(p => p.id === selected);
  const players = state.players;

  const eligible = players.filter(p => p.connected && p.stack > 0).length;
  return <div className="table-stage" data-player-count={9}>
    <div className="felt">
      <div className="board-content">
        <div className="pot" aria-label={`Pot ${formatAmount(state.pot, state.cents)} chips`}><span>Pot</span> {formatAmount(state.pot, state.cents)}</div>
        <div className="community-cards">
          <Cards cards={state.board} />
        </div>
        <p className="table-caption">{state.running ? `${players.find(p => p.id === state.actor)?.name || "Table"} to act` : state.street === "complete" ? "Hand complete" : eligible < 2 ? "Waiting for players" : "Ready for the next hand"}</p>
      </div>
      <span className="felt-brand" aria-hidden="true">HEADWINS <b>POKER</b></span>
    </div>
    {Array.from({ length: 9 }, (_, index) => {
      const occupant = players.find(p => p.seat === index);
      const [mx, my] = portraitPosition(index, 9);
      const angle = index * Math.PI * 2 / 9;
      return occupant ? <Seat key={index} player={occupant} state={state} index={index} count={9} select={() => {
        setSelected(occupant.id);
        dialog.current?.showModal();
      }} /> : <button key={index} className="table-seat empty-seat" type="button"
        style={{ "--seat-x": `${50 - 40 * Math.sin(angle)}%`, "--seat-y": `${50 + 37 * Math.cos(angle)}%`, "--mobile-x": `${mx}%`, "--mobile-y": `${my}%` } as CSSProperties}
        disabled={!ready || state.running} title={state.running ? "Change seats between hands" : `Move to seat ${index + 1}`}
        onClick={() => send({ type: "move_seat", seat: index })}>
        <span aria-hidden="true">+</span> Seat {index + 1}
      </button>;
    })}
    <dialog ref={dialog} className="feedback-modal player-modal" aria-labelledby="player-title">
      <h2 id="player-title">{player?.name || "Player has left"}</h2>
      {player && <p>Seat {player.seat + 1} · {formatAmount(player.stack, state.cents)} chips</p>}
      {player?.id === state.you
        ? <p>Click an empty seat to move between hands.</p>
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
      return state.running && player.committed > 0 ? <div key={player.id} className="table-bet" style={{left: `${50 - 28 * Math.sin(angle)}%`, top: `${50 + 24 * Math.cos(angle)}%`, "--desktop-bet-x": `${50 - 28 * Math.sin(angle)}%`, "--desktop-bet-y": `${50 + 24 * Math.cos(angle)}%`, "--mobile-bet-x": `${50 + (mx - 50) * .58}%`, "--mobile-bet-y": `${my + (my < 50 ? 8 : -3)}%`} as CSSProperties} aria-label={`${player.name} bet ${formatAmount(player.committed, state.cents)}`}><i aria-hidden="true" />{formatAmount(player.committed, state.cents)}</div> : null;
    })}
  </div>;
}
