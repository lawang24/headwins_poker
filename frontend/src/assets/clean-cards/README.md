# Clean card faces

The approved minimal deck: 52 white, rounded 5:7 cards, each with one large serif
rank above one offset suit. Hearts and diamonds are red; clubs and spades are
charcoal. There are no mirrored indices, pip arrays, or court illustrations.

Each SVG is self-contained. Lettering is outlined, so rendering requires no font
installation or network request. The rank artwork was prepared from Bodoni 72
Bold outlines; no font software is included. Suit silhouettes are project paths.
The shared geometry is in `frontend/scripts/card-ranks.json` and
`frontend/scripts/generate-cards.mjs`.

From `frontend`, regenerate with `node scripts/generate-cards.mjs`. The app imports
the generated SVGs inline. Card shadows, sizing, and hand overlap remain in CSS.
