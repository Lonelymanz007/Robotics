/* ************************************************************************** */
/*                                                                            */
/*                                                        :::      ::::::::   */
/*   main.c                                             :+:      :+:    :+:   */
/*                                                    +:+ +:+         +:+     */
/*   By: book <book@student.42.fr>                  +#+  +:+       +#+        */
/*                                                +#+#+#+#+#+   +#+           */
/*   Created: 2026/10/22 23:15:00 by book              #+#    #+#             */
/*   Updated: 2026/10/22 23:15:00 by book             ###   ########.fr       */
/*                                                                            */
/* ************************************************************************** */

#include "robotic.h"

static void	print_header_banner(void)
{
	printf(COLOR_GREEN COLOR_BOLD);
	printf("====================================================================\n");
	printf("   Hybrid 'Digital Twin' Chess System - Core Decision Engine (C)   \n");
	printf("   Team: GM ลงเชิฟ | White: Human (Vision) | Black: Robot (Webots)  \n");
	printf("====================================================================\n");
	printf(COLOR_RESET);
}

static void	trim_whitespace(char *str)
{
	int	len;

	len = strlen(str);
	while (len > 0 && (str[len - 1] == '\n' || str[len - 1] == '\r'
			|| isspace((unsigned char)str[len - 1])))
	{
		str[len - 1] = '\0';
		len--;
	}
}

static bool	find_matching_move(const char *buf, t_move legal_moves[],
				int num_legal, t_move *out_move)
{
	int	fr;
	int	fc;
	int	tr;
	int	tc;
	int	i;

	if (strlen(buf) != 4 || !parse_square(buf, &fr, &fc)
		|| !parse_square(buf + 2, &tr, &tc))
		return (false);
	i = 0;
	while (i < num_legal)
	{
		if (legal_moves[i].from_r == fr && legal_moves[i].from_c == fc
			&& legal_moves[i].to_r == tr && legal_moves[i].to_c == tc)
		{
			*out_move = legal_moves[i];
			return (true);
		}
		i++;
	}
	return (false);
}

static bool	process_human_input(t_game_state *game, t_move legal_moves[],
				int num_legal)
{
	char	input[64];
	char	*p;
	t_move	chosen_move;

	printf(COLOR_YELLOW "Turn %d: [HUMAN (White)] Enter move (e.g. 'e2e4' or 'quit'): "
		COLOR_RESET, game->move_count);
	if (!fgets(input, sizeof(input), stdin))
		return (false);
	trim_whitespace(input);
	p = input;
	while (*p && isspace((unsigned char)*p))
		p++;
	if (strcmp(p, "quit") == 0 || strcmp(p, "exit") == 0)
	{
		printf("Exiting game...\n");
		return (false);
	}
	if (!find_matching_move(p, legal_moves, num_legal, &chosen_move))
	{
		printf(COLOR_RED ">> ILLEGAL MOVE! Invalid format or rule violation.\n" COLOR_RESET);
		return (true);
	}
	make_move(game, &chosen_move);
	print_board(game);
	return (true);
}

static void	process_robot_turn(t_game_state *game)
{
	t_move	best_move;
	char	from_sq[4];
	char	to_sq[4];

	printf(COLOR_CYAN "Turn %d: [ROBOT (Black)] Thinking... (Calculating best move)...\n"
		COLOR_RESET, game->move_count);
	minimax(game, 3, -INF, INF, false, &best_move);
	square_to_str(best_move.from_r, best_move.from_c, from_sq);
	square_to_str(best_move.to_r, best_move.to_c, to_sq);
	printf(COLOR_GREEN ">> Robot Decision: %s -> %s\n" COLOR_RESET, from_sq, to_sq);
	print_robot_instruction(&best_move);
	make_move(game, &best_move);
	print_board(game);
}

int	main(void)
{
	t_game_state	game;
	t_move			legal_moves[MAX_MOVES];
	int				num_legal;

	init_game(&game);
	print_header_banner();
	print_board(&game);
	while (1)
	{
		num_legal = generate_legal_moves(&game, game.current_turn, legal_moves);
		if (num_legal == 0)
		{
			if (is_in_check(&game, game.current_turn))
				printf(COLOR_RED COLOR_BOLD "\n>> CHECKMATE! %s WINS!\n" COLOR_RESET,
					(game.current_turn == WHITE) ? "ROBOT (BLACK)" : "HUMAN (WHITE)");
			else
				printf(COLOR_YELLOW COLOR_BOLD "\n>> STALEMATE! THE GAME IS A DRAW!\n" COLOR_RESET);
			break ;
		}
		if (is_insufficient_material(&game))
		{
			printf(COLOR_YELLOW COLOR_BOLD "\n>> DRAW BY INSUFFICIENT MATERIAL!\n" COLOR_RESET);
			break ;
		}
		if (game.current_turn == WHITE)
		{
			if (!process_human_input(&game, legal_moves, num_legal))
				break ;
		}
		else
			process_robot_turn(&game);
	}
	return (0);
}
