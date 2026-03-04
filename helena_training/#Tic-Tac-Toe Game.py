board = ['1','2','3','4','5','6','7','8','9']
def grid():
    print(board[0], '|', board[1], '|', board[2])
    print('--+---+--')
    print(board[3], '|', board[4], '|', board[5])
    print('--+---+--')
    print(board[6], '|', board[7], '|', board[8])
grid()

def invalid_inputX():
    while True:
        try:
            loc = int(input('enter the location for X: '))
        except ValueError:
            print('invalid input, please enter a number from 1 to 9.')
            continue
        if not 1 <= loc <= 9:
            print('invalid input, please enter a number from 1 to 9.')
            continue
        if board[loc-1] not in ('X', 'O'):
            board[loc-1] = 'X'
            break
        else:
            print('cell already taken, try again.')

def invalid_inputO():
    while True:
        try:
            loc = int(input('enter the location for O: '))
        except ValueError:
            print('invalid input, please enter a number from 1 to 9.')
            continue
        if not 1 <= loc <= 9:
            print('invalid input, please enter a number from 1 to 9.')
            continue
        if board[loc-1] not in ('X', 'O'):
            board[loc-1] = 'O'
            break
        else:
            print('cell already taken, try again.')

player1 = input("enter player 1 name: ")
player2 = input("enter player 2 name: ")

turn = 0
while True:
    if turn % 2 == 0:
        print('hello', player1)
        invalid_inputX()
        grid()
        if (board[0] == board[1] == board[2]) or (board[3] == board[4] == board[5]) or (board[6] == board[7] == board[8]) or (board[0] == board[3] == board[6]) or (board[1] == board[4] == board[7]) or (board[2] == board[5] == board[8]) or (board[0] == board[4] == board[8]) or (board[2] == board[4] == board[6]):
            print(player1, 'wins!')
            break
        elif turn == 8:
            print("It's a tie!")
            break
    else:
        print('hello', player2)
        invalid_inputO()
        grid()
    if (board[0] == board[1] == board[2]) or (board[3] == board[4] == board[5]) or (board[6] == board[7] == board[8]) or (board[0] == board[3] == board[6]) or (board[1] == board[4] == board[7]) or (board[2] == board[5] == board[8]) or (board[0] == board[4] == board[8]) or (board[2] == board[4] == board[6]):
        print(player2, 'wins!')
        break
    elif turn == 8: 
        print("It's a tie!")
        break
    turn += 1