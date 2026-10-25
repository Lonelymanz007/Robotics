/* ************************************************************************** */
/*                                                                            */
/*                                                        :::      ::::::::   */
/*   display.c                                          :+:      :+:    :+:   */
/*                                                    +:+ +:+         +:+     */
/*   By: book <book@student.42.fr>                  +#+  +:+       +#+        */
/*                                                +#+#+#+#+#+   +#+           */
/*   Created: 2026/10/22 23:15:00 by book              #+#    #+#             */
/*   Updated: 2026/10/22 23:15:00 by book             ###   ########.fr       */
/*                                                                            */
/* ************************************************************************** */

#include "robotic.h"

static char	get_piece_char(t_piece p)
{
	static const char	w_sym[7] = {' ', 'P', 'N', 'B', 'R', 'Q', 'K'};
	static const char	b_sym[7] = {' ', 'p', 'n', 'b', 'r', 'q', 'k'};

	if (p.color == WHITE)
		return (w_sym[p.type]);
	if (p.color == BLACK)
		return (b_sym[p.type]);
	return (' ');
}

static const char	*get_square_bg(const t_game_state *game, int r, int c,
						bool checks[2])
{
	t_piece	p;

	p = game->board[r][c];
	if (p.type == KING)
	{
		if ((p.color == WHITE && checks[0]) || (p.color == BLACK && checks[1]))
			return (BG_CHECK_RED);
	}
	if (game->has_last_move)
	{
		if ((game->last_move.from_r == r && game->last_move.from_c == c)
			|| (game->last_move.to_r == r && game->last_move.to_c == c))
			return (BG_LAST_MOVE);
	}
	if ((r + c) % 2 == 0)
		return (BG_LIGHT_SQ);
	return (BG_DARK_SQ);
}

void	print_board(const t_game_state *game)
{
	int			r;
	int			c;
	bool		checks[2];
	const char	*fg;

	checks[0] = is_in_check(game, WHITE);
	checks[1] = is_in_check(game, BLACK);
	printf("\n  " COLOR_BOLD "    a   b   c   d   e   f   g   h" COLOR_RESET "\n");
	printf("    +---+---+---+---+---+---+---+---+\n");
	r = -1;
	while (++r < BOARD_SIZE)
	{
		printf("  %d |", 8 - r);
		c = -1;
		while (++c < BOARD_SIZE)
		{
			fg = (game->board[r][c].color == WHITE) ? COLOR_WHITE : COLOR_BLACK;
			printf("%s %s%c" COLOR_RESET "%s |",
				get_square_bg(game, r, c, checks), fg,
				get_piece_char(game->board[r][c]), COLOR_RESET);
		}
		printf(" %d\n    +---+---+---+---+---+---+---+---+\n", 8 - r);
	}
	printf("  " COLOR_BOLD "    a   b   c   d   e   f   g   h" COLOR_RESET "\n\n");
	if (checks[0])
		printf(COLOR_RED COLOR_BOLD "  >> [ALERT] WHITE KING IS IN CHECK!\n" COLOR_RESET);
	if (checks[1])
		printf(COLOR_RED COLOR_BOLD "  >> [ALERT] BLACK KING IS IN CHECK!\n" COLOR_RESET);
}

void	print_robot_instruction(const t_move *m)
{
	char	from_sq[4];
	char	to_sq[4];

	square_to_str(m->from_r, m->from_c, from_sq);
	square_to_str(m->to_r, m->to_c, to_sq);
	printf("\n" COLOR_CYAN COLOR_BOLD
		"================ [ ROBOT COMMAND TO WEBOTS ] ================" COLOR_RESET "\n");
	if (m->is_castling)
	{
		printf("[ACTION 1] KINEMATICS: MOVE KING   FROM %s TO %s (%s Castle)\n",
			from_sq, to_sq, (m->to_c == 6) ? "Kingside" : "Queenside");
		printf("[ACTION 2] KINEMATICS: MOVE ROOK   FROM %s TO %s\n",
			(m->to_c == 6) ? "h8" : "a8", (m->to_c == 6) ? "f8" : "d8");
	}
	else
	{
		if (m->captured_piece.type != EMPTY)
			printf("[ACTION 1] GRIPPER: PICK PIECE AT %s -> MOVE TO GRAVEYARD_BIN\n", to_sq);
		printf("[ACTION %d] GRIPPER: PICK BLACK PIECE AT %s -> PLACE AT %s\n",
			(m->captured_piece.type != EMPTY) ? 2 : 1, from_sq, to_sq);
	}
	printf(">> RAW PROTOCOL: MOVE %s %s\n", from_sq, to_sq);
	printf(COLOR_CYAN COLOR_BOLD
		"==============================================================" COLOR_RESET "\n\n");
}
