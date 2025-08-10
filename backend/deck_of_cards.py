import random

class DeckOfCards:
    def __init__(self):
        self.cards = [r + s for s in "hdcs" for r in [str(n) for n in range(2, 10)] + ["T", "J", "Q", "K", "A"]]

    def shuffle(self):
        random.shuffle(self.cards)

    def draw(self):
        return self.cards.pop()