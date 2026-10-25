/* ************************************************************************** */
/*                                                                            */
/*                                                        :::      ::::::::   */
/*   board.c                                            :+:      :+:    :+:   */
/*                                                    +:+ +:+         +:+     */
/*   By: book <book@student.42.fr>                  +#+  +:+       +#+        */
/*                                                +#+#+#+#+#+   +#+           */
/*   Created: 2026/10/22 23:15:00 by book              #+#    #+#             */
/*   Updated: 2026/10/22 23:15:00 by book             ###   ########.fr       */
/*                                                                            */
/* ************************************************************************** */

#include "robotic.h"

void	init_game(t_game_state *game)
{
	int						c;
	int						r;
	static const t_piece_type	back_rank[8] = {
		ROOK, KNIGHT, BISHOP, QUEEN, KING, BISHOP, KNIGHT, ROOK
	};

	memset(game, 0, sizeof(t_game_state));
	game->current_turn = WHITE;
	game->has_last_move = false;
	game->move_count = 1;
	game->castling.white_kingside = true;
	game->castling.white_queenside = true;
	game->castling.black_kingside = true;
	game->castling.black_queenside = true;
	c = 0;
	while (c < BOARD_SIZE)
	{
		game->board[0][c] = (t_piece){back_rank[c], BLACK};
		game->board[1][c] = (t_piece){PAWN, BLACK};
		game->board[6][c] = (t_piece){PAWN, WHITE};
		game->board[7][c] = (t_piece){back_rank[c], WHITE};
		c++;
	}
	r = 2;
	while (r < 6)
	{
		c = 0;
		while (c < BOARD_SIZE)
		{
			game->board[r][c] = (t_piece){EMPTY, NO_COLOR};
			c++;
		}
		r++;
	}
}

bool	is_valid_coord(int r, int c)
{
	return (r >= 0 && r < BOARD_SIZE && c >= 0 && c < BOARD_SIZE);
}

void	square_to_str(int r, int c, char *str)
{
	str[0] = (char)('a' + c);
	str[1] = (char)('8' - r);
	str[2] = '\0';
}

bool	parse_square(const char *str, int *r, int *c)
{
	char	col_char;
	char	row_char;

	if (!str || strlen(str) < 2)
		return (false);
	col_char = tolower(str[0]);
	row_char = str[1];
	if (col_char < 'a' || col_char > 'h' || row_char < '1' || row_char > '8')
		return (false);
	*c = col_char - 'a';
	*r = '8' - row_char;
	return (true);
}

bool	is_insufficient_material(const t_game_state *game)
{
	int		r;
	int		c;
	t_piece	p;

	r = 0;
	while (r < BOARD_SIZE)
	{
		c = 0;
		while (c < BOARD_SIZE)
		{
			p = game->board[r][c];
			if (p.type != EMPTY && p.type != KING)
				return (false);
			c++;
		}
		r++;
	}
	return (true);
}
