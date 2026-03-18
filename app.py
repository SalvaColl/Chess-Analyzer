from flask import Flask, render_template, jsonify, request
import chess
import chess.engine
import os
import requests
import json
from dotenv import load_dotenv

app = Flask(__name__)

load_dotenv()
LICHESS_TOKEN = os.getenv("LICHESS_TOKEN")

# CHESS.COM REQUIRES A USER-AGENT. 
HEADERS = {
    "User-Agent": "ChessAnalysisApp/1.0 (Contact: salva.coll.alonso@gmail.com)"
}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/fetch_recent_games', methods=['POST'])
def fetch_recent_games():
    data = request.json
    platform = data.get('platform')
    username = data.get('username')

    if not username:
        return jsonify({"error": "Username is required"}), 400

    recent_games = []

    try:
        if platform == 'lichess':
            url = f"https://lichess.org/api/games/user/{username}?max=10&clocks=true"
            headers = {"Accept": "application/x-ndjson"}
            response = requests.get(url, headers=headers)
            
            if response.status_code != 200:
                return jsonify({"error": f"Lichess error ({response.status_code})"}), 404
            
            games_data = response.text.strip().split('\n')
            for line in games_data:
                if not line: continue
                g = json.loads(line)
                w_name = g.get('players', {}).get('white', {}).get('user', {}).get('name', 'Unknown')
                b_name = g.get('players', {}).get('black', {}).get('user', {}).get('name', 'Unknown')
                pgn = g.get('pgn', '')
                recent_games.append({
                    "label": f"White: {w_name} vs Black: {b_name}",
                    "pgn": pgn
                })

        else:
            archives_url = f"https://api.chess.com/pub/player/{username}/games/archives"
            resp = requests.get(archives_url, headers=HEADERS)
            if resp.status_code != 200:
                return jsonify({"error": "Chess.com user not found"}), 404
            
            archives = resp.json().get("archives", [])
            if not archives:
                return jsonify({"error": "No game history found"}), 404
            
            games_resp = requests.get(archives[-1], headers=HEADERS)
            if games_resp.status_code != 200:
                return jsonify({"error": "Could not fetch games"}), 500
            
            games = games_resp.json().get("games", [])
            if not games:
                return jsonify({"error": "No games found this month"}), 404
            
            # Change to fetch more games
            for g in games[-20:]:
                w_name = g.get('white', {}).get('username', 'Unknown')
                b_name = g.get('black', {}).get('username', 'Unknown')
                pgn = g.get('pgn', '')
                recent_games.append({
                    "label": f"White: {w_name} vs Black: {b_name}",
                    "pgn": pgn
                })
            
            # Reverse to get the newest game at the top
            recent_games.reverse()

        return jsonify({"games": recent_games})

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"error": "Internal server error"}), 500

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

STOCKFISH_PATH = os.path.join(BASE_DIR, "stockfish", "stockfish-windows-x86-64-avx2.exe")

@app.route('/api/analyze', methods=['POST'])
def analyze_game():
    data = request.json
    fens = data.get('fens', [])
    depth = int(data.get('depth', 14))
    
    evals = []
    best_moves = []
    
    try:
        with chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH) as engine:
            for fen in fens:
                board = chess.Board(fen)
                
                if board.is_checkmate():
                    evals.append(30.0 if board.turn == chess.BLACK else -30.0)
                    best_moves.append(None) 
                    continue
                elif board.is_game_over():
                    evals.append(0.0)
                    best_moves.append(None)
                    continue
                
                info = engine.analyse(board, chess.engine.Limit(depth=depth))
                
                top_move = None
                if "pv" in info and len(info["pv"]) > 0:
                    top_move = info["pv"][0].uci()
                best_moves.append(top_move)
                
                score = info["score"].white() 
                if score.is_mate():
                    mate_moves = score.mate()
                    if mate_moves is not None:
                        eval_val = 30.0 if mate_moves > 0 else -30.0
                    else:
                        eval_val = 30.0 if board.turn == chess.BLACK else -30.0
                else:
                    eval_val = score.score() / 100.0 
                    
                evals.append(eval_val)
                
        return jsonify({"evals": evals, "best_moves": best_moves})
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
@app.route('/api/theory', methods=['GET'])
def get_theory():
    fen = request.args.get('fen')
    if not fen:
        return jsonify({"error": "No FEN provided"}), 400
        
    url = f"https://explorer.lichess.ovh/masters?fen={fen}"
    
    headers = {}
    if LICHESS_TOKEN:
        headers["Authorization"] = f"Bearer {LICHESS_TOKEN}"
        
    try:
        response = requests.get(url, headers=headers)
        return jsonify(response.json()), response.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run()