// frontend/src/App.tsx
import React, { useEffect, useRef, useState } from "react";
import "./App.css";

type MsgType =
  | "join"
  | "message"
  | "draw_card"
  | "start_game"
  | "fold"
  | "check_call"
  | "commit_money";

interface ChatMessage {
  type: MsgType;
  username?: string;
  text?: string;
  amount?: number;
}

type ServerEvent =
  | { type: "new_round"; hand: string[] }
  | { type: "chat" | "system" | "info" | "error"; message: string }
  | { type: "set_blind"; amount: number }
  | { type: "game_state_update"; game_state: SharedGameState }
  | { type: "get_hand"; hand: string[] }
  | { type: "your_turn_now" }
  | { type: string;[key: string]: any };

interface PlayerShared {
  username: string;
  isActive: boolean;
  isInHand: boolean;
  stack_size: number;
  current_raised: number;
  money_commited_this_round: number;
  your_turn: boolean;
}

interface SharedGameState {
  pot: number;
  board: string[];
  players: PlayerShared[];
  small_blind: number;
  big_blind: number;
  threshold: number;
  last_raise: number;
  started: boolean;
}

const username = `Player ${Math.ceil(Math.random() * 100)}`;

function App() {
  const [messages, setMessages] = useState<string[]>([]);
  const [hand, setHand] = useState<string[]>([]);
  const [input, setInput] = useState("");
  const [raiseAmt, setRaiseAmt] = useState<string>("");
  const [sharedGameState, setSharedGameState] = useState<SharedGameState | null>(null);

  const ws = useRef<WebSocket | null>(null);

  useEffect(() => {
    ws.current = new WebSocket("ws://localhost:8000/ws");
    ws.current.onopen = () => { send({ type: "join", username }); };
    ws.current.onclose = () => { setMessages((prev) => [...prev, "🔌 Disconnected"]); };
    return () => { ws.current?.close(); };
  }, []);

  useEffect(() => {
    if (!ws.current) return;
    ws.current.onmessage = (event: MessageEvent) => {
      const raw = event.data;

      console.log(raw)
      try {
        const msg: ServerEvent = JSON.parse(raw);
        switch (msg.type) {
          case "new_round":
            setHand(Array.isArray((msg as any).hand) ? (msg as any).hand : []);
            setMessages([`🃏 You were dealt: ${((msg as any).hand || []).join(", ")}`]);
            break;
          case "game_state_update":
            setSharedGameState((msg as any).game_state as SharedGameState);
            break;
          case "get_hand":
            setHand((msg as any).hand ?? []);
            break;
          case "chat":
          case "system":
          case "info":
          case "error":
            setMessages((prev) => [...prev, (msg as any).message]);
            break;
          default:
            setMessages((prev) => [...prev, `${JSON.stringify(msg)}`]);
            break;
        }
      } catch {
        setMessages((prev) => [...prev, raw]);
      }
    };
  }, []);

  const send = (msg: ChatMessage) => {
    if (ws.current && ws.current.readyState === WebSocket.OPEN) {
      ws.current.send(JSON.stringify(msg));
    }
  };

  const sendChat = () => {
    if (!input.trim()) return;
    send({ type: "message", username, text: input });
    setInput("");
  };

  const startGame = () => send({ type: "start_game", username });
  const fold = () => { send({ type: "fold", username }); };
  const checkOrCall = () => {
    if (!sharedGameState) return;
    send({ type: "commit_money", amount: sharedGameState.threshold });
  };
  const raise = () => {
    if (!sharedGameState) return;
    const me = getMyPlayerObject();
    const amt = Number(raiseAmt);
    if (!Number.isFinite(amt) || amt <= 0) {
      setMessages((prev) => [...prev, "⚠️ Enter a valid positive raise amount"]);
      return;
    }
    const commit = amt + (me?.money_commited_this_round ?? 0);
    send({ type: "commit_money", username, amount: commit });
    setMessages((prev) => [...prev, `You: Raise ${amt}`]);
  };

  const getMyPlayerObject = (): PlayerShared | undefined =>
    sharedGameState?.players.find((p) => p.username === username);

  // Seat geometry for elliptical table
  const seatStyle = (idx: number, total: number) => {
    const angle = (-Math.PI / 2) + (idx * (2 * Math.PI / total)); // start top, clockwise

    // Radii for ellipse (half of width and height minus padding)
    const rx = 500; // horizontal radius (adjust as needed)
    const ry = 300;
    ; // vertical radius (adjust as needed)

    // Center of table-wrapper (half of its width/height)
    const cx = 1200 / 2;
    const cy = 640 / 2;

    const x = cx + rx * Math.cos(angle);
    const y = cy + ry * Math.sin(angle);

    return {
      left: `${x}px`,
      top: `${y}px`,
      transform: "translate(-50%, -50%)",
      position: "absolute" as const
    };
  };

  return (
    <div className="app-root">
      <h1 className="title">Headwins Poker</h1>

      {!sharedGameState ? (
        <div className="waiting">Waiting for game state...</div>
      ) : (
        <>
          {/* Centered, scalable table */}
          <div className="table-shell">
            <div className="table-wrapper">
              <div className="table-felt" />
              <div className="table-center">
                <div className="pot">💰 Pot: {sharedGameState.pot}</div>
                <div className="blinds">
                  <span>SB: {sharedGameState.small_blind}</span>
                  <span>BB: {sharedGameState.big_blind}</span>
                </div>
                <div className="board">
                  <div className="board-title">Board</div>
                  {sharedGameState.board?.length ? (
                    <div className="cards-row">
                      {sharedGameState.board.map((c, i) => (
                        <span key={i} className="card">{c}</span>
                      ))}
                    </div>
                  ) : (
                    <div className="muted">— no cards yet —</div>
                  )}
                </div>
              </div>

              {sharedGameState.players.map((p, i) => {
                const me = p.username === username;
                return (
                  <div
                    key={p.username}
                    className={`seat ${me ? "me" : ""} ${p.isActive ? "active" : ""} ${p.isInHand ? "" : "folded"}`}
                    style={seatStyle(i, sharedGameState.players.length)}
                  >
                    <div className="seat-name">{p.username} {me ? "(you)" : ""}</div>
                    <div className="seat-row"><span className="chip">Stack: {p.stack_size}</span></div>
                    <div className="seat-row"><span className="chip">In: {p.money_commited_this_round ?? 0}</span></div>
                    {me && (
                      <div className="my-hand">
                        {hand.length ? hand.map((c, j) => <span key={j} className="card small">{c}</span>)
                          : <span className="muted">— hand —</span>}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          {/* Top-right log with chat underneath */}
          <div className="log-and-chat">
            <div className="log">
              <div className="log-title">Table Log</div>
              <div className="log-body">
                {messages.map((m, i) => (
                  <div key={i} className="log-line">{m}</div>
                ))}
              </div>
            </div>

            <div className="chat">
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Type a message"
                onKeyDown={(e) => e.key === "Enter" && sendChat()}
              />
              <button onClick={sendChat}>Send</button>
            </div>
          </div>

          {/* Bottom-left controls */}
          <div className="controls">
            {getMyPlayerObject().your_turn && (
              <div className="actions">
                <button onClick={fold}>Fold</button>
                <button onClick={checkOrCall}>
                  {getMyPlayerObject()?.money_commited_this_round === sharedGameState.threshold ? "Check" : "Call"}
                </button>
                <input
                  type="number"
                  min="1"
                  step="1"
                  value={raiseAmt}
                  onChange={(e) => setRaiseAmt(e.target.value)}
                  placeholder="Raise amount"
                />
                <button onClick={raise}>Raise</button>
              </div>
            )}
            <div className="misc">
              {
                // !sharedGameState.started &&
                <button onClick={startGame}>Restart Game</button>
              }
              <div className="whoami">Connected as <b>{username}</b></div>
            </div>
          </div>
        </>



      )}
    </div>
  );
}

export default App;
