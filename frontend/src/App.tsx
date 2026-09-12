import { useEffect, useRef, useState } from "react";
import "./App.css";

type Player = {
  id: string;
  name: string;
  stack: number;
  connected: boolean;
  in_hand: boolean;
  folded: boolean;
  committed: number;
  all_in: boolean;
};
type State = {
  players: Player[];
  you: string;
  host: string;
  dealer: string;
  actor: string | null;
  street: string;
  running: boolean;
  board: string[];
  hand: string[];
  pot: number;
  target: number;
  small_blind: number;
  big_blind: number;
  min_raise_to: number;
  max_raise_to: number;
  can_raise: boolean;
  call_amount: number;
  hand_number: number;
  history: string[];
  result: null | {
    payouts: Record<string, number>;
    hands: Record<string, string[]>;
  };
};
type Message = { type: string; amount?: number; text?: string };
const assets = import.meta.glob(
  [
    "./assets/SVG-cards-1.3/*.svg",
    "!./assets/SVG-cards-1.3/*2.svg",
    "!./assets/SVG-cards-1.3/*joker.svg",
  ],
  { eager: true, query: "?url", import: "default" },
) as Record<string, string>;
const ranks: Record<string, string> = {
  T: "10",
  J: "jack",
  Q: "queen",
  K: "king",
  A: "ace",
};
const suits: Record<string, string> = {
  h: "hearts",
  d: "diamonds",
  c: "clubs",
  s: "spades",
};
function Card({ code }: { code: string }) {
  const name = `${ranks[code[0]] || code[0]}_of_${suits[code[1]]}`;
  return (
    <img
      className="card"
      src={assets[`./assets/SVG-cards-1.3/${name}.svg`]}
      alt={name.replaceAll("_", " ")}
    />
  );
}
function Cards({ cards }: { cards: string[] }) {
  return (
    <div className="cards">
      {cards.map((c) => (
        <Card key={c} code={c} />
      ))}
    </div>
  );
}
const sessionKey = "headwins:global";

export default function App() {
  const [name, setName] = useState(
    sessionStorage.getItem(`${sessionKey}:name`) || "",
  );
  const [joined, setJoined] = useState(
    Boolean(sessionStorage.getItem(`${sessionKey}:token`)),
  );
  const [state, setState] = useState<State | null>(null);
  const [status, setStatus] = useState("Offline");
  const [error, setError] = useState("");
  const [chat, setChat] = useState("");
  const [raiseTo, setRaiseTo] = useState("");
  const [stack, setStack] = useState("1000");
  const [pending, setPending] = useState(false);
  const [copied, setCopied] = useState(false);
  const ws = useRef<WebSocket | null>(null);
  const log = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!joined) return;
    let stopped = false;
    let retry: ReturnType<typeof setTimeout>;
    let attempts = 0;
    function connect() {
      setStatus("Connecting");
      const configured = import.meta.env.VITE_WS_URL as string | undefined;
      const url = new URL(
        configured ||
          `${location.protocol === "https:" ? "wss:" : "ws:"}//${location.host}/ws`,
      );
      const socket = new WebSocket(url);
      ws.current = socket;
      socket.onopen = () => {
        if (stopped) {
          socket.close();
          return;
        }
        attempts = 0;
        setStatus("Connected");
        setError("");
        socket.send(
          JSON.stringify({
            type: "join",
            name: sessionStorage.getItem(`${sessionKey}:name`) || "Player",
            token: sessionStorage.getItem(`${sessionKey}:token`),
          }),
        );
      };
      socket.onmessage = (event) => {
        if (stopped) return;
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === "session")
            sessionStorage.setItem(`${sessionKey}:token`, msg.token);
          if (msg.type === "state") {
            setState(msg.state);
            setPending(false);
          }
          if (msg.type === "error") {
            setError(msg.message);
            setPending(false);
          }
        } catch {
          setError("The server sent an unreadable response.");
        }
      };
      socket.onerror = () => {
        if (!stopped)
          setError("Connection failed. Check that the server is running.");
      };
      socket.onclose = (event) => {
        if (stopped) return;
        setPending(false);
        if (event.code === 4001) {
          setStatus("Seat opened elsewhere");
          setError(
            "This seat was opened in another window. Close this window or reload to reclaim it.",
          );
          return;
        }
        setStatus("Reconnecting");
        retry = setTimeout(connect, Math.min(1000 * 2 ** attempts++, 10000));
      };
    }
    connect();
    return () => {
      stopped = true;
      clearTimeout(retry);
      ws.current?.close();
    };
  }, [joined]);
  useEffect(() => {
    log.current?.scrollTo({ top: log.current.scrollHeight });
  }, [state?.history]);

  const send = (msg: Message) => {
    if (ws.current?.readyState !== WebSocket.OPEN) {
      setError("Wait until you reconnect.");
      return;
    }
    setError("");
    if (msg.type === "raise") setRaiseTo("");
    setPending(true);
    ws.current.send(JSON.stringify(msg));
  };
  const me = state?.players.find((p) => p.id === state.you);
  const myTurn = state?.actor === state?.you;
  const ready = status === "Connected" && !pending;
  const eligible =
    state?.players.filter((p) => p.connected && p.stack > 0).length || 0;
  const raiseAmount = Number(raiseTo);
  const validRaise =
    state &&
    Number.isInteger(raiseAmount) &&
    raiseAmount > state.target &&
    raiseAmount <= state.max_raise_to &&
    (raiseAmount >= state.min_raise_to || raiseAmount === state.max_raise_to);

  return (
    <main className="app">
      <header>
        <div>
          <p className="eyebrow">PLAY MONEY • NO-LIMIT HOLD’EM</p>
          <h1>Headwins Poker</h1>
        </div>
        <div className="connection-info">
          <span className={`status ${status === "Connected" ? "online" : ""}`}>
            {status}
          </span>
          {joined && (
            <button
              onClick={() => {
                setJoined(false);
                setState(null);
                setStatus("Offline");
                setPending(false);
                setError("");
                sessionStorage.removeItem(`${sessionKey}:token`);
              }}
            >
              Leave table
            </button>
          )}
          <button
            onClick={async () => {
              try {
                await navigator.clipboard.writeText(
                  `${location.origin}${location.pathname}`,
                );
                setCopied(true);
              } catch {
                setError(
                  "Copy the table URL from your address bar to invite friends.",
                );
              }
            }}
          >
            {copied ? "Link copied" : "Invite friends"}
          </button>
        </div>
      </header>
      {error && (
        <div role="alert" className="error">
          {error}
          <button aria-label="Dismiss error" onClick={() => setError("")}>
            ×
          </button>
        </div>
      )}
      {!joined ? (
        <section className="join panel">
          <p className="eyebrow">TAKE A SEAT</p>
          <h2>Bring your poker face.</h2>
          <p>
            Join this table with 1,000 play chips. Share the table link to play
            with friends.
          </p>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (!name.trim()) return;
              sessionStorage.setItem(`${sessionKey}:name`, name.trim());
              setJoined(true);
            }}
          >
            <label>
              Your name
              <input
                autoFocus
                maxLength={24}
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Enter your name"
              />
            </label>
            <button className="primary">Join table</button>
          </form>
          <p className="hint">
            Two to nine players. Stacks can be adjusted between hands.
          </p>
        </section>
      ) : !state ? (
        <section className="panel join" role="status">
          <h2>Connecting to the table…</h2>
          <p>
            The server should be available in a moment. Connection retries
            happen automatically.
          </p>
        </section>
      ) : (
        <>
          <div className="game-layout">
            <section className="table-area" aria-label="Poker table">
              <div className="table-heading">
                <span>Hand #{state.hand_number}</span>
                <strong>{state.street}</strong>
                <span>
                  Blinds {state.small_blind} / {state.big_blind}
                </span>
              </div>
              <div className="felt">
                <div className="pot-label">
                  {state.running
                    ? "IN THE POT"
                    : state.street === "complete"
                      ? "HAND COMPLETE"
                      : "READY WHEN YOU ARE"}
                </div>
                <div className="pot">
                  {state.running ? state.pot.toLocaleString() : "♠"}
                </div>
                {state.board.length ? (
                  <Cards cards={state.board} />
                ) : (
                  <div className="board-placeholder">
                    Community cards appear here
                  </div>
                )}
                <p className="table-caption">
                  {state.running
                    ? `${state.players.find((p) => p.id === state.actor)?.name || "Table"} to act`
                    : eligible < 2
                      ? "Waiting for at least two players with chips"
                      : "The host can deal the next hand"}
                </p>
              </div>
              <div className="seats">
                {state.players.map((p) => (
                  <article
                    key={p.id}
                    className={`seat ${state.actor === p.id ? "acting" : ""} ${p.folded ? "folded" : ""}`}
                  >
                    <div className="seat-title">
                      <strong>
                        {p.name}
                        {p.id === state.you ? " (you)" : ""}
                      </strong>
                      {p.id === state.dealer && (
                        <span className="dealer" title="Dealer">
                          D
                        </span>
                      )}
                    </div>
                    <div className="stack">
                      {p.stack.toLocaleString()} <span>chips</span>
                    </div>
                    <div className="seat-meta">
                      {!p.connected
                        ? "Disconnected"
                        : p.folded
                          ? "Folded"
                          : p.all_in && state.running
                            ? "All-in"
                            : state.actor === p.id
                              ? "Thinking…"
                              : !p.in_hand && state.running
                                ? "Next hand"
                                : p.id === state.host
                                  ? "Table host"
                                  : "Seated"}
                      {state.running &&
                        p.committed > 0 &&
                        ` · Bet ${p.committed}`}
                    </div>
                    {state.result?.hands[p.id] && (
                      <Cards cards={state.result.hands[p.id]} />
                    )}
                    {Boolean(state.result?.payouts[p.id]) && (
                      <div className="payout">
                        Received {state.result?.payouts[p.id]} chips
                      </div>
                    )}
                  </article>
                ))}
              </div>
              <section className="hand-controls panel">
                <div>
                  <p className="eyebrow">YOUR HAND</p>
                  {state.hand.length ? (
                    <Cards cards={state.hand} />
                  ) : (
                    <p className="hint">You’ll be dealt in next hand.</p>
                  )}
                </div>
                <div className="controls">
                  <h2>
                    {state.running
                      ? myTurn
                        ? "Your move"
                        : "Waiting for your turn"
                      : "Between hands"}
                  </h2>
                  {state.running ? (
                    <>
                      <p className="hint">
                        {myTurn
                          ? state.call_amount
                            ? `${state.call_amount} to call${me && state.call_amount === me.stack ? " (all-in)" : ""}`
                            : "You can check"
                          : "Actions unlock when it’s your turn."}
                      </p>
                      <div className="action-row">
                        <button
                          disabled={!ready || !myTurn}
                          onClick={() => send({ type: "fold" })}
                        >
                          Fold
                        </button>
                        <button
                          className="primary"
                          disabled={!ready || !myTurn}
                          onClick={() => send({ type: "check_call" })}
                        >
                          {state.call_amount
                            ? `Call ${state.call_amount}`
                            : "Check"}
                        </button>
                      </div>
                      <form
                        className="raise-row"
                        onSubmit={(e) => {
                          e.preventDefault();
                          if (validRaise)
                            send({ type: "raise", amount: raiseAmount });
                        }}
                      >
                        <label>
                          Raise to (total chips)
                          <input
                            type="number"
                            step="1"
                            min={Math.min(
                              state.min_raise_to,
                              state.max_raise_to,
                            )}
                            max={state.max_raise_to}
                            placeholder={`${Math.min(state.min_raise_to, state.max_raise_to)}`}
                            value={raiseTo}
                            onChange={(e) => setRaiseTo(e.target.value)}
                            disabled={!ready || !myTurn || !state.can_raise}
                          />
                        </label>
                        <button
                          disabled={
                            !ready || !myTurn || !state.can_raise || !validRaise
                          }
                        >
                          Raise
                        </button>
                        <button
                          type="button"
                          disabled={!ready || !myTurn || !state.can_raise}
                          onClick={() =>
                            send({ type: "raise", amount: state.max_raise_to })
                          }
                        >
                          All-in
                        </button>
                      </form>
                    </>
                  ) : (
                    <>
                      <button
                        className="primary"
                        disabled={
                          !ready || state.host !== state.you || eligible < 2
                        }
                        onClick={() => send({ type: "start" })}
                      >
                        Deal {state.hand_number ? "next" : "first"} hand
                      </button>
                      {state.host !== state.you && (
                        <p className="hint">
                          Waiting for{" "}
                          {state.players.find((p) => p.id === state.host)?.name}
                          , the table host.
                        </p>
                      )}
                      <form
                        className="raise-row"
                        onSubmit={(e) => {
                          e.preventDefault();
                          send({ type: "set_stack", amount: Number(stack) });
                        }}
                      >
                        <label>
                          Your play-chip stack
                          <input
                            type="number"
                            min="0"
                            max="1000000"
                            step="1"
                            required
                            value={stack}
                            onChange={(e) => setStack(e.target.value)}
                          />
                        </label>
                        <button disabled={!ready}>Set stack</button>
                      </form>
                    </>
                  )}
                </div>
              </section>
            </section>
            <aside className="panel chat-panel">
              <h2>Table talk</h2>
              <div
                className="log"
                ref={log}
                role="log"
                aria-label="Table activity"
              >
                {state.history.length ? (
                  state.history.map((m, i) => <p key={i}>{m}</p>)
                ) : (
                  <p className="hint">Welcome to the table. Say hello.</p>
                )}
              </div>
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  if (!chat.trim()) return;
                  send({ type: "chat", text: chat });
                  setChat("");
                }}
              >
                <label className="sr-only" htmlFor="chat">
                  Chat message
                </label>
                <input
                  id="chat"
                  maxLength={300}
                  value={chat}
                  onChange={(e) => setChat(e.target.value)}
                  placeholder="Message the table…"
                />
                <button disabled={!ready || !chat.trim()}>Send</button>
              </form>
            </aside>
          </div>
          <footer>
            Connected as {me?.name} · Disconnecting folds a live hand unless
            you’re all-in. Refreshing restores your seat; a server restart
            resets the table.
          </footer>
        </>
      )}
    </main>
  );
}
