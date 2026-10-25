/* ************************************************************************** */
/*                                                                            */
/*                                                        :::      ::::::::   */
/*   robotic.h                                          :+:      :+:    :+:   */
/*                                                    +:+ +:+         +:+     */
/*   By: book <book@student.42.fr>                  +#+  +:+       +#+        */
/*                                                +#+#+#+#+#+   +#+           */
/*   Created: 2026/10/22 23:15:00 by book              #+#    #+#             */
/*   Updated: 2026/10/22 23:15:00 by book             ###   ########.fr       */
/*                                                                            */
/* ************************************************************************** */

#ifndef ROBOTIC_H
# define ROBOTIC_H

# include <stdio.h>
# include <stdlib.h>
# include <string.h>
# include <ctype.h>
# include <stdbool.h>

# define BOARD_SIZE		8
# define MAX_MOVES		256
# define INF			1000000

/* ANSI Color Codes for 2D Terminal Interface */
# define COLOR_RESET	"\033[0m"
# define COLOR_BOLD		"\033[1m"
# define COLOR_RED		"\033[1;31m"
# define COLOR_GREEN	"\033[1;32m"
# define COLOR_YELLOW	"\033[1;33m"
# define COLOR_CYAN		"\033[1;36m"
# define COLOR_WHITE	"\033[1;37m"
# define COLOR_BLACK	"\033[1;30m"

# define BG_LIGHT_SQ	"\033[48;5;250m"
# define BG_DARK_SQ		"\033[48;5;240m"
# define BG_CHECK_RED	"\033[48;5;196m\033[5m"
# define BG_LAST_MOVE	"\033[48;5;178m"

/* Piece Types */
typedef enum e_piece_type
{
	EMPTY = 0,
	PAWN = 1,
	KNIGHT = 2,
	BISHOP = 3,
	ROOK = 4,
	QUEEN = 5,
	KING = 6
}	t_piece_type;

/* Piece Colors */
typedef enum e_piece_color
{
	NO_COLOR = 0,
	WHITE = 1,
	BLACK = 2
}	t_piece_color;

/* Piece Structure */
typedef struct s_piece
{
	t_piece_type	type;
	t_piece_color	color;
}	t_piece;

/* Move Structure */
typedef struct s_move
{
	int				from_r;
	int				from_c;
	int				to_r;
	int				to_c;
	t_piece			moved_piece;
	t_piece			captured_piece;
	bool			is_castling;
	bool			is_promotion;
	t_piece_type	promo_piece;
}	t_move;

/* Castling Rights */
typedef struct s_castling_rights
{
	bool	white_kingside;
	bool	white_queenside;
	bool	black_kingside;
	bool	black_queenside;
}	t_castling_rights;

/* Game State */
typedef struct s_game_state
{
	t_piece				board[BOARD_SIZE][BOARD_SIZE];
	t_piece_color		current_turn;
	t_castling_rights	castling;
	t_move				last_move;
	bool				has_last_move;
	int					move_count;
}	t_game_state;

/* Compatibility typedefs */
typedef t_piece_type		PieceType;
typedef t_piece_color		PieceColor;
typedef t_piece				Piece;
typedef t_move				Move;
typedef t_castling_rights	CastlingRights;
typedef t_game_state		GameState;

/* Board Lifecycle & Coordinates (board.c) */
void	init_game(t_game_state *game);
bool	is_valid_coord(int r, int c);
void	square_to_str(int r, int c, char *str);
bool	parse_square(const char *str, int *r, int *c);
bool	is_insufficient_material(const t_game_state *game);

/* Move Generation & Rules Validation (moves.c) */
bool	is_square_attacked(const t_game_state *game, int r, int c,
			t_piece_color by_color);
bool	is_in_check(const t_game_state *game, t_piece_color color);
int		generate_pseudo_moves(const t_game_state *game, t_piece_color color,
			t_move move_list[]);
int		generate_legal_moves(t_game_state *game, t_piece_color color,
			t_move move_list[]);
bool	make_move(t_game_state *game, const t_move *m);
void	undo_move(t_game_state *game, const t_move *m,
			const t_castling_rights *prev_castling);

/* AI Decision Engine (ai.c) */
int		evaluate_board(const t_game_state *game);
int		minimax(t_game_state *game, int depth, int alpha, int beta,
			bool is_maximizing, t_move *best_move);

/* 2D Visualizer & Robot Output (display.c) */
void	print_board(const t_game_state *game);
void	print_robot_instruction(const t_move *m);

#endif
