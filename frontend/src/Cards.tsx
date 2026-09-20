const assets = import.meta.glob(
  "./assets/clean-cards/*.svg",
  { eager: true, query: "?inline", import: "default" },
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
function Card({ code, hole }: { code: string; hole: boolean }) {
  const name = `${ranks[code[0]] || code[0]}_of_${suits[code[1]]}`;
  const face = (
    <img
      className={hole ? "card-face" : "card"}
      src={assets[`./assets/clean-cards/${name}.svg`]}
      alt={name.replaceAll("_", " ")}
    />
  );
  return hole ? <picture className="card hole-card">
    <source
      media="(max-width: 1023px) and (min-height: 501px), (max-width: 600px)"
      srcSet={assets[`./assets/clean-cards/${name}-mobile.svg`]}
    />
    {face}
  </picture> : face;
}
export function Cards({ cards, hole = false }: { cards: string[]; hole?: boolean }) {
  return (
    <div className="cards">
      {cards.map((c) => (
        <Card key={c} code={c} hole={hole} />
      ))}
    </div>
  );
}
