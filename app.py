from flask import Flask, render_template, jsonify, request
import chess
import chess.engine
import os
import requests
import json

app = Flask(__name__)

# CHESS.COM REQUIRES A USER-AGENT. 
# They will block "empty" requests. Using a descriptive header fixes this.
HEADERS = {
    "User-Agent": "ChessAnalysisApp/1.0 (Contact: your_email@example.com)"
}

@app.route('/')
def index():
    # This serves your HTML file located in the /templates folder
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
            # Lichess can return multiple games as NDJSON (Newline Delimited JSON)
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
            # Chess.com logic
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
            
            # Grab the last 10 games from the archive array
            for g in games[-20:]:
                w_name = g.get('white', {}).get('username', 'Unknown')
                b_name = g.get('black', {}).get('username', 'Unknown')
                pgn = g.get('pgn', '')
                recent_games.append({
                    "label": f"White: {w_name} vs Black: {b_name}",
                    "pgn": pgn
                })
            
            # Reverse the list so the absolute newest game is at the top of the dropdown
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
    
    try:
        # Boot up your native Windows engine
        with chess.engine.SimpleEngine.popen_uci(STOCKFISH_PATH) as engine:
            for fen in fens:
                board = chess.Board(fen)
                # Analyze the position up to the requested depth
                info = engine.analyse(board, chess.engine.Limit(depth=depth))
                
                # Get the score from White's perspective
                score = info["score"].white() 
                
                if score.is_mate():
                    mate_in = score.mate()
                    # Assign +/- 30 pawns for forced mates to max out the probability curve
                    eval_val = 30.0 if mate_in > 0 else -30.0
                else:
                    # Convert centipawns to pawns (e.g., 150 cp -> 1.5)
                    eval_val = score.score() / 100.0 
                    
                evals.append(eval_val)
                
        return jsonify({"evals": evals})
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    # Run the server on http://127.0.0.1:5000
    app.run()