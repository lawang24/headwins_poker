import { useRef, useState } from "react";
import { Feedback } from "./Feedback";

export function TableToolbar({ name, status, settingsOpen, settings, leave }: {
  name: string; status: string; settingsOpen: boolean; settings: () => void; leave: () => void;
}) {
  const menu = useRef<HTMLDialogElement>(null);
  const [copied, setCopied] = useState(false);
  const [copyError, setCopyError] = useState(false);
  return <header className="table-toolbar">
    <button className="toolbar-icon" aria-label="Options" onClick={() => menu.current?.showModal()}>
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 5h18M3 12h18M3 19h18" /></svg>
      <span>Options</span>
    </button>
    <span className={`status ${status === "Connected" ? "online" : ""}`} role="status" title={status}><span className="sr-only">{status}</span></span>
    <Feedback name={name} />
    <dialog ref={menu} className="feedback-modal table-options" aria-labelledby="options-title">
      <div className="feedback-heading"><h2 id="options-title">Table options</h2><button autoFocus aria-label="Close options" onClick={() => menu.current?.close()}>×</button></div>
      <p className="hint">{name} · {status}</p>
      <nav aria-label="Table options">
        <button onClick={() => { menu.current?.close(); settings(); }}>{settingsOpen ? "Back to table" : "Settings"}</button>
        <button onClick={async () => {
          try { await navigator.clipboard.writeText(`${location.origin}${location.pathname}`); setCopied(true); setCopyError(false); }
          catch { setCopyError(true); }
        }}>{copied ? "Link copied" : "Invite friends"}</button>
        <button onClick={() => { menu.current?.close(); leave(); }}>Leave table</button>
      </nav>
      {copyError && <p role="alert">Copy the table URL from your address bar to invite friends.</p>}
      <details><summary>How this table works</summary><p>Play chips only. Hands deal automatically when two connected players have chips. Click your name to adjust your stack between hands. Disconnecting folds a live hand unless you’re all-in. Refreshing restores a retained seat.</p></details>
    </dialog>
  </header>;
}
