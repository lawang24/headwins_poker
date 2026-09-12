const assets = import.meta.glob(
  [
    "./assets/SVG-cards-1.3/*.svg",
    "!./assets/SVG-cards-1.3/*2.svg",
    "!./assets/SVG-cards-1.3/*joker.svg",
  ],
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
export function Cards({ cards }: { cards: string[] }) {
  return (
    <div className="cards">
      {cards.map((c) => (
        <Card key={c} code={c} />
      ))}
    </div>
  );
}
