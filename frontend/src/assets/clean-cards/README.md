# Card faces

The deck contains 52 desktop faces and 52 portrait hole-card variants, drawn at a
native 61:74 aspect ratio. White rounded cards use Abril Fatface rank outlines and
shared vector suit silhouettes. Portrait variants put a smaller rank and suit
in the exposed corner above the nameplate. Board cards use the desktop artwork.

Abril Fatface is by TypeTogether, distributed under the SIL Open Font License.
The outlines come from [Google Fonts](https://github.com/google/fonts/tree/main/ofl/abrilfatface).
The license is retained in `frontend/scripts/AbrilFatface-OFL.txt`. SVGs contain
outlines, so rendering requires no installed font or external network request.
Suit silhouettes are project paths.

From `frontend`, regenerate with `node scripts/generate-cards.mjs`. Rank outlines
live in `scripts/card-ranks.json`; all face geometry is in the generator. The app
bundles the SVGs and selects portrait hole-card faces with a picture source.
Sizing, shadows, and hand overlap remain in CSS.
