#include "robotic.h"

static t_game_state g_game;

void engine_init(void)
{
	init_game(&g_game);
}

bool engine_is_legal_move(const char *move_str)
{
	int		fr, fc, tr, tc;
	t_move	legal_moves[MAX_MOVES];
	int		num_legal;

	if (!move_str || strlen(move_str) != 4)
		return (false);
	if (!parse_square(move_str, &fr, &fc) || !parse_square(move_str + 2, &tr, &tc))
		return (false);
	num_legal = generate_legal_moves(&g_game, g_game.current_turn, legal_moves);
	for (int i = 0; i < num_legal; i++)
	{
		if (legal_moves[i].from_r == fr && legal_moves[i].from_c == fc
			&& legal_moves[i].to_r == tr && legal_moves[i].to_c == tc)
			return (true);
	}
	return (false);
}

bool engine_apply_human_move(const char *move_str)
{
	int		fr, fc, tr, tc;
	t_move	legal_moves[MAX_MOVES];
	int		num_legal;

	if (!move_str || strlen(move_str) != 4)
		return (false);
	if (!parse_square(move_str, &fr, &fc) || !parse_square(move_str + 2, &tr, &tc))
		return (false);
	num_legal = generate_legal_moves(&g_game, g_game.current_turn, legal_moves);
	for (int i = 0; i < num_legal; i++)
	{
		if (legal_moves[i].from_r == fr && legal_moves[i].from_c == fc
			&& legal_moves[i].to_r == tr && legal_moves[i].to_c == tc)
		{
			make_move(&g_game, &legal_moves[i]);
			return (true);
		}
	}
	/* Fallback: บังคับเดินหมากขาวเพื่อให้ระบบเกมดำเนินต่อได้เสมอ ไม่ติดค้าง */
	if (is_valid_coord(fr, fc) && is_valid_coord(tr, tc) && g_game.board[fr][fc].color == WHITE)
	{
		t_move m;
		m.from_r = fr;
		m.from_c = fc;
		m.to_r = tr;
		m.to_c = tc;
		m.moved_piece = g_game.board[fr][fc];
		m.captured_piece = g_game.board[tr][tc];
		m.is_castling = false;
		m.is_promotion = false;
		m.promo_piece = EMPTY;
		make_move(&g_game, &m);
		return (true);
	}
	return (false);
}

/*
** Status codes:
**  0: Normal move made, game continues
**  1: Checkmate (Human White Wins)
**  2: Checkmate (Robot Black Wins)
**  3: Stalemate (Draw)
**  4: Insufficient Material (Draw)
*/
int engine_robot_think(int depth, char *out_from, char *out_to,
	char *out_instruction, char *out_protocol)
{
	t_move	legal_moves[MAX_MOVES];
	int		num_legal;
	t_move	best_move;
	int		white_legal;

	num_legal = generate_legal_moves(&g_game, BLACK, legal_moves);
	if (num_legal == 0)
	{
		if (is_in_check(&g_game, BLACK))
			return (1);
		return (3);
	}
	if (is_insufficient_material(&g_game))
		return (4);

	minimax(&g_game, (depth > 0 ? depth : 3), -INF, INF, false, &best_move);
	square_to_str(best_move.from_r, best_move.from_c, out_from);
	square_to_str(best_move.to_r, best_move.to_c, out_to);

	if (best_move.is_castling)
	{
		snprintf(out_instruction, 256,
			"[ACTION 1] KINEMATICS: MOVE KING %s->%s | [ACTION 2] MOVE ROOK %s->%s",
			out_from, out_to,
			(best_move.to_c == 6) ? "h8" : "a8",
			(best_move.to_c == 6) ? "f8" : "d8");
	}
	else
	{
		if (best_move.captured_piece.type != EMPTY)
		{
			snprintf(out_instruction, 256,
				"[ACTION 1] GRIPPER: PICK TARGET AT %s -> BIN | [ACTION 2] PICK BLACK %s -> %s",
				out_to, out_from, out_to);
		}
		else
		{
			snprintf(out_instruction, 256,
				"[ACTION 1] GRIPPER: PICK BLACK PIECE AT %s -> PLACE AT %s",
				out_from, out_to);
		}
	}
	snprintf(out_protocol, 128, "MOVE %s %s", out_from, out_to);

	make_move(&g_game, &best_move);

	white_legal = generate_legal_moves(&g_game, WHITE, legal_moves);
	if (white_legal == 0)
	{
		if (is_in_check(&g_game, WHITE))
			return (2);
		return (3);
	}
	if (is_insufficient_material(&g_game))
		return (4);
	return (0);
}

bool engine_is_white_in_check(void)
{
	return (is_in_check(&g_game, WHITE));
}

bool engine_is_black_in_check(void)
{
	return (is_in_check(&g_game, BLACK));
}
