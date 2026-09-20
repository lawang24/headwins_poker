export type Player = {
  id: string;
  name: string;
  seat: number;
  stack: number;
  connected: boolean;
  in_hand: boolean;
  folded: boolean;
  committed: number;
  all_in: boolean;
};
export type State = {
  players: Player[];
  you: string;
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
  cents: boolean;
  min_raise_to: number;
  max_raise_to: number;
  can_raise: boolean;
  call_amount: number;
  hand_number: number;
  history: string[];
  runout_vote: null | {
    hand_id: string;
    eligible: string[];
    votes: Record<string, number>;
    deadline: string;
  };
  result: null | {
    payouts: Record<string, number>;
    hands: Record<string, string[]>;
    runouts?: { board: string[]; payouts: Record<string, number>; pots: { amount: number; winners: string[]; runout: number }[] }[];
  };
};
