import { useEffect, useRef, useState } from "react";
import "./App.css";
import type { State } from "./types";
import { ActionControls, type Action } from "./ActionControls";
import { PokerTable } from "./PokerTable";

import { Feedback } from "./Feedback";
import { Settings } from "./Settings";
import { formatAmount } from "./amounts";

const sessionKey = "headwins:global";

export default function App() {
  const [name, setName] = useState(
    sessionStorage.getItem(`${sessionKey}:name`) || localStorage.getItem(`${sessionKey}:name`) || "",
  );
  const [joined, setJoined] = useState(
    Boolean(sessionStorage.getItem(`${sessionKey}:token`)),
  );
  const [state, setState] = useState<State | null>(null);
  const [status, setStatus] = useState("Offline");
  const [error, setError] = useState("");
  const [chat, setChat] = useState("");
  const [pending, setPending] = useState(false);
  const [copied, setCopied] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
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
            name: sessionStorage.getItem(`${sessionKey}:name`) || localStorage.getItem(`${sessionKey}:name`) || "Player",
            token: sessionStorage.getItem(`${sessionKey}:token`) || localStorage.getItem(`${sessionKey}:token`),
          }),
        );
      };
      socket.onmessage = (event) => {
        if (stopped) return;
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === "session") {
            sessionStorage.setItem(`${sessionKey}:token`, msg.token);
            localStorage.setItem(`${sessionKey}:token`, msg.token);
          }
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

  const send = (msg: Action) => {
    if (ws.current?.readyState !== WebSocket.OPEN) {
      setError("Wait until you reconnect.");
      return;
    }
    setError("");
    setPending(true);
    ws.current.send(JSON.stringify(msg));
  };
  const me = state?.players.find((p) => p.id === state.you);
  const ready = status === "Connected" && !pending;

  return (
    <main className={`app ${joined && state && !settingsOpen ? "app-table" : ""}`}>
      <header>
        <div>
          <p className="eyebrow">PLAY MONEY • NO-LIMIT HOLD’EM</p>
          <h1>Headwins Poker</h1>
        </div>
        <div className="connection-info">
          <span className={`status ${status === "Connected" ? "online" : ""}`}>
            {status}
          </span>
          {state && <button aria-pressed={settingsOpen} onClick={() => setSettingsOpen(!settingsOpen)}>{settingsOpen ? "Table" : "Settings"}</button>}
          {joined && <button className="chat-toggle" aria-expanded={chatOpen} aria-controls="table-chat" onClick={() => setChatOpen(!chatOpen)}>{chatOpen ? "Close chat" : "Chat & log"}</button>}
          {joined && (
            <button
              onClick={() => {
                setSettingsOpen(false);
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
        <Feedback name={me?.name || name} />
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
          <h2>Join the table</h2>
          <p>
            Join this table with 1,000 play chips. Share the table link to play
            with friends.
          </p>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (!name.trim()) return;
              sessionStorage.setItem(`${sessionKey}:name`, name.trim());
              localStorage.setItem(`${sessionKey}:name`, name.trim());
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
      ) : settingsOpen ? (
        <Settings key={`${state.small_blind}:${state.big_blind}:${state.cents}:${state.auto_deal}:${state.running}`} state={state} ready={ready} send={send} back={() => setSettingsOpen(false)} />
      ) : (
        <>
          <div className="game-layout">
            <section className="table-area" aria-label="Poker table">
              <div className="table-heading">
                <span>Hand #{state.hand_number}</span>
                <strong>{state.street}</strong>
                <span>
                  Blinds {formatAmount(state.small_blind, state.cents)} / {formatAmount(state.big_blind, state.cents)}
                </span>
              </div>
              <PokerTable state={state} />
              <ActionControls key={`${state.hand_number}:${state.street}:${state.actor}:${state.target}:${state.max_raise_to}:${state.cents}`} state={state} ready={ready} send={send} />
            </section>
            <aside id="table-chat" className={`panel chat-panel ${chatOpen ? "chat-open" : ""}`}>
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
            you’re all-in. Refreshing restores a retained seat. Play chips only.
          </footer>
        </>
      )}
    </main>
  );
}
