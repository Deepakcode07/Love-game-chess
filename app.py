from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_socketio import SocketIO, emit, join_room, leave_room
import json
import uuid
from datetime import datetime
import random

app = Flask(__name__)
# The template folder is where Flask looks for index.html, game.html, etc.
app.template_folder = 'templates'
app.config['SECRET_KEY'] = 'your-very-romantic-secret-key'
socketio = SocketIO(app, cors_allowed_origins="*")

# --- DATA STORAGE ---
# Store active games. The key is the game_id.
games = {}
# Store player session IDs to easily find their game and color on disconnect.
players = {}

# --- LOVE-THEMED CONTENT ---
# Love messages that will be spoken by the system after a move.
LOVE_MESSAGES = [
    "A brilliant move, my love! Just like you.",
    "Every move you make fills my heart with joy.",
    "Your intelligence shines brighter than any star.",
    "You make even chess feel like a beautiful dance.",
    "I love watching you play with such grace and brilliance.",
    "Your mind is as captivating as your heart.",
    "Checkmate! You've captured my heart all over again.",
    "Playing with you is the only victory I need."
]

# (The ChessGame class remains exactly the same as you provided)
class ChessGame:
    # ... (No changes needed to your ChessGame class) ...
    def __init__(self):
        self.board = self.init_board()
        self.current_player = 'white'
        self.game_over = False
        self.winner = None
        self.move_history = []
        self.captured_pieces = {'white': [], 'black': []}
        self.king_positions = {'white': (7, 4), 'black': (0, 4)}
        self.has_king_moved = {'white': False, 'black': False}
        self.has_rook_moved = {
            'white': {'kingside': False, 'queenside': False},
            'black': {'kingside': False, 'queenside': False}
        }
        self.en_passant_target = None
        self.love_messages_sent = 0
        
    def init_board(self):
        # Initialize 8x8 chess board
        board = [[None for _ in range(8)] for _ in range(8)]
        
        # Place pawns
        for col in range(8):
            board[1][col] = {'type': 'pawn', 'color': 'black'}
            board[6][col] = {'type': 'pawn', 'color': 'white'}
        
        # Place other pieces
        pieces = ['rook', 'knight', 'bishop', 'queen', 'king', 'bishop', 'knight', 'rook']
        for col, piece in enumerate(pieces):
            board[0][col] = {'type': piece, 'color': 'black'}
            board[7][col] = {'type': piece, 'color': 'white'}
        
        return board
    
    def is_valid_position(self, row, col):
        return 0 <= row < 8 and 0 <= col < 8
    
    def get_piece_moves(self, row, col):
        piece = self.board[row][col]
        if not piece:
            return []
        
        moves = []
        piece_type = piece['type']
        color = piece['color']
        
        if piece_type == 'pawn':
            moves = self.get_pawn_moves(row, col, color)
        elif piece_type == 'rook':
            moves = self.get_rook_moves(row, col)
        elif piece_type == 'knight':
            moves = self.get_knight_moves(row, col)
        elif piece_type == 'bishop':
            moves = self.get_bishop_moves(row, col)
        elif piece_type == 'queen':
            moves = self.get_queen_moves(row, col)
        elif piece_type == 'king':
            moves = self.get_king_moves(row, col)
        
        # Filter out moves that would put own king in check
        valid_moves = []
        for move in moves:
            if self.is_legal_move(row, col, move[0], move[1]):
                valid_moves.append(move)
        
        return valid_moves
    
    def get_pawn_moves(self, row, col, color):
        moves = []
        direction = -1 if color == 'white' else 1
        start_row = 6 if color == 'white' else 1
        
        # Move forward
        new_row = row + direction
        if self.is_valid_position(new_row, col) and not self.board[new_row][col]:
            moves.append((new_row, col))
            
            # Double move from starting position
            if row == start_row and not self.board[new_row + direction][col]:
                moves.append((new_row + direction, col))
        
        # Capture diagonally
        for dc in [-1, 1]:
            new_row, new_col = row + direction, col + dc
            if self.is_valid_position(new_row, new_col):
                target = self.board[new_row][new_col]
                if target and target['color'] != color:
                    moves.append((new_row, new_col))
                # En passant
                elif (new_row, new_col) == self.en_passant_target:
                    moves.append((new_row, new_col))
        
        return moves
    
    def get_rook_moves(self, row, col):
        moves = []
        directions = [(0, 1), (0, -1), (1, 0), (-1, 0)]
        
        for dr, dc in directions:
            for i in range(1, 8):
                new_row, new_col = row + dr * i, col + dc * i
                if not self.is_valid_position(new_row, new_col):
                    break
                
                target = self.board[new_row][new_col]
                if not target:
                    moves.append((new_row, new_col))
                elif target['color'] != self.board[row][col]['color']:
                    moves.append((new_row, new_col))
                    break
                else:
                    break
        
        return moves
    
    def get_knight_moves(self, row, col):
        moves = []
        knight_moves = [(2, 1), (2, -1), (-2, 1), (-2, -1), (1, 2), (1, -2), (-1, 2), (-1, -2)]
        
        for dr, dc in knight_moves:
            new_row, new_col = row + dr, col + dc
            if self.is_valid_position(new_row, new_col):
                target = self.board[new_row][new_col]
                if not target or target['color'] != self.board[row][col]['color']:
                    moves.append((new_row, new_col))
        
        return moves
    
    def get_bishop_moves(self, row, col):
        moves = []
        directions = [(1, 1), (1, -1), (-1, 1), (-1, -1)]
        
        for dr, dc in directions:
            for i in range(1, 8):
                new_row, new_col = row + dr * i, col + dc * i
                if not self.is_valid_position(new_row, new_col):
                    break
                
                target = self.board[new_row][new_col]
                if not target:
                    moves.append((new_row, new_col))
                elif target['color'] != self.board[row][col]['color']:
                    moves.append((new_row, new_col))
                    break
                else:
                    break
        
        return moves
    
    def get_queen_moves(self, row, col):
        return self.get_rook_moves(row, col) + self.get_bishop_moves(row, col)
    
    def get_king_moves(self, row, col):
        moves = []
        directions = [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)]
        
        for dr, dc in directions:
            new_row, new_col = row + dr, col + dc
            if self.is_valid_position(new_row, new_col):
                target = self.board[new_row][new_col]
                if not target or target['color'] != self.board[row][col]['color']:
                    moves.append((new_row, new_col))
        
        # Castling
        color = self.board[row][col]['color']
        if not self.has_king_moved[color] and not self.is_in_check(color):
            # Kingside castling
            if (not self.has_rook_moved[color]['kingside'] and 
                not self.board[row][5] and not self.board[row][6] and
                not self.is_square_attacked(row, 5, color) and 
                not self.is_square_attacked(row, 6, color)):
                moves.append((row, 6))
            
            # Queenside castling
            if (not self.has_rook_moved[color]['queenside'] and 
                not self.board[row][3] and not self.board[row][2] and not self.board[row][1] and
                not self.is_square_attacked(row, 3, color) and 
                not self.is_square_attacked(row, 2, color)):
                moves.append((row, 2))
        
        return moves
    
    def is_square_attacked(self, row, col, defending_color):
        # Check if square is attacked by opponent
        for r in range(8):
            for c in range(8):
                piece = self.board[r][c]
                if piece and piece['color'] != defending_color:
                    if piece['type'] == 'pawn':
                        moves = self.get_pawn_attack_squares(r, c, piece['color'])
                    else:
                        moves = self.get_piece_attack_squares(r, c)
                    
                    if (row, col) in moves:
                        return True
        return False
    
    def get_pawn_attack_squares(self, row, col, color):
        moves = []
        direction = -1 if color == 'white' else 1
        
        for dc in [-1, 1]:
            new_row, new_col = row + direction, col + dc
            if self.is_valid_position(new_row, new_col):
                moves.append((new_row, new_col))
        
        return moves
    
    def get_piece_attack_squares(self, row, col):
        piece = self.board[row][col]
        if not piece:
            return []
        
        piece_type = piece['type']
        
        if piece_type == 'rook':
            return self.get_rook_moves(row, col)
        elif piece_type == 'knight':
            return self.get_knight_moves(row, col)
        elif piece_type == 'bishop':
            return self.get_bishop_moves(row, col)
        elif piece_type == 'queen':
            return self.get_queen_moves(row, col)
        elif piece_type == 'king':
            moves = []
            directions = [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)]
            for dr, dc in directions:
                new_row, new_col = row + dr, col + dc
                if self.is_valid_position(new_row, new_col):
                    moves.append((new_row, new_col))
            return moves
        
        return []
    
    def is_in_check(self, color):
        king_pos = self.king_positions[color]
        return self.is_square_attacked(king_pos[0], king_pos[1], color)
    
    def is_legal_move(self, from_row, from_col, to_row, to_col):
        # Make temporary move
        piece = self.board[from_row][from_col]
        captured = self.board[to_row][to_col]
        
        self.board[to_row][to_col] = piece
        self.board[from_row][from_col] = None
        
        # Update king position if king moved
        if piece['type'] == 'king':
            old_king_pos = self.king_positions[piece['color']]
            self.king_positions[piece['color']] = (to_row, to_col)
        
        # Check if own king is in check
        legal = not self.is_in_check(piece['color'])
        
        # Restore board
        self.board[from_row][from_col] = piece
        self.board[to_row][to_col] = captured
        
        # Restore king position
        if piece['type'] == 'king':
            self.king_positions[piece['color']] = old_king_pos
        
        return legal
    
    def make_move(self, from_row, from_col, to_row, to_col):
        piece = self.board[from_row][from_col]
        if not piece or piece['color'] != self.current_player:
            return False
        
        valid_moves = self.get_piece_moves(from_row, from_col)
        if (to_row, to_col) not in valid_moves:
            return False
        
        # Handle special moves
        captured_piece = self.board[to_row][to_col]
        special_move = None
        
        # En passant
        if (piece['type'] == 'pawn' and (to_row, to_col) == self.en_passant_target):
            capture_row = to_row + (1 if piece['color'] == 'white' else -1)
            captured_piece = self.board[capture_row][to_col]
            self.board[capture_row][to_col] = None
            special_move = 'en_passant'
        
        # Castling
        if piece['type'] == 'king' and abs(to_col - from_col) == 2:
            special_move = 'castling'
            if to_col > from_col:  # Kingside
                rook = self.board[from_row][7]
                self.board[from_row][7] = None
                self.board[from_row][5] = rook
            else:  # Queenside
                rook = self.board[from_row][0]
                self.board[from_row][0] = None
                self.board[from_row][3] = rook
        
        # Make the move
        self.board[to_row][to_col] = piece
        self.board[from_row][from_col] = None
        
        # Update king position
        if piece['type'] == 'king':
            self.king_positions[piece['color']] = (to_row, to_col)
            self.has_king_moved[piece['color']] = True
        
        # Update rook moved status
        if piece['type'] == 'rook':
            if from_col == 0:
                self.has_rook_moved[piece['color']]['queenside'] = True
            elif from_col == 7:
                self.has_rook_moved[piece['color']]['kingside'] = True
        
        # Handle captured piece
        if captured_piece:
            self.captured_pieces[self.current_player].append(captured_piece)
        
        # Set en passant target
        self.en_passant_target = None
        if (piece['type'] == 'pawn' and abs(to_row - from_row) == 2):
            self.en_passant_target = ((from_row + to_row) // 2, from_col)
        
        # Handle pawn promotion
        if (piece['type'] == 'pawn' and 
            (to_row == 0 or to_row == 7)):
            self.board[to_row][to_col] = {'type': 'queen', 'color': piece['color']}
            special_move = 'promotion'
        
        # Record move
        move_record = {
            'from': (from_row, from_col),
            'to': (to_row, to_col),
            'piece': piece,
            'captured': captured_piece,
            'special': special_move,
            'timestamp': datetime.now().isoformat()
        }
        self.move_history.append(move_record)
        
        # Switch players
        self.current_player = 'black' if self.current_player == 'white' else 'white'
        
        # Check for checkmate or stalemate
        if self.is_checkmate(self.current_player):
            self.game_over = True
            self.winner = 'black' if self.current_player == 'white' else 'white'
        elif self.is_stalemate(self.current_player):
            self.game_over = True
            self.winner = 'draw'
        
        return True
    
    def is_checkmate(self, color):
        if not self.is_in_check(color):
            return False
        
        return not self.has_legal_moves(color)
    
    def is_stalemate(self, color):
        if self.is_in_check(color):
            return False
        
        return not self.has_legal_moves(color)
    
    def has_legal_moves(self, color):
        for row in range(8):
            for col in range(8):
                piece = self.board[row][col]
                if piece and piece['color'] == color:
                    if self.get_piece_moves(row, col):
                        return True
        return False
    
    def get_game_state(self):
        return {
            'board': self.board,
            'current_player': self.current_player,
            'game_over': self.game_over,
            'winner': self.winner,
            'captured_pieces': self.captured_pieces,
            'move_history': self.move_history,
            'in_check': {
                'white': self.is_in_check('white'),
                'black': self.is_in_check('black')
            },
            'possible_moves': self.get_all_possible_moves(self.current_player)
        }

    def get_all_possible_moves(self, color):
        """Calculates all possible moves for a given color."""
        all_moves = {}
        if self.game_over or color != self.current_player:
            return all_moves

        for r in range(8):
            for c in range(8):
                piece = self.board[r][c]
                if piece and piece['color'] == color:
                    moves = self.get_piece_moves(r, c)
                    if moves:
                        all_moves[f'{r},{c}'] = moves
        return all_moves

# --- HTTP ROUTES ---

@app.route('/')
def index():
    """Serves the beautiful landing page."""
    return render_template('index.html')

@app.route('/validate_game', methods=['POST'])
def validate_game():
    """
    API endpoint for the landing page to check/create a game room
    before redirecting the user to the actual game page.
    """
    data = request.get_json()
    game_id = data.get('game_id')
    mode = data.get('mode') # 'create' or 'join'

    if not game_id:
        return jsonify({'success': False, 'message': 'A Game Room ID is required, my love.'})

    if mode == 'create':
        if game_id in games:
            return jsonify({'success': False, 'message': 'This room is already taken! Try another romantic name.'})
        # Create a new game room
        games[game_id] = {
            'game': ChessGame(),
            'players': {},
            'spectators': []
        }
        return jsonify({'success': True, 'message': 'Your romantic game room is ready!'})
    
    elif mode == 'join':
        if game_id not in games:
            return jsonify({'success': False, 'message': 'This love chamber was not found. Are you sure it exists?'})
        if len(games[game_id]['players']) >= 2:
            return jsonify({'success': False, 'message': 'This game of hearts is already full!'})
        return jsonify({'success': True, 'message': 'Joining the game of love...'})
    
    return jsonify({'success': False, 'message': 'An unexpected error occurred.'})


@app.route('/game/<game_id>')
def game(game_id):
    """Serves the main game page."""
    player_name = request.args.get('player_name', 'A Secret Admirer')
    # Check if the game room actually exists before rendering
    if game_id not in games:
        # In a real app, you might use flash messages to show an error
        return redirect(url_for('index'))
    return render_template('game.html', game_id=game_id, player_name=player_name)

# --- SOCKET.IO EVENTS ---

@socketio.on('join_game')
def handle_join_game(data):
    """Handles a player joining a game room from the game.html page."""
    game_id = data['game_id']
    player_name = data['player_name']
    sid = request.sid
    
    if game_id not in games:
        emit('error', {'message': 'Game not found.'})
        return
    
    game_data = games[game_id]
    
    # Assign player color or spectator role
    if 'white' not in game_data['players']:
        color = 'white'
    elif 'black' not in game_data['players']:
        color = 'black'
    else:
        color = 'spectator'
        game_data['spectators'].append(sid)
    
    if color != 'spectator':
        game_data['players'][color] = {'name': player_name, 'sid': sid}
        players[sid] = {'game_id': game_id, 'color': color, 'name': player_name}
    else:
         players[sid] = {'game_id': game_id, 'color': 'spectator', 'name': player_name}

    join_room(game_id)
    
    # Notify the joining player of their status and the game state
    emit('game_joined', {
        'color': color,
        'game_state': game_data['game'].get_game_state(),
        'players': {c: p['name'] for c, p in game_data['players'].items()}
    })
    
    # Notify everyone else in the room that a new player has connected
    emit('player_joined', {
        'player_name': player_name,
        'color': color
    }, room=game_id, include_self=False)

@socketio.on('make_move')
def handle_make_move(data):
    """Handles a player making a move on the board."""
    if request.sid not in players:
        return
    
    player_info = players[request.sid]
    game_id = player_info['game_id']
    player_color = player_info['color']
    
    if game_id not in games:
        return
    
    game = games[game_id]['game']
    
    if game.current_player != player_color:
        emit('error', {'message': "It's not your turn, my dear."})
        return
    
    success = game.make_move(
        data['from_row'], data['from_col'],
        data['to_row'], data['to_col']
    )
    
    if success:
        # After a successful move, send a random love message
        love_message = random.choice(LOVE_MESSAGES)
        
        emit('move_made', {
            'game_state': game.get_game_state(),
            'move': data,
            'love_message': love_message,
            'is_check': game.is_in_check(game.current_player)
        }, room=game_id)
    else:
        emit('error', {'message': 'That move is not allowed, my love.'})

@socketio.on('send_love_note')
def handle_send_love_note(data):
    """Handles sending a custom love note to the other player"""
    if request.sid not in players: return
    
    player_info = players[request.sid]
    game_id = player_info['game_id']
    
    emit('love_note_received', {
        'from_player': player_info['name'],
        'note': data.get('note', '...')
    }, room=game_id)


@socketio.on('disconnect')
def handle_disconnect():
    """Handles a player disconnecting from the game."""
    if request.sid in players:
        player_info = players.pop(request.sid)
        game_id = player_info['game_id']
        
        if game_id in games:
            game_data = games[game_id]
            player_color = player_info['color']

            # Remove player from game data
            if player_color != 'spectator' and player_color in game_data['players']:
                del game_data['players'][player_color]
            elif request.sid in game_data['spectators']:
                game_data['spectators'].remove(request.sid)

            # If the room is now empty, delete it
            if not game_data['players'] and not game_data['spectators']:
                del games[game_id]
            else:
                emit('player_disconnected', {
                    'color': player_color,
                    'name': player_info['name']
                }, room=game_id)
        
        leave_room(game_id)

if __name__ == '__main__':
    # Use 0.0.0.0 to make it accessible on your local network
    socketio.run(app, debug=True, host='0.0.0.0', port=5000)