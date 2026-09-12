import { useEffect, useRef, useState } from "react";

export function Feedback({ name }: { name: string }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const connection = useRef<WebSocket | null>(null);
  const [reporter, setReporter] = useState("");
  const [message, setMessage] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  useEffect(() => () => connection.current?.close(), []);

  async function submit() {
    if (pending || !message.trim()) return;
    setPending(true);
    setError("");
    try {
      const url = new URL(import.meta.env.VITE_WS_URL || `${location.protocol === "https:" ? "wss:" : "ws:"}//${location.host}/ws`);
      url.pathname = url.pathname.replace(/\/ws\/?$/, "/feedback");
      url.search = "";
      await new Promise<void>((resolve, reject) => {
        const socket = new WebSocket(url);
        connection.current = socket;
        const timer = setTimeout(() => finish(new Error("Could not confirm your feedback was saved. Please try again.")), 30000);
        let finished = false;
        function finish(failure?: Error) {
          if (finished) return;
          finished = true;
          clearTimeout(timer);
          socket.close();
          connection.current = null;
          if (failure) reject(failure); else resolve();
        }
        socket.onopen = () => socket.send(JSON.stringify({
          message,
          name: reporter,
          token: sessionStorage.getItem("headwins:global:token") || localStorage.getItem("headwins:global:token"),
        }));
        socket.onmessage = event => {
          try {
            const reply = JSON.parse(event.data);
            finish(reply.type === "feedback_saved" ? undefined : new Error(reply.message || "Could not save feedback."));
          } catch { finish(new Error("Could not confirm your feedback was saved.")); }
        };
        socket.onerror = () => finish(new Error("Unable to connect. Please try again."));
        socket.onclose = () => finish(new Error("Connection closed before feedback was confirmed. Please try again."));
      });
      setSaved(true);
      setMessage("");
    } catch (failure) {
      setError(failure instanceof Error ? failure.message : "Could not save feedback. Please try again.");
    } finally { setPending(false); }
  }

  return <>
    <button className="feedback-button" type="button" aria-label="Feedback" title="Feedback" onClick={() => {
      if (!reporter) setReporter(name);
      setSaved(false);
      setError("");
      dialog.current?.showModal();
    }}>
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M21 11.5a8.4 8.4 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.4 8.4 0 0 1-3.8-.9L3 21l1.9-5.7a8.4 8.4 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.4 8.4 0 0 1 3.8-.9h.5a8.5 8.5 0 0 1 8 8v.5Z" />
        <path d="M8 10h8M8 14h5" />
      </svg>
    </button>
    <dialog ref={dialog} className="feedback-modal" aria-labelledby="feedback-title" onCancel={event => { if (pending) event.preventDefault(); }}>
      <div className="feedback-heading">
        <h2 id="feedback-title">Share feedback</h2>
        <button type="button" aria-label="Close feedback" disabled={pending} onClick={() => dialog.current?.close()}>×</button>
      </div>
      {saved ? <div role="status">
        <p>Thanks! Your feedback has been saved.</p>
        <button type="button" onClick={() => dialog.current?.close()}>Done</button>
      </div> : <form onSubmit={event => { event.preventDefault(); void submit(); }}>
        <p className="hint">Found a bug or have an idea? Feedback is private and includes your name and the time you send it.</p>
        <label>Reporter name<input required maxLength={40} value={reporter} disabled={pending} onChange={event => setReporter(event.target.value)} autoComplete="name" /></label>
        <label htmlFor="feedback-message">Feedback</label><textarea id="feedback-message" required autoFocus maxLength={2000} rows={6} value={message} disabled={pending} onChange={event => setMessage(event.target.value)} placeholder="What could we improve?" />
        <span className="hint">{message.length}/2000 · Returning players are identified by their saved player profile.</span>
        {error && <p className="error" role="alert">{error}</p>}
        <div className="feedback-actions">
          <button type="button" disabled={pending} onClick={() => dialog.current?.close()}>Cancel</button>
          <button className="primary" disabled={pending || !message.trim() || !reporter.trim()}>{pending ? "Sending…" : "Send feedback"}</button>
        </div>
      </form>}
    </dialog>
  </>;
}
