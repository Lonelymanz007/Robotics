/* ************************************************************************** */
/*                                                                            */
/*                                                        :::      ::::::::   */
/*   moves.c                                            :+:      :+:    :+:   */
/*                                                    +:+ +:+         +:+     */
/*   By: book <book@student.42.fr>                  +#+  +:+       +#+        */
/*                                                +#+#+#+#+#+   +#+           */
/*   Created: 2026/10/22 23:15:00 by book              #+#    #+#             */
/*   Updated: 2026/10/22 23:15:00 by book             ###   ########.fr       */
/*                                                                            */
/* ************************************************************************** */

#include "robotic.h"

static void	add_move(t_move move_list[], int *count, t_move m)
{
	if (*count >= MAX_MOVES)
		return ;
	move_list[(*count)++] = m;
}

static bool	is_ray_attacked(const t_game_state *game, int r, int c,
				t_piece_color by_color, bool is_diag)
{
	int	d;
	int	nr;
	int	nc;
	static const int	diag_r[4] = {-1, -1, 1, 1};
	static const int	diag_c[4] = {-1, 1, -1, 1};
	static const int	ortho_r[4] = {-1, 1, 0, 0};
	static const int	ortho_c[4] = {0, 0, -1, 1};

	d = 0;
	while (d < 4)
	{
		nr = r + (is_diag ? diag_r[d] : ortho_r[d]);
		nc = c + (is_diag ? diag_c[d] : ortho_c[d]);
		while (is_valid_coord(nr, nc))
		{
			if (game->board[nr][nc].type != EMPTY)
			{
				if (game->board[nr][nc].color == by_color)
				{
					if (is_diag && (game->board[nr][nc].type == BISHOP
						|| game->board[nr][nc].type == QUEEN))
						return (true);
					if (!is_diag && (game->board[nr][nc].type == ROOK
						|| game->board[nr][nc].type == QUEEN))
						return (true);
				}
				break ;
			}
			nr += (is_diag ? diag_r[d] : ortho_r[d]);
			nc += (is_diag ? diag_c[d] : ortho_c[d]);
		}
		d++;
	}
	return (false);
}

bool	is_square_attacked(const t_game_state *game, int r, int c,
			t_piece_color by_color)
{
	int					i;
	int					nr;
	int					nc;
	static const int	kn_r[8] = {-2, -2, -1, -1, 1, 1, 2, 2};
	static const int	kn_c[8] = {-1, 1, -2, 2, -2, 2, -1, 1};
	static const int	k_r[8] = {-1, -1, -1, 0, 0, 1, 1, 1};
	static const int	k_c[8] = {-1, 0, 1, -1, 1, -1, 0, 1};

	nr = r + ((by_color == WHITE) ? 1 : -1);
	if (is_valid_coord(nr, c - 1) && game->board[nr][c - 1].type == PAWN
		&& game->board[nr][c - 1].color == by_color)
		return (true);
	if (is_valid_coord(nr, c + 1) && game->board[nr][c + 1].type == PAWN
		&& game->board[nr][c + 1].color == by_color)
		return (true);
	i = -1;
	while (++i < 8)
	{
		nr = r + kn_r[i];
		nc = c + kn_c[i];
		if (is_valid_coord(nr, nc) && game->board[nr][nc].type == KNIGHT
			&& game->board[nr][nc].color == by_color)
			return (true);
		nr = r + k_r[i];
		nc = c + k_c[i];
		if (is_valid_coord(nr, nc) && game->board[nr][nc].type == KING
			&& game->board[nr][nc].color == by_color)
			return (true);
	}
	return (is_ray_attacked(game, r, c, by_color, true)
		|| is_ray_attacked(game, r, c, by_color, false));
}

bool	is_in_check(const t_game_state *game, t_piece_color color)
{
	int				r;
	int				c;
	t_piece_color	opp;

	opp = (color == WHITE) ? BLACK : WHITE;
	r = 0;
	while (r < BOARD_SIZE)
	{
		c = 0;
		while (c < BOARD_SIZE)
		{
			if (game->board[r][c].type == KING
				&& game->board[r][c].color == color)
				return (is_square_attacked(game, r, c, opp));
			c++;
		}
		r++;
	}
	return (false);
}

static void	gen_pawn_moves(const t_game_state *game, int r, int c,
				t_piece_color color, t_move move_list[], int *count)
{
	int				fwd;
	int				f1;
	int				i;
	int				nc;
	t_piece_color	opp;

	opp = (color == WHITE) ? BLACK : WHITE;
	fwd = (color == WHITE) ? -1 : 1;
	f1 = r + fwd;
	if (is_valid_coord(f1, c) && game->board[f1][c].type == EMPTY)
	{
		add_move(move_list, count, (t_move){r, c, f1, c, game->board[r][c],
			game->board[f1][c], false, (f1 == 0 || f1 == 7), QUEEN});
		if (r == ((color == WHITE) ? 6 : 1)
			&& game->board[r + 2 * fwd][c].type == EMPTY)
			add_move(move_list, count, (t_move){r, c, r + 2 * fwd, c,
				game->board[r][c], game->board[r + 2 * fwd][c], false, false, EMPTY});
	}
	i = -1;
	while (++i < 2)
	{
		nc = (i == 0) ? c - 1 : c + 1;
		if (is_valid_coord(f1, nc) && game->board[f1][nc].type != EMPTY
			&& game->board[f1][nc].color == opp)
			add_move(move_list, count, (t_move){r, c, f1, nc, game->board[r][c],
				game->board[f1][nc], false, (f1 == 0 || f1 == 7), QUEEN});
	}
}

static void	gen_sliding_moves(const t_game_state *game, int r, int c,
				t_move move_list[], int *count)
{
	int					d;
	int					nr;
	int					nc;
	int					nd;
	static const int	dr[8] = {-1, -1, 1, 1, -1, 1, 0, 0};
	static const int	dc[8] = {-1, 1, -1, 1, 0, 0, -1, 1};

	nd = (game->board[r][c].type == QUEEN) ? 8 : 4;
	d = (game->board[r][c].type == ROOK) ? 4 : 0;
	nd = (game->board[r][c].type == ROOK) ? 8 : nd;
	while (d < nd)
	{
		nr = r + dr[d];
		nc = c + dc[d];
		while (is_valid_coord(nr, nc))
		{
			if (game->board[nr][nc].type == EMPTY)
				add_move(move_list, count, (t_move){r, c, nr, nc,
					game->board[r][c], game->board[nr][nc], false, false, EMPTY});
			else
			{
				if (game->board[nr][nc].color != game->board[r][c].color)
					add_move(move_list, count, (t_move){r, c, nr, nc,
						game->board[r][c], game->board[nr][nc], false, false, EMPTY});
				break ;
			}
			nr += dr[d];
			nc += dc[d];
		}
		d++;
	}
}

static void	gen_king_moves(const t_game_state *game, int r, int c,
				t_move move_list[], int *count)
{
	int					i;
	int					kr;
	t_piece_color		opp;
	bool				ks;
	bool				qs;
	static const int	dr[8] = {-1, -1, -1, 0, 0, 1, 1, 1};
	static const int	dc[8] = {-1, 0, 1, -1, 1, -1, 0, 1};

	opp = (game->board[r][c].color == WHITE) ? BLACK : WHITE;
	i = -1;
	while (++i < 8)
	{
		if (is_valid_coord(r + dr[i], c + dc[i])
			&& (game->board[r + dr[i]][c + dc[i]].type == EMPTY
			|| game->board[r + dr[i]][c + dc[i]].color == opp))
			add_move(move_list, count, (t_move){r, c, r + dr[i], c + dc[i],
				game->board[r][c], game->board[r + dr[i]][c + dc[i]], false, false, EMPTY});
	}
	kr = (game->board[r][c].color == WHITE) ? 7 : 0;
	ks = (game->board[r][c].color == WHITE) ? game->castling.white_kingside : game->castling.black_kingside;
	qs = (game->board[r][c].color == WHITE) ? game->castling.white_queenside : game->castling.black_queenside;
	if (r == kr && c == 4)
	{
		if (ks && game->board[kr][5].type == EMPTY && game->board[kr][6].type == EMPTY
			&& !is_square_attacked(game, kr, 4, opp) && !is_square_attacked(game, kr, 5, opp)
			&& !is_square_attacked(game, kr, 6, opp))
			add_move(move_list, count, (t_move){r, c, kr, 6, game->board[r][c],
				(t_piece){EMPTY, NO_COLOR}, true, false, EMPTY});
		if (qs && game->board[kr][1].type == EMPTY && game->board[kr][2].type == EMPTY
			&& game->board[kr][3].type == EMPTY && !is_square_attacked(game, kr, 4, opp)
			&& !is_square_attacked(game, kr, 3, opp) && !is_square_attacked(game, kr, 2, opp))
			add_move(move_list, count, (t_move){r, c, kr, 2, game->board[r][c],
				(t_piece){EMPTY, NO_COLOR}, true, false, EMPTY});
	}
}

int	generate_pseudo_moves(const t_game_state *game, t_piece_color color,
		t_move move_list[])
{
	int					r;
	int					c;
	int					i;
	int					count;
	static const int	kn_r[8] = {-2, -2, -1, -1, 1, 1, 2, 2};
	static const int	kn_c[8] = {-1, 1, -2, 2, -2, 2, -1, 1};

	count = 0;
	r = -1;
	while (++r < BOARD_SIZE)
	{
		c = -1;
		while (++c < BOARD_SIZE)
		{
			if (game->board[r][c].color != color)
				continue ;
			if (game->board[r][c].type == PAWN)
				gen_pawn_moves(game, r, c, color, move_list, &count);
			else if (game->board[r][c].type == KNIGHT)
			{
				i = -1;
				while (++i < 8)
				{
					if (is_valid_coord(r + kn_r[i], c + kn_c[i])
						&& game->board[r + kn_r[i]][c + kn_c[i]].color != color)
						add_move(move_list, &count, (t_move){r, c, r + kn_r[i], c + kn_c[i],
							game->board[r][c], game->board[r + kn_r[i]][c + kn_c[i]], false, false, EMPTY});
				}
			}
			else if (game->board[r][c].type == KING)
				gen_king_moves(game, r, c, move_list, &count);
			else
				gen_sliding_moves(game, r, c, move_list, &count);
		}
	}
	return (count);
}

bool	make_move(t_game_state *game, const t_move *m)
{
	int	r;

	game->board[m->to_r][m->to_c] = m->moved_piece;
	game->board[m->from_r][m->from_c] = (t_piece){EMPTY, NO_COLOR};
	if (m->is_promotion)
		game->board[m->to_r][m->to_c] = (t_piece){QUEEN, m->moved_piece.color};
	if (m->is_castling)
	{
		r = m->from_r;
		if (m->to_c == 6)
		{
			game->board[r][5] = game->board[r][7];
			game->board[r][7] = (t_piece){EMPTY, NO_COLOR};
		}
		else if (m->to_c == 2)
		{
			game->board[r][3] = game->board[r][0];
			game->board[r][0] = (t_piece){EMPTY, NO_COLOR};
		}
	}
	if (m->moved_piece.type == KING)
	{
		if (m->moved_piece.color == WHITE)
		{
			game->castling.white_kingside = false;
			game->castling.white_queenside = false;
		}
		else
		{
			game->castling.black_kingside = false;
			game->castling.black_queenside = false;
		}
	}
	if (m->moved_piece.type == ROOK)
	{
		if (m->from_r == 7 && m->from_c == 7)
			game->castling.white_kingside = false;
		if (m->from_r == 7 && m->from_c == 0)
			game->castling.white_queenside = false;
		if (m->from_r == 0 && m->from_c == 7)
			game->castling.black_kingside = false;
		if (m->from_r == 0 && m->from_c == 0)
			game->castling.black_queenside = false;
	}
	game->current_turn = (game->current_turn == WHITE) ? BLACK : WHITE;
	game->last_move = *m;
	game->has_last_move = true;
	game->move_count++;
	return (true);
}

void	undo_move(t_game_state *game, const t_move *m,
			const t_castling_rights *prev_castling)
{
	int	r;

	game->board[m->from_r][m->from_c] = m->moved_piece;
	game->board[m->to_r][m->to_c] = m->captured_piece;
	if (m->is_castling)
	{
		r = m->from_r;
		if (m->to_c == 6)
		{
			game->board[r][7] = game->board[r][5];
			game->board[r][5] = (t_piece){EMPTY, NO_COLOR};
		}
		else if (m->to_c == 2)
		{
			game->board[r][0] = game->board[r][3];
			game->board[r][3] = (t_piece){EMPTY, NO_COLOR};
		}
	}
	game->castling = *prev_castling;
	game->current_turn = (game->current_turn == WHITE) ? BLACK : WHITE;
	game->move_count--;
}

int	generate_legal_moves(t_game_state *game, t_piece_color color,
		t_move move_list[])
{
	t_move				pseudo[MAX_MOVES];
	int					p_count;
	int					legal_count;
	int					i;
	t_castling_rights	saved_castling;

	p_count = generate_pseudo_moves(game, color, pseudo);
	legal_count = 0;
	i = 0;
	while (i < p_count)
	{
		saved_castling = game->castling;
		make_move(game, &pseudo[i]);
		if (!is_in_check(game, color))
			move_list[legal_count++] = pseudo[i];
		undo_move(game, &pseudo[i], &saved_castling);
		i++;
	}
	return (legal_count);
}
