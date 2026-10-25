# **************************************************************************** #
#                                                                              #
#                                                         :::      ::::::::    #
#    Makefile                                           :+:      :+:    :+:    #
#                                                     +:+ +:+         +:+      #
#    By: book <book@student.42.fr>                  +#+  +:+       +#+         #
#                                                 +#+#+#+#+#+   +#+            #
#    Created: 2026/10/22 23:15:00 by book              #+#    #+#              #
#    Updated: 2026/10/22 23:15:00 by book             ###   ########.fr        #
#                                                                              #
# **************************************************************************** #

NAME		= robotic_engine

CC			= cc
CFLAGS		= -Wall -Wextra -Werror -O2
RM			= rm -f

SRCS		= main.c board.c moves.c ai.c display.c
OBJS		= $(SRCS:.c=.o)
HEADERS		= robotic.h

all:		$(NAME)

$(NAME):	$(OBJS)
			$(CC) $(CFLAGS) $(OBJS) -o $(NAME)
			@echo "\033[1;32m[✓] $(NAME) compiled successfully!\033[0m"

%.o:		%.c $(HEADERS)
			$(CC) $(CFLAGS) -c $< -o $@

clean:
			$(RM) $(OBJS)
			@echo "\033[1;33m[✓] Object files cleaned.\033[0m"

fclean:		clean
			$(RM) $(NAME)
			@echo "\033[1;31m[✓] Binary $(NAME) removed.\033[0m"

re:			fclean all

.PHONY:		all clean fclean re
