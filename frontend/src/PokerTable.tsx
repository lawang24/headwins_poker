import type { CSSProperties } from "react";
import { Cards } from "./Cards";
import type { Player, State } from "./types";

// Portrait seats follow the reference's two side rails, with the viewer below.
function portraitPosition(index: number, count: number): [number, number] {
  if (index === 0) return [50, 91];
  if (count === 2) return [50, 10];
  const leftCount = Math.floor((count - 1) / 2);
  const rightCount = count - 1 - leftCount;
  const rails: Record<number, number[]> = { 1: [24], 2: [18, 76], 3: [14, 32, 78], 4: [14, 32, 66, 84] };
  if (index <= leftCount) return [20, [...rails[leftCount]].reverse()[index - 1]];
  return [80, rails[rightCount][index - leftCount - 1]];
}

function Seat({ player, state, index, count }: {
  player: Player; state: State; index: number; count: number;
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
    : !player.in_hand && state.running ? "Next hand" : mine ? "You" : player.id === state.host ? "Host" : "";
  return <article
    className={`table-seat ${mine ? "is-you" : ""} ${acting ? "is-acting" : ""} ${player.folded ? "is-folded" : ""} ${!player.connected ? "is-disconnected" : ""} ${payout ? "is-winner" : ""}`}
    style={{ "--seat-x": `${x}%`, "--seat-y": `${y}%`, "--mobile-x": `${mx}%`, "--mobile-y": `${my}%` } as CSSProperties}
    aria-label={`${player.name}${mine ? ", you" : ""}, ${player.stack} chips${label ? `, ${label}` : ""}`}
  >
    <div className="seat-body">
      <div className="seat-cards">
        {cards.length ? <Cards cards={cards} /> : covered ? <div className="card-backs" aria-label="Two hidden cards"><span /><span /></div> : <div className="empty-cards" aria-hidden="true">{player.folded ? "×" : ""}</div>}
      </div>
      <div className="nameplate">
        <strong title={player.name}>{player.name}</strong>
        <span className="seat-balance">{player.stack.toLocaleString()}</span>
        <span className="player-status">{label || "Seated"}</span>
      </div>
      {player.id === state.dealer && <span className="dealer-marker" title="Dealer" aria-label="Dealer">D</span>}
      {payout > 0 && <span className="seat-payout">+{payout.toLocaleString()}</span>}
    </div>
  </article>;
}

export function PokerTable({ state }: { state: State }) {
  const me = state.players.findIndex(p => p.id === state.you);
  const players = me < 0 ? state.players : [...state.players.slice(me), ...state.players.slice(0, me)];
  const eligible = players.filter(p => p.connected && p.stack > 0).length;
  return <div className="table-stage" data-player-count={players.length}>
    <div className="felt">
      <div className="board-content">
        <div className="pot" aria-label={`Pot ${state.pot} chips`}><span>Pot</span> {state.pot.toLocaleString()}</div>
        <div className="community-cards">
          <Cards cards={state.board} />
        </div>
        <p className="table-caption">{state.running ? `${players.find(p => p.id === state.actor)?.name || "Table"} to act` : state.street === "complete" ? "Hand complete" : eligible < 2 ? "Waiting for players" : "Ready for the next hand"}</p>
      </div>
      <span className="felt-brand" aria-hidden="true">HEADWINS <b>POKER</b></span>
    </div>
    {players.map((player, index) => <Seat key={player.id} player={player} state={state} index={index} count={players.length} />)}
    {players.map((player, index) => {
      const angle = index * Math.PI * 2 / Math.max(players.length, 2);
      const [mx, my] = portraitPosition(index, players.length);
      return state.running && player.committed > 0 ? <div key={player.id} className="table-bet" style={{left: `${50 - 28 * Math.sin(angle)}%`, top: `${50 + 24 * Math.cos(angle)}%`, "--mobile-bet-x": `${50 + (mx - 50) * .58}%`, "--mobile-bet-y": `${my + (my < 50 ? 8 : -3)}%`} as CSSProperties} aria-label={`${player.name} bet ${player.committed}`}><i aria-hidden="true" />{player.committed.toLocaleString()}</div> : null;
    })}
  </div>;
}
