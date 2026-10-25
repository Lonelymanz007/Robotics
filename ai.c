/* ************************************************************************** */
/*                                                                            */
/*                                                        :::      ::::::::   */
/*   ai.c                                               :+:      :+:    :+:   */
/*                                                    +:+ +:+         +:+     */
/*   By: book <book@student.42.fr>                  +#+  +:+       +#+        */
/*                                                +#+#+#+#+#+   +#+           */
/*   Created: 2026/10/22 23:15:00 by book              #+#    #+#             */
/*   Updated: 2026/10/22 23:15:00 by book             ###   ########.fr       */
/*                                                                            */
/* ************************************************************************** */

#include "robotic.h"

static const int	g_piece_values[7] = {
	0, 100, 320, 330, 500, 900, 20000
};

static const int	g_pawn_table[8][8] = {
	{0, 0, 0, 0, 0, 0, 0, 0},
	{50, 50, 50, 50, 50, 50, 50, 50},
	{10, 10, 20, 30, 30, 20, 10, 10},
	{5, 5, 10, 25, 25, 10, 5, 5},
	{0, 0, 0, 20, 20, 0, 0, 0},
	{5, -5, -10, 0, 0, -10, -5, 5},
	{5, 10, 10, -20, -20, 10, 10, 5},
	{0, 0, 0, 0, 0, 0, 0, 0}
};

static const int	g_knight_table[8][8] = {
	{-50, -40, -30, -30, -30, -30, -40, -50},
	{-40, -20, 0, 0, 0, 0, -20, -40},
	{-30, 0, 10, 15, 15, 10, 0, -30},
	{-30, 5, 15, 20, 20, 15, 5, -30},
	{-30, 0, 15, 20, 20, 15, 0, -30},
	{-30, 5, 10, 15, 15, 10, 5, -30},
	{-40, -20, 0, 5, 5, 0, -20, -40},
	{-50, -40, -30, -30, -30, -30, -40, -50}
};

int	evaluate_board(const t_game_state *game)
{
	int		r;
	int		c;
	int		score[2];
	t_piece	p;
	int		pst;

	score[0] = 0;
	score[1] = 0;
	r = -1;
	while (++r < BOARD_SIZE)
	{
		c = -1;
		while (++c < BOARD_SIZE)
		{
			p = game->board[r][c];
			if (p.type == EMPTY)
				continue ;
			pst = 0;
			if (p.type == PAWN)
				pst = (p.color == WHITE) ? g_pawn_table[r][c] : g_pawn_table[7 - r][c];
			else if (p.type == KNIGHT)
				pst = (p.color == WHITE) ? g_knight_table[r][c] : g_knight_table[7 - r][c];
			if (p.color == WHITE)
				score[0] += (g_piece_values[p.type] + pst);
			else
				score[1] += (g_piece_values[p.type] + pst);
		}
	}
	return (score[0] - score[1]);
}

static int	eval_max(t_game_state *game, int depth, int alpha, int beta,
				t_move *best_move, t_move legal_moves[], int num_moves)
{
	int					i;
	int					max_eval;
	int					eval;
	t_castling_rights	saved;

	max_eval = -INF;
	i = 0;
	while (i < num_moves)
	{
		saved = game->castling;
		make_move(game, &legal_moves[i]);
		eval = minimax(game, depth - 1, alpha, beta, false, NULL);
		undo_move(game, &legal_moves[i], &saved);
		if (eval > max_eval)
		{
			max_eval = eval;
			if (best_move)
				*best_move = legal_moves[i];
		}
		if (eval > alpha)
			alpha = eval;
		if (beta <= alpha)
			break ;
		i++;
	}
	return (max_eval);
}

static int	eval_min(t_game_state *game, int depth, int alpha, int beta,
				t_move *best_move, t_move legal_moves[], int num_moves)
{
	int					i;
	int					min_eval;
	int					eval;
	t_castling_rights	saved;

	min_eval = INF;
	i = 0;
	while (i < num_moves)
	{
		saved = game->castling;
		make_move(game, &legal_moves[i]);
		eval = minimax(game, depth - 1, alpha, beta, true, NULL);
		undo_move(game, &legal_moves[i], &saved);
		if (eval < min_eval)
		{
			min_eval = eval;
			if (best_move)
				*best_move = legal_moves[i];
		}
		if (eval < beta)
			beta = eval;
		if (beta <= alpha)
			break ;
		i++;
	}
	return (min_eval);
}

int	minimax(t_game_state *game, int depth, int alpha, int beta,
		bool is_maximizing, t_move *best_move)
{
	t_move			legal_moves[MAX_MOVES];
	t_piece_color	active_color;
	int				num_moves;

	active_color = is_maximizing ? WHITE : BLACK;
	num_moves = generate_legal_moves(game, active_color, legal_moves);
	if (num_moves == 0)
	{
		if (is_in_check(game, active_color))
			return (is_maximizing ? (-INF + (10 - depth)) : (INF - (10 - depth)));
		return (0);
	}
	if (depth == 0)
		return (evaluate_board(game));
	if (is_maximizing)
		return (eval_max(game, depth, alpha, beta, best_move, legal_moves, num_moves));
	return (eval_min(game, depth, alpha, beta, best_move, legal_moves, num_moves));
}
